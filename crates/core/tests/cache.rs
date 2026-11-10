use std::time::Duration;

use dccon_core::cache::{cache_key, ImageCache, MetaCache};
use dccon_core::http::{Client, Throttle};
use tokio_util::sync::CancellationToken;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

#[test]
fn cache_key_matches_python() {
    let raw = include_str!("golden/cache_key.json");
    let items: Vec<(String, String)> = serde_json::from_str(raw).unwrap();
    assert!(!items.is_empty());
    for (url, key) in items {
        assert_eq!(cache_key(&url), key, "{url}");
    }
}

#[test]
fn layout_matches_python() {
    let dir = tempfile::tempdir().unwrap();
    let c = ImageCache::new(dir.path().to_path_buf());
    let url = "https://dcimg5.dcinside.com/dccon.php?no=abc%2Fd&date=1";
    let key = cache_key(url);
    for ext in ["GIF", ".gif", ".GIF"] {
        assert_eq!(
            c.path_for(url, ext),
            dir.path().join(&key[..2]).join(format!("{key}.gif"))
        );
    }
}

#[tokio::test]
async fn get_fetches_once_concurrently() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/dccon.php"))
        .respond_with(
            ResponseTemplate::new(200)
                .set_body_bytes(b"IMGDATA".to_vec())
                .set_delay(Duration::from_millis(100)),
        )
        .mount(&server)
        .await;
    let dir = tempfile::tempdir().unwrap();
    let cache = ImageCache::new(dir.path().to_path_buf());
    let client = Client::new(
        "https://dccon.dcinside.com/",
        Throttle::new(Duration::ZERO, Duration::ZERO),
    );
    let cancel = CancellationToken::new();
    let url = format!("{}/dccon.php?no=zz1&date=1", server.uri());
    let mut tasks = Vec::new();
    for _ in 0..5 {
        let (cache, client, cancel, url) = (cache.clone(), client.clone(), cancel.clone(), url.clone());
        tasks.push(tokio::spawn(async move {
            cache.get(&client, &url, "png", &cancel).await.unwrap()
        }));
    }
    for t in tasks {
        assert_eq!(t.await.unwrap(), b"IMGDATA");
    }
    assert_eq!(server.received_requests().await.unwrap().len(), 1);
    assert_eq!(cache.peek(&url, "png").unwrap(), b"IMGDATA");
}

#[test]
fn peek_reads_existing_python_cache() {
    let dir = tempfile::tempdir().unwrap();
    let url = "https://dcimg5.dcinside.com/dccon.php?no=한글&date=1";
    let key = cache_key(url);
    let p = dir.path().join(&key[..2]);
    std::fs::create_dir_all(&p).unwrap();
    std::fs::write(p.join(format!("{key}.png")), b"OLD").unwrap();
    let c = ImageCache::new(dir.path().to_path_buf());
    assert_eq!(c.peek(url, "PNG").unwrap(), b"OLD");
    assert!(c.peek("https://x/y?no=none", "png").is_none());
}

#[test]
fn stats_and_clear() {
    let root = tempfile::tempdir().unwrap();
    let img = root.path().join("img");
    let meta = root.path().join("meta");
    let c = ImageCache::new(img.clone());
    assert_eq!(c.stats(), (0, 0));
    std::fs::create_dir_all(img.join("ab")).unwrap();
    std::fs::write(img.join("ab/one.png"), b"123").unwrap();
    std::fs::write(img.join("ab/two.gif"), b"45678").unwrap();
    let m = MetaCache::new(meta.clone());
    assert!(m.load(7).is_none());
    let v = serde_json::json!({"title": "한글", "n": 1});
    m.store(7, &v);
    assert_eq!(m.load(7).unwrap(), v);
    assert!(std::fs::read_to_string(meta.join("7.json")).unwrap().contains("한글"));
    assert_eq!(c.stats(), (2, 8));
    c.clear(&meta);
    assert!(!img.exists());
    assert!(!meta.exists());
}
