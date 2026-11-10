//! 공통 오류 타입.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("network: {0}")]
    Network(String),
    #[error("http {0}")]
    Http(u16),
    #[error("rate limited")]
    RateLimited,
    #[error("cancelled")]
    Cancelled,
    #[error("login required")]
    LoginRequired,
    #[error("not found: {0}")]
    NotFound(String),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("parse: {0}")]
    Parse(String),
    #[error("update: {0}")]
    Update(String),
}

pub type Result<T> = std::result::Result<T, Error>;

impl Error {
    pub fn kind(&self) -> &'static str {
        match self {
            Error::Network(_) | Error::Http(_) => "network",
            Error::RateLimited => "rate_limited",
            Error::Cancelled => "cancelled",
            Error::LoginRequired => "login_required",
            Error::NotFound(_) => "not_found",
            Error::Io(_) => "io",
            Error::Parse(_) => "parse",
            Error::Update(_) => "update",
        }
    }

    pub fn user_message(&self) -> String {
        match self {
            Error::Network(s) => format!("네트워크 오류: {s}"),
            Error::Http(code) => format!("서버 오류 (HTTP {code})"),
            Error::RateLimited => "요청이 너무 많습니다. 잠시 뒤 다시 시도하세요.".into(),
            Error::Cancelled => "중단됨".into(),
            Error::LoginRequired => "아카라이브 로그인이 필요합니다.".into(),
            Error::NotFound(s) | Error::Update(s) => s.clone(),
            Error::Io(e) => format!("파일 오류: {e}"),
            Error::Parse(s) => format!("응답을 해석하지 못했습니다: {s}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_send_sync<T: Send + Sync + 'static>() {}

    #[test]
    fn error_is_send_sync() {
        assert_send_sync::<Error>();
    }

    #[test]
    fn kinds_and_messages() {
        assert_eq!(Error::Http(500).kind(), "network");
        assert_eq!(Error::LoginRequired.user_message(), "아카라이브 로그인이 필요합니다.");
        assert_eq!(Error::Cancelled.user_message(), "중단됨");
        assert_eq!(Error::Http(503).user_message(), "서버 오류 (HTTP 503)");
        let io: Error = std::io::Error::other("x").into();
        assert_eq!(io.kind(), "io");
    }
}
