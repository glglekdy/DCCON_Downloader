//! 프런트에서 부르는 커맨드.

use std::sync::atomic::Ordering;
use std::sync::Arc;

use dccon_core::config::Settings;
use dccon_core::dccon::{self, Query, TopKind};
use dccon_core::models::{Package, Site};
use dccon_core::{arca, Error};
use tauri::{AppHandle, State};
use tauri_plugin_opener::OpenerExt;
use tokio_util::sync::CancellationToken;

use crate::dto::{CacheStats, CmdError, Job, ListPage};
use crate::state::AppState;

type St<'a> = State<'a, Arc<AppState>>;

#[tauri::command]
pub fn get_settings(state: St<'_>) -> Result<Settings, CmdError> {
    Ok(state.settings.read().unwrap().clone())
}

#[tauri::command]
pub fn save_settings(state: St<'_>, settings: Settings) -> Result<(), CmdError> {
    let n = settings.concurrency;
    settings.save(&state.paths.settings).map_err(Error::Io)?;
    *state.settings.write().unwrap() = settings;
    state.apply_concurrency(n);
    Ok(())
}

#[tauri::command]
pub fn begin_view(state: St<'_>) -> Result<u64, CmdError> {
    Ok(state.view_gen.fetch_add(1, Ordering::SeqCst) + 1)
}

#[tauri::command]
pub async fn list_top(state: St<'_>, kind: TopKind) -> Result<ListPage, CmdError> {
    let _permit = state.nav_permit().await?;
    let items = dccon::fetch_top(&state.dccon, kind, &CancellationToken::new()).await?;
    Ok(ListPage { items, page: 1, pages: 1, total: None })
}

#[tauri::command]
pub async fn list_all(state: St<'_>, page: u32) -> Result<ListPage, CmdError> {
    let _permit = state.nav_permit().await?;
    let (items, pages, total) =
        dccon::fetch_all(&state.dccon, page, &CancellationToken::new()).await?;
    Ok(ListPage { items, page, pages, total: Some(total) })
}

#[tauri::command]
pub async fn list_arca(state: St<'_>, kind: String, page: u32) -> Result<ListPage, CmdError> {
    let _permit = state.nav_permit().await?;
    let (items, pages) =
        arca::fetch_list(&state.arca, &kind, page, &CancellationToken::new()).await?;
    Ok(ListPage { items, page, pages, total: None })
}

#[tauri::command]
pub async fn search(
    state: St<'_>,
    site: Site,
    word: String,
    search_type: String,
    page: u32,
) -> Result<ListPage, CmdError> {
    let _permit = state.nav_permit().await?;
    let cancel = CancellationToken::new();
    let (items, pages) = match site {
        Site::Dccon => dccon::search(&state.dccon, &word, &search_type, page, &cancel).await?,
        Site::Arca => arca::search(&state.arca, &word, &search_type, page, &cancel).await?,
    };
    Ok(ListPage { items, page, pages, total: None })
}

#[tauri::command]
pub async fn open_package(state: St<'_>, site: Site, id: u64) -> Result<Package, CmdError> {
    let _permit = state.nav_permit().await?;
    let package = state.load_package(site, id, &CancellationToken::new()).await?;
    let snapshot = {
        let mut s = state.settings.write().unwrap();
        s.remember(id);
        s.clone()
    };
    let _ = snapshot.save(&state.paths.settings);
    Ok(package)
}

#[tauri::command]
pub fn parse_input(site: Site, text: String) -> Result<Query, CmdError> {
    Ok(match site {
        Site::Dccon => dccon::parse_query(&text),
        Site::Arca => match arca::parse_ids(&text) {
            Some(ids) => Query::Ids(ids),
            None => Query::Search(text.trim().to_string()),
        },
    })
}

#[tauri::command]
pub fn enqueue(
    app: AppHandle,
    state: St<'_>,
    site: Site,
    jobs: Vec<Job>,
) -> Result<(), CmdError> {
    let shared = state.inner().clone();
    state.queue.start(app, shared, site, jobs)
}

#[tauri::command]
pub fn pause_queue(state: St<'_>, paused: bool) -> Result<(), CmdError> {
    state.queue.pause(&state, paused);
    Ok(())
}

#[tauri::command]
pub fn cancel_queue(state: St<'_>) -> Result<(), CmdError> {
    state.queue.cancel();
    Ok(())
}

#[tauri::command]
pub fn open_folder(app: AppHandle, state: St<'_>) -> Result<(), CmdError> {
    let dir = state.settings.read().unwrap().download_dir.clone();
    std::fs::create_dir_all(&dir).map_err(|e| CmdError::new("io", e.to_string()))?;
    app.opener()
        .open_path(dir, None::<&str>)
        .map_err(|e| CmdError::new("io", e.to_string()))
}

#[tauri::command]
pub fn cache_stats(state: St<'_>) -> Result<CacheStats, CmdError> {
    let (files, bytes) = state.images.stats();
    Ok(CacheStats { files, bytes })
}

#[tauri::command]
pub fn clear_cache(state: St<'_>) -> Result<(), CmdError> {
    state.images.clear(&state.paths.cache_meta);
    Ok(())
}
