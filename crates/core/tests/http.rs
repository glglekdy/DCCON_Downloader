use std::time::Duration;

use dccon_core::http::{Client, Throttle};
use dccon_core::Error;
use tokio_util::sync::CancellationToken;
use wiremock::matchers::{header, method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

fn client(scale: f64) -> Client {
    Client::new(
        "https://dccon.dcinside.com/",
        Throttle::new(Duration::ZERO, Duration::ZERO),
    )
    .with_backoff_scale(scale)
}

async fn count(server: &MockServer) -> usize {
    server.received_requests().await.unwrap().len()
}

#[tokio::test]
async fn sends_default_headers() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/x"))
        .and(header("Referer", "https://dccon.dcinside.com/"))
        // wiremock's `header` splits values on commas, so match this one by hand.
        .and(|req: &wiremock::Request| {
            req.headers
                .get("accept-language")
                .map(|v| v.as_bytes() == b"ko-KR,ko;q=0.9")
                .unwrap_or(false)
        })
        .respond_with(ResponseTemplate::new(200).set_body_string("ok"))
        .mount(&server)
        .await;
    let resp = client(0.01)
        .get(&format!("{}/x", server.uri()), &CancellationToken::new())
        .await
        .unwrap();
    assert_eq!(resp.status, 200);
    assert_eq!(resp.text(), "ok");
}

#[tokio::test]
async fn retries_5xx_then_succeeds() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(503))
        .up_to_n_times(2)
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&server)
        .await;
    let resp = client(0.01)
        .get(&server.uri(), &CancellationToken::new())
        .await
        .unwrap();
    assert_eq!(resp.status, 200);
    assert_eq!(count(&server).await, 3);
}

#[tokio::test]
async fn gives_up_after_four_retries() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(502))
        .mount(&server)
        .await;
    let err = client(0.01)
        .get(&server.uri(), &CancellationToken::new())
        .await
        .unwrap_err();
    assert!(matches!(err, Error::RateLimited), "{err:?}");
    assert_eq!(count(&server).await, 5);
}

#[tokio::test]
async fn pauses_globally_on_429() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(429))
        .up_to_n_times(1)
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&server)
        .await;
    // 5 s * 0.5 = 2.5 s pause: plenty of headroom to observe it.
    let c = client(0.5);
    let c2 = c.clone();
    let uri = server.uri();
    let task = tokio::spawn(async move { c2.get(&uri, &CancellationToken::new()).await });
    for _ in 0..5000 {
        if count(&server).await >= 1 {
            break;
        }
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    assert!(count(&server).await >= 1, "server never saw the request");
    let mut seen = false;
    for _ in 0..1000 {
        if c.is_paused() {
            seen = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    assert!(seen, "client never paused after 429");
    let resp = task.await.unwrap().unwrap();
    assert_eq!(resp.status, 200);
    assert!(!c.is_paused());
    assert_eq!(count(&server).await, 2);
}

#[tokio::test]
async fn cancel_while_paused() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&server)
        .await;
    let c = client(0.01);
    c.pause();
    let cancel = CancellationToken::new();
    let cc = cancel.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(100)).await;
        cc.cancel();
    });
    let err = c.get(&server.uri(), &cancel).await.unwrap_err();
    assert!(matches!(err, Error::Cancelled), "{err:?}");
    assert_eq!(count(&server).await, 0);
}

#[tokio::test]
async fn http_404_is_http_error() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(404))
        .mount(&server)
        .await;
    let err = client(0.01)
        .get(&server.uri(), &CancellationToken::new())
        .await
        .unwrap_err();
    assert!(matches!(err, Error::Http(404)), "{err:?}");
    assert_eq!(count(&server).await, 1);
}

#[tokio::test]
async fn session_sets_ua_and_cookie() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(header("User-Agent", "UA"))
        .and(header("Cookie", "a=1; b=2"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&server)
        .await;
    let c = client(0.01);
    c.set_session("UA", &[("a".into(), "1".into()), ("b".into(), "2".into())]);
    let resp = c.get(&server.uri(), &CancellationToken::new()).await.unwrap();
    assert_eq!(resp.status, 200);
}

#[tokio::test]
async fn final_url_after_redirect() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/r"))
        .respond_with(ResponseTemplate::new(302).insert_header("Location", "/u/login"))
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .and(path("/u/login"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&server)
        .await;
    let resp = client(0.01)
        .get(&format!("{}/r", server.uri()), &CancellationToken::new())
        .await
        .unwrap();
    assert!(resp.url.ends_with("/u/login"), "{}", resp.url);
}

#[tokio::test]
async fn post_form_sends_body() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(wiremock::matchers::body_string("a=1&b=x+y"))
        .respond_with(ResponseTemplate::new(200).set_body_string("{\"k\":1}"))
        .mount(&server)
        .await;
    let resp = client(0.01)
        .post_form(
            &server.uri(),
            &[("a", "1".into()), ("b", "x y".into())],
            &[],
            &CancellationToken::new(),
        )
        .await
        .unwrap();
    assert_eq!(resp.json().unwrap()["k"], 1);
}

#[tokio::test]
async fn user_pause_survives_auto_resume() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(429))
        .up_to_n_times(1)
        .mount(&server)
        .await;
    Mock::given(method("GET"))
        .respond_with(ResponseTemplate::new(200))
        .mount(&server)
        .await;
    let c = client(0.1); // auto pause 0.5 s
    let c2 = c.clone();
    let uri = server.uri();
    let task = tokio::spawn(async move { c2.get(&uri, &CancellationToken::new()).await });
    let mut seen = false;
    for _ in 0..5000 {
        if c.is_paused() {
            seen = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    assert!(seen);
    c.pause(); // user pause on top of the auto pause
    tokio::time::sleep(Duration::from_millis(900)).await; // well past 0.5 s
    assert!(c.is_paused(), "auto resume cancelled the user pause");
    assert!(!task.is_finished());
    assert_eq!(count(&server).await, 1);
    c.resume();
    let resp = task.await.unwrap().unwrap();
    assert_eq!(resp.status, 200);
    assert!(!c.is_paused());
}
