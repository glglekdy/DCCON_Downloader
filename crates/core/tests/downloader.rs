use std::path::Path;
use std::time::Duration;

use dccon_core::cache::ImageCache;
use dccon_core::downloader::*;
use dccon_core::http::{Client, Throttle};
use dccon_core::models::{Item, Package};
use dccon_core::naming::{item_filename, package_dirname, pad_width};
use dccon_core::Error;
use tokio_util::sync::CancellationToken;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

const PNG: &[u8] = b"\x89PNG\r\n\x1a\nBODY";
const GIF: &[u8] = b"GIF89aBODY";

fn client() -> Client {
    Client::new("https://dccon.dcinside.com/", Throttle::new(Duration::ZERO, Duration::ZERO))
}

fn pkg(server: &MockServer, main: bool) -> Package {
    let items = [(1u32, "안녕"), (2, "하이"), (3, "바이")]
        .iter()
        .map(|(s, t)| Item {
            idx: *s as u64,
            title: t.to_string(),
            sort: *s,
            ext: "png".into(),
            path: format!("{}/img/{s}", server.uri()),
            thumb: String::new(),
        })
        .collect();
    Package {
        idx: 77,
        title: "테스트콘".into(),
        description: "d".into(),
        seller: "s".into(),
        price: "0".into(),
        reg_date: "r".into(),
        main_img_path: if main { format!("{}/img/main", server.uri()) } else { String::new() },
        list_img_path: String::new(),
        items,
        tags: vec![],
    }
}

async fn mount(server: &MockServer, p: &str, body: &[u8]) {
    Mock::given(method("GET"))
        .and(path(p))
        .respond_with(ResponseTemplate::new(200).set_body_bytes(body.to_vec()))
        .mount(server)
        .await;
}

fn opts() -> DownloadOptions {
    DownloadOptions { save_main_image: true, write_meta: true }
}

async fn run(
    server: &MockServer,
    package: &Package,
    root: &Path,
    only: Option<&[u32]>,
    o: &DownloadOptions,
) -> dccon_core::Result<DownloadResult> {
    let cache_dir = tempfile::tempdir().unwrap();
    let cache = ImageCache::new(cache_dir.path().to_path_buf());
    let _ = server;
    download_package(&client(), &cache, package, root, only, o, &|_, _, _| {}, &CancellationToken::new()).await
}

#[tokio::test]
async fn saves_and_skips_existing() {
    let server = MockServer::start().await;
    mount(&server, "/img/main", PNG).await;
    for s in 1..=3 {
        mount(&server, &format!("/img/{s}"), PNG).await;
    }
    let p = pkg(&server, true);
    let root = tempfile::tempdir().unwrap();
    let dest = root.path().join(package_dirname(77, "테스트콘"));
    std::fs::create_dir_all(&dest).unwrap();
    std::fs::write(dest.join("02_하이.png"), b"old").unwrap();
    let r = run(&server, &p, root.path(), None, &opts()).await.unwrap();
    assert_eq!((r.saved, r.skipped), (3, 1));
    assert!(r.failed.is_empty());
    assert_eq!(r.dest, dest);
    assert_eq!(std::fs::read(dest.join("02_하이.png")).unwrap(), b"old");
    assert!(dest.join("01_안녕.png").exists());
    assert!(dest.join("_main.png").exists());
    assert!(dest.join("_meta.json").exists());
}

#[tokio::test]
async fn leftover_part_file_is_not_skipped() {
    let server = MockServer::start().await;
    mount(&server, "/img/1", PNG).await;
    let p = pkg(&server, false);
    let root = tempfile::tempdir().unwrap();
    let dest = root.path().join(package_dirname(77, "테스트콘"));
    std::fs::create_dir_all(&dest).unwrap();
    std::fs::write(dest.join("01_안녕.png.part"), b"half").unwrap();
    let r = run(&server, &p, root.path(), Some(&[1]), &opts()).await.unwrap();
    assert_eq!((r.saved, r.skipped), (1, 0));
    assert_eq!(std::fs::read(dest.join("01_안녕.png")).unwrap(), PNG);
    assert!(!dest.join("01_안녕.png.part").exists());
}

#[tokio::test]
async fn main_image_ext_sniffed() {
    let server = MockServer::start().await;
    mount(&server, "/img/main", GIF).await;
    let p = pkg(&server, true);
    let root = tempfile::tempdir().unwrap();
    let r = run(&server, &p, root.path(), Some(&[]), &opts()).await.unwrap();
    assert_eq!(r.saved, 1);
    assert!(r.dest.join("_main.gif").exists());
    assert_eq!(sniff_ext(GIF, "jpg"), "gif");
    assert_eq!(sniff_ext(b"\xff\xd8\xffx", "png"), "jpg");
    assert_eq!(sniff_ext(b"RIFF\0\0\0\0WEBPx", "png"), "webp");
    assert_eq!(sniff_ext(b"zzz", "jpg"), "jpg");
}

#[tokio::test]
async fn only_sorts_filters() {
    let server = MockServer::start().await;
    mount(&server, "/img/2", PNG).await;
    let mut p = pkg(&server, false);
    for i in &mut p.items {
        if i.sort == 3 {
            i.sort = 10;
        }
    }
    let root = tempfile::tempdir().unwrap();
    let r = run(&server, &p, root.path(), Some(&[2]), &opts()).await.unwrap();
    assert_eq!(r.saved, 1);
    // 자릿수는 전체 최대 sort(10) 기준 -> 2자리.
    assert!(r.dest.join("02_하이.png").exists());
    assert!(!r.dest.join("01_안녕.png").exists());
}

#[tokio::test]
async fn failure_is_collected() {
    let server = MockServer::start().await;
    mount(&server, "/img/1", PNG).await;
    mount(&server, "/img/3", PNG).await;
    Mock::given(method("GET")).and(path("/img/2"))
        .respond_with(ResponseTemplate::new(404)).mount(&server).await;
    let p = pkg(&server, false);
    let root = tempfile::tempdir().unwrap();
    let r = run(&server, &p, root.path(), None, &opts()).await.unwrap();
    assert_eq!(r.saved, 2);
    assert_eq!(r.failed.len(), 1);
    assert_eq!(r.failed[0].0, "02_하이.png");
    assert!(!r.failed[0].1.is_empty());
    assert!(r.dest.join("03_바이.png").exists());
}

#[test]
fn meta_json_matches_python() {
    let base = env!("CARGO_MANIFEST_DIR");
    let v: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(format!("{base}/tests/fixtures/dccon_detail.json")).unwrap(),
    )
    .unwrap();
    let p = Package::from_api(&v).unwrap();
    let width = pad_width(p.items.iter().map(|i| i.sort as usize).max().unwrap());
    assert_eq!(item_filename(1, "a", "png", width).len(), "01_a.png".len());
    let dir = tempfile::tempdir().unwrap();
    write_meta(dir.path(), &p, width).unwrap();
    let got = std::fs::read(dir.path().join("_meta.json")).unwrap();
    let want = std::fs::read(format!("{base}/tests/golden/meta.json")).unwrap();
    assert_eq!(String::from_utf8_lossy(&got), String::from_utf8_lossy(&want));
    assert_eq!(got, want);
}

#[tokio::test]
async fn cancel_stops() {
    let server = MockServer::start().await;
    let p = pkg(&server, false);
    let root = tempfile::tempdir().unwrap();
    let cache_dir = tempfile::tempdir().unwrap();
    let cache = ImageCache::new(cache_dir.path().to_path_buf());
    let cancel = CancellationToken::new();
    cancel.cancel();
    let r = download_package(&client(), &cache, &p, root.path(), None, &opts(), &|_, _, _| {}, &cancel).await;
    assert!(matches!(r, Err(Error::Cancelled)));
}
