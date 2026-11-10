//! 파일명 정규화 (파이썬 `dccon/naming.py` 와 동일한 결과를 낸다).

use regex::Regex;
use std::sync::OnceLock;

const MAX_COMPONENT: usize = 80;
const RESERVED: &[&str] = &[
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
];

fn forbidden() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r#"[<>:"/\|?*\x00-\x1f]"#).unwrap())
}

fn spaces() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"\s+").unwrap())
}

fn rstrip_dot_space(s: &str) -> &str {
    s.trim_end_matches(['.', ' '])
}

/// 앞 `MAX_COMPONENT` 문자(코드포인트)만 남긴다.
fn truncate_chars(s: &str) -> &str {
    match s.char_indices().nth(MAX_COMPONENT) {
        Some((i, _)) => &s[..i],
        None => s,
    }
}

/// 경로 한 조각(폴더명 또는 파일명 본체)을 안전하게 만든다.
pub fn sanitize(name: &str, fallback: &str) -> String {
    let cleaned = forbidden().replace_all(name, "_");
    let cleaned = spaces().replace_all(&cleaned, " ");
    let mut cleaned = rstrip_dot_space(cleaned.trim()).to_string();
    if cleaned.chars().count() > MAX_COMPONENT {
        cleaned = rstrip_dot_space(truncate_chars(&cleaned)).to_string();
    }
    if RESERVED.contains(&cleaned.to_uppercase().as_str()) {
        cleaned = format!("_{cleaned}");
    }
    if cleaned.is_empty() {
        fallback.to_string()
    } else {
        cleaned
    }
}

/// 패키지 폴더명.
pub fn package_dirname(idx: u64, title: &str) -> String {
    sanitize(title, &format!("package_{idx}"))
}

/// 100개 넘는 패키지에서도 정렬이 맞도록 자릿수를 맞춘다.
pub fn pad_width(total: usize) -> usize {
    2.max(total.max(1).to_string().len())
}

/// `01_안녕.png` 형태.
pub fn item_filename(sort: u32, title: &str, ext: &str, width: usize) -> String {
    let safe = forbidden().replace_all(title, "_");
    let safe = rstrip_dot_space(safe.trim());
    let safe = spaces().replace_all(safe, " ");
    let mut safe = safe.to_string();
    if safe.chars().count() > MAX_COMPONENT {
        safe = rstrip_dot_space(truncate_chars(&safe)).to_string();
    }
    let ext = if ext.is_empty() { "png" } else { ext };
    let ext = ext.to_lowercase();
    let ext = ext.trim_start_matches('.');
    format!("{sort:0width$}_{safe}.{ext}")
}
