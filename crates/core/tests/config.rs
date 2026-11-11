use dccon_core::config::{Paths, Settings};
use std::path::PathBuf;

fn golden(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/golden").join(name)
}

#[test]
fn settings_default_matches_python() {
    let loaded = Settings::load(&golden("settings_default.json"));
    let expected = Settings {
        download_dir: loaded.download_dir.clone(),
        ..Default::default()
    };
    assert_eq!(loaded, expected);
    assert_eq!(loaded.concurrency, 3);
    assert_eq!(loaded.theme, "system");
}

#[test]
fn settings_roundtrip_format() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("sub").join("settings.json");
    let s = Settings {
        theme: "테마".into(),
        ..Default::default()
    };
    s.save(&path).unwrap();
    let text = std::fs::read_to_string(&path).unwrap();
    assert!(text.contains("\"테마\""));
    assert!(!text.contains("\\u"));
    assert!(text.starts_with("{\n  \"download_dir\""));
    assert!(!text.contains('\r'));
    assert!(!dir.path().join("sub").join("settings.json.tmp").exists());
    assert_eq!(Settings::load(&path), s);
}

#[test]
fn settings_corrupt_falls_back() {
    let dir = tempfile::tempdir().unwrap();
    let p = dir.path().join("s.json");
    std::fs::write(&p, r#"{"concurrency": 5, "theme": "dark""#).unwrap();
    assert_eq!(Settings::load(&p), Settings::default());

    std::fs::write(&p, r#"{"concurrency": 5, "zzz": 1}"#).unwrap();
    let s = Settings::load(&p);
    assert_eq!(s.concurrency, 5);
    assert_eq!(s, Settings { concurrency: 5, ..Settings::default() });

    std::fs::write(&p, r#"{"concurrency": "x"}"#).unwrap();
    assert_eq!(Settings::load(&p), Settings::default());

    assert_eq!(Settings::load(&dir.path().join("missing.json")), Settings::default());
}

#[test]
fn remember_dedups_and_caps() {
    let mut s = Settings::default();
    for i in 1..=30 {
        s.remember(i);
    }
    s.remember(5);
    assert_eq!(s.recent_packages[0], 5);
    assert_eq!(s.recent_packages.len(), 24);
    assert_eq!(s.recent_packages.iter().filter(|&&x| x == 5).count(), 1);
}

#[test]
fn paths_layout() {
    let p = Paths::new("D".into());
    assert_eq!(p.cache_img, PathBuf::from("D").join("cache").join("img"));
    assert_eq!(p.cache_meta, PathBuf::from("D").join("cache").join("meta"));
    assert_eq!(p.settings, PathBuf::from("D").join("settings.json"));
    assert_eq!(p.arca_session, PathBuf::from("D").join("arca_session.json"));
    assert_eq!(p.webview, PathBuf::from("D").join("webview"));
    assert_eq!(p.update, PathBuf::from("D").join("update"));
    assert_eq!(p.code, PathBuf::from("D").join("code"));
    assert_eq!(p.logs, PathBuf::from("D").join("logs"));
}
