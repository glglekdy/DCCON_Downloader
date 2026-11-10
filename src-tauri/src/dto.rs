//! 프런트와 주고받는 자료형.

use dccon_core::models::Brief;
use dccon_core::Error;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Debug)]
pub struct CmdError {
    pub kind: &'static str,
    pub message: String,
}

impl CmdError {
    pub fn new(kind: &'static str, message: impl Into<String>) -> Self {
        Self { kind, message: message.into() }
    }
}

impl From<Error> for CmdError {
    fn from(e: Error) -> Self {
        Self { kind: e.kind(), message: e.user_message() }
    }
}

#[derive(Serialize, Debug)]
pub struct ListPage {
    pub items: Vec<Brief>,
    pub page: u32,
    pub pages: u32,
    pub total: Option<u64>,
}

#[derive(Deserialize, Clone, Debug)]
pub struct Job {
    pub id: u64,
    pub title: String,
    pub sorts: Option<Vec<u32>>,
}

#[derive(Serialize, Debug)]
pub struct ReleaseInfo {
    pub version: String,
    pub notes: String,
    pub page_url: String,
    pub can_apply: bool,
    /// 받을 파일 이름. 없으면 자동 업데이트를 할 수 없다.
    pub asset_name: Option<String>,
}

#[derive(Serialize, Debug)]
pub struct CacheStats {
    pub files: u64,
    pub bytes: u64,
}
