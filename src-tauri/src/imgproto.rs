//! `img://` 프로토콜. 웹뷰가 요청한 썸네일·이미지를 디스크 캐시에서 내주고, 없으면 받아온다.
//!
//! 요청 형식: `?u=<URL 인코딩된 원본 주소>&e=<ext>&g=<세대>&s=<dccon|arca>`.
//! 캐시에 있으면 세대와 상관없이 바로 내주고, 없는데 세대가 지났으면 204 로 버린다.

use std::sync::atomic::Ordering;
use std::sync::Arc;

use dccon_core::models::Site;
use percent_encoding::percent_decode_str;
use tauri::http::{header, Request, Response};
use tauri::{Manager, Runtime, UriSchemeContext, UriSchemeResponder};
use tokio_util::sync::CancellationToken;

use crate::state::AppState;

type Headers = Vec<(String, String)>;

/// 받아도 되는 호스트(자기 자신 또는 그 하위 도메인). 새 이미지 CDN 이 생기면 여기에 추가해야 한다.
/// 사이트 클라이언트가 Referer·쿠키를 붙이므로, 목록 밖 주소로는 요청을 보내지 않는다.
const ALLOWED_HOSTS: &[&str] = &["dcinside.com", "dcinside.co.kr", "arca.live", "namu.la"];

fn url_allowed(raw: &str) -> bool {
    let Ok(u) = url::Url::parse(raw) else { return false };
    if !matches!(u.scheme(), "http" | "https") {
        return false;
    }
    let Some(host) = u.host_str() else { return false };
    let host = host.to_ascii_lowercase();
    // 테스트의 wiremock 서버(루프백)만 허용. 제품 빌드에는 들어가지 않는다.
    #[cfg(test)]
    if host == "127.0.0.1" || host == "localhost" {
        return true;
    }
    ALLOWED_HOSTS.iter().any(|d| host == *d || host.ends_with(&format!(".{d}")))
}

fn ext_allowed(ext: &str) -> bool {
    (1..=5).contains(&ext.len()) && ext.bytes().all(|b| b.is_ascii_alphanumeric())
}

fn content_type(ext: &str) -> &'static str {
    match ext.trim_start_matches('.').to_lowercase().as_str() {
        "png" => "image/png",
        "gif" => "image/gif",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "mp4" => "video/mp4",
        _ => "application/octet-stream",
    }
}

fn param(query: &str, key: &str) -> Option<String> {
    query.split('&').find_map(|kv| {
        let (k, v) = kv.split_once('=')?;
        (k == key).then(|| percent_decode_str(v).decode_utf8_lossy().into_owned())
    })
}

enum Span {
    Ok(usize, usize),
    Unsatisfiable,
    Ignore,
}

/// `bytes=a-b`, `bytes=a-`, `bytes=-n` 만 다룬다. 해석 못 하면 범위를 무시한다.
fn parse_range(header: &str, total: usize) -> Span {
    let Some(spec) = header.trim().strip_prefix("bytes=") else { return Span::Ignore };
    if spec.contains(',') {
        return Span::Ignore;
    }
    let Some((a, b)) = spec.split_once('-') else { return Span::Ignore };
    let (a, b) = (a.trim(), b.trim());
    let (start, end) = if a.is_empty() {
        let Ok(n) = b.parse::<usize>() else { return Span::Ignore };
        if n == 0 || total == 0 {
            return Span::Unsatisfiable;
        }
        (total.saturating_sub(n), total - 1)
    } else {
        let Ok(start) = a.parse::<usize>() else { return Span::Ignore };
        let end = if b.is_empty() {
            usize::MAX
        } else {
            match b.parse::<usize>() {
                Ok(e) => e,
                Err(_) => return Span::Ignore,
            }
        };
        if start >= total || start > end {
            return Span::Unsatisfiable;
        }
        (start, end.min(total - 1))
    };
    Span::Ok(start, end)
}

fn reply(status: u16, mut headers: Headers, body: Vec<u8>) -> (u16, Headers, Vec<u8>) {
    headers.push(("Access-Control-Allow-Origin".into(), "*".into()));
    (status, headers, body)
}

fn ok_headers(ext: &str) -> Headers {
    let mut h = vec![
        ("Content-Type".to_string(), content_type(ext).to_string()),
        ("Cache-Control".to_string(), "max-age=31536000".to_string()),
    ];
    if content_type(ext) == "video/mp4" {
        h.push(("Accept-Ranges".into(), "bytes".into()));
    }
    h
}

fn respond_data(ext: &str, data: Vec<u8>, range: Option<&str>) -> (u16, Headers, Vec<u8>) {
    let total = data.len();
    match range.map(|r| parse_range(r, total)).unwrap_or(Span::Ignore) {
        Span::Ok(a, b) => {
            let mut h = ok_headers(ext);
            h.retain(|(k, _)| k != "Accept-Ranges");
            h.push(("Accept-Ranges".into(), "bytes".into()));
            h.push(("Content-Range".into(), format!("bytes {a}-{b}/{total}")));
            reply(206, h, data[a..=b].to_vec())
        }
        Span::Unsatisfiable => reply(
            416,
            vec![
                ("Accept-Ranges".into(), "bytes".into()),
                ("Content-Range".into(), format!("bytes */{total}")),
            ],
            Vec::new(),
        ),
        Span::Ignore => reply(200, ok_headers(ext), data),
    }
}

pub(crate) async fn serve(
    state: &AppState,
    query: &str,
    range: Option<&str>,
) -> (u16, Headers, Vec<u8>) {
    let url = match param(query, "u") {
        Some(u) if !u.is_empty() => u,
        _ => return reply(400, vec![], Vec::new()),
    };
    if !url_allowed(&url) {
        return reply(400, vec![], Vec::new());
    }
    let ext = param(query, "e").unwrap_or_default();
    if !ext_allowed(&ext) {
        return reply(400, vec![], Vec::new());
    }
    // g 가 없거나 숫자가 아니면 현재 세대로 본다(버리지 않는다).
    let generation = param(query, "g").and_then(|g| g.parse::<u64>().ok());
    let site = match param(query, "s").as_deref() {
        Some("arca") => Site::Arca,
        _ => Site::Dccon,
    };

    if let Some(data) = state.images.peek(&url, &ext) {
        return respond_data(&ext, data, range);
    }
    let stale = |g: Option<u64>| g.is_some_and(|g| g != state.view_gen.load(Ordering::SeqCst));
    if stale(generation) {
        return reply(204, vec![], Vec::new());
    }
    let sem = state.thumb.read().unwrap().clone();
    let Ok(_permit) = sem.acquire_owned().await else {
        return reply(502, vec![], Vec::new());
    };
    // 허가를 기다리는 사이 화면이 바뀌었을 수 있다.
    if stale(generation) {
        return reply(204, vec![], Vec::new());
    }
    match state.images.get(state.client(site), &url, &ext, &CancellationToken::new()).await {
        Ok(data) => respond_data(&ext, data, range),
        Err(_) => reply(502, vec![], Vec::new()),
    }
}

pub fn handle<R: Runtime>(
    ctx: UriSchemeContext<'_, R>,
    request: Request<Vec<u8>>,
    responder: UriSchemeResponder,
) {
    let state = ctx.app_handle().state::<Arc<AppState>>().inner().clone();
    let query = request.uri().query().unwrap_or("").to_string();
    let range = request
        .headers()
        .get(header::RANGE)
        .and_then(|v| v.to_str().ok())
        .map(str::to_string);
    tauri::async_runtime::spawn(async move {
        let (status, headers, body) = serve(&state, &query, range.as_deref()).await;
        let mut b = Response::builder().status(status);
        for (k, v) in headers {
            b = b.header(k, v);
        }
        let resp = b
            .body(body)
            .unwrap_or_else(|_| Response::builder().status(500).body(Vec::new()).expect("빈 응답"));
        responder.respond(resp);
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use dccon_core::config::Paths;
    use wiremock::matchers::method;
    use wiremock::{Mock, MockServer, ResponseTemplate};

    fn state() -> (AppState, tempfile::TempDir) {
        let dir = tempfile::tempdir().unwrap();
        (AppState::new(Paths::new(dir.path().to_path_buf())), dir)
    }

    fn q(url: &str, ext: &str, g: u64) -> String {
        let enc =
            percent_encoding::utf8_percent_encode(url, percent_encoding::NON_ALPHANUMERIC)
                .to_string();
        format!("u={enc}&e={ext}&g={g}&s=dccon")
    }

    fn hdr<'a>(h: &'a Headers, k: &str) -> Option<&'a str> {
        h.iter().find(|(n, _)| n == k).map(|(_, v)| v.as_str())
    }

    async fn server(status: u16, body: &[u8]) -> MockServer {
        let s = MockServer::start().await;
        Mock::given(method("GET"))
            .respond_with(ResponseTemplate::new(status).set_body_bytes(body.to_vec()))
            .mount(&s)
            .await;
        s
    }

    #[tokio::test]
    async fn serves_cached_without_network() {
        let (st, _d) = state();
        let s = server(500, b"").await;
        let url = format!("{}/a.png?no=1", s.uri());
        let p = st.images.path_for(&url, "png");
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(&p, b"PNGDATA").unwrap();
        st.view_gen.store(5, Ordering::SeqCst);
        let (code, h, body) = serve(&st, &q(&url, "png", 1), None).await;
        assert_eq!(code, 200);
        assert_eq!(body, b"PNGDATA");
        assert_eq!(hdr(&h, "Content-Type"), Some("image/png"));
        assert_eq!(hdr(&h, "Cache-Control"), Some("max-age=31536000"));
        assert_eq!(hdr(&h, "Access-Control-Allow-Origin"), Some("*"));
        assert!(s.received_requests().await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn stale_generation_is_dropped() {
        let (st, _d) = state();
        let s = server(200, b"x").await;
        st.view_gen.store(2, Ordering::SeqCst);
        let url = format!("{}/a.png?no=2", s.uri());
        let (code, h, body) = serve(&st, &q(&url, "png", 1), None).await;
        assert_eq!(code, 204);
        assert!(body.is_empty());
        assert!(hdr(&h, "Cache-Control").is_none());
        assert!(s.received_requests().await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn fetches_and_caches() {
        let (st, _d) = state();
        let s = server(200, b"GIFDATA").await;
        st.view_gen.store(3, Ordering::SeqCst);
        let url = format!("{}/a.gif?no=3", s.uri());
        let (code, h, body) = serve(&st, &q(&url, "gif", 3), None).await;
        assert_eq!(code, 200);
        assert_eq!(body, b"GIFDATA");
        assert_eq!(hdr(&h, "Content-Type"), Some("image/gif"));
        assert_eq!(st.images.peek(&url, "gif").as_deref(), Some(&b"GIFDATA"[..]));
    }

    #[tokio::test]
    async fn range_request_for_mp4() {
        let (st, _d) = state();
        let s = server(200, b"0123456789").await;
        let url = format!("{}/a.mp4?no=4", s.uri());
        let query = q(&url, "mp4", 0);
        let (code, h, body) = serve(&st, &query, Some("bytes=0-1")).await;
        assert_eq!(code, 206);
        assert_eq!(body, b"01");
        assert_eq!(hdr(&h, "Content-Range"), Some("bytes 0-1/10"));
        assert_eq!(hdr(&h, "Content-Type"), Some("video/mp4"));
        let (code, h, body) = serve(&st, &query, Some("bytes=-3")).await;
        assert_eq!((code, body.as_slice()), (206, &b"789"[..]));
        assert_eq!(hdr(&h, "Content-Range"), Some("bytes 7-9/10"));
        let (code, _, body) = serve(&st, &query, Some("bytes=8-")).await;
        assert_eq!((code, body.as_slice()), (206, &b"89"[..]));
        let (code, h, _) = serve(&st, &query, Some("bytes=20-30")).await;
        assert_eq!(code, 416);
        assert_eq!(hdr(&h, "Content-Range"), Some("bytes */10"));
        let (code, h, _) = serve(&st, &query, None).await;
        assert_eq!(code, 200);
        assert_eq!(hdr(&h, "Accept-Ranges"), Some("bytes"));
    }

    #[tokio::test]
    async fn upstream_error_is_502() {
        let (st, _d) = state();
        let s = server(404, b"nope").await;
        let url = format!("{}/a.png?no=5", s.uri());
        let (code, _, _) = serve(&st, &q(&url, "png", 0), None).await;
        assert_eq!(code, 502);
    }

    #[tokio::test]
    async fn missing_url_is_400() {
        let (st, _d) = state();
        assert_eq!(serve(&st, "e=png&g=0", None).await.0, 400);
    }

    #[test]
    fn accepts_listed_host_suffix() {
        assert!(url_allowed("https://dcimg5.dcinside.com/dccon.php?no=x"));
        assert!(url_allowed("https://ac.namu.la/x.png"));
        assert!(url_allowed("http://arca.live/a"));
        assert!(!url_allowed("https://evildcinside.com/"));
        assert!(!url_allowed("https://dcinside.com.evil.com/"));
    }

    #[tokio::test]
    async fn rejects_non_http_scheme() {
        let (st, _d) = state();
        let (code, h, _) = serve(&st, &q("file:///C:/x", "png", 0), None).await;
        assert_eq!(code, 400);
        assert_eq!(hdr(&h, "Access-Control-Allow-Origin"), Some("*"));
    }

    #[tokio::test]
    async fn rejects_unlisted_host() {
        let (st, _d) = state();
        let (code, _, _) = serve(&st, &q("https://example.com/a.png", "png", 0), None).await;
        assert_eq!(code, 400);
    }

    #[tokio::test]
    async fn rejects_traversal_ext() {
        let (st, _d) = state();
        let s = server(200, b"x").await;
        let url = format!("{}/a.png?no=9", s.uri());
        let (code, _, _) = serve(&st, &q(&url, "./../../x", 0), None).await;
        assert_eq!(code, 400);
        assert!(s.received_requests().await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn missing_generation_is_current() {
        let (st, _d) = state();
        let s = server(200, b"ok").await;
        st.view_gen.store(7, Ordering::SeqCst);
        let url = format!("{}/a.png?no=8", s.uri());
        let enc = percent_encoding::utf8_percent_encode(&url, percent_encoding::NON_ALPHANUMERIC);
        let (code, _, body) = serve(&st, &format!("u={enc}&e=png"), None).await;
        assert_eq!((code, body.as_slice()), (200, &b"ok"[..]));
    }
}
