//! 앱 전역 상태.

use std::sync::atomic::AtomicU64;
use std::sync::{Arc, RwLock};

use dccon_core::cache::{ImageCache, MetaCache};
use dccon_core::config::{Paths, Settings};
use dccon_core::http::{Client, Throttle};
use dccon_core::models::{Package, Site};
use dccon_core::{arca, dccon, Error};
use tokio::sync::{OwnedSemaphorePermit, Semaphore};
use tokio_util::sync::CancellationToken;

use crate::queue::Queue;

pub struct AppState {
    pub paths: Paths,
    pub settings: RwLock<Settings>,
    pub dccon: Client,
    pub arca: Client,
    pub images: ImageCache,
    pub meta: MetaCache,
    pub nav: RwLock<Arc<Semaphore>>,
    pub thumb: RwLock<Arc<Semaphore>>,
    pub view_gen: AtomicU64,
    pub queue: Queue,
}

fn thumb_permits(n: u32) -> usize {
    n.max(2) as usize
}

impl AppState {
    pub fn new(paths: Paths) -> AppState {
        let settings = Settings::load(&paths.settings);
        let thumb = Arc::new(Semaphore::new(thumb_permits(settings.concurrency)));
        AppState {
            settings: RwLock::new(settings),
            dccon: Client::new("https://dccon.dcinside.com/", Throttle::default_site()),
            arca: Client::new("https://arca.live/e/", Throttle::default_site()),
            images: ImageCache::new(paths.cache_img.clone()),
            meta: MetaCache::new(paths.cache_meta.clone()),
            nav: RwLock::new(Arc::new(Semaphore::new(2))),
            thumb: RwLock::new(thumb),
            view_gen: AtomicU64::new(0),
            queue: Queue::default(),
            paths,
        }
    }

    pub fn client(&self, site: Site) -> &Client {
        match site {
            Site::Dccon => &self.dccon,
            Site::Arca => &self.arca,
        }
    }

    /// 썸네일 세마포어를 새로 만들어 교체한다. 다운로드는 실행 시작 때 읽는다.
    pub fn apply_concurrency(&self, n: u32) {
        *self.thumb.write().unwrap() = Arc::new(Semaphore::new(thumb_permits(n)));
    }

    pub async fn nav_permit(&self) -> Result<OwnedSemaphorePermit, Error> {
        let sem = self.nav.read().unwrap().clone();
        sem.acquire_owned().await.map_err(|_| Error::Cancelled)
    }

    /// 패키지 상세를 읽는다. 디시콘은 메타 캐시 우선, 아카콘은 캐시하지 않는다.
    pub async fn load_package(
        &self,
        site: Site,
        id: u64,
        cancel: &CancellationToken,
    ) -> Result<Package, Error> {
        match site {
            Site::Dccon => {
                if let Some(pkg) = self.meta.load(id).and_then(|v| Package::from_api(&v)) {
                    return Ok(pkg);
                }
                let (pkg, payload) = dccon::fetch_package(&self.dccon, id, cancel).await?;
                self.meta.store(id, &payload);
                Ok(pkg)
            }
            Site::Arca => arca::fetch_package(&self.arca, id, cancel).await,
        }
    }
}
