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

fn busy() -> CmdError {
    CmdError::new("busy", "이미 다운로드 중입니다.")
}

fn resume_clients(state: &AppState) {
    state.dccon.resume();
    state.arca.resume();
}

impl Queue {
    pub fn start(
        &self,
        app: AppHandle,
        state: Arc<AppState>,
        site: Site,
        jobs: Vec<Job>,
    ) -> Result<(), CmdError> {
        if self.active.lock().unwrap().is_some() {
            return Err(busy());
        }
        let settings = state.settings.read().unwrap().clone();
        let dest = prepare_dest(&settings, site)?;
        let cancel = CancellationToken::new();
        {
            // 확인과 설정만 락 안에서 한다.
            let mut active = self.active.lock().unwrap();
            if active.is_some() {
                return Err(busy());
            }
            *active = Some(cancel.clone());
        }

        // 이전에 일시정지해 둔 채로 시작해도 멈춰 있지 않게 한다.
        resume_clients(&state);

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

    /// 실행을 취소한다. 일시정지로 멈춰 있던 클라이언트도 풀어 둔다.
    pub fn cancel(&self, state: &AppState) {
        if let Some(t) = self.active.lock().unwrap().as_ref() {
            t.cancel();
        }
        resume_clients(state);
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
            jobs: jobs
                .iter()
                .map(|j| JobRef {
                    id: j.id,
                    title: j.title.clone(),
                })
                .collect(),
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
        // 순서대로 시작하도록 자리를 먼저 잡는다. 취소되면 기다리지 않는다.
        let permit = tokio::select! {
            p = sem.clone().acquire_owned() => p.ok(),
            _ = cancel.cancelled() => None,
        };
        let Some(permit) = permit else {
            let _ = app.emit(
                "queue-error",
                QueueError {
                    id: job.id,
                    message: Error::Cancelled.user_message(),
                },
            );
            continue;
        };
        let id = job.id;
        let (app, state, cancel) = (app.clone(), state.clone(), cancel.clone());
        let (dest, opts) = (dest.clone(), opts.clone());
        handles.push((
            id,
            tauri::async_runtime::spawn(async move {
                let r = run_job(&app, &state, site, job, &dest, &opts, &cancel).await;
                drop(permit);
                r
            }),
        ));
    }

    let mut total = Finished {
        saved: 0,
        skipped: 0,
        failed: 0,
    };
    for (id, h) in handles {
        match h.await {
            Ok(Some((saved, skipped, failed))) => {
                total.saved += saved;
                total.skipped += skipped;
                total.failed += failed;
            }
            Ok(None) => {}
            Err(_) => {
                let _ = app.emit(
                    "queue-error",
                    QueueError {
                        id,
                        message: "알 수 없는 오류로 중단됨".into(),
                    },
                );
            }
        }
    }
    // 일시정지한 채 끝나도 이후 탐색이 멈추지 않게 한다.
    resume_clients(&state);
    state.queue.finish();
    let _ = app.emit("queue-finished", total);
}

async fn run_job(
    app: &AppHandle,
    state: &AppState,
    site: Site,
    job: Job,
    dest: &Path,
    opts: &DownloadOptions,
    cancel: &CancellationToken,
) -> Option<(u32, u32, u32)> {
    let outcome = async {
        if cancel.is_cancelled() {
            return Err(Error::Cancelled);
        }
        let package = state.load_package(site, job.id, cancel).await?;
        let id = job.id;
        let progress = |done: usize, total: usize, name: &str| {
            let _ = app.emit(
                "queue-progress",
                Progress {
                    id,
                    done,
                    total,
                    name: name.to_string(),
                },
            );
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
            let _ = app.emit(
                "queue-error",
                QueueError {
                    id: job.id,
                    message: e.user_message(),
                },
            );
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
        assert!(
            err.message.starts_with("폴더를 만들 수 없습니다."),
            "{}",
            err.message
        );
    }

    #[test]
    fn cancel_resumes_paused_clients() {
        let dir = tempfile::tempdir().unwrap();
        let state = AppState::new(dccon_core::config::Paths::new(dir.path().to_path_buf()));
        *state.queue.active.lock().unwrap() = Some(CancellationToken::new());
        state.queue.pause(&state, true);
        assert!(state.dccon.is_paused() && state.arca.is_paused());
        state.queue.cancel(&state);
        assert!(!state.dccon.is_paused() && !state.arca.is_paused());
    }

    #[test]
    fn dest_dir_for_arca() {
        let settings = Settings {
            download_dir: "/x/dl".into(),
            ..Settings::default()
        };
        assert_eq!(
            dest_dir(&settings, Site::Arca),
            PathBuf::from("/x/dl").join("arcacon")
        );
        assert_eq!(dest_dir(&settings, Site::Dccon), PathBuf::from("/x/dl"));
    }
}
