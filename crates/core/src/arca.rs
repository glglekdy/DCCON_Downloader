//! 아카콘(arca.live/e) 엔드포인트와 HTML 파서, 로그인 세션 파일 (`dccon/arca.py`,
//! `dccon/arca_login.py` 의 포팅).
//!
//! 전부 서버 렌더 HTML 이고 로그인해야 보인다. 로그인 없이 부르면 `/u/login?goto=...` 로
//! 넘어간다. 아카콘용 `Client` 는 `Client::new("https://arca.live/e/", ...)` 처럼
//! Referer 를 `https://arca.live/e/` 로 만들어야 한다 (이 모듈은 Referer 를 따로 붙이지 않는다).

use std::collections::HashMap;
use std::path::Path;
use std::sync::LazyLock;

use html_escape::decode_html_entities;
use regex::Regex;
use serde::{Deserialize, Serialize};
use tokio_util::sync::CancellationToken;

use crate::error::{Error, Result};
use crate::http::{Client, Resp};
use crate::models::{Brief, Item, Package};

pub const ARCA_BASE: &str = "https://arca.live";
pub const LOGIN_URL: &str = "https://arca.live/u/login?goto=/e/";
pub const ARCA_TABS: [(&str, &str); 3] =
    [("new", "최신"), ("weekly", "주간 인기"), ("monthly", "월간 인기")];
pub const SEARCH_TYPES: [(&str, &str); 3] = [("title", "제목"), ("nickname", "작가"), ("tag", "태그")];

fn re(p: &str) -> Regex {
    Regex::new(p).unwrap()
}

static CARD_RE: LazyLock<Regex> = LazyLock::new(|| {
    re(r#"(?s)<a[^>]*href="/e/(\d+)[^"]*"[^>]*>\s*<div class="emoticon">(.*?)</a>"#)
});
static IMG_SRC_RE: LazyLock<Regex> =
    LazyLock::new(|| re(r#"<img[^>]*\ssrc="((?:https?:)?//[^"]+)""#));
static TITLE_RE: LazyLock<Regex> = LazyLock::new(|| re(r#"(?s)class="title"[^>]*>(.*?)</div>"#));
static MAKER_RE: LazyLock<Regex> = LazyLock::new(|| re(r#"(?s)class="maker"[^>]*>(.*?)</div>"#));
static AUTHOR_RE: LazyLock<Regex> = LazyLock::new(|| re(r#"(?s)class="author"[^>]*>(.*?)</div>"#));
static INFO_TITLE_RE: LazyLock<Regex> = LazyLock::new(|| {
    re(r#"(?s)class="emoticon-info"[^>]*>\s*<div class="title"[^>]*>(.*?)</div>"#)
});
static ICON_RE: LazyLock<Regex> =
    LazyLock::new(|| re(r#"(?s)class="emoticon-header-icon"[^>]*>\s*<img[^>]*\ssrc="([^"]+)""#));
static PAGE_RE: LazyLock<Regex> = LazyLock::new(|| re(r#"href="/e/\?[^"]*?\bp=(\d+)"#));
static MEDIA_RE: LazyLock<Regex> = LazyLock::new(|| re(r"(?s)<(img|video)\b([^>]*)>"));
static ATTR_RE: LazyLock<Regex> = LazyLock::new(|| re(r#"([\w-]+)="([^"]*)""#));
static TAG_RE: LazyLock<Regex> = LazyLock::new(|| re(r"<[^>]+>"));
static ID_IN_URL: LazyLock<Regex> = LazyLock::new(|| re(r"arca\.live/e/(\d+)"));

fn text_of(fragment: &str) -> String {
    let stripped = TAG_RE.replace_all(fragment, "");
    decode_html_entities(&stripped).trim().to_string()
}

fn url_of(src: &str) -> String {
    let src = decode_html_entities(src.trim()).into_owned();
    if src.starts_with("//") {
        format!("https:{src}")
    } else {
        src
    }
}

pub fn list_query(kind: &str, page: u32) -> Vec<(&'static str, String)> {
    let mut q = vec![("p", page.max(1).to_string())];
    if kind == "weekly" || kind == "monthly" {
        q.push(("rank", kind.to_string()));
    }
    q
}

pub fn search_query(word: &str, target: &str, page: u32) -> Vec<(&'static str, String)> {
    let target = if SEARCH_TYPES.iter().any(|(k, _)| *k == target) { target } else { "title" };
    vec![
        ("target", target.to_string()),
        ("keyword", word.to_string()),
        ("p", page.max(1).to_string()),
    ]
}

pub fn parse_list(body: &str) -> Vec<Brief> {
    CARD_RE
        .captures_iter(body)
        .map(|c| {
            let idx_s = &c[1];
            let chunk = &c[2];
            // 별점 아이콘(/static/...)이 먼저 나오므로 CDN 주소인 첫 이미지를 고른다.
            Brief {
                idx: idx_s.parse().unwrap_or(0),
                title: TITLE_RE
                    .captures(chunk)
                    .map(|m| text_of(&m[1]))
                    .unwrap_or_else(|| format!("#{idx_s}")),
                seller: MAKER_RE.captures(chunk).map(|m| text_of(&m[1])).unwrap_or_default(),
                thumb_url: IMG_SRC_RE.captures(chunk).map(|m| url_of(&m[1])).unwrap_or_default(),
            }
        })
        .collect()
}

pub fn parse_pages(body: &str, page: u32) -> u32 {
    PAGE_RE
        .captures_iter(body)
        .filter_map(|m| m[1].parse::<u32>().ok())
        .fold(page, u32::max)
}

pub fn parse_package(id: u64, body: &str) -> Package {
    let title = INFO_TITLE_RE.captures(body);
    let author = AUTHOR_RE.captures(body);
    let icon = ICON_RE.captures(body);

    let wrapper = match body.find("class=\"emoticons-wrapper\"") {
        Some(start) => match body[start..].find("</div>") {
            Some(n) => &body[start..start + n],
            None => &body[start..],
        },
        None => "",
    };

    let mut items: Vec<Item> = Vec::new();
    for m in MEDIA_RE.captures_iter(wrapper) {
        let tag = &m[1];
        let attrs: HashMap<&str, &str> = ATTR_RE
            .captures_iter(m.get(2).unwrap().as_str())
            .map(|a| (a.get(1).unwrap().as_str(), a.get(2).unwrap().as_str()))
            .collect();
        let src = attrs
            .get("data-src")
            .filter(|s| !s.is_empty())
            .or_else(|| attrs.get("src"))
            .copied()
            .unwrap_or("");
        if src.is_empty() {
            continue;
        }
        let url = url_of(src);
        let ext = url
            .split('?')
            .next()
            .and_then(|u| u.rsplit('.').next())
            .unwrap_or("")
            .to_lowercase();
        let ext = if ext.is_empty() { "png".to_string() } else { ext };
        let poster = attrs.get("poster").copied().unwrap_or("");
        items.push(Item {
            idx: attrs.get("data-id").and_then(|s| s.parse().ok()).unwrap_or(0),
            title: String::new(),
            sort: items.len() as u32 + 1,
            ext: if tag == "video" && ext != "mp4" && ext != "webm" { "mp4".into() } else { ext },
            path: url,
            thumb: if poster.is_empty() { String::new() } else { url_of(poster) },
        });
    }
    Package {
        idx: id,
        title: title.map(|m| text_of(&m[1])).unwrap_or_else(|| format!("아카콘 {id}")),
        description: String::new(),
        seller: author.map(|m| text_of(&m[1])).unwrap_or_default(),
        price: "0".into(),
        reg_date: String::new(),
        main_img_path: icon.map(|m| url_of(&m[1])).unwrap_or_default(),
        list_img_path: String::new(),
        items,
        tags: Vec::new(),
    }
}

/// 아카콘 번호나 `arca.live/e/` 주소들이면 번호 목록, 아니면 None.
pub fn parse_ids(text: &str) -> Option<Vec<u64>> {
    let mut ids: Vec<u64> = Vec::new();
    for token in text.split(|c: char| c.is_whitespace() || c == ',').filter(|t| !t.is_empty()) {
        let id = if token.chars().all(|c| c.is_ascii_digit()) {
            token.parse().ok()?
        } else {
            ID_IN_URL.captures(token)?[1].parse().ok()?
        };
        if !ids.contains(&id) {
            ids.push(id);
        }
    }
    if ids.is_empty() {
        None
    } else {
        Some(ids)
    }
}

/// 최종 URL 경로가 `/u/login` 이면 로그인 필요.
pub fn check_login(resp: &Resp) -> Result<()> {
    let path = reqwest::Url::parse(&resp.url)
        .map(|u| u.path().to_string())
        .unwrap_or_else(|_| resp.url.clone());
    if path.contains("/u/login") {
        Err(Error::LoginRequired)
    } else {
        Ok(())
    }
}

async fn get_body(
    c: &Client,
    base: &str,
    path: &str,
    query: &[(&str, String)],
    cancel: &CancellationToken,
) -> Result<String> {
    let resp = match c.get_with(&format!("{base}{path}"), query, &[], cancel).await {
        Err(Error::Http(401 | 403)) => return Err(Error::LoginRequired),
        r => r?,
    };
    check_login(&resp)?;
    Ok(resp.text())
}

#[doc(hidden)]
pub async fn fetch_list_at(
    c: &Client,
    base: &str,
    kind: &str,
    page: u32,
    cancel: &CancellationToken,
) -> Result<(Vec<Brief>, u32)> {
    let body = get_body(c, base, "/e/", &list_query(kind, page), cancel).await?;
    Ok((parse_list(&body), parse_pages(&body, page)))
}

#[doc(hidden)]
pub async fn search_at(
    c: &Client,
    base: &str,
    word: &str,
    target: &str,
    page: u32,
    cancel: &CancellationToken,
) -> Result<(Vec<Brief>, u32)> {
    let body = get_body(c, base, "/e/", &search_query(word, target, page), cancel).await?;
    Ok((parse_list(&body), parse_pages(&body, page)))
}

#[doc(hidden)]
pub async fn fetch_package_at(
    c: &Client,
    base: &str,
    id: u64,
    cancel: &CancellationToken,
) -> Result<Package> {
    let body = get_body(c, base, &format!("/e/{id}"), &[], cancel).await?;
    let pkg = parse_package(id, &body);
    if pkg.items.is_empty() {
        return Err(Error::NotFound(format!("아카콘 {id} 를 찾을 수 없습니다.")));
    }
    Ok(pkg)
}

pub async fn fetch_list(
    c: &Client,
    kind: &str,
    page: u32,
    cancel: &CancellationToken,
) -> Result<(Vec<Brief>, u32)> {
    fetch_list_at(c, ARCA_BASE, kind, page, cancel).await
}

pub async fn search(
    c: &Client,
    word: &str,
    target: &str,
    page: u32,
    cancel: &CancellationToken,
) -> Result<(Vec<Brief>, u32)> {
    search_at(c, ARCA_BASE, word, target, page, cancel).await
}

pub async fn fetch_package(c: &Client, id: u64, cancel: &CancellationToken) -> Result<Package> {
    fetch_package_at(c, ARCA_BASE, id, cancel).await
}

fn default_path() -> String {
    "/".into()
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SessionCookie {
    pub name: String,
    pub value: String,
    #[serde(default)]
    pub domain: String,
    #[serde(default = "default_path")]
    pub path: String,
}

/// 로그인 브라우저에서 꺼낸 쿠키와 그 브라우저의 User-Agent (1.3.0 파일 형식 그대로).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ArcaSession {
    pub user_agent: String,
    pub cookies: Vec<SessionCookie>,
}

impl ArcaSession {
    /// 파일이 없거나 깨졌거나 `user_agent`/`cookies` 가 없으면 None.
    pub fn load(path: &Path) -> Option<Self> {
        let text = std::fs::read_to_string(path).ok()?;
        serde_json::from_str(&text).ok()
    }

    pub fn save(&self, path: &Path) -> std::io::Result<()> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let json = serde_json::to_string(self).map_err(std::io::Error::other)?;
        std::fs::write(path, json)
    }

    pub fn forget(path: &Path) {
        let _ = std::fs::remove_file(path);
    }

    pub fn cookie_pairs(&self) -> Vec<(String, String)> {
        self.cookies.iter().map(|c| (c.name.clone(), c.value.clone())).collect()
    }
}
