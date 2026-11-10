//! 디시콘 다운로더 핵심 로직.

pub mod config;
pub mod error;
pub mod http;
pub mod models;
pub mod naming;

pub use error::{Error, Result};
