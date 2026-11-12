//! 선택한 디시콘을 저장 폴더에 쓴다. 파이썬 `dccon/downloader.py` 와 같은 동작.

use std::path::{Path, PathBuf};

use serde::Serialize;
use tokio_util::sync::CancellationToken;

use crate::cache::ImageCache;
use crate::error::{Error, Result};
use crate::http::Client;
use crate::models::Package;
use crate::naming::{item_filename, package_dirname, pad_width};

pub struct DownloadOptions {
    pub save_main_image: bool,
    pub write_meta: bool,
}

#[derive(Serialize, Debug)]
pub struct DownloadResult {
    pub package_idx: u64,
    pub package_title: String,
    pub dest: PathBuf,
    pub saved: u32,
    pub skipped: u32,
    pub failed: Vec<(String, String)>,
}

/// 대표 이미지는 ext 를 안 알려줘서 매직 바이트로 판별한다.
pub fn sniff_ext(data: &[u8], default: &str) -> String {
    if data.starts_with(b"\x89PNG\r\n\x1a\n") {
        "png"
    } else if data.starts_with(b"GIF") {
        "gif"
    } else if data.starts_with(b"\xff\xd8\xff") {
        "jpg"
    } else if data.len() >= 12 && &data[..4] == b"RIFF" && &data[8..12] == b"WEBP" {
        "webp"
    } else {
        default
    }
    .to_string()
}

async fn is_file(p: &Path) -> bool {
    tokio::fs::metadata(p).await.map(|m| m.is_file()).unwrap_or(false)
}

/// `.part` 에 쓰고 rename 해서, 최종 파일은 항상 온전하다.
async fn write_atomic(target: &Path, data: &[u8]) -> std::io::Result<()> {
    let mut tmp = target.as_os_str().to_owned();
    tmp.push(".part");
    let tmp = PathBuf::from(tmp);
    tokio::fs::write(&tmp, data).await?;
    tokio::fs::rename(&tmp, target).await
}

#[allow(clippy::too_many_arguments)]
pub async fn download_package(
    client: &Client,
    cache: &ImageCache,
    package: &Package,
    dest_root: &Path,
    only_sorts: Option<&[u32]>,
    opts: &DownloadOptions,
    progress: &(dyn Fn(usize, usize, &str) + Send + Sync),
    cancel: &CancellationToken,
) -> Result<DownloadResult> {
    let items: Vec<_> = package
        .items
        .iter()
        .filter(|i| only_sorts.is_none_or(|w| w.contains(&i.sort)))
        .collect();

    let dest = dest_root.join(package_dirname(package.idx, &package.title));
    tokio::fs::create_dir_all(&dest).await.map_err(Error::Io)?;
    let mut result = DownloadResult {
        package_idx: package.idx,
        package_title: package.title.clone(),
        dest: dest.clone(),
        saved: 0,
        skipped: 0,
        failed: Vec::new(),
    };

    let width = pad_width(
        package.items.iter().map(|i| i.sort as usize).max().unwrap_or(items.len()),
    );
    let with_main = opts.save_main_image && !package.main_img_path.is_empty();
    let total = items.len() + usize::from(with_main);
    let mut done = 0;

    if with_main {
        let step: Result<bool> = async {
            let data = cache.get(client, &package.main_url(), "jpg", cancel).await?;
            let target = dest.join(format!("_main.{}", sniff_ext(&data, "jpg")));
            if is_file(&target).await {
                return Ok(false);
            }
            tokio::fs::write(&target, &data).await?;
            Ok(true)
        }
        .await;
        match step {
            Ok(true) => result.saved += 1,
            Ok(false) => result.skipped += 1,
            Err(Error::Cancelled) => return Err(Error::Cancelled),
            Err(e) => result.failed.push(("_main".into(), e.user_message())),
        }
        done += 1;
        progress(done, total, "_main");
    }

    for item in items {
        if cancel.is_cancelled() {
            return Err(Error::Cancelled);
        }
        let name = item_filename(item.sort, &item.title, &item.ext, width);
        let target = dest.join(&name);
        let step: Result<bool> = async {
            if is_file(&target).await {
                return Ok(false);
            }
            let data = cache.get(client, &item.url(), &item.ext, cancel).await?;
            write_atomic(&target, &data).await?;
            Ok(true)
        }
        .await;
        match step {
            Ok(true) => result.saved += 1,
            Ok(false) => result.skipped += 1,
            Err(Error::Cancelled) => return Err(Error::Cancelled),
            Err(e) => result.failed.push((name.clone(), e.user_message())),
        }
        done += 1;
        progress(done, total, &name);
    }

    if opts.write_meta {
        let _ = write_meta(&dest, package, width);
    }
    Ok(result)
}

#[derive(Serialize)]
struct MetaItem {
    sort: u32,
    title: String,
    ext: String,
    file: String,
}

#[derive(Serialize)]
struct Meta<'a> {
    package_idx: u64,
    title: &'a str,
    description: &'a str,
    seller: &'a str,
    reg_date: &'a str,
    tags: &'a [String],
    items: Vec<MetaItem>,
}

/// `_meta.json` 을 쓴다. 항목은 선택과 무관하게 패키지 전체.
pub fn write_meta(dest: &Path, package: &Package, width: usize) -> std::io::Result<()> {
    let meta = Meta {
        package_idx: package.idx,
        title: &package.title,
        description: &package.description,
        seller: &package.seller,
        reg_date: &package.reg_date,
        tags: &package.tags,
        items: package
            .items
            .iter()
            .map(|i| MetaItem {
                sort: i.sort,
                title: i.title.clone(),
                ext: i.ext.clone(),
                file: item_filename(i.sort, &i.title, &i.ext, width),
            })
            .collect(),
    };
    let text = serde_json::to_string_pretty(&meta).map_err(std::io::Error::other)?;
    std::fs::write(dest.join("_meta.json"), text)
}
