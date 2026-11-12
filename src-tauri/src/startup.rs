//! 시작 처리: 파일 로그, panic 기록, 이전 흔적 정리, WebView2 확인.

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Duration;

use dccon_core::config::Paths;
use dccon_core::updater::apply;

const LOG_PREFIX: &str = "dccon-downloader.log";
const KEEP_LOGS: usize = 3;

/// `DATA_DIR/logs/` 에 하루 단위 로그 파일을 만들고 panic 도 같은 곳에 남긴다.
/// 로그를 못 만들어도 앱은 뜬다. 쿠키·세션 내용은 남기지 않는다.
pub fn init_logging(paths: &Paths) {
    let _ = std::fs::create_dir_all(&paths.logs);
    let appender = tracing_appender::rolling::Builder::new()
        .rotation(tracing_appender::rolling::Rotation::DAILY)
        .filename_prefix(LOG_PREFIX)
        .max_log_files(KEEP_LOGS)
        .build(&paths.logs);
    if let Ok(appender) = appender {
        let _ = tracing_subscriber::fmt()
            .with_writer(Mutex::new(appender))
            .with_ansi(false)
            .with_max_level(tracing::Level::INFO)
            .try_init();
    }
    let default = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let place = info
            .location()
            .map(|l| format!("{}:{}", l.file(), l.line()))
            .unwrap_or_default();
        let msg = info
            .payload()
            .downcast_ref::<&str>()
            .map(|s| s.to_string())
            .or_else(|| info.payload().downcast_ref::<String>().cloned())
            .unwrap_or_default();
        tracing::error!("panic at {place}: {msg}");
        default(info);
    }));
    tracing::info!("시작 {}", env!("CARGO_PKG_VERSION"));
}

/// 윈도우 릴리즈 실행에서만 이전 흔적을 치운다.
/// (남은 업데이트 실패 사유, 정리 뒤 exe 경로). exe 경로는 `AppState::exe_path` 에 넣는다.
pub fn cleanup(paths: &Paths) -> (Option<String>, Option<PathBuf>) {
    if !(cfg!(windows) && !cfg!(debug_assertions)) {
        return (None, None);
    }
    let Ok(exe) = std::env::current_exe() else {
        return (None, None);
    };
    let failure = apply::cleanup_after_start(&exe, paths);
    if failure.is_some() {
        tracing::info!("지난 업데이트 실패 사유를 읽었다");
    }
    // `.old` 는 지난 업데이트가 이 실행을 띄운 이름(= 이름을 바꾸기 전 경로) 옆에 있다.
    retry_remove_old(&exe);
    // 1.3.0 의 크롬 프로필은 클 수 있어 창을 늦추지 않게 뒤에서 지운다.
    let legacy = paths.clone();
    std::thread::spawn(move || apply::remove_legacy_arca_profile(&legacy));
    let (exe, removed) = apply::tidy_sibling_builds(
        &exe,
        env!("CARGO_PKG_VERSION"),
        &|p| apply::exe_file_version(p),
        &|p| apply::recycle(p),
    );
    if !removed.is_empty() {
        tracing::info!("이전 빌드 정리: {}", removed.join(", "));
    }
    (failure, Some(exe))
}

/// 옛 프로세스가 아직 끝나는 중이면 `<exe>.old` 가 안 지워진다. 백그라운드에서 몇 초 더 시도한다.
fn retry_remove_old(exe: &Path) {
    let mut name = exe.file_name().unwrap_or_default().to_os_string();
    name.push(".old");
    let old: PathBuf = exe.with_file_name(name);
    if !old.exists() {
        return;
    }
    std::thread::spawn(move || {
        for _ in 0..20 {
            if std::fs::remove_file(&old).is_ok() || !old.exists() {
                return;
            }
            std::thread::sleep(Duration::from_millis(250));
        }
        tracing::warn!("{} 을 지우지 못했다", old.display());
    });
}

/// WebView2 가 없으면 안내 상자를 띄우고 false.
#[cfg(windows)]
pub fn ensure_webview2() -> bool {
    if tauri::webview_version().is_ok() {
        return true;
    }
    tracing::error!("WebView2 런타임을 찾지 못했다");
    use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};
    let wide = |s: &str| s.encode_utf16().chain(Some(0)).collect::<Vec<u16>>();
    let text = wide(
        "WebView2 런타임이 필요합니다.\nhttps://developer.microsoft.com/microsoft-edge/webview2/ 에서 설치한 뒤 다시 실행해 주세요.",
    );
    let title = wide("디시콘 다운로더");
    unsafe {
        MessageBoxW(
            std::ptr::null_mut(),
            text.as_ptr(),
            title.as_ptr(),
            MB_OK | MB_ICONERROR,
        );
    }
    false
}

#[cfg(not(windows))]
pub fn ensure_webview2() -> bool {
    true
}
