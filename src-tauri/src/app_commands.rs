// 프런트가 부르는 앱 명령 전부. build.rs 가 이 파일을 include! 해 명령마다 ACL 권한
// (`allow-<명령>`, 밑줄은 하이픈)을 만들고, capabilities/default.json 이 그 권한을 `main` 창에만 준다.
// 앱 ACL 이 있으면 모든 앱 명령이 출처와 상관없이 권한 검사를 받으므로, 여기에 없는 명령은
// 실행 중에 거부된다. main.rs 의 generate_handler! 와 같아야 한다 (main.rs 의 시험이 확인한다).
// build.rs 에서도 읽으므로 내부 문서 주석(//!)을 쓰지 않는다.

pub const APP_COMMANDS: &[&str] = &[
    "get_settings",
    "save_settings",
    "begin_view",
    "list_top",
    "list_all",
    "list_arca",
    "search",
    "open_package",
    "parse_input",
    "enqueue",
    "pause_queue",
    "cancel_queue",
    "open_folder",
    "cache_stats",
    "clear_cache",
    "check_update",
    "download_update",
    "cancel_update",
    "apply_update",
    "skip_version",
    "open_release_page",
    "take_last_error",
    "arca_status",
    "arca_login",
    "arca_login_cancel",
    "arca_logout",
    "arca_forget_session",
];
