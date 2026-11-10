include!("src/app_commands.rs");

fn main() {
    // 앱 명령에도 ACL 을 건다. 권한은 capabilities/default.json 에서 `main` 창에만 준다.
    // 그래서 로그인 창(원격 사이트)은 그 안의 프레임이 앱 주소여도 앱 명령을 부를 수 없다.
    let manifest = tauri_build::AppManifest::new().commands(APP_COMMANDS);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
        .expect("tauri-build 실패");
}
