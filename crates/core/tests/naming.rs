use dccon_core::models::{image_url, Package, IMAGE_BASE};
use dccon_core::naming::{item_filename, package_dirname, pad_width, sanitize};
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
        assert_eq!(sanitize(name, "untitled"), e["sanitize"].as_str().unwrap(), "sanitize {name:?}");
        let idx = e["dirname_idx"].as_u64().unwrap();
        assert_eq!(package_dirname(idx, name), e["dirname"].as_str().unwrap(), "dirname {name:?}");
        let it = &e["item"];
        let f = item_filename(
            it["sort"].as_u64().unwrap() as u32,
            name,
            it["ext"].as_str().unwrap(),
            it["width"].as_u64().unwrap() as usize,
        );
        assert_eq!(f, it["file"].as_str().unwrap(), "file {name:?}");
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
