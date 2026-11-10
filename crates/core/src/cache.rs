//! 디스크 캐시. 파이썬 1.3.0 의 `dccon/cache.py` 와 같은 키·경로를 쓴다.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

use percent_encoding::percent_decode_str;
use regex::Regex;
use sha1::{Digest, Sha1};
use tokio_util::sync::CancellationToken;

use crate::error::Result;
use crate::http::Client;

/// `no=` 값만 뽑아 키로 쓴다. 없으면 쿼리를 뗀 URL 을 쓴다.
pub fn cache_key(url: &str) -> String {
    static NO_PARAM: OnceLock<Regex> = OnceLock::new();
    let re = NO_PARAM.get_or_init(|| Regex::new(r"[?&]no=([^&]+)").unwrap());
    let token = match re.captures(url) {
        Some(c) => c.get(1).unwrap().as_str(),
        None => url.split('?').next().unwrap_or(url),
    };
    let decoded = percent_decode_str(token).decode_utf8_lossy();
    hex::encode(Sha1::digest(decoded.as_bytes()))
}

type LockMap = Mutex<HashMap<String, Arc<tokio::sync::Mutex<()>>>>;

#[derive(Clone)]
pub struct ImageCache {
    root: PathBuf,
    locks: Arc<LockMap>,
}

impl ImageCache {
    pub fn new(root: PathBuf) -> Self {
        Self { root, locks: Arc::new(Mutex::new(HashMap::new())) }
    }

    fn path_for_key(&self, key: &str, ext: &str) -> PathBuf {
        let ext = ext.to_lowercase();
        let ext = ext.trim_start_matches('.');
        self.root.join(&key[..2]).join(format!("{key}.{ext}"))
    }

    pub fn path_for(&self, url: &str, ext: &str) -> PathBuf {
        self.path_for_key(&cache_key(url), ext)
    }

    fn lock_for(&self, key: &str) -> Arc<tokio::sync::Mutex<()>> {
        let mut map = self.locks.lock().unwrap();
        map.entry(key.to_string()).or_default().clone()
    }

    pub fn peek(&self, url: &str, ext: &str) -> Option<Vec<u8>> {
        std::fs::read(self.path_for(url, ext)).ok()
    }

    /// 캐시에 있으면 그대로, 없으면 받아서 저장한 뒤 돌려준다.
    pub async fn get(
        &self,
        client: &Client,
        url: &str,
        ext: &str,
        cancel: &CancellationToken,
    ) -> Result<Vec<u8>> {
        let key = cache_key(url);
        let path = self.path_for_key(&key, ext);
        if let Ok(data) = tokio::fs::read(&path).await {
            return Ok(data);
        }
        let lock = self.lock_for(&key);
        let _guard = lock.lock().await;
        // 락을 기다리는 사이 다른 태스크가 받아놨을 수 있다.
        if let Ok(data) = tokio::fs::read(&path).await {
            return Ok(data);
        }
        let resp = client.get(url, cancel).await?;
        let data = resp.body.to_vec();
        if let Some(parent) = path.parent() {
            tokio::fs::create_dir_all(parent).await?;
        }
        let mut part = path.clone().into_os_string();
        part.push(".part");
        let part = PathBuf::from(part);
        tokio::fs::write(&part, &data).await?;
        tokio::fs::rename(&part, &path).await?;
        Ok(data)
    }

    /// (파일 수, 총 바이트).
    pub fn stats(&self) -> (u64, u64) {
        fn walk(dir: &Path, count: &mut u64, total: &mut u64) {
            let Ok(rd) = std::fs::read_dir(dir) else { return };
            for entry in rd.flatten() {
                let p = entry.path();
                if p.is_dir() {
                    walk(&p, count, total);
                } else if p.is_file() {
                    *count += 1;
                    if let Ok(m) = p.metadata() {
                        *total += m.len();
                    }
                }
            }
        }
        let (mut count, mut total) = (0, 0);
        walk(&self.root, &mut count, &mut total);
        (count, total)
    }

    pub fn clear(&self, meta_root: &Path) {
        for target in [self.root.as_path(), meta_root] {
            let _ = std::fs::remove_dir_all(target);
        }
    }
}

/// package_detail 응답을 그대로 보관한다.
pub struct MetaCache {
    root: PathBuf,
}

impl MetaCache {
    pub fn new(root: PathBuf) -> Self {
        Self { root }
    }

    fn path(&self, id: u64) -> PathBuf {
        self.root.join(format!("{id}.json"))
    }

    pub fn load(&self, id: u64) -> Option<serde_json::Value> {
        let text = std::fs::read_to_string(self.path(id)).ok()?;
        serde_json::from_str(&text).ok()
    }

    pub fn store(&self, id: u64, v: &serde_json::Value) {
        let _ = std::fs::create_dir_all(&self.root);
        if let Ok(s) = serde_json::to_string(v) {
            let _ = std::fs::write(self.path(id), s);
        }
    }
}
