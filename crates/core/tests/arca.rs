use dccon_core::arca::*;
use dccon_core::http::{Client, Throttle};
use dccon_core::models::Brief;
use dccon_core::Error;
use serde_json::{json, Value};
use std::time::Duration;
use tokio_util::sync::CancellationToken;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

fn read(p: &str) -> String {
    std::fs::read_to_string(format!("{}/tests/{p}", env!("CARGO_MANIFEST_DIR"))).unwrap()
}
fn golden(n: &str) -> Value {
    serde_json::from_str(&read(&format!("golden/{n}.json"))).unwrap()
}
fn rows_json(r: &[Brief]) -> Value {
    Value::Array(
        r.iter()
            .map(|b| json!({"idx": b.idx, "title": b.title, "seller": b.seller, "thumb_url": b.thumb_url}))
            .collect(),
    )
}

#[test]
fn parse_list_fixture() {
    let g = golden("parsed_arca_list");
    let body = read("fixtures/arca_list.html");
    let rows = parse_list(&body);
    assert_eq!(rows.iter().map(|r| r.idx).collect::<Vec<_>>(), vec![54566, 48750]);
    assert_eq!(rows[0].title, "고양이 & 밴시");
    assert_eq!(rows[0].seller, "작가1");
    assert_eq!(parse_pages(&body, 1), 12);
    assert_eq!(rows_json(&rows), g["rows"]);
    assert_eq!(json!(parse_pages(&body, 1)), g["pages"]);
}

#[test]
fn parse_detail_images_and_videos() {
    let g = golden("parsed_arca_detail");
    let pkg = parse_package(48750, &read("fixtures/arca_detail.html"));
    assert_eq!(pkg.title, "움짤콘");
    assert_eq!(pkg.seller, "작가2");
    assert_eq!(pkg.main_url(), "https://ac.arca.live/a/icon.png?expires=1&key=k");
    assert_eq!(pkg.items[1].url(), "https://ac.arca.live/a/2.mp4?expires=1&key=k");
    assert!(pkg.items[1].thumb.ends_with("2.thumbnail.jpg?expires=1&key=k"));
    let got: Vec<(u32, u64, String)> =
        pkg.items.iter().map(|i| (i.sort, i.idx, i.ext.clone())).collect();
    let want: Vec<(u32, u64, String)> = g["items"]
        .as_array()
        .unwrap()
        .iter()
        .map(|i| {
            (
                i["sort"].as_u64().unwrap() as u32,
                i["idx"].as_u64().unwrap(),
                i["ext"].as_str().unwrap().to_string(),
            )
        })
        .collect();
    assert_eq!(got, want);
    assert_eq!(serde_json::to_value(&pkg).unwrap(), g);
}

#[test]
fn parse_ids_cases() {
    assert_eq!(parse_ids("https://arca.live/e/54566?p=1 123"), Some(vec![54566, 123]));
    assert_eq!(parse_ids("고양이"), None);
    for row in golden("arca_parse_ids").as_array().unwrap() {
        let text = row[0].as_str().unwrap();
        let want: Option<Vec<u64>> = serde_json::from_value(row[1].clone()).unwrap();
        assert_eq!(parse_ids(text), want, "{text:?}");
    }
}

#[test]
fn query_params() {
    assert_eq!(
        list_query("weekly", 3),
        vec![("p", "3".to_string()), ("rank", "weekly".to_string())]
    );
    assert_eq!(list_query("new", 0), vec![("p", "1".to_string())]);
    assert_eq!(
        search_query("고양이", "tag", 2),
        vec![("target", "tag".to_string()), ("keyword", "고양이".to_string()), ("p", "2".to_string())]
    );
    assert_eq!(search_query("x", "bogus", 1)[0], ("target", "title".to_string()));
}

fn client() -> Client {
    Client::new("https://arca.live/e/", Throttle::new(Duration::ZERO, Duration::ZERO))
        .with_backoff_scale(0.0)
}

#[tokio::test]
async fn redirect_to_login_is_login_required() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/e/"))
        .respond_with(ResponseTemplate::new(302).insert_header("Location", "/u/login?goto=/e/"))
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .and(path("/u/login"))
        .respond_with(ResponseTemplate::new(200).set_body_string("login"))
        .mount(&server)
        .await;
    let r = fetch_list_at(&client(), &server.uri(), "new", 1, &CancellationToken::new()).await;
    assert!(matches!(r, Err(Error::LoginRequired)), "{r:?}");
}

#[tokio::test]
async fn forbidden_is_login_required() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/e/7"))
        .respond_with(ResponseTemplate::new(403))
        .mount(&server)
        .await;
    let r = fetch_package_at(&client(), &server.uri(), 7, &CancellationToken::new()).await;
    assert!(matches!(r, Err(Error::LoginRequired)), "{r:?}");
}

#[tokio::test]
async fn fetch_list_and_empty_package() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/e/"))
        .respond_with(ResponseTemplate::new(200).set_body_string(read("fixtures/arca_list.html")))
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .and(path("/e/5"))
        .respond_with(ResponseTemplate::new(200).set_body_string("<html></html>"))
        .mount(&server)
        .await;
    let c = client();
    let t = CancellationToken::new();
    let (rows, pages) = fetch_list_at(&c, &server.uri(), "new", 1, &t).await.unwrap();
    assert_eq!((rows.len(), pages), (2, 12));
    let r = fetch_package_at(&c, &server.uri(), 5, &t).await;
    assert!(matches!(r, Err(Error::NotFound(ref m)) if m == "아카콘 5 를 찾을 수 없습니다."), "{r:?}");
}

#[test]
fn session_file_compat() {
    let dir = tempfile::tempdir().unwrap();
    let p = dir.path().join("sub").join("arca_session.json");
    assert!(ArcaSession::load(&p).is_none());
    std::fs::create_dir_all(p.parent().unwrap()).unwrap();
    std::fs::write(
        &p,
        r#"{"user_agent": "UA/1 한글", "cookies": [{"name": "a", "value": "1", "domain": ".arca.live", "path": "/"}, {"name": "b", "value": "2"}]}"#,
    )
    .unwrap();
    let s = ArcaSession::load(&p).unwrap();
    assert_eq!(s.cookies[1].path, "/");
    assert_eq!(s.cookies[1].domain, "");
    assert_eq!(s.cookie_pairs(), vec![("a".into(), "1".into()), ("b".into(), "2".into())]);
    let p2 = dir.path().join("new").join("s.json");
    s.save(&p2).unwrap();
    assert!(std::fs::read_to_string(&p2).unwrap().contains("한글"));
    assert_eq!(ArcaSession::load(&p2).unwrap(), s);
    std::fs::write(&p2, "{broken").unwrap();
    assert!(ArcaSession::load(&p2).is_none());
    std::fs::write(&p2, r#"{"cookies": []}"#).unwrap();
    assert!(ArcaSession::load(&p2).is_none());
    ArcaSession::forget(&p2);
    assert!(!p2.exists());
    ArcaSession::forget(&p2);
}
