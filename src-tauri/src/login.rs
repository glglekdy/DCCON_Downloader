//! 아카콘 로그인 (설계 §6): 앱 안의 로그인 창.
//!
//! `https://arca.live/u/login?goto=/e/` 를 별도 창으로 열고, 창이 `/e/` 에 닿으면(로그인 성공)
//! 그 창의 쿠키를 꺼내 `arca_session.json` 에 저장한다. 사용자가 창을 먼저 닫으면 그때의
//! 쿠키로 시도한다. 꺼낸 세션으로 `GET /e/` 를 불러 `/u/login` 으로 가지 않아야 성공이다.
//!
//! 격리:
//! - 로그인 창은 어떤 권한(capability)에도 들어가지 않는다. 앱 명령에도 ACL 이 걸려 있어
//!   (`build.rs` 의 앱 매니페스트, `capabilities/default.json` 은 `main` 창만) 이 창 안에서는
//!   주소가 앱 자신(`http://tauri.localhost`)인 프레임이라도 명령을 부를 수 없다.
//! - `on_navigation` 은 **최상위 프레임에만** 걸린다 (wry 는 NavigationStarting 만 본다).
//!   iframe 은 막지 못하므로, 이 창에서는 `tauri` 프로토콜이 앱 화면을 내주지 않고
//!   (`on_web_resource_request` 가 403) `img` 프로토콜도 `main` 이 아니면 403 이다.
//! - 페이지에 스크립트를 넣지 않는다. 새 창(`window.open`, `target=_blank`)은 만들지 않고
//!   웹 주소면 이 창에서 연다.
//!
//! 데이터 폴더는 따로 정하지 않아 메인 창과 같은 기본 WebView2 폴더를 함께 쓴다
//! (한 프로세스에서 데이터 폴더 하나에 환경 하나). 그래서 아카라이브 쿠키가 남아
//! 다음 로그인 때 다시 쓰인다. 세션이 만료되면(`login_required`) 세션 파일과 클라이언트
//! 쿠키만 버리고 웹뷰 쿠키는 둔다 (`forget_session`). 웹뷰 쿠키까지 지우는 건 명시적
//! 로그아웃(`logout`)뿐이다.
//!
//! WebView2 쿠키 함수는 메인 스레드로 일을 보내고 결과를 기다리며 막힌다. 메인 스레드
//! (이벤트 처리 중)에서 부르면 멈추고, tokio 작업 스레드에서 부르면 그 스레드를 붙잡으므로
//! `spawn_blocking` 스레드에서 부른다.

use std::borrow::Cow;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use dccon_core::arca::{self, ArcaSession, SessionCookie, ARCA_BASE, LOGIN_URL};
use dccon_core::http::{Client, Throttle, USER_AGENT};
use dccon_core::Error;
use serde::Serialize;
use tauri::http::StatusCode;
use tauri::webview::{Cookie, NewWindowResponse, PageLoadEvent, PageLoadPayload};
use tauri::{
    AppHandle, Emitter, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent,
};
use tokio_util::sync::CancellationToken;
use url::Url;

use crate::dto::CmdError;
use crate::state::AppState;

pub const WINDOW_LABEL: &str = "arca-login";
const MAIN_LABEL: &str = "main";
const TITLE: &str = "아카콘 로그인";
pub const NOT_LOGGED_IN: &str = "로그인되지 않았습니다. 로그인을 마친 뒤 창을 닫아 주세요.";
pub const EVENT: &str = "login-finished";

/// `login-finished` 이벤트 내용. 로그인 시도마다 한 번만 보낸다.
#[derive(Debug, Clone, Serialize)]
pub struct LoginFinished {
    /// `arca_login` 이 돌려준 시도 번호. 프런트는 다른 번호의 결과를 무시한다.
    pub id: u64,
    pub ok: bool,
    pub message: String,
}

fn is_arca_domain(domain: &str) -> bool {
    let d = domain
        .strip_prefix('.')
        .unwrap_or(domain)
        .to_ascii_lowercase();
    d == "arca.live" || d.ends_with(".arca.live")
}

/// 웹뷰에서 꺼낸 쿠키 `(이름, 값, 도메인, 경로)` 중 arca.live 것만 남겨 세션을 만든다.
pub fn to_session(ua: &str, cookies: &[(&str, &str, &str, &str)]) -> ArcaSession {
    ArcaSession {
        user_agent: ua.to_string(),
        cookies: cookies
            .iter()
            .filter(|(_, _, domain, _)| is_arca_domain(domain))
            .map(|&(name, value, domain, path)| SessionCookie {
                name: name.to_string(),
                value: value.to_string(),
                domain: domain.to_string(),
                path: if path.is_empty() { "/" } else { path }.to_string(),
            })
            .collect(),
    }
}

/// 로그인 창이 아카콘 첫 화면(`arca.live/e/`)에 닿았나.
pub fn is_login_done(url: &Url) -> bool {
    url.host_str() == Some("arca.live") && url.path() == "/e/"
}

/// WebView2 런타임 버전으로 만든 Edge UA. Cloudflare 확인은 UA 에 묶이므로 창과 세션이 같은 값을 쓴다.
pub fn edge_user_agent(version: &str) -> String {
    let major = version.split('.').next().unwrap_or(version);
    format!(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) \
         Chrome/{major}.0.0.0 Safari/537.36 Edg/{version}"
    )
}

#[cfg(target_os = "macos")]
const SAFARI_USER_AGENT: &str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) \
AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15";

/// 로그인 창에 줄 UA. 창에 직접 지정하고 같은 값을 세션에 저장한다.
fn login_user_agent() -> String {
    #[cfg(windows)]
    {
        match tauri::webview_version() {
            Ok(v) if !v.trim().is_empty() => edge_user_agent(v.trim()),
            _ => USER_AGENT.to_string(),
        }
    }
    #[cfg(target_os = "macos")]
    {
        SAFARI_USER_AGENT.to_string()
    }
    #[cfg(not(any(windows, target_os = "macos")))]
    {
        USER_AGENT.to_string()
    }
}

/// 로그인 창(최상위 프레임)은 웹 사이트만 다닌다. 앱 자체 주소(`*.localhost`, `tauri:` 등)로는 못 간다.
fn allow_navigation(url: &Url) -> bool {
    match url.scheme() {
        "https" | "http" => !url
            .host_str()
            .is_some_and(|h| h == "localhost" || h.ends_with(".localhost")),
        "about" => true,
        _ => false,
    }
}

/// 한 번의 로그인 시도 (창 하나).
struct Attempt {
    id: u64,
    ua: String,
    /// 끝났나 (`login-finished` 를 보냈거나 보내는 중).
    done: AtomicBool,
    /// 쿠키 확인은 한 번에 하나만.
    gate: tokio::sync::Mutex<()>,
}

impl Attempt {
    /// 이 시도를 끝낸 것으로 표시한다. 처음 부른 쪽만 true.
    fn claim(&self) -> bool {
        !self.done.swap(true, Ordering::SeqCst)
    }
}

static NEXT_ID: AtomicU64 = AtomicU64::new(1);
/// 가장 최근에 띄운 로그인 창의 시도.
static CURRENT: Mutex<Option<Arc<Attempt>>> = Mutex::new(None);

#[derive(Clone, Copy, PartialEq, Eq)]
enum Trigger {
    /// 창이 `/e/` 에 닿았다. 확인에 실패하면 창을 그대로 둔다.
    Page,
    /// 사용자가 창을 닫았다. 결과가 어떻든 끝낸다.
    Closed,
}

/// 저장해 둔 세션(1.3.0 이 남긴 것 포함)을 아카콘 클라이언트에 붙인다.
pub fn apply_saved(state: &AppState) {
    if let Some(s) = ArcaSession::load(&state.paths.arca_session) {
        state.arca.set_session(&s.user_agent, &s.cookie_pairs());
        state.arca_logged_in.store(true, Ordering::SeqCst);
    }
}

/// 아카콘 클라이언트에 세션이 붙어 있나 (파이썬판 `self.arca_session is not None`).
/// 저장에 실패한 로그인도 이번 실행 동안은 로그인된 것으로 본다.
pub fn has_session(state: &AppState) -> bool {
    state.arca_logged_in.load(Ordering::SeqCst)
}

/// 세션 파일과 클라이언트 쿠키만 버린다 (세션 만료 때). 웹뷰의 아카라이브 쿠키는 남겨
/// 다시 로그인할 때 로그인 창이 바로 `/e/` 로 넘어갈 수 있게 한다.
pub fn forget_session(state: &AppState) {
    ArcaSession::forget(&state.paths.arca_session);
    state.arca.set_session(USER_AGENT, &[]);
    state.arca_logged_in.store(false, Ordering::SeqCst);
}

/// 로그인 창을 띄우고 바로 시도 번호를 돌려준다. 이미 떠 있으면 앞으로 가져온다.
pub async fn open(app: &AppHandle, state: Arc<AppState>) -> Result<u64, CmdError> {
    // 취소 직후라 지난 창이 없어지는 중이면 잠깐 기다린다.
    for _ in 0..30 {
        if app.get_webview_window(WINDOW_LABEL).is_none() {
            break;
        }
        let current = CURRENT.lock().unwrap().clone();
        if let Some(a) = current.filter(|a| !a.done.load(Ordering::SeqCst)) {
            if let Some(w) = app.get_webview_window(WINDOW_LABEL) {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
            return Ok(a.id);
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    if app.get_webview_window(WINDOW_LABEL).is_some() {
        return Err(CmdError::new(
            "login",
            "이전 로그인 창이 아직 닫히는 중입니다. 잠시 후 다시 시도해 주세요.",
        ));
    }
    let ua = login_user_agent();
    let attempt = Arc::new(Attempt {
        id: NEXT_ID.fetch_add(1, Ordering::SeqCst),
        ua: ua.clone(),
        done: AtomicBool::new(false),
        gate: tokio::sync::Mutex::new(()),
    });
    let url = Url::parse(LOGIN_URL).expect("LOGIN_URL 은 올바른 주소");

    let on_load = {
        let (app, attempt, state) = (app.clone(), attempt.clone(), state.clone());
        move |_w: WebviewWindow, p: PageLoadPayload<'_>| {
            if p.event() == PageLoadEvent::Finished && is_login_done(p.url()) {
                let (app, attempt, state) = (app.clone(), attempt.clone(), state.clone());
                tauri::async_runtime::spawn(async move {
                    try_finish(app, attempt, state, Trigger::Page).await
                });
            }
        }
    };
    let on_new_window = {
        let app = app.clone();
        move |url: Url, _features| {
            // 새 창은 만들지 않는다. 웹 주소면 로그인 창에서 연다 (이벤트 처리 밖에서).
            if allow_navigation(&url) {
                let app = app.clone();
                tauri::async_runtime::spawn(async move {
                    if let Some(w) = app.get_webview_window(WINDOW_LABEL) {
                        let _ = w.navigate(url);
                    }
                });
            }
            NewWindowResponse::Deny
        }
    };

    let window = WebviewWindowBuilder::new(app, WINDOW_LABEL, WebviewUrl::External(url))
        .title(TITLE)
        .inner_size(480.0, 720.0)
        .center()
        .user_agent(&ua)
        .on_navigation(allow_navigation)
        .on_new_window(on_new_window)
        // `tauri` 프로토콜(앱 화면) 응답에만 불린다. arca.live 같은 원격 요청은 오지 않는다.
        .on_web_resource_request(|_req, resp| {
            resp.headers_mut().clear();
            *resp.status_mut() = StatusCode::FORBIDDEN;
            *resp.body_mut() = Cow::Borrowed(&[]);
        })
        .on_page_load(on_load)
        .build()
        .map_err(|e| CmdError::new("login", format!("로그인 창을 열지 못했습니다.\n{e}")))?;
    *CURRENT.lock().unwrap() = Some(attempt.clone());
    let id = attempt.id;

    let app2 = app.clone();
    window.on_window_event(move |event| match event {
        WindowEvent::CloseRequested { api, .. } => {
            if attempt.done.load(Ordering::SeqCst) {
                return;
            }
            // 닫기 전에 그 시점의 쿠키로 시도한다. 끝나면 이쪽에서 창을 없앤다.
            api.prevent_close();
            let (app, attempt, state) = (app2.clone(), attempt.clone(), state.clone());
            tauri::async_runtime::spawn(async move {
                try_finish(app, attempt, state, Trigger::Closed).await
            });
        }
        WindowEvent::Destroyed => {
            // 확인 없이 사라졌다 (취소, 앱 종료). 창은 이미 없다.
            finish(&app2, &attempt, false, NOT_LOGGED_IN.to_string(), false);
        }
        _ => {}
    });
    Ok(id)
}

/// 로그인 창을 닫는다 (앱에서 취소). 결과는 `login-finished {ok:false}` 로 간다.
pub fn cancel(app: &AppHandle) {
    if let Some(w) = app.get_webview_window(WINDOW_LABEL) {
        let _ = w.destroy();
    }
}

/// 메인 창이 사라지면 로그인 창도 닫아 앱이 끝나게 한다.
pub fn on_main_destroyed(app: &AppHandle) {
    cancel(app);
}

/// 결과를 보낸다. `close` 면 창을 없앤다. 먼저 `claim` 한 쪽만 부른다.
fn deliver(app: &AppHandle, attempt: &Attempt, ok: bool, message: String, close: bool) {
    if close {
        if let Some(w) = app.get_webview_window(WINDOW_LABEL) {
            let _ = w.destroy();
        }
    }
    let payload = LoginFinished {
        id: attempt.id,
        ok,
        message,
    };
    let _ = app.emit_to(MAIN_LABEL, EVENT, payload);
}

/// 결과를 한 번만 보낸다.
fn finish(app: &AppHandle, attempt: &Attempt, ok: bool, message: String, close: bool) {
    if attempt.claim() {
        deliver(app, attempt, ok, message, close);
    }
}

/// 웹뷰의 arca.live 쿠키를 읽는다 (막히는 호출이라 blocking 스레드에서).
async fn arca_cookies(window: WebviewWindow) -> Result<Vec<Cookie<'static>>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let url = Url::parse(ARCA_BASE).map_err(|e| e.to_string())?;
        window.cookies_for_url(url).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

async fn try_finish(app: AppHandle, attempt: Arc<Attempt>, state: Arc<AppState>, by: Trigger) {
    let _gate = attempt.gate.lock().await;
    if attempt.done.load(Ordering::SeqCst) {
        return;
    }
    let Some(window) = app.get_webview_window(WINDOW_LABEL) else {
        return; // Destroyed 쪽에서 끝냈다.
    };
    if by == Trigger::Closed {
        // 확인하는 몇 초 동안 닫기 단추가 먹통처럼 보이지 않게 먼저 숨긴다.
        let _ = window.hide();
    }
    let cookies = match arca_cookies(window).await {
        Ok(c) => c,
        Err(e) => {
            if by == Trigger::Closed {
                let message = format!("쿠키를 읽지 못했습니다.\n{e}");
                finish(&app, &attempt, false, message, true);
            }
            return;
        }
    };
    let tuples: Vec<(&str, &str, &str, &str)> = cookies
        .iter()
        .map(|c| {
            (
                c.name(),
                c.value(),
                c.domain().unwrap_or(""),
                c.path().unwrap_or("/"),
            )
        })
        .collect();
    let session = to_session(&attempt.ua, &tuples);
    match verify(&session).await {
        Ok(()) => {
            // 확인하는 동안 취소됐으면(창이 사라졌으면) 저장도 적용도 하지 않는다.
            if !attempt.claim() {
                return;
            }
            state
                .arca
                .set_session(&session.user_agent, &session.cookie_pairs());
            state.arca_logged_in.store(true, Ordering::SeqCst);
            let message = match session.save(&state.paths.arca_session) {
                Ok(()) => String::new(),
                Err(e) => format!("로그인은 되었지만 세션을 저장하지 못했습니다.\n{e}"),
            };
            deliver(&app, &attempt, true, message, true);
        }
        Err(message) => {
            // 창이 /e/ 에 닿았는데도 확인이 안 되면 창을 그대로 둔다. 닫으면 다시 시도한다.
            if by == Trigger::Closed {
                finish(&app, &attempt, false, message, true);
            }
        }
    }
}

/// 꺼낸 세션으로 `GET /e/` 를 불러 로그인 화면으로 가지 않는지 본다.
async fn verify(session: &ArcaSession) -> Result<(), String> {
    if session.cookies.is_empty() {
        return Err(NOT_LOGGED_IN.into());
    }
    let client = Client::new("https://arca.live/e/", Throttle::default_site());
    client.set_session(&session.user_agent, &session.cookie_pairs());
    match client
        .get(&format!("{ARCA_BASE}/e/"), &CancellationToken::new())
        .await
    {
        Ok(resp) => arca::check_login(&resp).map_err(|_| NOT_LOGGED_IN.to_string()),
        Err(Error::Http(_) | Error::LoginRequired) => Err(NOT_LOGGED_IN.into()),
        Err(e) => Err(format!(
            "로그인을 확인하지 못했습니다.\n{}",
            e.user_message()
        )),
    }
}

fn is_arca_cookie(c: &Cookie<'_>) -> bool {
    c.domain().is_some_and(is_arca_domain)
}

/// 명시적 로그아웃: 세션을 버리고 웹뷰의 아카라이브 쿠키도 지운다.
/// 메인 창과 로그인 창은 같은 WebView2 데이터 폴더를 쓰므로 메인 창에서 지워도 된다.
pub async fn logout(app: &AppHandle, state: &AppState) {
    forget_session(state);
    let Some(main) = app.get_webview_window(MAIN_LABEL) else {
        return;
    };
    let _ = tauri::async_runtime::spawn_blocking(move || {
        // 경로·하위 도메인 쿠키까지 보려고 프로필의 쿠키 전부에서 고른다.
        if let Ok(all) = main.cookies() {
            for c in all.into_iter().filter(is_arca_cookie) {
                let _ = main.delete_cookie(c);
            }
        }
        // cookie 크레이트는 도메인 앞의 점을 떼므로 `.arca.live` 쿠키(cf_clearance 등)는 위에서
        // 지워지지 않을 수 있다. 남아 있으면 웹뷰 데이터를 통째로 지운다. 앱 화면은
        // localStorage 등을 쓰지 않으므로 잃는 건 HTTP 캐시 정도다.
        let left = main
            .cookies()
            .map(|v| v.iter().any(is_arca_cookie))
            .unwrap_or(true);
        if left {
            let _ = main.clear_all_browsing_data();
        }
    })
    .await;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn to_session_keeps_only_arca_cookies() {
        let cookies = [
            ("arca_session", "abc", "arca.live", "/"),
            ("cf_clearance", "cf", ".arca.live", "/"),
            ("sub", "s", "www.arca.live", "/e/"),
            ("other", "x", "example.com", "/"),
            ("fake", "y", "notarca.live", "/"),
            ("nodomain", "z", "", "/"),
        ];
        let s = to_session("UA/1", &cookies);
        assert_eq!(s.user_agent, "UA/1");
        let names: Vec<&str> = s.cookies.iter().map(|c| c.name.as_str()).collect();
        assert_eq!(names, ["arca_session", "cf_clearance", "sub"]);
        assert_eq!(s.cookies[1].domain, ".arca.live");
        assert_eq!(s.cookies[2].path, "/e/");
        assert_eq!(s.cookie_pairs()[0], ("arca_session".into(), "abc".into()));
    }

    #[test]
    fn to_session_defaults_empty_path_to_root() {
        let s = to_session("UA", &[("a", "1", "ARCA.live", "")]);
        assert_eq!(s.cookies.len(), 1);
        assert_eq!(s.cookies[0].path, "/");
    }

    #[test]
    fn login_done_only_on_arca_emoticon_home() {
        let done = |u: &str| is_login_done(&url::Url::parse(u).unwrap());
        assert!(done("https://arca.live/e/"));
        assert!(done("https://arca.live/e/?p=1"));
        assert!(!done("https://arca.live/u/login?goto=/e/"));
        assert!(!done("https://arca.live/e/12345"));
        assert!(!done("https://evil.example/e/"));
        assert!(!done("https://arca.live.evil.example/e/"));
    }

    #[test]
    fn edge_user_agent_uses_runtime_version() {
        assert_eq!(
            edge_user_agent("131.0.2903.70"),
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) \
             Chrome/131.0.0.0 Safari/537.36 Edg/131.0.2903.70"
        );
    }

    #[test]
    fn login_window_cannot_reach_app_origins() {
        let ok = |u: &str| allow_navigation(&url::Url::parse(u).unwrap());
        assert!(ok("https://arca.live/u/login?goto=/e/"));
        assert!(ok("https://challenges.cloudflare.com/x"));
        assert!(ok("about:blank"));
        assert!(!ok("http://tauri.localhost/index.html"));
        assert!(!ok("https://tauri.localhost/"));
        assert!(!ok("tauri://localhost/"));
        assert!(ok("http://arca.live/e/"));
        assert!(!ok("http://localhost:5173/"));
        assert!(!ok("file:///c:/x"));
    }

    #[test]
    fn forget_session_drops_file_and_client_but_not_flag_only() {
        let dir = tempfile::tempdir().unwrap();
        let state = AppState::new(dccon_core::config::Paths::new(dir.path().to_path_buf()));
        let session = to_session("UA", &[("arca_session", "v", "arca.live", "/")]);
        session.save(&state.paths.arca_session).unwrap();
        apply_saved(&state);
        assert!(has_session(&state));
        forget_session(&state);
        assert!(!has_session(&state));
        assert!(!state.paths.arca_session.exists());
    }

    #[test]
    fn has_session_follows_memory_not_file() {
        // 저장에 실패해도 이번 실행 동안은 로그인 상태다 (파이썬판과 같다).
        let dir = tempfile::tempdir().unwrap();
        let state = AppState::new(dccon_core::config::Paths::new(dir.path().to_path_buf()));
        assert!(!has_session(&state));
        state.arca_logged_in.store(true, Ordering::SeqCst);
        assert!(has_session(&state));
        // 깨진 파일은 세션으로 치지 않는다.
        std::fs::write(&state.paths.arca_session, "{").unwrap();
        let fresh = AppState::new(dccon_core::config::Paths::new(dir.path().to_path_buf()));
        apply_saved(&fresh);
        assert!(!has_session(&fresh));
    }

    #[test]
    fn attempt_claims_once() {
        let a = Attempt {
            id: 1,
            ua: String::new(),
            done: AtomicBool::new(false),
            gate: tokio::sync::Mutex::new(()),
        };
        assert!(a.claim());
        assert!(!a.claim());
    }
}
