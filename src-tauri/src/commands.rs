//! 프런트에서 부르는 커맨드.

use std::sync::atomic::Ordering;
use std::sync::Arc;

use dccon_core::config::Settings;
use dccon_core::dccon::{self, Query, TopKind};
use dccon_core::models::{Package, Site};
use dccon_core::updater::{self, LATEST_URL, RELEASES_PAGE};
use dccon_core::{arca, Error};
use serde_json::json;
use tauri::{AppHandle, Emitter, State};
use tauri_plugin_opener::OpenerExt;
use tokio_util::sync::CancellationToken;

use crate::dto::{CacheStats, CmdError, Job, ListPage, ReleaseInfo};
use crate::state::AppState;

type St<'a> = State<'a, Arc<AppState>>;

#[tauri::command(async)]
pub fn get_settings(state: St<'_>) -> Result<Settings, CmdError> {
    Ok(state.settings.read().unwrap().clone())
}

#[tauri::command(async)]
pub fn save_settings(state: St<'_>, mut settings: Settings) -> Result<(), CmdError> {
    let n = settings.concurrency;
    {
        // 저장은 쓰기 락을 잡은 채로 해서 동시 저장이 .tmp 를 두고 다투지 않게 한다.
        let mut current = state.settings.write().unwrap();
        // 앱이 관리하는 값은 프런트가 들고 있는 사본으로 덮지 않는다.
        settings.recent_packages = current.recent_packages.clone();
        settings.skipped_version = current.skipped_version.clone();
        // 저장 폴더가 없으면 만들어 둔다 (파이썬판 apply_to). 못 만들어도 저장은 한다.
        let _ = std::fs::create_dir_all(&settings.download_dir);
        settings.save(&state.paths.settings).map_err(Error::Io)?;
        *current = settings;
    }
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
    Ok(ListPage {
        items,
        page: 1,
        pages: 1,
        total: None,
    })
}

#[tauri::command]
pub async fn list_all(state: St<'_>, page: u32) -> Result<ListPage, CmdError> {
    let _permit = state.nav_permit().await?;
    let (items, pages, total) =
        dccon::fetch_all(&state.dccon, page, &CancellationToken::new()).await?;
    Ok(ListPage {
        items,
        page,
        pages,
        total: Some(total),
    })
}

#[tauri::command]
pub async fn list_arca(state: St<'_>, kind: String, page: u32) -> Result<ListPage, CmdError> {
    let _permit = state.nav_permit().await?;
    let (items, pages) =
        arca::fetch_list(&state.arca, &kind, page, &CancellationToken::new()).await?;
    Ok(ListPage {
        items,
        page,
        pages,
        total: None,
    })
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
    Ok(ListPage {
        items,
        page,
        pages,
        total: None,
    })
}

#[tauri::command]
pub async fn open_package(state: St<'_>, site: Site, id: u64) -> Result<Package, CmdError> {
    let _permit = state.nav_permit().await?;
    let package = state
        .load_package(site, id, &CancellationToken::new())
        .await?;
    {
        let mut s = state.settings.write().unwrap();
        s.remember(id);
        let _ = s.save(&state.paths.settings);
    }
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
pub fn enqueue(app: AppHandle, state: St<'_>, site: Site, jobs: Vec<Job>) -> Result<(), CmdError> {
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
    state.queue.cancel(&state);
    Ok(())
}

#[tauri::command]
pub fn open_folder(app: AppHandle, state: St<'_>) -> Result<(), CmdError> {
    let dir = state.settings.read().unwrap().download_dir.clone();
    std::fs::create_dir_all(&dir)
        .map_err(|e| CmdError::new("io", format!("폴더를 열 수 없습니다.\n{e}")))?;
    app.opener()
        .open_path(dir, None::<&str>)
        .map_err(|e| CmdError::new("io", format!("폴더를 열 수 없습니다.\n{e}")))
}

#[tauri::command(async)]
pub fn cache_stats(state: St<'_>) -> Result<CacheStats, CmdError> {
    let (files, bytes) = state.images.stats();
    Ok(CacheStats { files, bytes })
}

#[tauri::command(async)]
pub fn clear_cache(state: St<'_>) -> Result<(), CmdError> {
    state.images.clear(&state.paths.cache_meta);
    Ok(())
}

// ---------------------------------------------------------------- 업데이트
const VERSION: &str = env!("CARGO_PKG_VERSION");

/// 디버그 빌드에서만 `DCCON_UPDATE_URL` 로 조회 주소를 바꿀 수 있다 (실측용).
#[cfg(debug_assertions)]
fn debug_url_override() -> Option<String> {
    std::env::var("DCCON_UPDATE_URL")
        .ok()
        .filter(|u| !u.trim().is_empty())
}

#[cfg(not(debug_assertions))]
fn debug_url_override() -> Option<String> {
    None
}

fn latest_url() -> String {
    debug_url_override().unwrap_or_else(|| LATEST_URL.to_string())
}

/// 이 실행에서 exe 를 갈아끼울 수 있나: 윈도우 정식 빌드, 또는 주소를 바꿔 실측하는 디버그 빌드.
fn can_apply() -> bool {
    cfg!(windows) && (!cfg!(debug_assertions) || debug_url_override().is_some())
}

/// 새 버전을 사용자에게 알릴지. 자동 확인은 설정(끄기·건너뛴 버전)을 따르고, 수동은 새 버전이면 항상 알린다.
fn should_notify(settings: &Settings, manual: bool, current: &str, remote: &str) -> bool {
    if !updater::is_newer(remote, current) {
        return false;
    }
    manual || (settings.check_updates && settings.skipped_version != remote)
}

fn update_err(message: impl Into<String>) -> CmdError {
    CmdError::new("update", message)
}

#[tauri::command]
pub async fn check_update(state: St<'_>, manual: bool) -> Result<Option<ReleaseInfo>, CmdError> {
    let snapshot = state.settings.read().unwrap().clone();
    if !manual && !snapshot.check_updates {
        return Ok(None);
    }
    // 개발 실행은 주소를 바꾸지 않는 한 자동 확인을 하지 않는다.
    if !manual && cfg!(debug_assertions) && debug_url_override().is_none() {
        return Ok(None);
    }
    let http = updater::http_client(VERSION);
    let release = match updater::fetch_latest(&http, &latest_url()).await {
        Ok(r) => r,
        Err(e) if manual => return Err(e.into()),
        Err(_) => return Ok(None), // 시작할 때 확인은 오프라인이어도 조용히 넘어간다.
    };
    let Some(release) = release else {
        return Ok(None);
    };
    let version = release.version();
    if !should_notify(&snapshot, manual, VERSION, &version) {
        return Ok(None);
    }
    let asset = updater::pick_asset(&release).map(|a| a.name.clone());
    let info = ReleaseInfo {
        version,
        notes: release.notes.clone(),
        page_url: release.page_url.clone(),
        // 받을 exe 가 없는 릴리즈는 자동 업데이트 대신 릴리즈 페이지를 안내한다.
        can_apply: can_apply() && asset.is_some(),
        asset_name: asset,
    };
    let mut slot = state.update.lock().unwrap();
    slot.release = Some(release);
    slot.downloaded = None;
    Ok(Some(info))
}

#[tauri::command]
pub async fn download_update(app: AppHandle, state: St<'_>) -> Result<(), CmdError> {
    let (asset, tag, cancel) = {
        let mut slot = state.update.lock().unwrap();
        if slot.cancel.is_some() {
            return Err(update_err("이미 받는 중입니다."));
        }
        let release = slot
            .release
            .clone()
            .ok_or_else(|| update_err("받을 업데이트가 없습니다."))?;
        let asset = updater::pick_asset(&release)
            .cloned()
            .ok_or_else(|| update_err("이 실행 방식에 맞는 업데이트 파일을 찾지 못했습니다."))?;
        let tag = release.tag.clone();
        if tag.is_empty()
            || tag.contains("..")
            || !tag
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_'))
        {
            return Err(update_err("잘못된 릴리즈 이름입니다."));
        }
        let cancel = CancellationToken::new();
        slot.cancel = Some(cancel.clone());
        slot.downloaded = None;
        (asset, tag, cancel)
    };
    let http = updater::http_client(VERSION);
    // 조각마다 보내면 화면이 밀리므로 0.5% 단위로만 알린다.
    let last = std::sync::atomic::AtomicU64::new(u64::MAX);
    let progress = move |done: u64, total: u64| {
        let bucket = done
            .saturating_mul(200)
            .checked_div(total)
            .unwrap_or(done >> 20);
        if last.swap(bucket, Ordering::Relaxed) != bucket {
            let _ = app.emit("update-progress", json!({ "done": done, "total": total }));
        }
    };
    let result = updater::download(
        &http,
        &asset,
        &state.paths.update.join(&tag),
        &progress,
        &cancel,
    )
    .await;
    let mut slot = state.update.lock().unwrap();
    slot.cancel = None;
    let path = result?;
    slot.downloaded = Some(path);
    Ok(())
}

/// 받는 도중 창을 닫으면 부른다. 받는 중이 아니면 아무 일도 없다.
#[tauri::command]
pub fn cancel_update(state: St<'_>) -> Result<(), CmdError> {
    if let Some(token) = &state.update.lock().unwrap().cancel {
        token.cancel();
    }
    Ok(())
}

#[tauri::command(async)]
pub fn apply_update(app: AppHandle, state: St<'_>) -> Result<(), CmdError> {
    let downloaded = state
        .update
        .lock()
        .unwrap()
        .downloaded
        .clone()
        .ok_or_else(|| update_err("받아 둔 업데이트가 없습니다."))?;
    let current = std::env::current_exe()
        .map_err(|e| update_err(format!("실행 파일 위치를 알 수 없습니다. ({e})")))?;
    updater::apply::apply(&downloaded, &current)?;
    state.update.lock().unwrap().downloaded = None;

    let mut cmd = std::process::Command::new(&current);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: 이 프로세스가 끝나도 새 앱은 남는다.
        cmd.creation_flags(0x0000_0008 | 0x0000_0200);
    }
    if let Err(e) = cmd.spawn() {
        return Err(CmdError::new(
            "restart",
            format!("업데이트는 적용했지만 새 버전을 실행하지 못했습니다. 직접 다시 실행해 주세요.\n{e}"),
        ));
    }
    app.exit(0);
    Ok(())
}

/// 이 버전을 건너뛴다. 설정 저장과 같은 쓰기 락 아래에서 해서 서로 덮어쓰지 않는다.
#[tauri::command(async)]
pub fn skip_version(state: St<'_>, version: String) -> Result<(), CmdError> {
    let mut current = state.settings.write().unwrap();
    let mut next = current.clone();
    next.skipped_version = version;
    next.save(&state.paths.settings).map_err(Error::Io)?;
    *current = next;
    Ok(())
}

#[tauri::command]
pub fn open_release_page(app: AppHandle, state: St<'_>) -> Result<(), CmdError> {
    let url = state
        .update
        .lock()
        .unwrap()
        .release
        .as_ref()
        .map(|r| r.page_url.clone())
        .unwrap_or_else(|| RELEASES_PAGE.to_string());
    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|e| CmdError::new("io", format!("릴리즈 페이지를 열 수 없습니다.\n{e}")))
}

#[tauri::command]
pub fn take_last_error(state: St<'_>) -> Result<Option<String>, CmdError> {
    Ok(state.take_last_error())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn settings(check: bool, skipped: &str) -> Settings {
        Settings {
            check_updates: check,
            skipped_version: skipped.into(),
            ..Settings::default()
        }
    }

    #[test]
    fn startup_check_respects_skip() {
        // 자동: 꺼져 있으면 알리지 않는다.
        assert!(!should_notify(
            &settings(false, ""),
            false,
            "1.0.0",
            "1.1.0"
        ));
        // 자동: 건너뛴 버전이면 알리지 않는다.
        assert!(!should_notify(
            &settings(true, "1.1.0"),
            false,
            "1.0.0",
            "1.1.0"
        ));
        // 자동: 더 새 버전이 나오면 다시 알린다.
        assert!(should_notify(
            &settings(true, "1.1.0"),
            false,
            "1.0.0",
            "1.2.0"
        ));
        assert!(should_notify(&settings(true, ""), false, "1.0.0", "1.1.0"));
        // 새 버전이 아니면 알리지 않는다.
        assert!(!should_notify(&settings(true, ""), false, "1.1.0", "1.1.0"));
        assert!(!should_notify(&settings(true, ""), false, "1.1.0", "1.0.9"));
    }

    #[test]
    fn manual_check_ignores_settings_but_needs_newer() {
        assert!(should_notify(
            &settings(false, "1.1.0"),
            true,
            "1.0.0",
            "1.1.0"
        ));
        assert!(!should_notify(&settings(true, ""), true, "1.1.0", "1.1.0"));
    }
}
