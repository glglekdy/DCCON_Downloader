use dccon_core::updater::*;
use dccon_core::Error;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tokio_util::sync::CancellationToken;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

fn golden() -> Value {
    let p = format!("{}/tests/golden/version.json", env!("CARGO_MANIFEST_DIR"));
    serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
}

#[test]
fn version_matches_python() {
    let g = golden();
    for c in g["parse"].as_array().unwrap() {
        let want: Vec<u32> = c[1].as_array().unwrap().iter().map(|n| n.as_u64().unwrap() as u32).collect();
        assert_eq!(parse_version(c[0].as_str().unwrap()), want, "{}", c[0]);
    }
    for c in g["newer"].as_array().unwrap() {
        assert_eq!(
            is_newer(c[0].as_str().unwrap(), c[1].as_str().unwrap()),
            c[2].as_bool().unwrap(),
            "{} {}",
            c[0],
            c[1]
        );
    }
}

fn release(names: &[&str]) -> Release {
    let assets: Vec<Value> = names
        .iter()
        .map(|n| json!({"name": n, "browser_download_url": format!("https://x/{n}"), "size": 1}))
        .collect();
    Release::from_api(&json!({"tag_name": "v2.0.0", "assets": assets}))
}

#[test]
fn pick_asset_cases() {
    let r = release(&[
        "dccon-downloader-2.0.0-macos.zip",
        "dccon-downloader-2.0.0-win64.zip",
        "dccon-code-2.0.0-abcdef123456.pyz",
        "dccon-downloader-2.0.0-macos.exe",
        "dccon-downloader-2.0.0.exe",
    ]);
    assert_eq!(pick_asset(&r).unwrap().name, "dccon-downloader-2.0.0.exe");
    assert_eq!(r.version(), "2.0.0");
    let r = release(&["a.zip", "b.pyz", "dccon-darwin.exe"]);
    assert!(pick_asset(&r).is_none());
    let r = release(&["other.exe", "dccon-win.exe"]);
    assert_eq!(pick_asset(&r).unwrap().name, "dccon-win.exe");
    assert_eq!(release_name("2.0.0"), "dccon-downloader-2.0.0.exe");
}

#[tokio::test]
async fn fetch_latest_parses_release() {
    let s = MockServer::start().await;
    Mock::given(method("GET")).and(path("/latest"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "tag_name": "v2.0.0", "name": "N", "body": "notes", "html_url": "https://h",
            "assets": [{"name": "a.exe", "browser_download_url": "https://u", "size": 5, "digest": "sha256:ab"}]
        })))
        .mount(&s).await;
    let r = fetch_latest(&http_client("1.0.0"), &format!("{}/latest", s.uri())).await.unwrap().unwrap();
    assert_eq!((r.tag.as_str(), r.name.as_str(), r.notes.as_str()), ("v2.0.0", "N", "notes"));
    assert_eq!(r.assets[0].size, 5);
    assert_eq!(r.assets[0].digest, "sha256:ab");
}

#[tokio::test]
async fn fetch_latest_404_is_none() {
    let s = MockServer::start().await;
    Mock::given(method("GET")).respond_with(ResponseTemplate::new(404)).mount(&s).await;
    assert!(fetch_latest(&http_client("1.0.0"), &s.uri()).await.unwrap().is_none());
}

#[tokio::test]
async fn fetch_latest_rate_limited_message() {
    let s = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(403).insert_header("x-ratelimit-remaining", "0"))
        .mount(&s).await;
    match fetch_latest(&http_client("1.0.0"), &s.uri()).await {
        Err(Error::Update(m)) => assert_eq!(m, "GitHub 요청 한도를 넘었습니다. 잠시 뒤 다시 시도하세요."),
        other => panic!("{other:?}"),
    }
}

#[tokio::test]
async fn fetch_latest_http_error_and_bad_json() {
    let s = MockServer::start().await;
    Mock::given(method("GET")).and(path("/e")).respond_with(ResponseTemplate::new(500)).mount(&s).await;
    Mock::given(method("GET")).and(path("/j")).respond_with(ResponseTemplate::new(200).set_body_string("nope")).mount(&s).await;
    let c = http_client("1.0.0");
    match fetch_latest(&c, &format!("{}/e", s.uri())).await {
        Err(Error::Update(m)) => assert_eq!(m, "릴리즈 정보를 가져오지 못했습니다. (HTTP 500)"),
        other => panic!("{other:?}"),
    }
    match fetch_latest(&c, &format!("{}/j", s.uri())).await {
        Err(Error::Update(m)) => assert_eq!(m, "릴리즈 정보를 가져오지 못했습니다. (응답 해석 실패)"),
        other => panic!("{other:?}"),
    }
}

#[tokio::test]
async fn fetch_latest_connection_error_message() {
    let port = {
        let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        l.local_addr().unwrap().port()
    };
    match fetch_latest(&http_client("1.0.0"), &format!("http://127.0.0.1:{port}/")).await {
        Err(Error::Update(m)) => assert!(m.starts_with("GitHub 에 연결하지 못했습니다."), "{m}"),
        other => panic!("{other:?}"),
    }
}

fn asset(url: String, body: &[u8], size: u64, digest: String) -> Asset {
    let _ = body;
    Asset { name: "app.exe".into(), url, size, digest }
}

#[tokio::test]
async fn download_verifies_size_and_digest() {
    let s = MockServer::start().await;
    let body: &[u8] = b"hello exe bytes";
    Mock::given(method("GET")).and(path("/f")).respond_with(ResponseTemplate::new(200).set_body_bytes(body)).mount(&s).await;
    Mock::given(method("GET")).and(path("/gone")).respond_with(ResponseTemplate::new(404)).mount(&s).await;
    let url = format!("{}/f", s.uri());
    let good = format!("sha256:{}", hex::encode(Sha256::digest(body)).to_uppercase());
    let c = http_client("1.0.0");
    let tmp = tempfile::tempdir().unwrap();
    let dir = tmp.path().join("stage");
    let cancel = CancellationToken::new();
    let seen = std::sync::Mutex::new((0u64, 0u64));
    let prog = |d: u64, t: u64| *seen.lock().unwrap() = (d, t);

    let ok = download(&c, &asset(url.clone(), body, body.len() as u64, good.clone()), &dir, &prog, &cancel).await.unwrap();
    assert_eq!(ok, dir.join("app.exe"));
    assert_eq!(std::fs::read(&ok).unwrap(), body);
    assert_eq!(*seen.lock().unwrap(), (body.len() as u64, body.len() as u64));
    assert!(!dir.join("app.exe.part").exists());
    std::fs::remove_file(&ok).unwrap();

    for a in [
        asset(url.clone(), body, 3, good.clone()),
        asset(url.clone(), body, body.len() as u64, "sha256:00".into()),
    ] {
        let want = if a.size == 3 {
            "받은 파일 크기가 맞지 않습니다. 다시 시도하세요."
        } else {
            "받은 파일이 손상되었습니다. (SHA-256 불일치)"
        };
        match download(&c, &a, &dir, &prog, &cancel).await {
            Err(Error::Update(m)) => assert_eq!(m, want),
            other => panic!("{other:?}"),
        }
        assert!(!dir.join("app.exe.part").exists());
        assert!(!dir.join("app.exe").exists());
    }

    match download(&c, &asset(format!("{}/gone", s.uri()), body, 0, String::new()), &dir, &prog, &cancel).await {
        Err(Error::Update(m)) => assert_eq!(m, "파일을 받지 못했습니다. (HTTP 404)"),
        other => panic!("{other:?}"),
    }
    assert!(!dir.join("app.exe.part").exists());

    cancel.cancel();
    assert!(matches!(
        download(&c, &asset(url, body, 0, String::new()), &dir, &prog, &cancel).await,
        Err(Error::Cancelled)
    ));
    assert!(!dir.join("app.exe.part").exists());
}
