//! 앱 경로와 사용자 설정.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

const APP_NAME: &str = "DcconDownloader";

fn home_dir() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .filter(|v| !v.is_empty())
        .or_else(|| std::env::var_os("HOME").filter(|v| !v.is_empty()))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn non_empty_env(name: &str) -> Option<PathBuf> {
    std::env::var_os(name).filter(|v| !v.is_empty()).map(PathBuf::from)
}

/// 앱 데이터 폴더. 파이썬 1.3.0 의 `_data_dir` 과 같은 규칙.
pub fn data_dir() -> PathBuf {
    if cfg!(target_os = "macos") {
        return home_dir().join("Library").join("Application Support").join(APP_NAME);
    }
    if let Some(base) = non_empty_env("LOCALAPPDATA").or_else(|| non_empty_env("XDG_DATA_HOME")) {
        return base.join(APP_NAME);
    }
    home_dir().join(format!(".{}", APP_NAME.to_lowercase()))
}

#[derive(Clone, Debug, PartialEq)]
pub struct Paths {
    pub data: PathBuf,
    pub cache_img: PathBuf,
    pub cache_meta: PathBuf,
    pub settings: PathBuf,
    pub arca_session: PathBuf,
    pub webview: PathBuf,
    pub logs: PathBuf,
    pub update: PathBuf,
    pub code: PathBuf,
}

impl Paths {
    pub fn new(data: PathBuf) -> Self {
        let cache = data.join("cache");
        Self {
            cache_img: cache.join("img"),
            cache_meta: cache.join("meta"),
            settings: data.join("settings.json"),
            arca_session: data.join("arca_session.json"),
            webview: data.join("webview"),
            logs: data.join("logs"),
            update: data.join("update"),
            code: data.join("code"),
            data,
        }
    }

    pub fn system() -> Self {
        Self::new(data_dir())
    }
}

fn default_download_dir() -> String {
    home_dir().join("Downloads").join("dccon").to_string_lossy().into_owned()
}

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Settings {
    pub download_dir: String,
    pub concurrency: u32,
    pub save_main_image: bool,
    pub write_meta_json: bool,
    pub reduce_motion: bool,
    pub theme: String,
    pub animate_gifs: bool,
    pub check_updates: bool,
    pub skipped_version: String,
    pub recent_packages: Vec<u64>,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            download_dir: default_download_dir(),
            concurrency: 3,
            save_main_image: true,
            write_meta_json: true,
            reduce_motion: false,
            theme: "system".into(),
            animate_gifs: true,
            check_updates: true,
            skipped_version: String::new(),
            recent_packages: Vec::new(),
        }
    }
}

impl Settings {
    /// 읽기나 해석에 실패하면 기본값.
    pub fn load(path: &Path) -> Self {
        std::fs::read_to_string(path)
            .ok()
            .and_then(|text| serde_json::from_str(&text).ok())
            .unwrap_or_default()
    }

    pub fn save(&self, path: &Path) -> std::io::Result<()> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let text = serde_json::to_string_pretty(self).map_err(std::io::Error::other)?;
        let mut tmp = path.as_os_str().to_owned();
        tmp.push(".tmp");
        let tmp = PathBuf::from(tmp);
        std::fs::write(&tmp, text)?;
        std::fs::rename(&tmp, path)
    }

    pub fn remember(&mut self, id: u64) {
        self.recent_packages.retain(|&i| i != id);
        self.recent_packages.insert(0, id);
        self.recent_packages.truncate(24);
    }
}
