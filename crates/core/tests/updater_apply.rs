use std::fs;
use std::path::Path;

use dccon_core::config::Paths;
use dccon_core::updater::apply::{apply, cleanup_after_start, tidy_sibling_builds};

fn write(p: &Path, c: &[u8]) {
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    fs::write(p, c).unwrap();
}

#[test]
fn apply_replaces_and_keeps_old() {
    let d = tempfile::tempdir().unwrap();
    let cur = d.path().join("디시콘 다운로더.exe");
    let new = d.path().join("staging").join("new.exe");
    write(&cur, b"old");
    write(&new, b"new");
    apply(&new, &cur).unwrap();
    assert_eq!(fs::read(&cur).unwrap(), b"new");
    assert_eq!(fs::read(d.path().join("디시콘 다운로더.exe.old")).unwrap(), b"old");
}

#[test]
fn apply_rolls_back_when_new_missing() {
    let d = tempfile::tempdir().unwrap();
    let cur = d.path().join("app.exe");
    write(&cur, b"old");
    let r = apply(&d.path().join("missing.exe"), &cur);
    assert!(r.is_err());
    assert_eq!(fs::read(&cur).unwrap(), b"old");
    assert!(!d.path().join("app.exe.old").exists());
}

fn paths(d: &Path) -> Paths {
    Paths::new(d.join("data"))
}

#[test]
fn cleanup_removes_migration_leftovers() {
    let d = tempfile::tempdir().unwrap();
    let exe = d.path().join("app").join("dccon-downloader.exe");
    write(&exe, b"x");
    write(&d.path().join("app/dccon-downloader.exe.old"), b"o");
    write(&d.path().join("app/_internal/MIGRATED.txt"), b"m");
    let p = paths(d.path());
    write(&p.code.join("1.2.5/dccon/a.py"), b"c");
    write(&p.update.join("v1/x.zip"), b"z");
    write(&p.update.join("apply_update.ps1"), b"s");
    assert_eq!(cleanup_after_start(&exe, &p), None);
    assert!(!d.path().join("app/dccon-downloader.exe.old").exists());
    assert!(!d.path().join("app/_internal").exists());
    assert!(!p.code.exists());
    assert!(!p.update.join("v1").exists());
    assert!(!p.update.join("apply_update.ps1").exists());
    assert!(exe.exists());
}

#[test]
fn cleanup_keeps_real_internal() {
    let d = tempfile::tempdir().unwrap();
    let exe = d.path().join("dccon-downloader.exe");
    write(&exe, b"x");
    write(&d.path().join("_internal/MIGRATED.txt"), b"m");
    write(&d.path().join("_internal/other.dll"), b"d");
    cleanup_after_start(&exe, &paths(d.path()));
    assert!(d.path().join("_internal/MIGRATED.txt").exists());
    assert!(d.path().join("_internal/other.dll").exists());
}

#[test]
fn cleanup_returns_last_error() {
    let d = tempfile::tempdir().unwrap();
    let exe = d.path().join("a.exe");
    write(&exe, b"x");
    let p = paths(d.path());
    let mut bytes = vec![0xEF, 0xBB, 0xBF];
    bytes.extend_from_slice("실패했습니다\r\n".as_bytes());
    write(&p.update.join("last_error.log"), &bytes);
    assert_eq!(cleanup_after_start(&exe, &p).as_deref(), Some("실패했습니다"));
    assert!(!p.update.join("last_error.log").exists());
}

#[test]
fn tidy_renames_release_named_exe() {
    let d = tempfile::tempdir().unwrap();
    let exe = d.path().join("dccon-downloader-2.0.1.exe");
    write(&exe, b"n");
    write(&d.path().join("dccon-downloader-2.0.0.exe"), b"o");
    write(&d.path().join("my.exe"), b"m");
    let (cur, removed) = tidy_sibling_builds(&exe, "2.0.1", &|_| None, &|p| fs::remove_file(p).is_ok());
    assert_eq!(cur, d.path().join("디시콘 다운로더.exe"));
    assert_eq!(removed, vec!["dccon-downloader-2.0.0.exe".to_string()]);
    assert!(cur.exists());
    assert!(!exe.exists());
    assert!(d.path().join("my.exe").exists());
}

#[test]
fn tidy_keeps_newer_local_name() {
    let d = tempfile::tempdir().unwrap();
    let exe = d.path().join("dccon-downloader-2.0.1.exe");
    write(&exe, b"n");
    write(&d.path().join("디시콘 다운로더.exe"), b"l");
    let (cur, removed) = tidy_sibling_builds(&exe, "2.0.1", &|_| Some("9.0.0".into()), &|_| panic!("no recycle"));
    assert_eq!(cur, exe);
    assert!(removed.is_empty());
    assert!(exe.exists());
    assert!(d.path().join("디시콘 다운로더.exe").exists());
}

#[test]
fn tidy_unknown_local_version_keeps_it() {
    let d = tempfile::tempdir().unwrap();
    let exe = d.path().join("dccon-downloader-2.0.1.exe");
    write(&exe, b"n");
    write(&d.path().join("디시콘 다운로더.exe"), b"l");
    let (cur, removed) = tidy_sibling_builds(&exe, "2.0.1", &|_| None, &|_| panic!("no recycle"));
    assert_eq!(cur, exe);
    assert!(removed.is_empty());
    assert_eq!(fs::read(d.path().join("디시콘 다운로더.exe")).unwrap(), b"l");
    assert!(exe.exists());
}

#[test]
fn tidy_replaces_older_local_name() {
    let d = tempfile::tempdir().unwrap();
    let exe = d.path().join("dccon-downloader-2.0.1.exe");
    write(&exe, b"n");
    write(&d.path().join("디시콘 다운로더.exe"), b"l");
    let (cur, removed) = tidy_sibling_builds(&exe, "2.0.1", &|_| Some("1.9.0".into()), &|p| fs::remove_file(p).is_ok());
    assert_eq!(cur, d.path().join("디시콘 다운로더.exe"));
    assert_eq!(removed, vec!["디시콘 다운로더.exe".to_string()]);
    assert_eq!(fs::read(&cur).unwrap(), b"n");
    assert!(!exe.exists());
}

#[test]
fn tidy_matches_win64_and_uppercase() {
    let d = tempfile::tempdir().unwrap();
    let exe = d.path().join("DCCON-Downloader-2.0.1-Win64.EXE");
    write(&exe, b"n");
    write(&d.path().join("dccon-downloader-1.0.0-win64.exe"), b"o");
    let (cur, removed) = tidy_sibling_builds(&exe, "2.0.1", &|_| None, &|p| fs::remove_file(p).is_ok());
    assert_eq!(cur, d.path().join("디시콘 다운로더.exe"));
    assert_eq!(removed, vec!["dccon-downloader-1.0.0-win64.exe".to_string()]);
}

#[test]
fn apply_replaces_existing_old() {
    let d = tempfile::tempdir().unwrap();
    let cur = d.path().join("app.exe");
    let new = d.path().join("new.exe");
    write(&cur, b"cur");
    write(&new, b"new");
    write(&d.path().join("app.exe.old"), b"stale");
    apply(&new, &cur).unwrap();
    assert_eq!(fs::read(&cur).unwrap(), b"new");
    assert_eq!(fs::read(d.path().join("app.exe.old")).unwrap(), b"cur");
}

#[cfg(windows)]
#[test]
fn exe_file_version_reads_notepad() {
    use dccon_core::updater::apply::exe_file_version;
    assert!(exe_file_version(Path::new(r"C:\Windows\System32\notepad.exe")).is_some());
    let d = tempfile::tempdir().unwrap();
    let f = d.path().join("x.txt");
    write(&f, b"hello");
    assert_eq!(exe_file_version(&f), None);
}
