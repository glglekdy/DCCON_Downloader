# 디시콘 다운로더 Rust 재작성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 파이썬 1.3.0 앱과 기능이 같은 Tauri 2 앱(2.0.0)을 만들고, 옛 앱 사용자가 자동 업데이트로 넘어오게 한다.

**Architecture:** Cargo 워크스페이스. `crates/core`(dccon-core)는 Tauri 없이 HTTP·파서·캐시·저장·업데이트를 맡고,
`src-tauri`는 상태·커맨드·`img://` 프로토콜·큐·로그인만 얇게 감싼다. 화면은 `ui/`의 Svelte 5 + TS.

**Tech Stack:** Rust stable(MSVC), Tauri 2, tokio, reqwest(rustls), regex, serde/serde_json, thiserror, tokio-util(CancellationToken),
sha1, sha2, percent-encoding, html-escape, trash, tracing; 테스트 wiremock, tempfile. 프론트 Svelte 5, TypeScript, Vite, vitest.

**Spec:** `docs/superpowers/specs/2026-11-10-rust-rewrite-design.md` (섹션 번호는 이 문서 기준)

## Global Constraints

- 창 제목 `디시콘 다운로더`. 바이너리 이름 `dccon-downloader`. 버전 `2.0.0`(워크스페이스 한 곳에서 관리).
- `DATA_DIR`: 윈도우 `%LOCALAPPDATA%/DcconDownloader`, 맥 `~/Library/Application Support/DcconDownloader`, 그 밖 `$XDG_DATA_HOME/DcconDownloader` 또는 `~/.dccondownloader`.
- 캐시 `DATA_DIR/cache/img/<키 앞 2자>/<키>.<ext>`, `DATA_DIR/cache/meta/<id>.json`, 설정 `DATA_DIR/settings.json`, 세션 `DATA_DIR/arca_session.json`. 형식은 1.3.0 과 같다(스펙 7.5).
- 모든 디시콘 요청 기본 헤더: `User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36`, `Referer: https://dccon.dcinside.com/`, `Accept-Language: ko-KR,ko;q=0.9`. 아카콘 요청은 `Referer: https://arca.live/e/`.
- 스로틀 0.12초 + 지터 0~0.08초. 429/500/502/503/504 재시도 최대 4회, 대기 `min(2^n * 0.5, 8) + 0~0.4`초. 429 는 5초 전역 일시정지.
- 동시 수: 목록 2, 썸네일 max(2, 동시 다운로드 수), 다운로드 = 설정 `concurrency`(기본 3).
- 사용자에게 보이는 문구는 한국어. 파이썬 1.3.0 에 같은 문구가 있으면 그대로 쓴다.
- 아카콘 저장 위치 `<download_dir>/arcacon/`.
- 업데이트 대상 `https://api.github.com/repos/glglekdy/DCCON_Downloader/releases/latest`, 인증 없이. 릴리즈 페이지 `https://github.com/glglekdy/DCCON_Downloader/releases`.
- 릴리즈 자산 이름: `dccon-downloader-X.Y.Z.exe`, `dccon-downloader-X.Y.Z-win64.zip`, `dccon-downloader-X.Y.Z-macos.zip`. `.pyz` 는 만들지 않는다.
- 커밋 작성자 이메일은 저장소 로컬 설정(`nwb10102@gmail.com`)을 쓴다. 커밋 메시지 끝에 세션의 Co-Authored-By / Claude-Session 두 줄.
- 빌드 산출물은 `dist/`(gitignore)에만. 저장소에 `release/` 같은 폴더를 커밋하지 않는다.
- 파이썬 코드는 Task 23 전까지 지우지 않는다(골든 값 생성과 이전 실측에 쓴다).

## Review Focus

1. **저장 폴더를 만들 수 없을 때**(권한 없음, 없는 드라이브): 큐에 넣는 순간 `"폴더를 만들 수 없습니다.\n<이유>"` 오류를 돌려주고 큐는 시작하지 않는다. → Task 13 `enqueue_fails_when_dest_cannot_be_created`.
2. **오프라인에서 시작**: 시작할 때 업데이트 확인이 연결 실패해도 아무 창도 띄우지 않는다(수동 확인일 때만 `GitHub 에 연결하지 못했습니다.` 표시). → Task 11 `fetch_latest_connection_error_message`, Task 20 시작 확인 단계.
3. **중간에 끊긴 다운로드의 `.part`**: 남은 `NN_x.png.part` 는 "이미 있음"으로 치지 않고 다시 받아 덮는다. → Task 10 `leftover_part_file_is_not_skipped`.
4. **특수문자 검색어**(`/`, `#`, `%`, 공백, 한글): 경로 조각으로 전부 인코딩한다(`quote(safe="")` 와 같음). → Task 8 `search_url_encodes_everything`.
5. **깨진 `settings.json`**(잘린 JSON, 모르는 키, 타입이 틀린 값): 앱이 죽지 않고 기본값으로 뜬다. → Task 4 `settings_corrupt_falls_back`.

---

## 파일 구조

```
Cargo.toml                       워크스페이스 (members: crates/core, src-tauri), version = "2.0.0"
crates/core/Cargo.toml
crates/core/src/lib.rs           pub mod 선언
crates/core/src/error.rs         Error, Result
crates/core/src/config.rs        Paths, Settings
crates/core/src/models.rs        Site, Item, Package, Brief, image_url
crates/core/src/naming.rs        sanitize, package_dirname, pad_width, item_filename
crates/core/src/http.rs          Throttle, Client, Resp
crates/core/src/cache.rs         cache_key, ImageCache, MetaCache
crates/core/src/dccon.rs         디시콘 엔드포인트·파서·parse_query
crates/core/src/arca.rs          아카콘 엔드포인트·파서·parse_ids, ArcaSession
crates/core/src/downloader.rs    download_package, sniff_ext
crates/core/src/updater/mod.rs   Release, Asset, 버전, 조회, 받기
crates/core/src/updater/apply.rs exe 교체, 시작 정리, 이름 정리
crates/core/tests/golden/        파이썬이 만든 기대값 JSON
crates/core/tests/fixtures/      실측·합성 HTML/JSON
crates/core/tests/*.rs           모듈별 통합 테스트
src-tauri/Cargo.toml, build.rs, tauri.conf.json, capabilities/default.json, icons/
src-tauri/src/main.rs            진입, WebView2 안내, 로그, 시작 정리
src-tauri/src/state.rs           AppState
src-tauri/src/commands.rs        커맨드
src-tauri/src/dto.rs             프론트로 가는 직렬화 타입, CmdError
src-tauri/src/queue.rs           다운로드 큐
src-tauri/src/imgproto.rs        img:// 핸들러
src-tauri/src/login.rs           아카콘 로그인
ui/                              Vite + Svelte 5 + TS (package.json, vite.config.ts, src/...)
ui/src/lib/api.ts                invoke/listen 래퍼와 타입
ui/src/lib/theme.css             토큰
ui/src/lib/stores/*.ts           history, selection, view, queue, settings
ui/src/lib/components/*.svelte   화면 조각
tools/gen_golden.py              골든 값·픽스처 생성 (Task 23 에서 삭제)
build.ps1, build.sh              새 빌드 스크립트
.github/workflows/macos.yml      맥 빌드
```

---

### Task 1: 툴체인과 빈 창 뼈대

**Files:**
- Create: `Cargo.toml`, `crates/core/Cargo.toml`, `crates/core/src/lib.rs`, `src-tauri/Cargo.toml`, `src-tauri/build.rs`, `src-tauri/tauri.conf.json`, `src-tauri/capabilities/default.json`, `src-tauri/src/main.rs`, `src-tauri/icons/*`, `ui/*`(Vite 템플릿), `ui/src/assets/{icon.png,brand.svg,check.svg}`(파이썬 `dccon/gui/assets/` 에서 복사)
- Modify: `.gitignore` (`/target`, `ui/node_modules`, `ui/dist` 추가)

**Interfaces:**
- Produces: `cargo tauri build` 로 `target/release/dccon-downloader.exe` 생성. `npm --prefix ui run build` 가 `ui/dist` 생성. `tauri.conf.json` 의 `build.frontendDist = "../ui/dist"`, `devUrl = "http://localhost:5173"`, `identifier = "com.glglekdy.dccondownloader"`, `productName = "디시콘 다운로더"`, `mainBinaryName = "dccon-downloader"`, 창 하나 `title = "디시콘 다운로더"`, 1180x780, 최소 820x560.

- [ ] **Step 1: 툴체인 설치 확인**

`winget install Rustlang.Rustup`, `winget install OpenJS.NodeJS.LTS`, MSVC 가 없으면
`winget install Microsoft.VisualStudio.2022.BuildTools --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive"`.
그 뒤 `cargo install tauri-cli --version "^2" --locked`.
Run: `cargo --version; node --version; cargo tauri --version`
Expected: 셋 다 버전 출력(tauri-cli 2.x).

- [ ] **Step 2: 워크스페이스·Svelte·Tauri 뼈대 생성**

`npm create vite@latest ui -- --template svelte-ts` 후 `App.svelte` 를 `<main>디시콘 다운로더</main>` 하나로 줄인다.
아이콘은 `cargo tauri icon dccon/gui/assets/icon.png -o src-tauri/icons`. `main.rs` 는 `#![cfg_attr(not(feature = "console"), windows_subsystem = "windows")]` 과 기본 `tauri::Builder`.
`src-tauri/Cargo.toml` 에 `[features] console = []`, 의존성 `tauri = { version = "2", features = [] }`, `tauri-plugin-dialog = "2"`, `tauri-plugin-opener = "2"`, `dccon-core = { path = "../crates/core" }`.

- [ ] **Step 3: 빌드하고 창 확인**

Run: `cargo tauri build --no-bundle` 후 CLAUDE.md 3단계 스크립트를 `target\release\dccon-downloader.exe` 하나로 돌린다.
Expected: `alive=True window=디시콘 다운로더`. exe 크기를 기록한다(목표 15MB 이하).

- [ ] **Step 4: Commit** — `git add -A; git commit -m "Tauri 뼈대: 빈 창이 뜨는 워크스페이스"`

---

### Task 2: 아카콘 앱 내 로그인 스파이크 (사용자 참여, 버리는 코드)

**Files:**
- Create (임시): `src-tauri/src/spike_login.rs`, `main.rs` 에 디버그 커맨드 `spike_arca_login` 연결
- Modify: 스펙 6절에 결과 기록

**Interfaces:**
- Produces: 스펙 6절의 "확정 방식" 한 문단. Task 19 는 이 결정을 따른다.

- [ ] **Step 1: 스파이크 구현** — `WebviewWindowBuilder::new(app, "arca-login", WebviewUrl::External("https://arca.live/u/login?goto=/e/"))` 로 창을 열고, `on_navigation` 으로 URL 을 지켜보다 경로가 `/e/` 로 시작하면 `window.cookies_for_url("https://arca.live".parse()?)` 결과(이름, 도메인, HttpOnly 여부)와 `navigator.userAgent`(`eval` + IPC 로)를 로그로 찍는다. 데이터 폴더는 `DATA_DIR/webview`.
- [ ] **Step 2: 사용자에게 로그인 요청** — 사용자에게 `cargo tauri dev` 로 뜬 창에서 아카라이브 로그인을 해 달라고 하고, Cloudflare 확인이 통과하는지 함께 본다.
- [ ] **Step 3: 꺼낸 쿠키로 reqwest 요청** — 꺼낸 쿠키 전부를 `Cookie` 헤더로, UA 를 그대로 넣어 `GET https://arca.live/e/` 를 보낸다.
Expected(성공 조건 셋): Cloudflare 통과 / `cf_clearance` 와 세션 쿠키(HttpOnly 포함)가 목록에 있음 / reqwest 응답이 200 이고 최종 URL 에 `/u/login` 이 없음.
- [ ] **Step 4: 결정 기록과 정리** — 셋 다 되면 스펙 6절에 "확정: 앱 내 로그인 창"을, 하나라도 안 되면 "확정: Chrome CDP 방식"과 실패한 조건을 적는다. 스파이크 파일과 커맨드는 지운다.
- [ ] **Step 5: Commit** — `git commit -am "아카콘 로그인 방식 실측 결과"`

---

### Task 3: 골든 값과 픽스처

**Files:**
- Create: `tools/gen_golden.py`, `crates/core/tests/golden/*.json`, `crates/core/tests/fixtures/*`

**Interfaces:**
- Produces (모두 UTF-8 JSON):
  - `golden/naming.json`: `[{ "name", "sanitize", "dirname_idx": 7, "dirname", "item": {"sort", "ext", "width", "file"} }]`, `golden/pad_width.json`: `[[total, width]]`
  - `golden/cache_key.json`: `[[url, key]]`
  - `golden/parse_query.json`: `[[text, {"kind": "search"|"ids", "value"}]]`, `golden/arca_parse_ids.json`: `[[text, ids 또는 null]]`
  - `golden/version.json`: `{"parse": [[text, [ints]]], "newer": [[remote, local, bool]]}`
  - `golden/settings_default.json`(파이썬 `Settings().save()` 결과 바이트), `golden/meta.json`(아래 픽스처 패키지로 `_write_meta` 한 결과)
  - `fixtures/dccon_new_1.html`, `fixtures/dccon_hot_search.html`, `fixtures/dccon_detail.json`, `fixtures/dccon_top_day.txt`(실측), `fixtures/arca_list.html`, `fixtures/arca_detail.html`(`tests/test_arca.py` 의 `LIST_HTML`, `DETAIL_HTML`), `fixtures/dccon_new_synth_{1,6141,6145}.html`(`tests/test_all_list.py` 의 생성기 결과)
  - 각 픽스처의 파이썬 파서 결과: `golden/parsed_<픽스처 이름>.json` (Brief 는 `{idx,title,seller,thumb_url}`, Package 는 dataclass 필드 그대로, 페이지·총계 포함)

- [ ] **Step 1: 스크립트 작성** — `dccon` 패키지와 `tests` 모듈을 import 해서 위 파일을 만든다. 이름 입력은 최소한 `""`, `"a/b:c?"`, `"CON"`, `"con"`, `"  hello   world  "`, `"끝점..."`, `"x" * 85`, `"가" * 85`, `"😀콘"`, `"tab\there"`, `"a."`, `"NUL.txt"`, `"<>|*\x01"` 를 넣는다. pad_width 는 0,1,9,99,100,1000. parse_query 는 `"멍뭉"`, `"12345"`, `"12345 83649, 94849"`, `"12345 12345"`, `"https://dccon.dcinside.com/hot/1#12345"`, `"#777"`, `"https://example.com/#5"`, `"12 멍"`, `""`. cache_key 는 `dccon.php?no=abc%2Fd&date=1`, 같은 no 에 다른 date, 아카콘 서명 주소 둘, 쿼리 없는 주소. 실측 픽스처는 `DcconClient` 로 받는다(`/new/1`, `/hot/1/title/멍뭉`, 상세 하나, 일간 인기).
- [ ] **Step 2: 실행** — Run: `uv run python tools/gen_golden.py` / Expected: 위 파일이 모두 생기고 비어 있지 않다.
- [ ] **Step 3: Commit** — `git add tools crates/core/tests; git commit -m "파이썬 1.3.0 골든 값과 픽스처"`

---

### Task 4: core — error, config

**Files:**
- Create: `crates/core/src/error.rs`, `crates/core/src/config.rs`, `crates/core/tests/config.rs`

**Interfaces:**
- Produces:
  - `pub enum Error { Network(String), Http(u16), RateLimited, Cancelled, LoginRequired, NotFound(String), Io(#[from] std::io::Error), Parse(String), Update(String) }`, `pub type Result<T> = std::result::Result<T, Error>`
  - `impl Error { pub fn kind(&self) -> &'static str /* "network"|"rate_limited"|"cancelled"|"login_required"|"not_found"|"io"|"parse"|"update" ; Http → "network" */; pub fn user_message(&self) -> String }` — `LoginRequired` 문구 `아카라이브 로그인이 필요합니다.`, `Cancelled` 는 `중단됨`.
  - `pub struct Paths { pub data, pub cache_img, pub cache_meta, pub settings, pub arca_session, pub webview, pub logs, pub update, pub code: PathBuf }`, `impl Paths { pub fn new(data: PathBuf) -> Self; pub fn system() -> Self }`, `pub fn data_dir() -> PathBuf`
  - `#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)] #[serde(default)] pub struct Settings { download_dir: String, concurrency: u32, save_main_image: bool, write_meta_json: bool, reduce_motion: bool, theme: String, animate_gifs: bool, check_updates: bool, skipped_version: String, recent_packages: Vec<u64> }` (필드 순서 그대로, 기본값은 1.3.0 과 같음; `download_dir` 기본 `<home>/Downloads/dccon`)
  - `impl Settings { pub fn load(path: &Path) -> Self; pub fn save(&self, path: &Path) -> std::io::Result<()>; pub fn remember(&mut self, id: u64) }` — `remember` 는 맨 앞에 넣고 중복 제거, 24개까지.

- [ ] **Step 1: 실패하는 테스트 작성** — `crates/core/tests/config.rs`:
  - `settings_default_matches_python`: `golden/settings_default.json` 을 `load` 한 값이 `Settings::default()` 와 `download_dir` 을 빼고 같다.
  - `settings_roundtrip_format`: 임시 폴더에 `save` 한 바이트가 2칸 들여쓰기, 한글 이스케이프 없음(`"테마"` 같은 값을 넣고 `\\u` 가 없는지).
  - `settings_corrupt_falls_back`: `{"concurrency": 5, "theme": "dark"` (잘림) → `Settings::default()`; `{"concurrency": 5, "zzz": 1}` → concurrency 5, 나머지 기본; `{"concurrency": "x"}` → `Settings::default()`.
  - `remember_dedups_and_caps`: 1..=30 을 차례로 `remember` 한 뒤 `remember(5)` → 첫 값 5, 길이 24, 5 가 한 번만.
  - `paths_layout`: `Paths::new("D".into()).cache_img == "D/cache/img"`, `settings == "D/settings.json"`, `arca_session == "D/arca_session.json"`, `webview == "D/webview"`.
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-core --test config` / Expected: 컴파일 실패(정의 없음).
- [ ] **Step 3: 구현** — `save` 는 `<settings>.tmp` 에 `serde_json::to_string_pretty` 로 쓰고 `rename`. `load` 는 읽기·파싱 실패 시 기본값.
- [ ] **Step 4: 통과 확인** — Run: `cargo test -p dccon-core --test config` / Expected: 5 passed.
- [ ] **Step 5: Commit** — `git commit -m "core: 오류 타입과 설정"`

---

### Task 5: core — models, naming

**Files:**
- Create: `crates/core/src/models.rs`, `crates/core/src/naming.rs`, `crates/core/tests/naming.rs`

**Interfaces:**
- Produces:
  - `#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Hash, Debug)] #[serde(rename_all = "lowercase")] pub enum Site { Dccon, Arca }`
  - `#[derive(Serialize, Clone, Debug, PartialEq)] pub struct Item { pub idx: u64, pub title: String, pub sort: u32, pub ext: String, pub path: String, pub thumb: String }`, `impl Item { pub fn url(&self) -> String }`
  - `pub struct Package { idx: u64, title, description, seller, price, reg_date, main_img_path, list_img_path: String, items: Vec<Item>, tags: Vec<String> }` (Serialize, 모두 pub), `impl Package { pub fn main_url(&self) -> String; pub fn from_api(v: &serde_json::Value) -> Option<Package> }` — `info` 가 없으면 None, items 는 sort 정렬, ext 소문자·앞 점 제거, 빈 ext 는 `png`.
  - `pub struct Brief { pub idx: u64, pub title: String, pub seller: String, pub thumb_url: String }` (Serialize, Deserialize)
  - `pub const IMAGE_BASE: &str = "https://dcimg5.dcinside.com/dccon.php?no="`, `pub fn image_url(path: &str) -> String` (http/https 로 시작하면 그대로)
  - `pub fn sanitize(name: &str, fallback: &str) -> String`, `pub fn package_dirname(idx: u64, title: &str) -> String`, `pub fn pad_width(total: usize) -> usize`, `pub fn item_filename(sort: u32, title: &str, ext: &str, width: usize) -> String` — 길이 제한 80 은 **문자 수** 기준(파이썬 `len`).

- [ ] **Step 1: 실패하는 테스트** — `naming_matches_python`(golden/naming.json 전 항목의 sanitize·dirname·file 일치), `pad_width_matches_python`, `package_from_api_fixture`(`fixtures/dccon_detail.json` → `golden/parsed_dccon_detail.json` 과 필드 일치), `image_url_passthrough`(`"https://a/b.png"` 그대로, `"abc"` → `IMAGE_BASE + "abc"`).
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-core --test naming` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현** — 금지 문자 정규식은 파이썬 `[<>:"/\\|?*\x00-\x1f]` 그대로, 공백 접기는 `\s+`(유니코드).
- [ ] **Step 4: 통과 확인** — Run 같은 명령 / Expected: 4 passed.
- [ ] **Step 5: Commit** — `git commit -m "core: 모델과 파일명 규칙"`

---

### Task 6: core — HTTP 클라이언트

**Files:**
- Create: `crates/core/src/http.rs`, `crates/core/tests/http.rs`

**Interfaces:**
- Consumes: `Error` (Task 4)
- Produces:
  - `pub struct Throttle` + `impl Throttle { pub fn new(min: Duration, jitter: Duration) -> Self; pub fn default_site() -> Self /* 0.12s, 0.08s */; pub async fn wait(&self) }` — 파이썬과 같은 `next_at` 예약 방식.
  - `pub struct Resp { pub status: u16, pub url: String /* 최종 URL */, pub body: bytes::Bytes }`, `impl Resp { pub fn text(&self) -> String /* utf-8 lossy */; pub fn json(&self) -> Result<serde_json::Value> }`
  - `pub struct Client` (Clone, 내부 Arc), `impl Client {`
    - `pub fn new(referer: &str, throttle: Throttle) -> Self` — 기본 헤더(Global Constraints), 리다이렉트 따라감, 타임아웃 20초
    - `pub fn set_session(&self, user_agent: &str, cookies: &[(String, String)])` — UA 교체 + `Cookie` 헤더 고정
    - `pub async fn get(&self, url: &str, cancel: &CancellationToken) -> Result<Resp>`
    - `pub async fn get_with(&self, url: &str, query: &[(&str, String)], extra: &[(&str, &str)], cancel: &CancellationToken) -> Result<Resp>`
    - `pub async fn post_form(&self, url: &str, form: &[(&str, String)], extra: &[(&str, &str)], cancel: &CancellationToken) -> Result<Resp>`
    - `pub fn pause(&self); pub fn resume(&self); pub fn is_paused(&self) -> bool` `}`
  - 동작: 매 시도 전 취소 확인 → 일시정지 풀릴 때까지 대기(250ms 마다 취소 확인) → 스로틀 → 요청. 2xx·3xx 반환, 재시도 대상은 재시도, 그 밖 4xx 는 `Error::Http(code)`, 전송 오류는 `Error::Network(이름)`. 429 는 한 번만 pause 후 5초 뒤 resume. 테스트용으로 백오프 기본값을 바꿀 수 있게 `pub fn with_backoff_scale(self, scale: f64) -> Self`.

- [ ] **Step 1: 실패하는 테스트** (wiremock, `with_backoff_scale(0.01)`):
  - `sends_default_headers`: 서버가 Referer `https://dccon.dcinside.com/` 와 Accept-Language 를 요구하는 matcher 로 200.
  - `retries_5xx_then_succeeds`: 503 두 번 뒤 200 → Ok, 요청 3회.
  - `gives_up_after_four_retries`: 계속 502 → `Err(RateLimited)`, 요청 5회.
  - `429_pauses_globally`: 첫 응답 429 직후 `is_paused() == true`.
  - `cancel_while_paused`: `pause()` 상태에서 get, 100ms 뒤 cancel → `Err(Cancelled)`.
  - `404_is_http_error`: `Err(Http(404))`, 요청 1회.
  - `session_sets_ua_and_cookie`: `set_session("UA", [("a","1"),("b","2")])` 뒤 요청 헤더 `User-Agent: UA`, `Cookie: a=1; b=2`.
  - `final_url_after_redirect`: 302 → `/u/login` 이면 `resp.url` 이 `/u/login` 으로 끝남.
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-core --test http` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현** — 일시정지는 `tokio::sync::watch<bool>`.
- [ ] **Step 4: 통과 확인** — Expected: 8 passed.
- [ ] **Step 5: Commit** — `git commit -m "core: 스로틀·백오프·일시정지 HTTP 클라이언트"`

---

### Task 7: core — 캐시

**Files:**
- Create: `crates/core/src/cache.rs`, `crates/core/tests/cache.rs`

**Interfaces:**
- Consumes: `Client`, `Resp` (Task 6)
- Produces:
  - `pub fn cache_key(url: &str) -> String` — `[?&]no=([^&]+)` 값(없으면 `?` 앞)을 퍼센트 디코딩(UTF-8 lossy) 후 sha1 hex.
  - `pub struct ImageCache` (Clone), `impl ImageCache { pub fn new(root: PathBuf) -> Self; pub fn path_for(&self, url: &str, ext: &str) -> PathBuf; pub fn peek(&self, url: &str, ext: &str) -> Option<Vec<u8>>; pub async fn get(&self, client: &Client, url: &str, ext: &str, cancel: &CancellationToken) -> Result<Vec<u8>>; pub fn stats(&self) -> (u64, u64); pub fn clear(&self, meta_root: &Path) }` — 키별 `tokio::sync::Mutex`, 잠근 뒤 다시 확인, `.part` 에 쓰고 rename.
  - `pub struct MetaCache`, `impl MetaCache { pub fn new(root: PathBuf) -> Self; pub fn load(&self, id: u64) -> Option<serde_json::Value>; pub fn store(&self, id: u64, v: &serde_json::Value) }`

- [ ] **Step 1: 실패하는 테스트** — `cache_key_matches_python`(golden 전 항목), `layout_matches_python`(`path_for` 가 `<root>/<key[..2]>/<key>.gif`, ext 대문자·앞 점 정리), `get_fetches_once_concurrently`(같은 URL 동시 5개 → 서버 요청 1회, 결과 5개 같음), `peek_reads_existing_python_cache`(파이썬 규칙 경로에 미리 파일을 두면 네트워크 없이 읽힘), `stats_and_clear`(파일 2개 → (2, 합계 바이트); clear 후 img·meta 폴더 없음).
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-core --test cache` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인** — Expected: 5 passed.
- [ ] **Step 5: Commit** — `git commit -m "core: 이미지·메타 캐시 (1.3.0 과 같은 키)"`

---

### Task 8: core — 디시콘 API

**Files:**
- Create: `crates/core/src/dccon.rs`, `crates/core/tests/dccon.rs`

**Interfaces:**
- Consumes: `Client`, `Brief`, `Package`, `Error`
- Produces:
  - 상수 `BASE = "https://dccon.dcinside.com"`, `PACKAGE_DETAIL_URL = BASE + "/index/package_detail"`, `SEARCH_TYPES = [("title","제목"),("nick_name","작가"),("tags","태그")]`
  - `pub enum TopKind { Day, Week, Month, Official }` (serde lowercase), `pub fn top_url(kind: TopKind) -> &'static str` (1.3.0 `TOP_LISTS` 주소)
  - 순수 함수: `pub fn parse_list_page(body: &str) -> Vec<Brief>`, `pub fn parse_total_pages(body: &str) -> u32`, `pub fn parse_new_pages(body: &str, page: u32) -> u32`, `pub fn parse_new_total(body: &str) -> u64`, `pub fn parse_top(text: &str) -> Result<Vec<Brief>>`, `pub fn search_url(word: &str, search_type: &str, page: u32) -> String`
  - `pub enum Query { Search(String), Ids(Vec<u64>) }` (Serialize: `{"kind":"search","word"}` / `{"kind":"ids","ids"}`), `pub fn parse_query(text: &str) -> Query`
  - 비동기: `pub async fn fetch_package(c: &Client, id: u64, cancel) -> Result<(Package, serde_json::Value)>` (POST form `package_idx`, 헤더 `X-Requested-With: XMLHttpRequest`; `info` 없으면 `NotFound("패키지 {id} 를 찾을 수 없습니다.")`), `search(c, word, search_type, page, cancel) -> Result<(Vec<Brief>, u32)>`, `fetch_all(c, page, cancel) -> Result<(Vec<Brief>, u32, u64)>`(행이 비면 페이지 계산에 1을 넘긴다), `fetch_top(c, kind, cancel) -> Result<Vec<Brief>>`
  - HTML 정규식은 `dccon/api.py` 의 것을 `(?s)` 를 붙여 그대로 옮긴다. 엔티티 해제는 `html_escape::decode_html_entities`.

- [ ] **Step 1: 실패하는 테스트** — 각 픽스처의 파서 결과가 `golden/parsed_*.json` 과 같음(`list_page_new_1`, `list_page_search`, `top_day`, `new_synth_pages`: 합성 1페이지 → (15, 6142, 92133), 6141 → 9개·6142, 6145 → 0개·6145 미만), `parse_query_matches_python`(golden 전 항목), `search_url_encodes_everything`: `search_url("a/b #%멍", "title", 1) == "https://dccon.dcinside.com/hot/1/title/a%2Fb%20%23%25%EB%A9%8D"`, 모르는 종류는 `title`.
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-core --test dccon` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현** — 인코딩 집합은 `NON_ALPHANUMERIC` 에서 `_ . - ~` 를 뺀 것.
- [ ] **Step 4: 통과 확인** — Expected: 6 passed.
- [ ] **Step 5: Commit** — `git commit -m "core: 디시콘 목록·검색·상세·인기"`

---

### Task 9: core — 아카콘 API와 세션

**Files:**
- Create: `crates/core/src/arca.rs`, `crates/core/tests/arca.rs`

**Interfaces:**
- Consumes: `Client`, `Brief`, `Package`, `Item`, `Error`
- Produces:
  - 상수 `ARCA_BASE = "https://arca.live"`, `LOGIN_URL = ARCA_BASE + "/u/login?goto=/e/"`, `ARCA_TABS = [("new","최신"),("weekly","주간 인기"),("monthly","월간 인기")]`, `SEARCH_TYPES = [("title","제목"),("nickname","작가"),("tag","태그")]`
  - `pub fn list_query(kind: &str, page: u32) -> Vec<(&'static str, String)>` (`p` 와, weekly/monthly 면 `rank`), `pub fn search_query(word: &str, target: &str, page: u32) -> Vec<(&'static str, String)>` (`target`, `keyword`, `p`; 모르는 target 은 title)
  - `pub fn parse_list(body: &str) -> Vec<Brief>`, `pub fn parse_pages(body: &str, page: u32) -> u32`, `pub fn parse_package(id: u64, body: &str) -> Package`, `pub fn parse_ids(text: &str) -> Option<Vec<u64>>`
  - `pub fn check_login(resp: &Resp) -> Result<()>` — 최종 URL 경로에 `/u/login` 이면 `LoginRequired`. 요청 중 `Http(401|403)` 도 `LoginRequired` 로 바꾼다.
  - `pub async fn fetch_list(c, kind, page, cancel) -> Result<(Vec<Brief>, u32)>`, `search(c, word, target, page, cancel) -> Result<(Vec<Brief>, u32)>`, `fetch_package(c, id, cancel) -> Result<Package>` (항목 없으면 `NotFound("아카콘 {id} 를 찾을 수 없습니다.")`)
  - `#[derive(Serialize, Deserialize)] pub struct SessionCookie { name, value, domain, path: String }`, `pub struct ArcaSession { pub user_agent: String, pub cookies: Vec<SessionCookie> }`, `impl ArcaSession { pub fn load(path: &Path) -> Option<Self>; pub fn save(&self, path: &Path) -> std::io::Result<()>; pub fn forget(path: &Path); pub fn cookie_pairs(&self) -> Vec<(String, String)> }`

- [ ] **Step 1: 실패하는 테스트** — `parse_list_fixture`(idx `[54566, 48750]`, 첫 제목 `고양이 & 밴시`, 작가 `작가1`, 페이지 12, golden 과 일치), `parse_detail_images_and_videos`(제목 `움짤콘`, 작가 `작가2`, main_url `https://ac.arca.live/a/icon.png?expires=1&key=k`, 동영상 항목 url `https://ac.arca.live/a/2.mp4?expires=1&key=k`, thumb 이 `2.thumbnail.jpg?expires=1&key=k` 로 끝남, (sort, idx, ext) 목록은 golden 과 일치), `parse_ids_cases`(`"https://arca.live/e/54566?p=1 123"` → `[54566, 123]`, `"고양이"` → None, golden 전 항목), `query_params`(`list_query("weekly", 3)` = p=3, rank=weekly; `search_query("고양이","tag",2)` = target=tag, keyword=고양이, p=2), `redirect_to_login_is_login_required`(wiremock 302 → `/u/login`), `session_file_compat`(1.3.0 형식 JSON 을 load → save → 다시 load 같음; 깨진 파일은 None).
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-core --test arca` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현** — 정규식은 `dccon/arca.py` 그대로. 테스트를 위해 `fetch_*` 는 내부에서 `base: &str` 를 받는 `_at` 변형을 두고 공개 함수는 `ARCA_BASE` 로 부른다.
- [ ] **Step 4: 통과 확인** — Expected: 6 passed.
- [ ] **Step 5: Commit** — `git commit -m "core: 아카콘 목록·검색·상세와 세션 파일"`

---

### Task 10: core — 다운로더

**Files:**
- Create: `crates/core/src/downloader.rs`, `crates/core/tests/downloader.rs`

**Interfaces:**
- Consumes: `Client`, `ImageCache`, `Package`, naming 함수
- Produces:
  - `pub struct DownloadOptions { pub save_main_image: bool, pub write_meta: bool }`
  - `#[derive(Serialize)] pub struct DownloadResult { pub package_idx: u64, pub package_title: String, pub dest: PathBuf, pub saved: u32, pub skipped: u32, pub failed: Vec<(String, String)> }`
  - `pub fn sniff_ext(data: &[u8], default: &str) -> String` (png/gif/jpg/webp)
  - `pub async fn download_package(client: &Client, cache: &ImageCache, package: &Package, dest_root: &Path, only_sorts: Option<&[u32]>, opts: &DownloadOptions, progress: &(dyn Fn(usize, usize, &str) + Send + Sync), cancel: &CancellationToken) -> Result<DownloadResult>`
  - 동작은 `dccon/downloader.py` 그대로: `_main` 은 캐시 ext `jpg` 로 받고 실제 확장자는 판별, 항목은 있으면 건너뜀, `.part` → rename, 항목 실패는 모으고 계속, 취소는 `Err(Cancelled)`, `_meta.json` 은 필드 순서 `package_idx,title,description,seller,reg_date,tags,items[{sort,title,ext,file}]`, 2칸 들여쓰기, 한글 그대로, 전체 항목 기준.

- [ ] **Step 1: 실패하는 테스트** (임시 폴더 + wiremock, 항목 path 는 wiremock 전체 URL):
  - `saves_and_skips_existing`: 3개 중 1개 미리 존재 → saved 2(+_main 1), skipped 1, 파일명 `01_안녕.png` 형식.
  - `leftover_part_file_is_not_skipped`: `01_안녕.png.part` 만 있으면 다시 받아 `01_안녕.png` 생성, saved 에 셈.
  - `main_image_ext_sniffed`: GIF 바이트 → `_main.gif`.
  - `only_sorts_filters`: `Some(&[2])` → 2번만, 자릿수는 전체 기준.
  - `failure_is_collected`: 한 항목 404 → failed 에 (`02_….png`, 메시지), 나머지 저장.
  - `meta_json_matches_python`: 픽스처 패키지로 만든 `_meta.json` 이 `golden/meta.json` 과 바이트 일치.
  - `cancel_stops`: 시작 전 cancel → `Err(Cancelled)`.
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-core --test downloader` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인** — Expected: 7 passed.
- [ ] **Step 5: Commit** — `git commit -m "core: 다운로더"`

---

### Task 11: core — updater (조회·고르기·받기)

**Files:**
- Create: `crates/core/src/updater/mod.rs`, `crates/core/tests/updater_fetch.rs`

**Interfaces:**
- Produces:
  - 상수 `REPO`, `LATEST_URL`, `RELEASES_PAGE` (Global Constraints 값)
  - `pub struct Asset { name, url: String, size: u64, digest: String }`, `pub struct Release { tag, name, notes, page_url: String, assets: Vec<Asset> }`, `impl Release { pub fn from_api(v: &Value) -> Release; pub fn version(&self) -> String /* tag 에서 v/V 제거 */ }`
  - `pub fn parse_version(text: &str) -> Vec<u32>` (끝 0 제거), `pub fn is_newer(remote: &str, local: &str) -> bool`
  - `pub fn pick_asset(r: &Release) -> Option<&Asset>` — `.exe` 로 끝나고 url 있고 이름(소문자)에 `macos`,`darwin`,`mac-`,`-mac.` 없음, `win` 포함 우선.
  - `pub fn release_name(version: &str) -> String` → `dccon-downloader-{version}.exe`
  - `pub fn http_client(version: &str) -> reqwest::Client` (UA `dccon-downloader/{version}`, Accept `application/vnd.github+json`)
  - `pub async fn fetch_latest(http: &reqwest::Client, url: &str) -> Result<Option<Release>>` — 404 → None; 403 + `x-ratelimit-remaining: 0` → `Update("GitHub 요청 한도를 넘었습니다. 잠시 뒤 다시 시도하세요.")`; 그 밖 ≥400 → `Update("릴리즈 정보를 가져오지 못했습니다. (HTTP {code})")`; 연결 실패 → `Update("GitHub 에 연결하지 못했습니다. ({이름})")`
  - `pub async fn download(http: &reqwest::Client, asset: &Asset, staging: &Path, progress: &(dyn Fn(u64, u64) + Send + Sync), cancel: &CancellationToken) -> Result<PathBuf>` — `staging/<name>.part` 로 스트리밍, 크기 불일치 `Update("받은 파일 크기가 맞지 않습니다. 다시 시도하세요.")`, sha256 불일치 `Update("받은 파일이 손상되었습니다. (SHA-256 불일치)")`, 실패 시 `.part` 삭제, 성공 시 rename 후 경로 반환.

- [ ] **Step 1: 실패하는 테스트** — `version_matches_python`(golden/version.json), `pick_asset_cases`(win exe·mac zip·win64 zip·pyz 섞인 목록 → win exe; `dccon-downloader-2.0.0-macos.exe` 같은 것 제외; exe 없으면 None), `fetch_latest_404_is_none`, `fetch_latest_rate_limited_message`, `fetch_latest_connection_error_message`(닫힌 포트 → 메시지가 `GitHub 에 연결하지 못했습니다.` 로 시작), `download_verifies_size_and_digest`(정상 / 크기 틀림 / digest 틀림 각각, 실패 시 `.part` 없음).
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-core --test updater_fetch` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인** — Expected: 6 passed.
- [ ] **Step 5: Commit** — `git commit -m "core: 업데이트 조회와 받기"`

---

### Task 12: core — updater (교체·정리·이름 정리)

**Files:**
- Create: `crates/core/src/updater/apply.rs`, `crates/core/tests/updater_apply.rs`

**Interfaces:**
- Consumes: `Paths`, `parse_version`
- Produces:
  - `pub fn apply(new_exe: &Path, current_exe: &Path) -> Result<()>` — `current` → `<current 파일명>.old`(이미 있으면 먼저 삭제), `new` → `current` (rename 실패 시 copy+remove), 두 번째 단계 실패 시 `.old` 를 되돌리고 `Update("업데이트를 적용하지 못했습니다. ({이유})")`. 첫 단계 실패 = 쓰기 권한 없음 → `Update` 이며 호출 쪽은 릴리즈 페이지를 연다.
  - `pub const MIGRATION_MARKER: &str = "MIGRATED.txt"`
  - `pub fn cleanup_after_start(exe: &Path, paths: &Paths) -> Option<String>` — `<exe>.old` 삭제, exe 옆 `_internal` 이 `MIGRATED.txt` 하나만 가지면 삭제, `paths.code` 삭제, `paths.update` 안의 `last_error.log` 를 제외한 항목 삭제, `last_error.log` 는 (UTF-8 BOM 제거 후) 내용을 돌려주고 삭제.
  - `pub fn tidy_sibling_builds(exe: &Path, version: &str, exe_version: &dyn Fn(&Path) -> Option<String>, recycle: &dyn Fn(&Path) -> bool) -> (PathBuf, Vec<String>)` — 스펙 7.4-7 규칙. 이름 패턴 `^dccon-downloader-(\d+\.\d+\.\d+)(?:-win64)?\.exe$`(대소문자 무시), 로컬 이름 `디시콘 다운로더.exe`. 반환은 (지금 exe 경로, 치운 파일 이름들).
  - `#[cfg(windows)] pub fn exe_file_version(path: &Path) -> Option<String>` (`windows-sys` 의 `GetFileVersionInfoW`/`VerQueryValueW`, `X.Y.Z`), `pub fn recycle(path: &Path) -> bool` (`trash::delete`)

- [ ] **Step 1: 실패하는 테스트** (임시 폴더, 가짜 exe 는 바이트 파일):
  - `apply_replaces_and_keeps_old`: 적용 뒤 current 내용 = new, `.old` = 옛 내용.
  - `apply_rolls_back_when_new_missing`: new 경로가 없음 → Err, current 내용 그대로, `.old` 없음.
  - `cleanup_removes_migration_leftovers`: `.old`, `_internal/MIGRATED.txt`, `code/1.2.5/`, `update/v1/` 있음 → 모두 사라짐.
  - `cleanup_keeps_real_internal`: `_internal` 에 다른 파일이 있으면 그대로.
  - `cleanup_returns_last_error`: BOM 붙은 `update/last_error.log` → 내용 반환, 파일 삭제.
  - `tidy_renames_release_named_exe`: exe `dccon-downloader-2.0.1.exe`, 같은 폴더에 `dccon-downloader-2.0.0.exe`, `my.exe` → (`디시콘 다운로더.exe`, [`dccon-downloader-2.0.0.exe`]), `my.exe` 남음.
  - `tidy_keeps_newer_local_name`: `디시콘 다운로더.exe` 의 exe_version 이 `9.0.0` → 이름 바꾸지 않음.
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-core --test updater_apply` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인** — Expected: 7 passed. 그리고 `cargo test --workspace` 전체 통과.
- [ ] **Step 5: Commit** — `git commit -m "core: exe 교체, 이전 흔적 정리, 이름 정리"`

---

### Task 13: 앱 — 상태, 커맨드, 다운로드 큐

**Files:**
- Create: `src-tauri/src/state.rs`, `src-tauri/src/dto.rs`, `src-tauri/src/commands.rs`, `src-tauri/src/queue.rs`
- Modify: `src-tauri/src/main.rs` (상태 등록, 커맨드 등록)

**Interfaces:**
- Consumes: core 전부
- Produces:
  - `pub struct AppState { paths: Paths, settings: RwLock<Settings>, dccon: Client, arca: Client, images: ImageCache, meta: MetaCache, nav: RwLock<Arc<Semaphore>>, thumb: RwLock<Arc<Semaphore>>, view_gen: AtomicU64, queue: queue::Queue }` — `fn client(&self, site: Site) -> &Client`, `fn apply_concurrency(&self, n: u32)` (세마포어를 새로 만들어 교체)
  - `dto.rs`: `#[derive(Serialize)] pub struct CmdError { kind: &'static str, message: String }` (`From<core::Error>`), `pub struct ListPage { items: Vec<Brief>, page: u32, pages: u32, total: Option<u64> }`, `#[derive(Deserialize)] pub struct Job { id: u64, title: String, sorts: Option<Vec<u32>> }`, `pub struct ReleaseInfo { version, notes, page_url: String, can_apply: bool }`, `pub struct CacheStats { files: u64, bytes: u64 }`
  - 커맨드(전부 `Result<_, CmdError>`): `get_settings() -> Settings`, `save_settings(settings: Settings)`(저장 + 동시 수 반영), `begin_view() -> u64`, `list_top(kind: TopKind) -> ListPage`, `list_all(page: u32) -> ListPage`, `list_arca(kind: String, page: u32) -> ListPage`, `search(site: Site, word: String, search_type: String, page: u32) -> ListPage`, `open_package(site: Site, id: u64) -> Package`(디시콘은 메타 캐시 우선·저장, 아카콘은 캐시 안 함, 둘 다 `remember`), `parse_input(site: Site, text: String) -> Query`(아카콘은 `parse_ids` → Ids, 아니면 Search), `enqueue(site: Site, jobs: Vec<Job>)`, `pause_queue(paused: bool)`, `cancel_queue()`, `open_folder()`, `cache_stats() -> CacheStats`, `clear_cache()`
  - `queue.rs`: `pub struct Queue`, `impl Queue { pub fn start(&self, app: AppHandle, state: Arc<AppState>, site: Site, jobs: Vec<Job>) -> Result<(), CmdError>; pub fn pause(&self, on: bool); pub fn cancel(&self) }` — 대상 폴더 `download_dir`(아카콘이면 `/arcacon`)를 먼저 만들고, 실패하면 `CmdError { kind: "io", message: "폴더를 만들 수 없습니다.\n{이유}" }`. 패키지마다 다운로드 세마포어를 잡고 `open_package` 와 같은 로딩 후 `download_package`. 일시정지는 해당 사이트 클라이언트 pause.
  - 이벤트 이름과 페이로드: `queue-started {jobs:[{id,title}]}`, `queue-progress {id, done, total, name}`, `queue-package-done {id, title, saved, skipped, failed:[[name,msg]]}`, `queue-error {id, message}`(취소면 `중단됨`), `queue-finished {saved, skipped, failed}`

- [ ] **Step 1: 실패하는 테스트** — `src-tauri/src/queue.rs` 안 `#[cfg(test)]`: `enqueue_fails_when_dest_cannot_be_created`(download_dir 를 기존 **파일** 경로 아래로 지정 → Err kind `io`, 메시지가 `폴더를 만들 수 없습니다.` 로 시작, 이벤트 없음). 큐 실행 로직은 `fn dest_dir(settings: &Settings, site: Site) -> PathBuf` 와 `fn prepare_dest(..) -> Result<PathBuf, CmdError>` 로 빼서 AppHandle 없이 테스트한다. `dest_dir_for_arca`(`.../arcacon`).
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-downloader` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인** — Expected: 2 passed, `cargo build -p dccon-downloader` 성공.
- [ ] **Step 5: Commit** — `git commit -m "앱: 상태·커맨드·다운로드 큐"`

---

### Task 14: 앱 — img:// 프로토콜

**Files:**
- Create: `src-tauri/src/imgproto.rs`
- Modify: `src-tauri/src/main.rs` (`register_asynchronous_uri_scheme_protocol("img", ...)`)

**Interfaces:**
- Consumes: `AppState`(images, thumb 세마포어, view_gen, client)
- Produces:
  - 요청 형식 `?u=<URL 인코딩된 원본 주소>&e=<ext>&g=<세대>&s=<dccon|arca>`. 프론트 주소: 윈도우 `http://img.localhost/?...`, 그 밖 `img://localhost/?...`.
  - `pub(crate) async fn serve(state: &AppState, query: &str, range: Option<&str>) -> (u16, Vec<(String, String)>, Vec<u8>)` — 순수하게 테스트 가능한 핵심. 캐시 있으면 200; 없고 세대가 다르면 204; 세마포어 획득 뒤 세대 재확인; 받으면 200; 실패 502. `Content-Type`: png `image/png`, gif `image/gif`, jpg/jpeg `image/jpeg`, webp `image/webp`, mp4 `video/mp4`. `Range: bytes=a-b` 면 206 + `Content-Range`. 모든 응답에 `Cache-Control: max-age=31536000`.

- [ ] **Step 1: 실패하는 테스트** (`#[cfg(test)]`, 임시 캐시 + wiremock): `serves_cached_without_network`, `stale_generation_is_dropped`(세대 1 요청, 상태 세대 2 → 204, 서버 요청 0회), `fetches_and_caches`, `range_request_for_mp4`(`bytes=0-1` → 206, 본문 2바이트), `upstream_error_is_502`.
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-downloader imgproto` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현** — 핸들러는 `tauri::async_runtime::spawn` 안에서 `serve` 를 불러 `responder.respond` 한다.
- [ ] **Step 4: 통과 확인** — Expected: 5 passed.
- [ ] **Step 5: Commit** — `git commit -m "앱: img:// 프로토콜 (세대 단위 썸네일 취소)"`

---

### Task 15: 화면 — 테마, 셸, API 래퍼

**Files:**
- Create: `ui/src/lib/api.ts`, `ui/src/lib/theme.css`, `ui/src/lib/stores/settings.ts`, `ui/src/lib/components/{Sidebar,SearchBar,LoadingLine}.svelte`
- Modify: `ui/src/App.svelte`, `ui/src/main.ts`, `ui/package.json`(vitest, `@tauri-apps/api@2`, `@tauri-apps/plugin-dialog@2`, `@tauri-apps/plugin-opener@2`)

**Interfaces:**
- Consumes: Task 13 커맨드·DTO 이름 그대로
- Produces:
  - `api.ts`: Rust DTO 와 같은 snake_case TS 타입(`Settings`, `Brief`, `Item`, `Package`, `ListPage`, `Query`, `Job`, `ReleaseInfo`, `CacheStats`, `CmdError`, `Site = "dccon"|"arca"`), 커맨드마다 같은 이름의 camelCase 함수(`getSettings`, `saveSettings`, `beginView`, `listTop`, `listAll`, `listArca`, `search`, `openPackage`, `parseInput`, `enqueue`, `pauseQueue`, `cancelQueue`, `openFolder`, `cacheStats`, `clearCache`, 이후 태스크의 커맨드도 여기 추가), `imgUrl(url: string, ext: string, gen: number, site: Site): string`, `onEvent<T>(name, cb)`
  - `theme.css`: `dccon/gui/theme.py` 의 `LIGHT`/`DARK` 토큰을 `--bg`, `--glow` 처럼 밑줄을 하이픈으로 바꾼 CSS 변수로. `:root[data-theme="light"|"dark"]`, `system` 은 `@media (prefers-color-scheme: dark)`. `:root[data-reduce-motion]` 이면 모든 transition/animation 0.
  - `stores/settings.ts`: `settings` writable + `loadSettings()`, `updateSettings(patch)` (저장 후 `data-theme`·`data-reduce-motion` 반영, `getCurrentWindow().setTheme`)
  - 레이아웃: 사이드바 210px(로고+`dccon` 글자 = 홈, 디시콘/아카콘 세그먼트, 디시콘 메뉴 `인기: 일간 인기/주간 인기/월간 인기`, `둘러보기: 공식/전체 목록`, 아카콘 메뉴 `아카콘: 최신/주간 인기/월간 인기`, 아래 `폴더 열기`, `설정`), 검색줄(검색 종류 select + 입력, placeholder `검색어, 패키지 ID 또는 디시콘 URL`), 2px 로딩 줄. 여백·크기는 `main_window.py`, 스타일은 `theme.py` 의 스타일시트를 따른다.

- [ ] **Step 1: 실패하는 테스트** — `ui/src/lib/api.test.ts`: `imgUrl` 이 윈도우(`navigator.userAgent` 에 Windows 를 흉내)에서 `http://img.localhost/?u=https%3A%2F%2Fa%2Fb.gif&e=gif&g=3&s=dccon`, 그 밖에서 `img://localhost/?...` 를 만든다.
- [ ] **Step 2: 실패 확인** — Run: `npm --prefix ui test -- --run` / Expected: FAIL.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인과 화면 확인** — Run: `npm --prefix ui test -- --run` (PASS), `cargo tauri dev` 로 라이트/다크/시스템 전환 시 색이 바뀌는지 본다.
- [ ] **Step 5: Commit** — `git commit -m "화면: 테마 토큰, 사이드바, 검색줄"`

---

### Task 16: 화면 — 목록·패키지·그리드·이동 기록·페이지

**Files:**
- Create: `ui/src/lib/stores/{view,history,selection}.ts`, `ui/src/lib/stores/{history,selection}.test.ts`, `ui/src/lib/components/{Heading,Grid,Card,Thumb,PageJump}.svelte`
- Modify: `ui/src/App.svelte`

**Interfaces:**
- Consumes: `api.ts`, `settings` store
- Produces:
  - `type View = {kind:"top", tab:"day"|"week"|"month"|"official"} | {kind:"all", page:number} | {kind:"arca", tab:"new"|"weekly"|"monthly", page:number} | {kind:"search", site:Site, word:string, type:string, page:number} | {kind:"package", site:Site, id:number}`
  - `history.ts`: `createHistory()` → `{ push(v: View, scrollY: number), back(): {view, scrollY}|null, forward(): ...|null, canBack, canForward }` (push 하면 앞쪽 기록 삭제)
  - `selection.ts`: `createSelection()` → `{ toggle(key), setAll(keys, on), clear(), has(key), count }` (store)
  - `view.ts`: `showView(v: View, opts?: {record?: boolean})` — `beginView()` 로 세대를 받고, 맞는 커맨드를 불러 상태(`rows`/`package`/`page`/`pages`/`total`/`loading`/`error`)를 채움. 응답이 왔을 때 세대가 바뀌었으면 버림. `LoginRequired` 는 `loginNeeded` store 를 true 로.
  - `Card.svelte`: 폭 156, 썸네일 144(`cards.py`), 제목·부제 한 줄 말줄임, 클릭은 선택 토글, 더블클릭은 `package` 로 이동(목록일 때), 선택 시 체크 표시(`check.svg`). `Thumb.svelte`: `imgUrl` 로 로드, `animate_gifs` 꺼짐이면 첫 프레임을 canvas 에 그림, mp4 는 poster(`item.thumb`), 켜짐이면 `<video autoplay loop muted playsinline>`.
  - `Heading.svelte`: 크럼, 결과 수(전체 목록은 `총 92,133개` 처럼 천 단위 쉼표), `‹ n / N ›`(전체 목록·아카콘·검색에서만 보임), 가운데 누르면 `PageJump`, 패키지 화면에서 작가·개수와 안내 `저장할 디시콘을 선택한 뒤 다운로드하세요.`
  - 입력창 Enter: `parseInput` → Ids 1개면 패키지 열기, 여러 개면 `enqueue(site, ids.map(id => ({id, title:"#"+id, sorts:null})))`, Search 면 검색(빈 문자열은 무시).
  - 마우스 button 3 = 뒤로, 4 = 앞으로. 로고 = 지금 사이트의 홈 탭.

- [ ] **Step 1: 실패하는 테스트** — `history.test.ts`: push A,B,C → back 은 B, back 은 A, forward 는 B, 여기서 push D → canForward false; 스크롤 위치가 함께 돌아옴. `selection.test.ts`: setAll([1,2,3], true) → count 3, toggle(2) → count 2, clear → 0.
- [ ] **Step 2: 실패 확인** — Run: `npm --prefix ui test -- --run` / Expected: FAIL.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인과 화면 확인** — 테스트 PASS. `cargo tauri dev` 에서: 일간 인기 그리드 → 패키지 더블클릭 → 뒤로(마우스 4) → 전체 목록 `1 / 6142` → 다음 → 37페이지로 이동 → 패키지 열고 뒤로 하면 37페이지, 검색 `멍뭉`, 입력 `12345` 가 패키지를 연다.
- [ ] **Step 5: Commit** — `git commit -m "화면: 목록·패키지·그리드·이동 기록"`

---

### Task 17: 화면 — 독, 큐 바, 글로우

**Files:**
- Create: `ui/src/lib/stores/queue.ts`, `ui/src/lib/stores/queue.test.ts`, `ui/src/lib/components/{Dock,ActionBar,QueueBar,Glow}.svelte`

**Interfaces:**
- Consumes: Task 13 이벤트, `selection`, `view`
- Produces:
  - `queue.ts`: `createQueue()` → 상태 `{ running, paused, jobs: Map<id, {title, done, total, name, status: string|null}>, overall: {done, total}, summary: string|null }`, 메서드 `onStarted`, `onProgress`, `onPackageDone`, `onError`, `onFinished`, `dismiss()`. 패키지 완료 문구 `저장 N  건너뜀 N  실패 N`(0 인 항목 생략, 사이는 공백 두 칸), 오류 `오류: {메시지}`, 끝 요약 `완료 · 저장 N개, 건너뜀 N개, 실패 N개`(0 인 뒤 두 항목 생략) — 1.3.0 `_on_all_done` 문구와 같게.
  - `ActionBar`: `N개 선택`, `선택 해제`, `전체 선택`, `다운로드`(선택 0 이면 비활성). 다운로드는 패키지 화면이면 `{id, title, sorts: 선택한 sort}` 한 건, 목록이면 선택한 패키지마다 `sorts: null`.
  - `QueueBar`: 전체 진행 막대, 일시정지/재개, 취소, 패키지별 내역 펼치기, 끝나면 닫기(→ `dismiss`, 선택 줄로).
  - `Dock`: 최대 폭 620, 그리드 위에 떠 있음, ▼/▲ 손잡이(44x20)로 손잡이만 남기고 아래로 260ms 슬라이드, 받기 시작하면 자동으로 다시 보임. 그리드 아래에 독 높이만큼 여백.
  - `Glow`: 받는 동안 바닥에서 `--glow` 색이 번지는 애니메이션(`glow.py` 의 높이·색 따라), 독 아래에 깔림.

- [ ] **Step 1: 실패하는 테스트** — `queue.test.ts`: 두 작업 시작 → progress(1: 2/4), progress(2: 1/2) → overall 3/6; packageDone(saved 3, skipped 1, failed []) → 상태 `저장 3  건너뜀 1`; finished(saved 5, skipped 0, failed 2) → `완료 · 저장 5개, 실패 2개`.
- [ ] **Step 2: 실패 확인** — Run: `npm --prefix ui test -- --run` / Expected: FAIL.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인과 화면 확인** — 테스트 PASS. `cargo tauri dev` 에서 패키지 두 개를 받아 진행·일시정지·취소·숨기기·글로우를 확인하고, 저장 폴더 결과가 README 의 `저장 결과` 구조와 같은지 본다.
- [ ] **Step 5: Commit** — `git commit -m "화면: 다운로드 독·큐·글로우"`

---

### Task 18: 화면과 앱 — 설정, 업데이트, 페이지 이동, 단축키

**Files:**
- Create: `ui/src/lib/components/{Modal,SettingsDialog,UpdateDialog}.svelte`
- Modify: `src-tauri/src/commands.rs`(업데이트 커맨드), `src-tauri/src/state.rs`(받아 둔 업데이트 경로), `ui/src/lib/api.ts`, `ui/src/App.svelte`

**Interfaces:**
- Consumes: Task 11·12 updater, `settings` store
- Produces:
  - 커맨드: `check_update(manual: bool) -> Option<ReleaseInfo>` (새 버전 없으면 None; manual=false 이면 `check_updates` 꺼짐 또는 `skipped_version` 과 같을 때 None; `can_apply` = 윈도우 && 개발 실행 아님), `download_update() -> ()` (`update-progress {done,total}` 이벤트, 받은 경로를 상태에 보관), `apply_update() -> ()` (`apply` 후 새 exe 실행, `app.exit(0)`; 첫 단계 실패면 `CmdError{kind:"update"}` 를 돌려주고 프론트가 릴리즈 페이지를 연다), `skip_version(version: String)`, `open_release_page()`, `take_last_error() -> Option<String>`
  - 디버그 빌드(`cfg(debug_assertions)`)에서만 환경변수 `DCCON_UPDATE_URL` 이 있으면 `LATEST_URL` 대신 쓴다(Task 22 실측용). 릴리즈 빌드에는 이 분기가 없다.
  - `SettingsDialog`: 1.3.0 `settings_dialog.py` 의 항목·문구·순서 그대로(저장 폴더 + 찾아보기(dialog 플러그인), 동시 다운로드 수 1~8, 대표 이미지 저장, `_meta.json` 저장, GIF 미리보기 움직이기, 모션 줄이기, 테마 `시스템 설정 따르기/라이트/다크`, 시작할 때 새 버전 확인, 캐시 용량 표시와 `캐시 비우기`, `업데이트 확인`).
  - `UpdateDialog`: 1.3.0 `update_dialog.py` 의 문구·버튼(받기, 이 버전 건너뛰기, 나중에), 변경 내역(마크다운을 텍스트로), 진행 막대, `can_apply` 가 false 면 `릴리즈 페이지 열기`.
  - `Ctrl+L`(맥 `Meta+L`): 입력창 포커스 + 전체 선택. 모달은 Esc 로 닫힘.

- [ ] **Step 1: 실패하는 테스트** — `src-tauri` `#[cfg(test)]`: `startup_check_respects_skip`(순수 함수 `fn should_notify(settings: &Settings, manual: bool, current: &str, remote: &str) -> bool` — 자동이면 `check_updates=false` 일 때 false, `skipped_version == remote` 일 때 false; 수동이면 새 버전일 때만 true).
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-downloader should_notify` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인과 화면 확인** — 테스트 PASS. dev 에서 설정 값을 바꾸고 재시작해도 남는지, 캐시 비우기 뒤 용량 0, `업데이트 확인`이 지금 최신(1.3.0) 기준으로 "새 버전" 창을 띄우지 않는지(2.0.0 > 1.3.0) 본다.
- [ ] **Step 5: Commit** — `git commit -m "화면: 설정·업데이트·단축키"`

---

### Task 19: 아카콘 로그인과 사이트 전환

**Files:**
- Create: `src-tauri/src/login.rs`, `ui/src/lib/components/LoginPrompt.svelte`
- Modify: `src-tauri/src/commands.rs`, `src-tauri/src/main.rs`(시작 시 세션 적용), `ui/src/lib/api.ts`, `ui/src/App.svelte`

**Interfaces:**
- Consumes: Task 2 의 결정, `ArcaSession`, `Client::set_session`
- Produces:
  - 커맨드 `arca_status() -> bool`(세션 파일 존재), `arca_login() -> ()`(로그인 창 또는 브라우저를 띄우고 즉시 반환, 끝나면 `login-finished {ok, message}`), `arca_logout()`(세션 삭제, 쿠키 비움)
  - 로그인 성공 기준: 꺼낸 세션으로 `GET https://arca.live/e/` 의 최종 URL 에 `/u/login` 이 없음. 실패 문구 `로그인되지 않았습니다. 로그인을 마친 뒤 창을 닫아 주세요.`
  - Task 2 결정이 "Chrome CDP" 면 `login.rs` 는 `dccon/arca_login.py` 를 그대로 옮긴다(브라우저 찾기 순서, 프로필 `DATA_DIR/arca_browser`, 창 닫힘 대기 600초, headless 재실행 + `/json/version` + `Storage.getCookies`, UA 의 `HeadlessChrome` → `Chrome`, `tokio-tungstenite` 로 CDP).
  - 사이트 전환 흐름(1.3.0 과 같음): 아카콘을 눌렀는데 세션이 없으면 `LoginPrompt` 를 띄우고 세그먼트는 디시콘으로 남김; 세션이 있으면 아카콘 `최신` 1페이지와 검색 종류 목록(아카콘 것)으로 바꿈; 목록이 `login_required` 로 실패하면 세션을 지우고 다시 `LoginPrompt`.

- [ ] **Step 1: 실패하는 테스트** — `login.rs` `#[cfg(test)]`: `session_from_cookies`(쿠키 목록에서 도메인이 `arca.live` 로 끝나는 것만 남기고 UA 를 붙인 `ArcaSession` 을 만드는 순수 함수 `fn to_session(ua: &str, cookies: &[(name, value, domain, path)]) -> ArcaSession`; `example.com` 쿠키 제외).
- [ ] **Step 2: 실패 확인** — Run: `cargo test -p dccon-downloader login` / Expected: 컴파일 실패.
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인과 실사용 확인** — 테스트 PASS. 사용자에게 dev 에서 로그인을 부탁해 아카콘 최신 목록·검색·패키지(움직이는 mp4 포함)·다운로드(`arcacon/` 아래)를 확인한다. 1.3.0 이 남긴 `arca_session.json` 이 있으면 먼저 그걸로 시도되는지도 본다.
- [ ] **Step 5: Commit** — `git commit -m "아카콘 로그인과 사이트 전환"`

---

### Task 20: 시작 처리 — WebView2 안내, 로그, 정리, 시작 업데이트 확인

**Files:**
- Modify: `src-tauri/src/main.rs`, `src-tauri/Cargo.toml`(tracing, tracing-appender, windows-sys)
- Modify: `ui/src/App.svelte`

**Interfaces:**
- Consumes: `cleanup_after_start`, `tidy_sibling_builds`, `exe_file_version`, `recycle`, `check_update`
- Produces: 시작 순서 — (1) `DATA_DIR` 생성, `logs/` 에 tracing 파일 로그, panic hook 이 같은 파일에 기록; (2) 윈도우·릴리즈 실행이면 `cleanup_after_start` → 돌려받은 오류 문구를 상태에 보관(`take_last_error` 로 프론트가 표시), `tidy_sibling_builds`(치운 게 있으면 로그); (3) 아카콘 세션 적용; (4) Tauri 실행. 창 만들기가 실패하고 WebView2 가 없으면(`tauri::webview_version()` 실패) `MessageBoxW` 로 `WebView2 런타임이 필요합니다.\nhttps://developer.microsoft.com/microsoft-edge/webview2/ 에서 설치한 뒤 다시 실행해 주세요.` 를 띄우고 종료. 프론트는 첫 화면이 뜬 뒤 `take_last_error` 를 확인해 있으면 알림, 그리고 `check_update(false)` — 오류는 조용히 로그만.

- [ ] **Step 1: 확인 시나리오 작성과 실행** — 릴리즈 빌드(`cargo tauri build --no-bundle`)를 임시 폴더에 `dccon-downloader-2.0.0.exe` 로 복사하고 옆에 `_internal/MIGRATED.txt`, `dccon-downloader-1.9.0.exe` 를 둔 뒤, `%LOCALAPPDATA%/DcconDownloader/update/last_error.log` 에 `테스트 오류` 를 쓴다. 실행.
Expected: 이름이 `디시콘 다운로더.exe` 로 바뀜, `_internal` 과 1.9.0 사라짐(휴지통), 앱이 `테스트 오류` 알림을 띄움, 로그 파일 생김.
- [ ] **Step 2: 오프라인 시작** — 네트워크 어댑터를 끄거나 hosts 로 `api.github.com` 을 막고 실행. Expected: 창이 정상으로 뜨고 업데이트 관련 창이 없음.
- [ ] **Step 3: Commit** — `git commit -m "시작 처리: 로그, 이전 흔적 정리, 업데이트 확인"`

---

### Task 21: 빌드 스크립트, 맥 워크플로, CLAUDE.md, release 스킬

**Files:**
- Modify (전면 교체): `build.ps1`, `build.sh`, `.claude/CLAUDE.md`, `.claude/skills/release/SKILL.md`
- Create: `.github/workflows/macos.yml`

**Interfaces:**
- Produces:
  - `build.ps1 [-Clean] [-Console] [-Release]`: `npm --prefix ui ci` → `cargo tauri build --no-bundle`(`-Console` 이면 `--features console`) → `dist/dccon-downloader.exe` 복사. `-Release` 면 `dist/release/dccon-downloader-<버전>.exe` 와 `dist/release/dccon-downloader-<버전>-win64.zip`(안에 `dccon-downloader/dccon-downloader.exe`, `dccon-downloader/_internal/MIGRATED.txt`; 표식 내용은 `이전 버전에서 넘어올 때 쓰는 빈 폴더입니다. 지워도 됩니다.`). 끝에 `완료: <경로> (<MB>)` 를 찍는다. 버전은 `cargo metadata` 에서 읽는다.
  - `build.sh [--clean]`: `cargo tauri build --bundles app` → `dist/디시콘 다운로더.app`, `dist/dccon-downloader-<버전>-macos.zip`(`ditto -c -k --keepParent`).
  - `macos.yml`: `workflow_dispatch`, `macos-latest`, Node·Rust 설치, `./build.sh`, zip 을 아티팩트로 업로드.
  - CLAUDE.md: 코드 범위 `crates/`, `src-tauri/`, `ui/`, `Cargo.toml`, `build.ps1`, `build.sh`. 커밋 전 1) `cargo test --workspace` 와 `npm --prefix ui test -- --run` 2) `./build.ps1 -Clean` 3) `dist\dccon-downloader.exe` 하나로 기존 실행 확인 스크립트(`alive=True window=디시콘 다운로더`). `2>&1` 금지 주의는 유지. "알아둘 것"은 코드 업데이트 설명을 지우고, 대신 이전용 zip 과 `MIGRATED.txt` 규칙, 데이터 경로·형식 호환이 배포된 앱과의 약속이라는 점, 저장소 공개 유지, `dist/` 규칙을 적는다.
  - release 스킬: 버전 올리기(`Cargo.toml` 워크스페이스 버전 한 곳), `./build.ps1 -Clean -Release`, 맥 zip 은 Actions 아티팩트에서, 세 자산을 올리는 절차, `.pyz` 없음.

- [ ] **Step 1: 스킬 읽기** — 지금 `.claude/skills/release/SKILL.md` 를 읽고 남길 절차(태그, 노트, gh 명령)를 확인한다.
- [ ] **Step 2: 파일 작성.**
- [ ] **Step 3: 빌드 확인** — Run: `./build.ps1 -Clean -Release` / Expected: `완료:` 줄, `dist/release/` 에 두 파일, exe 15MB 이하. 새 CLAUDE.md 의 실행 확인 → `alive=True window=디시콘 다운로더`.
- [ ] **Step 4: 맥 워크플로** — 브랜치를 푸시해도 되는지 사용자에게 묻고, 허락하면 `gh workflow run macos.yml --ref rust` 후 아티팩트가 생기는지 본다. 허락이 없으면 이 단계는 건너뛰었다고 보고한다.
- [ ] **Step 5: Commit** — `git commit -m "빌드 스크립트·맥 워크플로·작업 규칙을 Rust 기준으로"`

---

### Task 22: 이전 경로 실측과 외형 비교

**Files:**
- Create (저장소 밖, 스크래치): 이전 테스트 폴더와 스크린샷

**Interfaces:**
- Consumes: Task 21 산출물, 파이썬 1.3.0 빌드(`git worktree add <스크래치>/v130 v1.3.0` 에서 `./build.ps1 -Clean`, `./build.ps1 -OneFile`)

- [ ] **Step 1: onefile 이전** — 1.3.0 onefile exe 를 임시 폴더에 두고, 파이썬 `updater._APPLY_SCRIPT` 를 `apply_update.ps1` 로 저장(UTF-8 BOM)한 뒤, `source/` 에 Rust `dccon-downloader-2.0.0.exe` 를 1.3.0 exe 와 같은 이름으로 두고 1.3.0 앱을 띄운 상태에서 `-WaitPids <pid> -Source <source> -Target <폴더> -Exe <exe> -Log <log>` 로 실행한 뒤 1.3.0 앱을 닫는다.
Expected: 로그 없음, 같은 경로에서 Rust 앱 창 `디시콘 다운로더` 가 뜸.
- [ ] **Step 2: onedir 이전** — 1.3.0 onedir 폴더에 대해 `uv run python -c "from dccon.updater import _extract_onedir; ..."` 로 Rust `-win64.zip` 을 풀어 검사 통과를 확인하고, 그 결과 폴더를 `-Source` 로 같은 스크립트 실행.
Expected: `_internal` 이 표식만 남았다가 Rust 앱 첫 실행 뒤 사라짐, 창이 뜸, 기존 `settings.json`·캐시가 그대로 쓰임(설정 화면 값, 이미 본 썸네일이 네트워크 없이 뜸).
- [ ] **Step 3: Rust → Rust 업데이트** — 버전을 임시로 1.9.9 로 낮춘 빌드를 만들어, `LATEST_URL` 대신 로컬 목 서버를 가리키는 디버그 환경변수 `DCCON_UPDATE_URL`(디버그 빌드에서만 읽음, Task 18 에서 추가)로 2.0.0 자산을 받게 해 `apply_update` 까지 확인. Expected: 재시작 후 2.0.0, `.old` 가 다음 실행 때 사라짐.
- [ ] **Step 4: 외형 비교** — 1.3.0 과 Rust 앱을 같은 창 크기로 띄워 홈, 검색 결과, 패키지, 다운로드 중, 설정, 라이트/다크를 캡처해 나란히 본다. 눈에 띄는 차이는 고치고 각 화면을 다시 캡처한다.
- [ ] **Step 5: 결과 보고와 커밋** — 고친 것이 있으면 `git commit -m "외형을 1.3.0 에 맞춤"`. 각 단계의 결과를 사용자에게 보고한다.

---

### Task 23: 파이썬 제거와 README

**Files:**
- Delete: `dccon/`, `run.py`, `dccon_boot.py`, `dccon-downloader.spec`, `pyproject.toml`, `uv.lock`, `.python-version`, `tests/`, `tools/`(gen_golden.py 포함)
- Modify: `README.md`, `.gitignore`

**Interfaces:**
- Consumes: 모든 이전 태스크 완료

- [ ] **Step 1: 지우기** — 위 파일을 지운다. `assets/icon.ico`, `assets/icon.icns` 는 더 쓰지 않으면 지운다(Tauri 는 `src-tauri/icons` 를 쓴다).
- [ ] **Step 2: README 갱신** — 실행(`npm --prefix ui ci`, `cargo tauri dev`), 쓰는 법·저장 결과·설정은 유지, 구조는 4절 트리, 엔드포인트 표와 설계 메모는 유지하되 스레드 풀·`_inflight` 대신 세마포어와 `img://` 세대 설명, 빌드·릴리즈·자동 업데이트는 새 자산 규칙과 이전용 zip 설명, 크기·시작 시간은 Task 21 에서 잰 값.
- [ ] **Step 3: 전체 확인** — Run: `cargo test --workspace`, `npm --prefix ui test -- --run`, `./build.ps1 -Clean`, 실행 확인 스크립트. Expected: 전부 통과, `alive=True window=디시콘 다운로더`.
- [ ] **Step 4: Commit** — `git commit -m "파이썬 구현 제거, README 를 Rust 기준으로"`
