//! HTTP 클라이언트: 스로틀, 지수 백오프, 전역 일시정지, 취소.
//!
//! 파이썬 `dccon/client.py` 의 포팅이다. 한 `Client` 를 여러 태스크가 복제해 공유한다.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::time::Duration;

use bytes::Bytes;
use rand::Rng;
use reqwest::header::{HeaderMap, HeaderName, HeaderValue};
use tokio::sync::watch;
use tokio::time::Instant;
use tokio_util::sync::CancellationToken;

use crate::error::{Error, Result};

pub const USER_AGENT: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const ACCEPT_LANGUAGE: &str = "ko-KR,ko;q=0.9";
const RETRIES: u32 = 4;
const PAUSE_SECS: f64 = 5.0;

fn is_retryable(status: u16) -> bool {
    matches!(status, 429 | 500 | 502 | 503 | 504)
}

/// 요청 시작 시각 사이에 최소 간격을 둔다.
pub struct Throttle {
    min: Duration,
    jitter: Duration,
    next_at: Mutex<Option<Instant>>,
}

impl Throttle {
    pub fn new(min: Duration, jitter: Duration) -> Self {
        Self { min, jitter, next_at: Mutex::new(None) }
    }

    pub fn default_site() -> Self {
        Self::new(Duration::from_millis(120), Duration::from_millis(80))
    }

    /// 다음 슬롯을 예약하고 그때까지 기다려야 할 시간을 돌려준다.
    fn reserve(&self) -> Duration {
        let now = Instant::now();
        let mut next = self.next_at.lock().unwrap();
        let start = match *next {
            Some(t) if t > now => t,
            _ => now,
        };
        let jitter = if self.jitter.is_zero() {
            Duration::ZERO
        } else {
            self.jitter.mul_f64(rand::rng().random::<f64>())
        };
        *next = Some(start + self.min + jitter);
        start - now
    }

    pub async fn wait(&self) {
        let d = self.reserve();
        if !d.is_zero() {
            tokio::time::sleep(d).await;
        }
    }
}

#[derive(Debug, Clone)]
pub struct Resp {
    pub status: u16,
    /// 리다이렉트를 따라간 최종 URL.
    pub url: String,
    pub body: Bytes,
}

impl Resp {
    pub fn text(&self) -> String {
        String::from_utf8_lossy(&self.body).into_owned()
    }

    pub fn json(&self) -> Result<serde_json::Value> {
        serde_json::from_slice(&self.body).map_err(|e| Error::Parse(e.to_string()))
    }
}

struct Session {
    user_agent: String,
    cookie: Option<String>,
}

struct Inner {
    http: reqwest::Client,
    referer: String,
    session: RwLock<Session>,
    throttle: Throttle,
    paused: watch::Sender<bool>,
    /// f64 비트. 백오프·일시정지 시간 배율(테스트용).
    scale: AtomicU64,
}

#[derive(Clone)]
pub struct Client {
    inner: Arc<Inner>,
}

enum Body<'a> {
    Get(&'a [(&'a str, String)]),
    PostForm(&'a [(&'a str, String)]),
}

impl Client {
    pub fn new(referer: &str, throttle: Throttle) -> Self {
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(20))
            .redirect(reqwest::redirect::Policy::limited(10))
            .pool_max_idle_per_host(8)
            .build()
            .expect("reqwest client");
        let (paused, _) = watch::channel(false);
        Self {
            inner: Arc::new(Inner {
                http,
                referer: referer.to_string(),
                session: RwLock::new(Session { user_agent: USER_AGENT.to_string(), cookie: None }),
                throttle,
                paused,
                scale: AtomicU64::new(1f64.to_bits()),
            }),
        }
    }

    /// 백오프 대기와 429 일시정지 시간에 곱할 배율. 테스트에서 줄이는 데 쓴다.
    pub fn with_backoff_scale(self, scale: f64) -> Self {
        self.inner.scale.store(scale.to_bits(), Ordering::Relaxed);
        self
    }

    fn scale(&self) -> f64 {
        f64::from_bits(self.inner.scale.load(Ordering::Relaxed))
    }

    /// UA 를 바꾸고 쿠키 헤더를 고정한다. 쿠키가 비어 있으면 헤더를 없앤다.
    pub fn set_session(&self, user_agent: &str, cookies: &[(String, String)]) {
        let mut s = self.inner.session.write().unwrap();
        if !user_agent.is_empty() {
            s.user_agent = user_agent.to_string();
        }
        s.cookie = if cookies.is_empty() {
            None
        } else {
            Some(
                cookies
                    .iter()
                    .map(|(k, v)| format!("{k}={v}"))
                    .collect::<Vec<_>>()
                    .join("; "),
            )
        };
    }

    // ---- 일시정지 ----
    pub fn pause(&self) {
        self.inner.paused.send_replace(true);
    }

    pub fn resume(&self) {
        self.inner.paused.send_replace(false);
    }

    pub fn is_paused(&self) -> bool {
        *self.inner.paused.borrow()
    }

    async fn await_resume(&self, cancel: &CancellationToken) -> Result<()> {
        let mut rx = self.inner.paused.subscribe();
        while *rx.borrow_and_update() {
            tokio::select! {
                _ = cancel.cancelled() => return Err(Error::Cancelled),
                _ = rx.changed() => {}
                _ = tokio::time::sleep(Duration::from_millis(250)) => {}
            }
        }
        Ok(())
    }

    /// 여러 워커가 동시에 429 를 맞아도 한 번만 멈추고, 5초 뒤 한 번만 푼다.
    fn backoff_pause(&self) {
        let started = self.inner.paused.send_if_modified(|p| {
            if *p {
                false
            } else {
                *p = true;
                true
            }
        });
        if started {
            let this = self.clone();
            let d = Duration::from_secs_f64(PAUSE_SECS * self.scale());
            tokio::spawn(async move {
                tokio::time::sleep(d).await;
                this.resume();
            });
        }
    }

    // ---- 요청 ----
    pub async fn get(&self, url: &str, cancel: &CancellationToken) -> Result<Resp> {
        self.get_with(url, &[], &[], cancel).await
    }

    pub async fn get_with(
        &self,
        url: &str,
        query: &[(&str, String)],
        extra: &[(&str, &str)],
        cancel: &CancellationToken,
    ) -> Result<Resp> {
        self.request(url, Body::Get(query), extra, cancel).await
    }

    pub async fn post_form(
        &self,
        url: &str,
        form: &[(&str, String)],
        extra: &[(&str, &str)],
        cancel: &CancellationToken,
    ) -> Result<Resp> {
        self.request(url, Body::PostForm(form), extra, cancel).await
    }

    fn headers(&self, extra: &[(&str, &str)]) -> HeaderMap {
        let mut h = HeaderMap::new();
        let s = self.inner.session.read().unwrap();
        let mut put = |k: HeaderName, v: &str| {
            if let Ok(v) = HeaderValue::from_str(v) {
                h.insert(k, v);
            }
        };
        put(reqwest::header::USER_AGENT, &s.user_agent);
        put(reqwest::header::REFERER, &self.inner.referer);
        put(reqwest::header::ACCEPT_LANGUAGE, ACCEPT_LANGUAGE);
        if let Some(c) = &s.cookie {
            put(reqwest::header::COOKIE, c);
        }
        for (k, v) in extra {
            if let Ok(k) = HeaderName::from_bytes(k.as_bytes()) {
                put(k, v);
            }
        }
        h
    }

    async fn send_once(
        &self,
        url: &str,
        body: &Body<'_>,
        extra: &[(&str, &str)],
    ) -> std::result::Result<Resp, reqwest::Error> {
        let headers = self.headers(extra);
        let rb = match body {
            Body::Get(q) => self.inner.http.get(url).query(q),
            Body::PostForm(f) => self.inner.http.post(url).form(f),
        };
        let resp = rb.headers(headers).send().await?;
        let status = resp.status().as_u16();
        let final_url = resp.url().to_string();
        let body = resp.bytes().await?;
        Ok(Resp { status, url: final_url, body })
    }

    async fn request(
        &self,
        url: &str,
        body: Body<'_>,
        extra: &[(&str, &str)],
        cancel: &CancellationToken,
    ) -> Result<Resp> {
        let mut last = Error::Network("request failed".into());
        for attempt in 0..=RETRIES {
            if cancel.is_cancelled() {
                return Err(Error::Cancelled);
            }
            self.await_resume(cancel).await?;
            let wait = self.inner.throttle.reserve();
            if !wait.is_zero() {
                tokio::select! {
                    _ = cancel.cancelled() => return Err(Error::Cancelled),
                    _ = tokio::time::sleep(wait) => {}
                }
            }
            let result = tokio::select! {
                _ = cancel.cancelled() => return Err(Error::Cancelled),
                r = self.send_once(url, &body, extra) => r,
            };
            match result {
                Ok(resp) if resp.status < 400 => return Ok(resp),
                Ok(resp) if is_retryable(resp.status) => {
                    if resp.status == 429 {
                        self.backoff_pause();
                    }
                    last = Error::RateLimited;
                }
                Ok(resp) => return Err(Error::Http(resp.status)),
                Err(e) => last = Error::Network(describe(&e)),
            }
            if attempt < RETRIES {
                let secs = (2f64.powi(attempt as i32) * 0.5).min(8.0)
                    + rand::rng().random_range(0.0..0.4);
                let d = Duration::from_secs_f64(secs * self.scale());
                tokio::select! {
                    _ = cancel.cancelled() => return Err(Error::Cancelled),
                    _ = tokio::time::sleep(d) => {}
                }
            }
        }
        Err(last)
    }
}

fn describe(e: &reqwest::Error) -> String {
    let kind = if e.is_timeout() {
        "timeout"
    } else if e.is_connect() {
        "connect"
    } else if e.is_redirect() {
        "redirect"
    } else if e.is_body() || e.is_decode() {
        "body"
    } else if e.is_request() {
        "request"
    } else {
        "error"
    };
    kind.to_string()
}
