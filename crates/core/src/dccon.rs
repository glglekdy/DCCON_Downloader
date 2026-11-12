//! 디시콘 엔드포인트와 HTML/JSONP 파서 (`dccon/api.py` 의 포팅).

use std::sync::LazyLock;

use html_escape::decode_html_entities;
use percent_encoding::{utf8_percent_encode, AsciiSet, NON_ALPHANUMERIC};
use regex::Regex;
use serde::{Deserialize, Serialize};
use tokio_util::sync::CancellationToken;

use crate::error::{Error, Result};
use crate::http::Client;
use crate::models::{Brief, Package};

pub const BASE: &str = "https://dccon.dcinside.com";
pub const PACKAGE_DETAIL_URL: &str = "https://dccon.dcinside.com/index/package_detail";
pub const SEARCH_TYPES: [(&str, &str); 3] =
    [("title", "제목"), ("nick_name", "작가"), ("tags", "태그")];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TopKind {
    Day,
    Week,
    Month,
    Official,
}

pub fn top_url(kind: TopKind) -> &'static str {
    match kind {
        TopKind::Day => "https://json2.dcinside.com/json1/dccon_day_top100.php",
        TopKind::Week => "https://json2.dcinside.com/json1/dccon_week_top100.php",
        TopKind::Month => "https://json2.dcinside.com/json1/dccon_month_top100.php",
        TopKind::Official => "https://json2.dcinside.com/json1/dccon_official.php",
    }
}

fn re(p: &str) -> Regex {
    Regex::new(p).unwrap()
}

static LI_RE: LazyLock<Regex> = LazyLock::new(|| {
    re(r#"(?s)<li[^>]*class="[^"]*div_package[^"]*"[^>]*package_idx="(\d+)"(.*?)</li>"#)
});
static THUMB_RE: LazyLock<Regex> =
    LazyLock::new(|| re(r#"(?s)<img[^>]*class="[^"]*thumb_img[^"]*"[^>]*src="([^"]+)""#));
static NAME_RE: LazyLock<Regex> = LazyLock::new(|| {
    re(r#"(?s)<strong[^>]*class="[^"]*dcon_name[^"]*"[^>]*>(.*?)</strong>"#)
});
static SELLER_RE: LazyLock<Regex> = LazyLock::new(|| {
    re(r#"(?s)<span[^>]*class="[^"]*dcon_seller[^"]*"[^>]*>(.*?)</span>"#)
});
static TOTAL_RE: LazyLock<Regex> =
    LazyLock::new(|| re(r#"(?s)class="total_num"[^>]*>\s*([\d,]+)"#));
static TAG_RE: LazyLock<Regex> = LazyLock::new(|| re(r"<[^>]+>"));
static NEW_LAST_RE: LazyLock<Regex> =
    LazyLock::new(|| re(r#"/new/(\d+)"[^>]*class="[^"]*page_end"#));
static NEW_PAGE_RE: LazyLock<Regex> = LazyLock::new(|| re(r#"/new/(\d+)""#));
static NEW_TOTAL_RE: LazyLock<Regex> =
    LazyLock::new(|| re(r"총 디시콘\s*<em[^>]*>\s*([\d,]+)"));
static ID_IN_URL: LazyLock<Regex> = LazyLock::new(|| re(r"(?:package_idx=|#)(\d+)"));

fn text_of(fragment: &str) -> String {
    let stripped = TAG_RE.replace_all(fragment, "");
    decode_html_entities(&stripped).trim().to_string()
}

pub fn parse_list_page(body: &str) -> Vec<Brief> {
    LI_RE
        .captures_iter(body)
        .map(|c| {
            let idx_s = &c[1];
            let chunk = &c[2];
            Brief {
                idx: idx_s.parse().unwrap_or(0),
                title: NAME_RE
                    .captures(chunk)
                    .map(|m| text_of(&m[1]))
                    .unwrap_or_else(|| format!("#{idx_s}")),
                seller: SELLER_RE
                    .captures(chunk)
                    .map(|m| text_of(&m[1]))
                    .unwrap_or_default(),
                thumb_url: THUMB_RE
                    .captures(chunk)
                    .map(|m| decode_html_entities(&m[1]).into_owned())
                    .unwrap_or_default(),
            }
        })
        .collect()
}

pub fn parse_total_pages(body: &str) -> u32 {
    TOTAL_RE
        .captures(body)
        .and_then(|m| m[1].replace(',', "").parse::<u32>().ok())
        .map(|n| n.max(1))
        .unwrap_or(1)
}

pub fn parse_new_pages(body: &str, page: u32) -> u32 {
    if let Some(m) = NEW_LAST_RE.captures(body) {
        return page.max(m[1].parse().unwrap_or(0));
    }
    NEW_PAGE_RE
        .captures_iter(body)
        .filter_map(|m| m[1].parse::<u32>().ok())
        .fold(page, u32::max)
}

pub fn parse_new_total(body: &str) -> u64 {
    NEW_TOTAL_RE
        .captures(body)
        .and_then(|m| m[1].replace(',', "").parse().ok())
        .unwrap_or(0)
}

pub fn parse_top(text: &str) -> Result<Vec<Brief>> {
    let mut t = text.trim();
    if let Some(r) = t.strip_prefix('(') {
        t = r;
    }
    if let Some(r) = t.strip_suffix(')') {
        t = r;
    }
    let v: serde_json::Value = serde_json::from_str(t).map_err(|e| Error::Parse(e.to_string()))?;
    let rows = v
        .as_array()
        .ok_or_else(|| Error::Parse("인기 목록이 배열이 아닙니다.".into()))?;
    let s = |row: &serde_json::Value, k: &str| -> String {
        row.get(k)
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .trim()
            .to_string()
    };
    Ok(rows
        .iter()
        .map(|row| {
            let idx = match row.get("package_idx") {
                Some(serde_json::Value::String(x)) => x.trim().parse().unwrap_or(0),
                Some(serde_json::Value::Number(n)) => n.as_u64().unwrap_or(0),
                _ => 0,
            };
            let img = row.get("img").and_then(|x| x.as_str()).unwrap_or("");
            let thumb_url = if img.starts_with("//") {
                format!("https:{img}")
            } else {
                img.to_string()
            };
            Brief {
                idx,
                title: s(row, "title"),
                seller: s(row, "nick_name"),
                thumb_url,
            }
        })
        .collect())
}

/// Python `quote(safe="")`: 영숫자와 `_ . - ~` 만 그대로 둔다.
const QUOTE_SET: &AsciiSet = &NON_ALPHANUMERIC
    .remove(b'_')
    .remove(b'.')
    .remove(b'-')
    .remove(b'~');

pub fn search_url(word: &str, search_type: &str, page: u32) -> String {
    let st = if SEARCH_TYPES.iter().any(|(k, _)| *k == search_type) {
        search_type
    } else {
        "title"
    };
    format!(
        "{BASE}/hot/{page}/{st}/{}",
        utf8_percent_encode(word, QUOTE_SET)
    )
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Query {
    Search(String),
    Ids(Vec<u64>),
}

impl Serialize for Query {
    fn serialize<S: serde::Serializer>(&self, s: S) -> std::result::Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let mut m = s.serialize_map(Some(2))?;
        match self {
            Query::Search(w) => {
                m.serialize_entry("kind", "search")?;
                m.serialize_entry("word", w)?;
            }
            Query::Ids(ids) => {
                m.serialize_entry("kind", "ids")?;
                m.serialize_entry("ids", ids)?;
            }
        }
        m.end()
    }
}

/// 검색창 한 줄을 해석한다. 숫자/URL/여러 줄 붙여넣기는 ID 목록, 그 외는 검색어.
pub fn parse_query(text: &str) -> Query {
    let raw = text.trim();
    if raw.is_empty() {
        return Query::Search(String::new());
    }
    let mut ids: Vec<u64> = Vec::new();
    for token in raw.split(|c: char| c.is_whitespace() || c == ',').filter(|t| !t.is_empty()) {
        if token.chars().all(|c| c.is_ascii_digit()) {
            if let Ok(n) = token.parse() {
                ids.push(n);
                continue;
            }
            return Query::Search(raw.to_string());
        }
        if let Some(f) = ID_IN_URL.captures(token) {
            if token.contains("dcinside") || token.starts_with('#') {
                if let Ok(n) = f[1].parse() {
                    ids.push(n);
                    continue;
                }
            }
        }
        return Query::Search(raw.to_string());
    }
    if ids.is_empty() {
        return Query::Search(raw.to_string());
    }
    let mut seen = std::collections::HashSet::new();
    ids.retain(|i| seen.insert(*i));
    Query::Ids(ids)
}

pub async fn fetch_package(
    c: &Client,
    id: u64,
    cancel: &CancellationToken,
) -> Result<(Package, serde_json::Value)> {
    let resp = c
        .post_form(
            PACKAGE_DETAIL_URL,
            &[("package_idx", id.to_string())],
            &[("X-Requested-With", "XMLHttpRequest")],
            cancel,
        )
        .await?;
    let payload = resp.json()?;
    let not_found = || Error::NotFound(format!("패키지 {id} 를 찾을 수 없습니다."));
    let has_info = match payload.get("info") {
        None | Some(serde_json::Value::Null) | Some(serde_json::Value::Bool(false)) => false,
        Some(serde_json::Value::String(s)) => !s.is_empty(),
        Some(serde_json::Value::Array(a)) => !a.is_empty(),
        Some(serde_json::Value::Object(o)) => !o.is_empty(),
        Some(serde_json::Value::Number(n)) => n.as_f64() != Some(0.0),
        Some(_) => true,
    };
    if !has_info {
        return Err(not_found());
    }
    let pkg = Package::from_api(&payload).ok_or_else(not_found)?;
    Ok((pkg, payload))
}

pub async fn search(
    c: &Client,
    word: &str,
    search_type: &str,
    page: u32,
    cancel: &CancellationToken,
) -> Result<(Vec<Brief>, u32)> {
    let resp = c.get(&search_url(word, search_type, page), cancel).await?;
    let body = resp.text();
    Ok((parse_list_page(&body), parse_total_pages(&body)))
}

pub async fn fetch_all(
    c: &Client,
    page: u32,
    cancel: &CancellationToken,
) -> Result<(Vec<Brief>, u32, u64)> {
    let page = page.max(1);
    let resp = c.get(&format!("{BASE}/new/{page}"), cancel).await?;
    let body = resp.text();
    let rows = parse_list_page(&body);
    let pages = parse_new_pages(&body, if rows.is_empty() { 1 } else { page });
    Ok((rows, pages, parse_new_total(&body)))
}

pub async fn fetch_top(
    c: &Client,
    kind: TopKind,
    cancel: &CancellationToken,
) -> Result<Vec<Brief>> {
    let resp = c.get(top_url(kind), cancel).await?;
    parse_top(&resp.text())
}
