#![cfg_attr(not(feature = "console"), windows_subsystem = "windows")]

mod commands;
mod dto;
mod imgproto;
mod queue;
mod state;

use std::sync::Arc;

use dccon_core::config::Paths;

fn main() {
    let state = Arc::new(state::AppState::new(Paths::system()));
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(state)
        .register_asynchronous_uri_scheme_protocol("img", imgproto::handle)
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
        ])
        .run(tauri::generate_context!())
        .expect("Tauri 실행 중 오류");
}
