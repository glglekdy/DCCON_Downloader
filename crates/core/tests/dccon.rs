use dccon_core::dccon::*;
use dccon_core::models::Brief;
use serde_json::{json, Value};

fn read(p: &str) -> String {
    std::fs::read_to_string(format!("{}/tests/{p}", env!("CARGO_MANIFEST_DIR"))).unwrap()
}
fn golden(n: &str) -> Value {
    serde_json::from_str(&read(&format!("golden/{n}.json"))).unwrap()
}
fn rows_json(r: &[Brief]) -> Value {
    Value::Array(
        r.iter()
            .map(|b| json!({"idx": b.idx, "title": b.title, "seller": b.seller, "thumb_url": b.thumb_url}))
            .collect(),
    )
}
/// fetch_all 의 순수 부분.
fn all(body: &str, page: u32) -> (Vec<Brief>, u32, u64) {
    let rows = parse_list_page(body);
    let pages = parse_new_pages(body, if rows.is_empty() { 1 } else { page });
    (rows, pages, parse_new_total(body))
}

#[test]
fn list_page_new_1() {
    let g = golden("parsed_dccon_new_1");
    let (rows, pages, total) = all(&read("fixtures/dccon_new_1.html"), 1);
    assert_eq!(rows_json(&rows), g["rows"]);
    assert_eq!(json!(pages), g["pages"]);
    assert_eq!(json!(total), g["total"]);
}

#[test]
fn list_page_search() {
    let g = golden("parsed_dccon_hot_search");
    let body = read("fixtures/dccon_hot_search.html");
    assert_eq!(rows_json(&parse_list_page(&body)), g["rows"]);
    assert_eq!(json!(parse_total_pages(&body)), g["pages"]);
}

#[test]
fn top_day() {
    let g = golden("parsed_dccon_top_day");
    let rows = parse_top(&read("fixtures/dccon_top_day.txt")).unwrap();
    assert_eq!(rows_json(&rows), g["rows"]);
    assert!(parse_top("(not json)").is_err());
}

#[test]
fn new_synth_pages() {
    for n in ["1", "6141", "6142", "6145"] {
        let g = golden(&format!("parsed_dccon_new_synth_{n}"));
        let page = g["page"].as_u64().unwrap() as u32;
        let (rows, pages, total) = all(&read(&format!("fixtures/dccon_new_synth_{n}.html")), page);
        assert_eq!(rows_json(&rows), g["rows"], "rows {n}");
        assert_eq!(json!(pages), g["pages"], "pages {n}");
        assert_eq!(json!(total), g["total"], "total {n}");
    }
}

#[test]
fn parse_query_matches_python() {
    for item in golden("parse_query").as_array().unwrap() {
        let text = item[0].as_str().unwrap();
        let exp = &item[1];
        let got = serde_json::to_value(parse_query(text)).unwrap();
        let want = if exp["kind"] == "search" {
            json!({"kind": "search", "word": exp["value"]})
        } else {
            json!({"kind": "ids", "ids": exp["value"]})
        };
        assert_eq!(got, want, "{text:?}");
    }
}

#[test]
fn search_url_encodes_everything() {
    assert_eq!(
        search_url("a/b #%멍", "title", 1),
        "https://dccon.dcinside.com/hot/1/title/a%2Fb%20%23%25%EB%A9%8D"
    );
    assert_eq!(search_url("x", "bogus", 2), "https://dccon.dcinside.com/hot/2/title/x");
    assert_eq!(search_url("a_b.c-d~", "tags", 1), "https://dccon.dcinside.com/hot/1/tags/a_b.c-d~");
}
