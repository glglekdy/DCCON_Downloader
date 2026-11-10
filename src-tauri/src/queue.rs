//! 다운로드 큐: 한 번에 한 실행, 패키지는 동시 수만큼 병렬.

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use dccon_core::config::Settings;
use dccon_core::downloader::{download_package, DownloadOptions};
use dccon_core::models::Site;
use dccon_core::Error;
use serde::Serialize;
use tauri::{AppHandle, Emitter};
use tokio::sync::Semaphore;
use tokio_util::sync::CancellationToken;

use crate::dto::{CmdError, Job};
use crate::state::AppState;

#[derive(Default)]
pub struct Queue {
    /// 실행 중이면 그 실행의 취소 토큰.
    active: Mutex<Option<CancellationToken>>,
}

#[derive(Serialize, Clone)]
struct JobRef {
    id: u64,
    title: String,
}

#[derive(Serialize, Clone)]
struct Started {
    jobs: Vec<JobRef>,
}

#[derive(Serialize, Clone)]
struct Progress {
    id: u64,
    done: usize,
    total: usize,
    name: String,
}

#[derive(Serialize, Clone)]
struct PackageDone {
    id: u64,
    title: String,
    saved: u32,
    skipped: u32,
    failed: Vec<(String, String)>,
}

#[derive(Serialize, Clone)]
struct QueueError {
    id: u64,
    message: String,
}

#[derive(Serialize, Clone)]
struct Finished {
    saved: u32,
    skipped: u32,
    failed: u32,
}

pub fn dest_dir(settings: &Settings, site: Site) -> PathBuf {
    let base = PathBuf::from(&settings.download_dir);
    match site {
        Site::Dccon => base,
        Site::Arca => base.join("arcacon"),
    }
}

pub fn prepare_dest(settings: &Settings, site: Site) -> Result<PathBuf, CmdError> {
    let dest = dest_dir(settings, site);
    std::fs::create_dir_all(&dest)
        .map_err(|e| CmdError::new("io", format!("폴더를 만들 수 없습니다.\n{e}")))?;
    Ok(dest)
}

impl Queue {
    pub fn start(
        &self,
        app: AppHandle,
        state: Arc<AppState>,
        site: Site,
        jobs: Vec<Job>,
    ) -> Result<(), CmdError> {
        let mut active = self.active.lock().unwrap();
        if active.is_some() {
            return Err(CmdError::new("busy", "이미 다운로드 중입니다."));
        }
        let settings = state.settings.read().unwrap().clone();
        let dest = prepare_dest(&settings, site)?;
        let cancel = CancellationToken::new();
        *active = Some(cancel.clone());
        drop(active);

        // 이전에 일시정지해 둔 채로 시작해도 멈춰 있지 않게 한다.
        state.dccon.resume();
        state.arca.resume();

        tauri::async_runtime::spawn(run(app, state, site, jobs, settings, dest, cancel));
        Ok(())
    }

    /// 사용자 일시정지. 두 사이트 클라이언트 모두.
    pub fn pause(&self, state: &AppState, on: bool) {
        for c in [&state.dccon, &state.arca] {
            if on {
                c.pause();
            } else {
                c.resume();
            }
        }
    }

    pub fn cancel(&self) {
        if let Some(t) = self.active.lock().unwrap().as_ref() {
            t.cancel();
        }
    }

    fn finish(&self) {
        *self.active.lock().unwrap() = None;
    }
}

async fn run(
    app: AppHandle,
    state: Arc<AppState>,
    site: Site,
    jobs: Vec<Job>,
    settings: Settings,
    dest: PathBuf,
    cancel: CancellationToken,
) {
    let _ = app.emit(
        "queue-started",
        Started {
            jobs: jobs.iter().map(|j| JobRef { id: j.id, title: j.title.clone() }).collect(),
        },
    );
    let sem = Arc::new(Semaphore::new(settings.concurrency.max(1) as usize));
    let opts = Arc::new(DownloadOptions {
        save_main_image: settings.save_main_image,
        write_meta: settings.write_meta_json,
    });
    let dest = Arc::new(dest);

    let mut handles = Vec::new();
    for job in jobs {
        let (app, state, sem, cancel) = (app.clone(), state.clone(), sem.clone(), cancel.clone());
        let (dest, opts) = (dest.clone(), opts.clone());
        handles.push(tauri::async_runtime::spawn(async move {
            run_job(&app, &state, site, job, &sem, &dest, &opts, &cancel).await
        }));
    }

    let mut total = Finished { saved: 0, skipped: 0, failed: 0 };
    for h in handles {
        if let Ok(Some((saved, skipped, failed))) = h.await {
            total.saved += saved;
            total.skipped += skipped;
            total.failed += failed;
        }
    }
    state.queue.finish();
    let _ = app.emit("queue-finished", total);
}

#[allow(clippy::too_many_arguments)]
async fn run_job(
    app: &AppHandle,
    state: &AppState,
    site: Site,
    job: Job,
    sem: &Semaphore,
    dest: &Path,
    opts: &DownloadOptions,
    cancel: &CancellationToken,
) -> Option<(u32, u32, u32)> {
    let outcome = async {
        let _permit = tokio::select! {
            p = sem.acquire() => p.map_err(|_| Error::Cancelled)?,
            _ = cancel.cancelled() => return Err(Error::Cancelled),
        };
        if cancel.is_cancelled() {
            return Err(Error::Cancelled);
        }
        let package = state.load_package(site, job.id, cancel).await?;
        let id = job.id;
        let progress = |done: usize, total: usize, name: &str| {
            let _ = app.emit("queue-progress", Progress { id, done, total, name: name.to_string() });
        };
        download_package(
            state.client(site),
            &state.images,
            &package,
            dest,
            job.sorts.as_deref(),
            opts,
            &progress,
            cancel,
        )
        .await
    }
    .await;

    match outcome {
        Ok(r) => {
            let failed = r.failed.len() as u32;
            let _ = app.emit(
                "queue-package-done",
                PackageDone {
                    id: job.id,
                    title: job.title,
                    saved: r.saved,
                    skipped: r.skipped,
                    failed: r.failed,
                },
            );
            Some((r.saved, r.skipped, failed))
        }
        Err(e) => {
            let _ = app.emit("queue-error", QueueError { id: job.id, message: e.user_message() });
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn enqueue_fails_when_dest_cannot_be_created() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("plain");
        std::fs::write(&file, b"x").unwrap();
        let settings = Settings {
            download_dir: file.join("sub").to_string_lossy().into_owned(),
            ..Settings::default()
        };
        let err = prepare_dest(&settings, Site::Dccon).unwrap_err();
        assert_eq!(err.kind, "io");
        assert!(err.message.starts_with("폴더를 만들 수 없습니다."), "{}", err.message);
    }

    #[test]
    fn dest_dir_for_arca() {
        let settings = Settings { download_dir: "/x/dl".into(), ..Settings::default() };
        assert_eq!(dest_dir(&settings, Site::Arca), PathBuf::from("/x/dl").join("arcacon"));
        assert_eq!(dest_dir(&settings, Site::Dccon), PathBuf::from("/x/dl"));
    }
}
