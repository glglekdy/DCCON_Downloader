#![cfg_attr(not(feature = "console"), windows_subsystem = "windows")]

#[cfg(test)]
mod acl_tests;
#[cfg(test)]
mod app_commands;
mod commands;
mod dto;
mod imgproto;
mod login;
mod queue;
mod state;

use std::sync::Arc;

use dccon_core::config::Paths;
use tauri::Manager;

fn main() {
    let state = Arc::new(state::AppState::new(Paths::system()));
    // 1.3.0 이 남긴 것을 포함해 저장해 둔 아카라이브 세션을 화면이 뜨기 전에 붙인다.
    login::apply_saved(&state);
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(state)
        .register_asynchronous_uri_scheme_protocol("img", imgproto::handle)
        .on_window_event(|window, event| {
            // 메인 창이 사라지면 로그인 창도 닫아 앱이 끝나게 한다.
            if window.label() == "main" && matches!(event, tauri::WindowEvent::Destroyed) {
                login::on_main_destroyed(window.app_handle());
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_settings,
            commands::save_settings,
            commands::begin_view,
            commands::list_top,
            commands::list_all,
            commands::list_arca,
            commands::search,
            commands::open_package,
            commands::parse_input,
            commands::enqueue,
            commands::pause_queue,
            commands::cancel_queue,
            commands::open_folder,
            commands::cache_stats,
            commands::clear_cache,
            commands::check_update,
            commands::download_update,
            commands::cancel_update,
            commands::apply_update,
            commands::skip_version,
            commands::open_release_page,
            commands::take_last_error,
            commands::arca_status,
            commands::arca_login,
            commands::arca_login_cancel,
            commands::arca_logout,
            commands::arca_forget_session,
        ])
        .run(tauri::generate_context!())
        .expect("Tauri 실행 중 오류");
}
