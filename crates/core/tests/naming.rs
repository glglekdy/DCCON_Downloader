// tests/golden/*.json 은 1.3.0(파이썬) 구현이 만든 기준값이다. 한 번 뽑아 데이터로 두었고 다시 만들지 않는다.
use dccon_core::models::{image_url, Package, IMAGE_BASE};
use dccon_core::naming::{item_filename, package_dirname, pad_width, safe_ext, sanitize};
use serde_json::Value;

fn read(p: &str) -> Value {
    let path = format!("{}/{}", env!("CARGO_MANIFEST_DIR"), p);
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

#[test]
fn naming_matches_python() {
    let g = read("tests/golden/naming.json");
    let arr = g.as_array().unwrap();
    assert!(!arr.is_empty());
    for e in arr {
        let name = e["name"].as_str().unwrap();
        // Intentional deviation from Python 1.3.0: its regex has `\|` (a literal pipe), so a
        // backslash survived. Rust replaces it with `_`; golden values are adjusted to match.
        let fix = |s: &str| s.replace('\\', "_");
        assert_eq!(sanitize(name, "untitled"), fix(e["sanitize"].as_str().unwrap()), "sanitize {name:?}");
        let idx = e["dirname_idx"].as_u64().unwrap();
        assert_eq!(package_dirname(idx, name), fix(e["dirname"].as_str().unwrap()), "dirname {name:?}");
        let it = &e["item"];
        let f = item_filename(
            it["sort"].as_u64().unwrap() as u32,
            name,
            it["ext"].as_str().unwrap(),
            it["width"].as_u64().unwrap() as usize,
        );
        assert_eq!(f, fix(it["file"].as_str().unwrap()), "file {name:?}");
    }
}

#[test]
fn pad_width_matches_python() {
    for p in read("tests/golden/pad_width.json").as_array().unwrap() {
        let total = p[0].as_u64().unwrap() as usize;
        assert_eq!(pad_width(total), p[1].as_u64().unwrap() as usize, "total {total}");
    }
}

#[test]
fn package_from_api_fixture() {
    let raw = read("tests/fixtures/dccon_detail.json");
    let pkg = Package::from_api(&raw).expect("info present");
    assert_eq!(serde_json::to_value(&pkg).unwrap(), read("tests/golden/parsed_dccon_detail.json"));
    assert!(Package::from_api(&serde_json::json!({})).is_none());
}

#[test]
fn image_url_passthrough() {
    assert_eq!(image_url("https://a/b.png"), "https://a/b.png");
    assert_eq!(image_url("abc"), format!("{IMAGE_BASE}abc"));
}

#[test]
fn backslash_never_survives() {
    assert!(!sanitize("..\\..\\evil", "x").contains('\\'));
    assert_eq!(item_filename(1, "a\\b", "png", 2), "01_a_b.png");
}

#[test]
fn ext_cannot_escape_the_folder() {
    // 1.3.0 과 같은 정리: 소문자, 앞의 점 떼기, 비면 png.
    assert_eq!(safe_ext(".PNG", "png"), "png");
    assert_eq!(safe_ext("gif", "png"), "gif");
    assert_eq!(safe_ext("", "png"), "png");
    assert_eq!(safe_ext("webm", "mp4"), "webm");
    // 영숫자 1~5자가 아니면 기본값.
    for bad in ["png/../../x", r"..\x", "a.b", "toolong", "p g", "확장"] {
        assert_eq!(safe_ext(bad, "png"), "png", "{bad}");
    }
    assert_eq!(item_filename(1, "a", "png/../../x", 2), "01_a.png");
}

#[test]
fn package_from_api_sanitizes_ext() {
    let pkg = Package::from_api(&serde_json::json!({
        "info": {"package_idx": 1, "title": "t"},
        "detail": [
            {"idx": 1, "title": "a", "sort": 1, "ext": "png/../../x", "path": "p1"},
            {"idx": 2, "title": "b", "sort": 2, "ext": ".GIF", "path": "p2"},
        ]
    }))
    .unwrap();
    let exts: Vec<&str> = pkg.items.iter().map(|i| i.ext.as_str()).collect();
    assert_eq!(exts, ["png", "gif"]);
}
