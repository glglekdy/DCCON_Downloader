//! GitHub 릴리즈 조회·자산 고르기·받기. (적용은 `apply` 에서.)

use std::path::{Path, PathBuf};
use std::time::Duration;

use futures_util::StreamExt;
use serde_json::Value;
use sha2::{Digest, Sha256};
use tokio::io::AsyncWriteExt;
use tokio_util::sync::CancellationToken;

pub mod apply;

use crate::{Error, Result};

pub const REPO: &str = "glglekdy/DCCON_Downloader";
pub const LATEST_URL: &str = "https://api.github.com/repos/glglekdy/DCCON_Downloader/releases/latest";
pub const RELEASES_PAGE: &str = "https://github.com/glglekdy/DCCON_Downloader/releases";

// ---------------------------------------------------------------- 버전
/// `v1.2.3`, `1.2`, `1.2.3-beta` 모두 숫자 부분만 본다. 끝의 0 은 뗀다(1.2 == 1.2.0).
pub fn parse_version(text: &str) -> Vec<u32> {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let re = RE.get_or_init(|| regex::Regex::new(r"^\s*v?(\d+(?:\.\d+)*)").unwrap());
    let Some(m) = re.captures(text) else {
        return Vec::new();
    };
    let mut parts: Vec<u32> = m[1].split('.').map(|p| p.parse().unwrap_or(u32::MAX)).collect();
    while parts.len() > 1 && parts.last() == Some(&0) {
        parts.pop();
    }
    parts
}

pub fn is_newer(remote: &str, local: &str) -> bool {
    let r = parse_version(remote);
    !r.is_empty() && r > parse_version(local)
}

// ---------------------------------------------------------------- 릴리즈
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Asset {
    pub name: String,
    pub url: String,
    pub size: u64,
    /// "sha256:..." (비어 있을 수 있다)
    pub digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Release {
    pub tag: String,
    pub name: String,
    pub notes: String,
    pub page_url: String,
    pub assets: Vec<Asset>,
}

fn text(v: &Value, key: &str) -> String {
    v.get(key).and_then(Value::as_str).unwrap_or("").to_string()
}

impl Release {
    pub fn from_api(v: &Value) -> Release {
        let tag = text(v, "tag_name");
        let name = Some(text(v, "name")).filter(|s| !s.is_empty()).unwrap_or_else(|| tag.clone());
        let page_url = Some(text(v, "html_url"))
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| RELEASES_PAGE.into());
        let assets = v
            .get("assets")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .map(|a| Asset {
                        name: text(a, "name"),
                        url: text(a, "browser_download_url"),
                        size: a.get("size").and_then(Value::as_u64).unwrap_or(0),
                        digest: text(a, "digest"),
                    })
                    .collect()
            })
            .unwrap_or_default();
        Release { tag, name, notes: text(v, "body"), page_url, assets }
    }

    pub fn version(&self) -> String {
        self.tag.trim_start_matches(['v', 'V']).to_string()
    }
}

/// 받을 단일 exe. macOS 용은 뺀다("darwin" 에도 win 이 들어 있다). 이름에 win 이 든 쪽이 먼저.
pub fn pick_asset(r: &Release) -> Option<&Asset> {
    let mut matches: Vec<&Asset> = r
        .assets
        .iter()
        .filter(|a| {
            let n = a.name.to_lowercase();
            n.ends_with(".exe")
                && !a.url.is_empty()
                && !["macos", "darwin", "mac-", "-mac."].iter().any(|t| n.contains(t))
        })
        .collect();
    matches.sort_by_key(|a| !a.name.to_lowercase().contains("win"));
    matches.into_iter().next()
}

pub fn release_name(version: &str) -> String {
    format!("dccon-downloader-{version}.exe")
}

// ---------------------------------------------------------------- HTTP
pub fn http_client(version: &str) -> reqwest::Client {
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(reqwest::header::ACCEPT, "application/vnd.github+json".parse().unwrap());
    reqwest::Client::builder()
        .user_agent(format!("dccon-downloader/{version}"))
        .default_headers(headers)
        .redirect(reqwest::redirect::Policy::limited(10))
        .connect_timeout(Duration::from_secs(20))
        .build()
        .expect("reqwest client")
}

fn kind_word(e: &reqwest::Error) -> &'static str {
    if e.is_timeout() {
        "timeout"
    } else if e.is_connect() {
        "connect"
    } else if e.is_decode() {
        "decode"
    } else if e.is_body() {
        "body"
    } else {
        "request"
    }
}

/// 최신 정식 릴리즈. 릴리즈가 하나도 없으면 None.
pub async fn fetch_latest(http: &reqwest::Client, url: &str) -> Result<Option<Release>> {
    let resp = http
        .get(url)
        .timeout(Duration::from_secs(20))
        .send()
        .await
        .map_err(|e| Error::Update(format!("GitHub 에 연결하지 못했습니다. ({})", kind_word(&e))))?;
    let code = resp.status().as_u16();
    if code == 404 {
        return Ok(None);
    }
    if code == 403
        && resp.headers().get("x-ratelimit-remaining").and_then(|v| v.to_str().ok()) == Some("0")
    {
        return Err(Error::Update("GitHub 요청 한도를 넘었습니다. 잠시 뒤 다시 시도하세요.".into()));
    }
    if code >= 400 {
        return Err(Error::Update(format!("릴리즈 정보를 가져오지 못했습니다. (HTTP {code})")));
    }
    let bad = || Error::Update("릴리즈 정보를 가져오지 못했습니다. (응답 해석 실패)".into());
    let body = resp.bytes().await.map_err(|_| bad())?;
    let v: Value = serde_json::from_slice(&body).map_err(|_| bad())?;
    Ok(Some(Release::from_api(&v)))
}

// ---------------------------------------------------------------- 받기
/// `staging/<name>` 으로 받아 크기·SHA-256 을 확인하고 그 경로를 돌려준다.
/// 실패하면 `.part` 는 지운다.
pub async fn download(
    http: &reqwest::Client,
    asset: &Asset,
    staging: &Path,
    progress: &(dyn Fn(u64, u64) + Send + Sync),
    cancel: &CancellationToken,
) -> Result<PathBuf> {
    let n = asset.name.as_str();
    if n.is_empty() || n.contains('/') || n.contains('\\') || n.contains("..") {
        return Err(Error::Update("잘못된 파일 이름입니다.".into()));
    }
    tokio::fs::create_dir_all(staging).await?;
    let target = staging.join(&asset.name);
    let part = staging.join(format!("{}.part", asset.name));
    match stream_to(http, asset, &part, progress, cancel).await {
        Ok(()) => {
            if let Err(e) = tokio::fs::rename(&part, &target).await {
                let _ = tokio::fs::remove_file(&part).await;
                return Err(e.into());
            }
            Ok(target)
        }
        Err(e) => {
            let _ = tokio::fs::remove_file(&part).await;
            Err(e)
        }
    }
}

async fn stream_to(
    http: &reqwest::Client,
    asset: &Asset,
    part: &Path,
    progress: &(dyn Fn(u64, u64) + Send + Sync),
    cancel: &CancellationToken,
) -> Result<()> {
    let cut = |e: reqwest::Error| Error::Update(format!("다운로드가 끊겼습니다. ({})", kind_word(&e)));
    let resp = http.get(&asset.url).send().await.map_err(cut)?;
    let code = resp.status().as_u16();
    if code >= 400 {
        return Err(Error::Update(format!("파일을 받지 못했습니다. (HTTP {code})")));
    }
    let total = resp.content_length().filter(|n| *n > 0).unwrap_or(asset.size);
    let mut file = tokio::fs::File::create(part).await?;
    let mut hasher = Sha256::new();
    let mut done = 0u64;
    let mut stream = resp.bytes_stream();
    loop {
        let next = tokio::select! {
            _ = cancel.cancelled() => return Err(Error::Cancelled),
            r = tokio::time::timeout(Duration::from_secs(60), stream.next()) => r,
        };
        let Ok(next) = next else {
            return Err(Error::Update("다운로드가 끊겼습니다. (timeout)".into()));
        };
        let Some(chunk) = next else { break };
        let chunk = chunk.map_err(cut)?;
        file.write_all(&chunk).await?;
        hasher.update(&chunk);
        done += chunk.len() as u64;
        progress(done, total);
    }
    if cancel.is_cancelled() {
        return Err(Error::Cancelled);
    }
    file.flush().await?;
    // 전원이 나가도 잘린 exe 가 남지 않게 디스크에 내린 뒤 이름을 바꾼다.
    file.sync_all().await?;
    drop(file);

    if asset.size > 0 && done != asset.size {
        return Err(Error::Update("받은 파일 크기가 맞지 않습니다. 다시 시도하세요.".into()));
    }
    if let Some(expected) = asset.digest.strip_prefix("sha256:") {
        if !expected.is_empty() && hex::encode(hasher.finalize()) != expected.to_lowercase() {
            return Err(Error::Update("받은 파일이 손상되었습니다. (SHA-256 불일치)".into()));
        }
    }
    Ok(())
}
