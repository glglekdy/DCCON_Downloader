//! 앱 명령 ACL 시험: 등록한 명령 = `APP_COMMANDS` = `main` 창에 준 권한, 그리고 실제 권한 검사에서
//! 로그인 창(`arca-login`)은 앱 주소에서 와도 명령을 못 부르는지.

use tauri::ipc::{CallbackFn, InvokeBody};
use tauri::test::{get_ipc_response, mock_builder, MockRuntime, INVOKE_KEY};
use tauri::webview::InvokeRequest;
use tauri::{Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use std::sync::Arc;

use dccon_core::config::Paths;

use crate::app_commands::APP_COMMANDS;
use crate::state::AppState;

fn sorted(mut v: Vec<String>) -> Vec<String> {
    v.sort();
    v
}

/// main.rs 의 `generate_handler![...]` 에 적힌 명령 이름들.
fn registered() -> Vec<String> {
    let src = include_str!("main.rs");
    let start = src
        .find("generate_handler![")
        .expect("generate_handler! 가 있어야 한다");
    let rest = &src[start + "generate_handler![".len()..];
    let body = &rest[..rest.find(']').unwrap()];
    body.split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|s| s.rsplit("::").next().unwrap().to_string())
        .collect()
}

#[test]
fn every_registered_command_is_in_the_acl_list() {
    let listed: Vec<String> = APP_COMMANDS.iter().map(|s| s.to_string()).collect();
    assert_eq!(sorted(registered()), sorted(listed));
}

#[test]
fn capability_grants_app_commands_to_main_only() {
    let cap: serde_json::Value =
        serde_json::from_str(include_str!("../capabilities/default.json")).unwrap();
    assert_eq!(cap["windows"], serde_json::json!(["main"]));
    assert!(cap.get("webviews").is_none());
    assert!(
        cap.get("remote").is_none(),
        "원격 주소에 권한을 주지 않는다"
    );
    let perms: Vec<&str> = cap["permissions"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|p| p.as_str())
        .collect();
    for cmd in APP_COMMANDS {
        let id = format!("allow-{}", cmd.replace('_', "-"));
        assert!(perms.contains(&id.as_str()), "{id} 가 없다");
    }
    // capabilities 폴더에는 이 파일 하나뿐이어야 한다 (다른 창에 권한을 주는 파일이 없게).
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("capabilities");
    let files: Vec<_> = std::fs::read_dir(dir).unwrap().collect();
    assert_eq!(files.len(), 1);
}

fn invoke(
    w: &WebviewWindow<MockRuntime>,
    cmd: &str,
    origin: &str,
) -> Result<serde_json::Value, serde_json::Value> {
    get_ipc_response(
        w,
        InvokeRequest {
            cmd: cmd.into(),
            callback: CallbackFn(0),
            error: CallbackFn(1),
            url: origin.parse().unwrap(),
            body: InvokeBody::default(),
            headers: Default::default(),
            invoke_key: INVOKE_KEY.to_string(),
        },
    )
    .map(|b| b.deserialize::<serde_json::Value>().unwrap())
}

#[test]
fn app_commands_run_only_in_main_window() {
    // 이 앱의 실제 설정·권한(build.rs 가 만든 ACL 포함)과 실제 명령 두 개로 모의 앱을 만든다.
    let dir = tempfile::tempdir().unwrap();
    let state = Arc::new(AppState::new(Paths::new(dir.path().to_path_buf())));
    let app = mock_builder()
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            crate::commands::arca_status,
            crate::commands::get_settings
        ])
        .build(tauri::generate_context!())
        .expect("모의 앱");
    let main = app.get_webview_window("main").unwrap_or_else(|| {
        WebviewWindowBuilder::new(&app, "main", WebviewUrl::default())
            .build()
            .unwrap()
    });
    let login = WebviewWindowBuilder::new(&app, crate::login::WINDOW_LABEL, WebviewUrl::default())
        .build()
        .unwrap();
    let local = if cfg!(windows) {
        "http://tauri.localhost"
    } else {
        "tauri://localhost"
    };

    // 메인 창은 그대로 동작한다.
    assert_eq!(
        invoke(&main, "arca_status", local),
        Ok(serde_json::json!(false))
    );
    let settings =
        invoke(&main, "get_settings", local).expect("main 은 get_settings 를 부를 수 있다");
    assert!(settings.get("download_dir").is_some());
    // 로그인 창: 앱 주소인 프레임(iframe)에서 와도, 원격 페이지에서 와도 거부.
    assert!(invoke(&login, "arca_status", local).is_err());
    assert!(invoke(&login, "get_settings", local).is_err());
    assert!(invoke(&login, "arca_status", "https://arca.live").is_err());
    // 메인 창이라도 원격 주소에서 오면 거부.
    assert!(invoke(&main, "arca_status", "https://arca.live").is_err());
}
