//! 받은 exe 로 실행 중인 exe 바꾸기, 시작 뒤 정리, 릴리즈 이름 정리.
//!
//! 윈도우는 실행 중인 exe 의 이름 바꾸기는 허용하고 삭제·덮어쓰기는 막는다.
//! 그래서 현재 exe 를 `.old` 로 옮기고 새 exe 를 그 자리에 둔 뒤, 다음 실행에서 `.old` 를 지운다.

use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};

use super::parse_version;
use crate::{Error, Result};

pub const MIGRATION_MARKER: &str = "MIGRATED.txt";
pub const LOCAL_NAME: &str = "디시콘 다운로더.exe";
const ERROR_LOG: &str = "last_error.log";
const ARCA_PROFILE_DIR: &str = "arca_browser";

fn old_path(current: &Path) -> PathBuf {
    let mut name: OsString = current.file_name().unwrap_or_default().to_os_string();
    name.push(".old");
    current.with_file_name(name)
}

/// `current` 를 `.old` 로 옮기고 `new_exe` 를 `current` 자리에 둔다.
pub fn apply(new_exe: &Path, current_exe: &Path) -> Result<()> {
    let old = old_path(current_exe);
    if old.exists() {
        fs::remove_file(&old).map_err(|e| {
            Error::Update(format!("이 폴더에 쓸 수 없어 업데이트를 적용하지 못했습니다. ({e})"))
        })?;
    }
    fs::rename(current_exe, &old).map_err(|e| {
        Error::Update(format!("이 폴더에 쓸 수 없어 업데이트를 적용하지 못했습니다. ({e})"))
    })?;
    let moved = fs::rename(new_exe, current_exe).or_else(|rename_err| {
        // 다른 볼륨 등으로 rename 이 안 되면 복사한 뒤 지운다.
        fs::copy(new_exe, current_exe)
            .map(|_| {
                let _ = fs::remove_file(new_exe);
            })
            .map_err(|copy_err| format!("{rename_err}; 복사도 실패: {copy_err}"))
    });
    if let Err(e) = moved {
        let _ = fs::remove_file(current_exe);
        let mut msg = format!("업데이트를 적용하지 못했습니다. ({e})");
        if fs::rename(&old, current_exe).is_err() {
            let name = old.file_name().unwrap_or_default().to_string_lossy();
            msg.push_str(&format!(" 이전 파일은 {name} 에 있습니다."));
        }
        return Err(Error::Update(msg));
    }
    Ok(())
}

/// 시작 직후 이전 흔적을 치운다. 실패해도 넘어간다. `last_error.log` 내용이 있으면 돌려준다.
pub fn cleanup_after_start(exe: &Path, paths: &crate::config::Paths) -> Option<String> {
    let _ = fs::remove_file(old_path(exe));

    if let Some(dir) = exe.parent() {
        let internal = dir.join("_internal");
        if let Ok(rd) = fs::read_dir(&internal) {
            let entries: Vec<_> = rd.flatten().collect();
            if entries.len() == 1
                && entries[0].file_name() == MIGRATION_MARKER
                && entries[0].path().is_file()
            {
                let _ = fs::remove_dir_all(&internal);
            }
        }
    }

    let _ = fs::remove_dir_all(&paths.code);
    // 1.3.0 의 크롬 로그인 프로필(ARCA_PROFILE_DIR). 2.0 은 쓰지 않는다.
    let _ = fs::remove_dir_all(paths.data.join(ARCA_PROFILE_DIR));

    let mut log = None;
    if let Ok(rd) = fs::read_dir(&paths.update) {
        for entry in rd.flatten() {
            let path = entry.path();
            if entry.file_name() == ERROR_LOG {
                if let Ok(bytes) = fs::read(&path) {
                    let text = String::from_utf8_lossy(&bytes);
                    let text = text.trim_start_matches('\u{feff}').trim();
                    if !text.is_empty() {
                        log = Some(text.to_string());
                    }
                }
                let _ = fs::remove_file(&path);
                continue;
            }
            if path.is_dir() {
                let _ = fs::remove_dir_all(&path);
            } else {
                let _ = fs::remove_file(&path);
            }
        }
    }
    log
}

fn named_version(name: &str) -> Option<String> {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let re = RE.get_or_init(|| {
        regex::Regex::new(r"(?i)^dccon-downloader-(\d+\.\d+\.\d+)(?:-win64)?\.exe$").unwrap()
    });
    re.captures(name).map(|c| c[1].to_string())
}

/// 받은 이름(`dccon-downloader-X.Y.Z.exe`)이면 `디시콘 다운로더.exe` 로 바꾸고,
/// 같은 폴더의 더 낮은 버전을 치운다. (지금 exe 경로, 치운 파일 이름들)
pub fn tidy_sibling_builds(
    exe: &Path,
    version: &str,
    exe_version: &dyn Fn(&Path) -> Option<String>,
    recycle: &dyn Fn(&Path) -> bool,
) -> (PathBuf, Vec<String>) {
    let here = parse_version(version);
    let mut removed = Vec::new();
    let mut exe = exe.to_path_buf();
    let Some(folder) = exe.parent().map(Path::to_path_buf) else {
        return (exe, removed);
    };

    let running_name = exe.file_name().and_then(|n| n.to_str()).unwrap_or("");
    if named_version(running_name).is_some() {
        let target = folder.join(LOCAL_NAME);
        if target.exists() {
            if let Some(other) = exe_version(&target) {
                if parse_version(&other) <= here && recycle(&target) {
                    removed.push(LOCAL_NAME.to_string());
                }
            }
        }
        if matches!(target.try_exists(), Ok(false)) && rename_no_replace(&exe, &target).is_ok() {
            exe = target;
        }
    }

    let mut names: Vec<String> = fs::read_dir(&folder)
        .map(|rd| rd.flatten().filter_map(|e| e.file_name().into_string().ok()).collect())
        .unwrap_or_default();
    names.sort();
    let running = exe.file_name().and_then(|n| n.to_str()).unwrap_or("").to_lowercase();
    for name in names {
        let Some(found) = named_version(&name) else { continue };
        if name.to_lowercase() == running {
            continue;
        }
        if parse_version(&found) < here && recycle(&folder.join(&name)) {
            removed.push(name);
        }
    }
    (exe, removed)
}

/// 이미 있는 파일은 덮어쓰지 않고 이름을 바꾼다. (윈도우의 `fs::rename` 은 덮어쓴다.)
#[cfg(windows)]
fn rename_no_replace(from: &Path, to: &Path) -> std::io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::MoveFileExW;
    let f: Vec<u16> = from.as_os_str().encode_wide().chain(Some(0)).collect();
    let t: Vec<u16> = to.as_os_str().encode_wide().chain(Some(0)).collect();
    // 플래그 0 = 대상이 있으면 실패.
    if unsafe { MoveFileExW(f.as_ptr(), t.as_ptr(), 0) } == 0 {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
fn rename_no_replace(from: &Path, to: &Path) -> std::io::Result<()> {
    if to.try_exists()? {
        return Err(std::io::ErrorKind::AlreadyExists.into());
    }
    fs::rename(from, to)
}

/// 휴지통으로 보낸다. `trash` 는 COM 초기화에 실패하면(예: MTA 스레드) 패닉할 수 있어
/// 잡아서 false 로 돌려준다. 가능하면 COM 을 건드리지 않은 스레드(STA/미초기화)에서 부른다.
pub fn recycle(path: &Path) -> bool {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| trash::delete(path).is_ok()))
        .unwrap_or(false)
}

#[cfg(windows)]
pub fn exe_file_version(path: &Path) -> Option<String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileVersionInfoSizeW, GetFileVersionInfoW, VerQueryValueW, VS_FIXEDFILEINFO,
    };

    let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    unsafe {
        let size = GetFileVersionInfoSizeW(wide.as_ptr(), std::ptr::null_mut());
        if size == 0 {
            return None;
        }
        let mut buf = vec![0u8; size as usize];
        if GetFileVersionInfoW(wide.as_ptr(), 0, size, buf.as_mut_ptr().cast()) == 0 {
            return None;
        }
        let sub: Vec<u16> = "\\".encode_utf16().chain(Some(0)).collect();
        let mut ptr: *mut core::ffi::c_void = std::ptr::null_mut();
        let mut len: u32 = 0;
        if VerQueryValueW(buf.as_ptr().cast(), sub.as_ptr(), &mut ptr, &mut len) == 0
            || ptr.is_null()
            || (len as usize) < std::mem::size_of::<VS_FIXEDFILEINFO>()
        {
            return None;
        }
        let info = std::ptr::read_unaligned(ptr as *const VS_FIXEDFILEINFO);
        if info.dwSignature != 0xFEEF04BD {
            return None;
        }
        let (ms, ls) = (info.dwFileVersionMS, info.dwFileVersionLS);
        Some(format!("{}.{}.{}", ms >> 16, ms & 0xFFFF, ls >> 16))
    }
}

#[cfg(not(windows))]
pub fn exe_file_version(_path: &Path) -> Option<String> {
    None
}
