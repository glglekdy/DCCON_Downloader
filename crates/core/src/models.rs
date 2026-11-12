//! 디시콘 API 응답을 감싸는 자료형.

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const IMAGE_BASE: &str = "https://dcimg5.dcinside.com/dccon.php?no=";

#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Hash, Debug)]
#[serde(rename_all = "lowercase")]
pub enum Site {
    Dccon,
    Arca,
}

/// 아카콘은 path 자리에 전체 주소가 들어온다.
pub fn image_url(path: &str) -> String {
    if path.starts_with("http://") || path.starts_with("https://") {
        path.to_string()
    } else {
        format!("{IMAGE_BASE}{path}")
    }
}

/// 파이썬 `int(x or 0)`: 문자열/숫자 모두 받고 비거나 없으면 0.
fn int_of(v: Option<&Value>) -> u64 {
    match v {
        Some(Value::Number(n)) => n
            .as_u64()
            .or_else(|| n.as_f64().map(|f| f.max(0.0) as u64))
            .unwrap_or(0),
        Some(Value::String(s)) => s.trim().parse().unwrap_or(0),
        _ => 0,
    }
}

/// 파이썬 `(x or "")`: 문자열이면 그대로, 아니면 빈 문자열.
fn str_of(v: Option<&Value>) -> &str {
    v.and_then(Value::as_str).unwrap_or("")
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Item {
    pub idx: u64,
    pub title: String,
    pub sort: u32,
    pub ext: String,
    pub path: String,
    pub thumb: String,
}

impl Item {
    pub fn url(&self) -> String {
        image_url(&self.path)
    }

    fn from_api(row: &Value) -> Item {
        let ext = crate::naming::safe_ext(str_of(row.get("ext")), "png");
        Item {
            idx: int_of(row.get("idx")),
            title: str_of(row.get("title")).trim().to_string(),
            sort: int_of(row.get("sort")) as u32,
            ext,
            path: str_of(row.get("path")).to_string(),
            thumb: String::new(),
        }
    }
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct Package {
    pub idx: u64,
    pub title: String,
    pub description: String,
    pub seller: String,
    pub price: String,
    pub reg_date: String,
    pub main_img_path: String,
    pub list_img_path: String,
    pub items: Vec<Item>,
    pub tags: Vec<String>,
}

impl Package {
    pub fn main_url(&self) -> String {
        if self.main_img_path.is_empty() {
            String::new()
        } else {
            image_url(&self.main_img_path)
        }
    }

    /// `package_detail` 응답을 해석한다. `info` 가 없으면 None.
    pub fn from_api(v: &Value) -> Option<Package> {
        let info = v.get("info").filter(|i| i.is_object())?;
        let mut items: Vec<Item> = v
            .get("detail")
            .and_then(Value::as_array)
            .map(|a| a.iter().map(Item::from_api).collect())
            .unwrap_or_default();
        items.sort_by_key(|i| i.sort);
        let price = match info.get("price") {
            Some(Value::String(s)) if !s.is_empty() => s.clone(),
            Some(Value::Number(n)) if n.as_f64() != Some(0.0) => n.to_string(),
            _ => "0".to_string(),
        };
        let tags = v
            .get("tags")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(|t| t.get("tag").and_then(Value::as_str))
                    .filter(|s| !s.is_empty())
                    .map(String::from)
                    .collect()
            })
            .unwrap_or_default();
        Some(Package {
            idx: int_of(info.get("package_idx")),
            title: str_of(info.get("title")).trim().to_string(),
            description: str_of(info.get("description")).trim().to_string(),
            seller: str_of(info.get("seller_name")).trim().to_string(),
            price,
            reg_date: str_of(info.get("reg_date")).to_string(),
            main_img_path: str_of(info.get("main_img_path")).to_string(),
            list_img_path: str_of(info.get("list_img_path")).to_string(),
            items,
            tags,
        })
    }
}

/// 검색 결과나 인기 목록의 한 줄. 상세를 아직 안 받은 상태.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Brief {
    pub idx: u64,
    pub title: String,
    #[serde(default)]
    pub seller: String,
    #[serde(default)]
    pub thumb_url: String,
}
