# 디시콘 다운로더 Rust 재작성 설계

- 날짜: 2026-11-10
- 브랜치: `rust`
- 목표 버전: 2.0.0

## 1. 목적과 성공 기준

파이썬(PySide6 + PyInstaller) 앱을 Rust(Tauri 2)로 다시 만든다. 이유는 네 가지다.

1. 용량과 시작 속도: 지금 onefile 30MB / 1.9초, onedir 78MB / 1.1초.
2. 성능과 안정성: GC·스레드 관련 문제(`_inflight`, GUI 스레드 GC 우회)를 구조적으로 없앤다.
3. 백신 오탐: PyInstaller onefile 의 오탐을 줄인다.
4. Rust 로 유지보수한다.

성공 기준:

- **기능 동등**: 1.3.0 의 모든 기능(아래 2절)이 있다. 빠지는 기능이 없다.
- **기존 사용자 자동 이전**: 1.3.0 이하 파이썬 앱(onefile, onedir)이 자동 업데이트로 2.0.0 Rust 앱을 받아 정상 실행된다.
- **데이터 연속성**: 설정, 이미지·메타 캐시, 저장 폴더 구조가 그대로 이어진다.
- **크기·속도**: 윈도우 exe 15MB 이하, 실행부터 창이 뜰 때까지 0.5초 이하.
- **외형**: 1.3.0 과 나란히 놓았을 때 같은 앱으로 보인다(사이드바, 카드, 독, 글로우, 테마).
- 윈도우와 macOS 에서 돈다.

## 2. 옮길 기능 목록 (1.3.0 기준)

- 사이트 전환: 디시콘 / 아카콘 (사이드바 세그먼트).
- 디시콘 메뉴: 인기(일간·주간·월간), 둘러보기(공식, 전체 목록).
- 아카콘 메뉴: 최신, 주간 인기, 월간 인기.
- 입력창 하나: 검색어(제목/작가/태그), 패키지 ID, URL, 여러 ID(바로 큐에 넣고 받기). `Ctrl+L`(맥 `⌘L`).
- 전체 목록 페이지네이션: `‹ 1 / 6142 ›`, 가운데를 눌러 페이지 이동.
- 그리드: 클릭은 선택, 더블클릭은 열기. 선택 해제 / 전체 선택 / 다운로드.
- 뒤로/앞으로(마우스 4·5번 버튼), 로고 클릭은 홈.
- 다운로드 큐: 진행률, 일시정지, 취소, 내역, 독 숨기기(▼/▲), 받는 동안 바닥 글로우.
- 저장 규칙: `<저장폴더>/<패키지명>/NN_<제목>.<ext>`, `_main.<ext>`, `_meta.json`, 있으면 건너뛰기,
  아카콘은 `<저장폴더>/arcacon/` 아래.
- 아카콘 로그인(쿠키 저장, 만료 시 다시 로그인 안내).
- 설정: 저장 폴더, 동시 다운로드 수(기본 3), 대표 이미지 저장, `_meta.json` 저장, 모션 줄이기,
  GIF 움직이기, 테마(시스템/라이트/다크), 시작할 때 업데이트 확인, 캐시 용량 보기·비우기, 업데이트 확인.
- 최근 연 패키지 기록(`recent_packages`, 24개).
- 자동 업데이트: 새 버전 알림, 변경 내역, 이 버전 건너뛰기, 받기·적용·재시작, 실패 사유를 다음 실행 때 표시.
- 받은 단일 exe 이름 정리(`디시콘 다운로더.exe` 로 바꾸고 옛 버전은 휴지통).

## 3. 기술 선택

| 항목 | 선택 | 이유 |
| --- | --- | --- |
| 앱 셸 | Tauri 2 | 화면을 웹으로 그려 지금 디자인(글로우·모션·GIF)을 재현하기 쉽고 exe 가 작다 |
| 프론트 | Svelte 5 + TypeScript + Vite | 상태가 많은 화면에 반응형이 맞고 런타임이 거의 없다 |
| HTTP | reqwest(rustls) + tokio | 비동기, 스레드 풀 대신 세마포어 |
| HTML 파싱 | `regex` (파이썬과 같은 정규식) | 기존 파서와 결과를 1:1 로 맞추기 쉽다 |
| 오류 | thiserror | core 의 오류 enum |
| 로그 | tracing + 파일 출력 | 콘솔 없는 릴리즈 빌드 |
| 휴지통 | `trash` 크레이트 | `tidy_sibling_builds` |
| 테스트 | cargo test, wiremock, vitest | |

## 4. 구조

Cargo 워크스페이스. core 는 Tauri 에 의존하지 않는다("GUI 를 걷어내도 코어만으로 동작" 원칙 유지).

```
Cargo.toml              워크스페이스
crates/core/            dccon-core
  src/http.rs           클라이언트: 기본 헤더(UA, Referer, Accept-Language), 스로틀(0.12초 + 지터 0.08초),
                        429 → 5초 전역 일시정지, 429/5xx 지수 백오프(최대 4회 재시도), 취소 토큰,
                        세션 교체(UA + 쿠키)
  src/dccon.rs          package_detail, 검색(/hot), 전체(/new), 인기·공식(JSONP), parse_query
  src/arca.rs           목록·검색·상세 파서, parse_ids, LoginRequired 판정(401/403, /u/login 리다이렉트)
  src/models.rs         Package, Item, Brief, image_url
  src/naming.rs         sanitize, package_dirname, pad_width, item_filename
  src/cache.rs          ImageCache(키별 잠금), MetaCache, stats, clear
  src/downloader.rs     download_package, 확장자 판별, _meta.json
  src/config.rs         DATA_DIR 등 경로, Settings
  src/updater.rs        릴리즈 조회, 자산 선택, 받기·검증, exe 교체, 이전 흔적 정리, 이름 정리
  src/error.rs          Error enum
  tests/fixtures/       실측 응답, 파이썬 골든 값
src-tauri/              앱 크레이트 (얇게)
  src/main.rs           진입, WebView2 없을 때 안내, 상태 등록
  src/commands.rs       프론트가 부르는 커맨드
  src/imgproto.rs       img:// 프로토콜
  src/queue.rs          다운로드 큐와 이벤트
  src/login.rs          아카콘 로그인
  tauri.conf.json
ui/                     Svelte 앱
  src/lib/theme.css     라이트/다크 토큰 (gui/theme.py 에서 옮김)
  src/lib/components/   Sidebar, SearchBar, Heading, Grid, Card, Dock, QueueBar, Glow, 모달들
  src/lib/stores/       history(뒤로/앞으로), selection, view
```

### 4.1 Rust 쪽 상태

`AppState` 하나를 Tauri 에 등록한다.

- `settings: RwLock<Settings>`
- `dccon: Client`, `arca: Client` (사이트별 세션·스로틀 분리, 파이썬과 같다)
- `image_cache`, `meta_cache`
- 세마포어 셋: `nav`(2), `thumb`(max(2, 동시 다운로드 수)), `download`(동시 다운로드 수). 1.3.0 의 풀 크기와 같다
- `view_generation: AtomicU64` (화면 세대)
- `queue: Mutex<Queue>`

### 4.2 커맨드 (프론트 → Rust)

| 커맨드 | 하는 일 |
| --- | --- |
| `get_settings` / `save_settings` | 설정 읽기·쓰기 |
| `begin_view() -> u64` | 화면 세대 올리기. 이전 세대 썸네일 요청을 버리게 한다 |
| `list_top(kind)` | 디시콘 인기·공식 |
| `list_all(page)` | 디시콘 전체 목록 (목록, 전체 페이지 수, 총 개수) |
| `search(site, word, type, page)` | 검색 |
| `list_arca(kind, page)` | 아카콘 최신·인기 |
| `open_package(site, id)` | 패키지 상세 (메타 캐시 사용), 최근 기록 |
| `parse_input(site, text)` | 입력 해석: `{search: word}` / `{ids: [..]}` |
| `enqueue(jobs)` | 다운로드 큐에 넣기. job = (site, id, 고른 sort 목록 또는 전체) |
| `pause_queue(bool)` / `cancel_queue()` | 큐 제어 |
| `open_folder()` | 저장 폴더 열기 |
| `cache_stats()` / `clear_cache()` | 캐시 |
| `arca_login()` / `arca_logout()` | 로그인 |
| `check_update()` / `download_update()` / `apply_update()` / `skip_version(v)` | 업데이트 |
| `take_last_error()` | 지난 업데이트 실패 사유 |

### 4.3 이벤트 (Rust → 프론트)

- `queue-progress {id, done, total, name}`
- `queue-package-done {id, title, saved, skipped, failed[]}`
- `queue-error {id, message}`
- `queue-finished`
- `update-progress {done, total}`
- `login-finished {ok, message}`

### 4.4 img:// 프로토콜

`img://localhost/?u=<url 인코딩>&e=<ext>&g=<세대>` 를 Tauri 비동기 URI 스킴으로 처리한다.

1. 캐시에 있으면 바로 응답(세대 무관).
2. 없으면 `g` 가 지금 세대가 아니면 `204` 로 버린다. 지금 세대면 `thumb` 세마포어를 잡은 뒤 다시 세대를
   확인하고, 사이트에 맞는 클라이언트로 받아 캐시에 쓰고 응답한다.
3. `Content-Type` 은 ext 로 정한다(png/gif/jpg/webp/mp4). mp4 는 `Range` 요청이 오면 206 으로 답한다.
4. 오류는 `502`, 프론트는 카드에 실패 표시.

## 5. 화면

레이아웃과 수치는 1.3.0 의 `main_window.py`, `cards.py`, `queuebar.py`, `glow.py`, `theme.py` 를 따른다.

- 사이드바 210px: 로고(홈), 사이트 세그먼트, 사이트별 메뉴, 아래에 `폴더 열기`, `설정`.
- 메인: 검색줄(검색 종류 콤보 + 입력창), 2px 로딩 줄, 스크롤 영역(제목 영역 + 카드 그리드),
  그리드 위에 떠 있는 독(선택 줄 ↔ 큐 바), 독 위 손잡이, 독 아래 깔리는 글로우.
- 그리드는 CSS grid `auto-fill`. 한 화면이 페이지 단위라 가상 스크롤은 쓰지 않는다.
- 테마: `theme.py` 토큰 두 벌을 CSS 변수로 옮긴다. `system` 은 `prefers-color-scheme` 을 따르고,
  창 테마는 Tauri `set_theme` 으로 맞춘다.
- 모션 줄이기: 설정이 켜졌거나 OS 가 `prefers-reduced-motion` 이면 transition·animation 을 0 으로.
- GIF 움직이기 끔: 이미지가 로드되면 첫 프레임을 `<canvas>` 에 그려 보여준다. 아카콘 mp4 는 poster 를
  보여주고, 움직이기가 켜졌을 때만 `<video autoplay loop muted playsinline>`.
- 뒤로/앞으로: Svelte 의 이동 기록 스택(화면 종류 + 인자 + 스크롤 위치). `mouseup` button 3/4.
- 모달: 설정, 업데이트 알림(변경 내역, 받기, 이 버전 건너뛰기), 아카콘 로그인 안내, 페이지 이동 입력.
- 폴더 선택은 `tauri-plugin-dialog`, 폴더·링크 열기는 `tauri-plugin-opener`.
- 창 제목은 `디시콘 다운로더` (검증 스크립트가 이 제목을 본다).

## 6. 아카콘 로그인

1차 방식: **앱 안 로그인 창.**

1. `WebviewWindow` 로 `https://arca.live/u/login?goto=/e/` 를 연다.
2. 창의 주소가 `/e/` 로 끝나는 페이지로 바뀌면(로그인 성공) `cookies_for_url("https://arca.live")` 로
   쿠키를 꺼내고, 창의 UA(`navigator.userAgent`)를 함께 `arca_session.json` 에 저장한 뒤 창을 닫는다.
   사용자가 창을 닫으면 그 시점의 쿠키로 시도한다.
3. 저장한 세션으로 `/e/` 를 불러 로그인 여부를 확인한다(`/u/login` 으로 가면 실패).

구현 첫 단계에서 이 방식을 실측한다(스파이크). Cloudflare 확인 통과, HttpOnly 쿠키 포함 여부, reqwest 로
그 쿠키를 썼을 때 통과 여부를 본다. 하나라도 안 되면 1.3.0 방식(설치된 Chrome/Edge 를 전용 프로필로 띄우고,
닫힌 뒤 headless + CDP `Storage.getCookies` 로 꺼냄)을 Rust 로 옮긴다.

## 7. 업데이트와 기존 사용자 이전

### 7.1 릴리즈 자산 (2.0.0 부터)

| 자산 | 받는 쪽 |
| --- | --- |
| `dccon-downloader-X.Y.Z.exe` | Rust 앱, 옛 파이썬 단일 exe |
| `dccon-downloader-X.Y.Z-win64.zip` | 옛 파이썬 onedir. 안에 `dccon-downloader/dccon-downloader.exe` 와 `dccon-downloader/_internal/MIGRATED.txt` |
| `dccon-downloader-X.Y.Z-macos.zip` | 맥 `.app` |

- `dccon-code-*.pyz` 는 올리지 않는다. 옛 앱은 코드 자산이 없으면 전체 자산을 고른다.
- 이전용 zip 은 옛 onedir 사용자가 남아 있을 수 있으므로 계속 올린다(수백 KB 정도라 부담이 없다).

### 7.2 옛 앱이 2.0.0 을 받을 때 (1.3.0 `updater.py` 기준)

- onefile: `pick_asset("onefile")` 이 `.exe` 를 고른다 → 지금 exe 이름으로 스테이징 → 옛 PowerShell 도우미가
  덮어쓰고 같은 경로로 실행한다. Rust exe 가 뜬다.
- onedir: `.zip` 을 고른다 → `_extract_onedir` 이 한 겹 폴더를 내려가 `*.exe` 와 `_internal/` 을 확인 →
  도우미가 `_internal` 을 통째로 바꾸고 exe 를 덮어써 `dccon-downloader.exe` 를 실행한다.
- 이를 위해 zip 안의 exe 이름은 반드시 `dccon-downloader.exe` 다(옛 onedir exe 이름과 같아야 같은 경로로 뜬다).
- 알려진 한계: onedir 사용자가 exe 이름을 직접 바꿔 썼다면, 도우미가 옛 이름의 파이썬 exe 를 이전용 표식만 든
  새 `_internal` 과 함께 띄워 실패한다. 이 경우는 릴리즈 노트의 "새로 받아 주세요" 안내로 대신한다.

### 7.3 Rust 앱이 처음 뜰 때 정리

- exe 옆 `_internal/` 에 `MIGRATED.txt` 하나만 있으면 지운다(다른 파일이 있으면 건드리지 않는다).
- `DATA_DIR/code/` (옛 코드 업데이트 폴더)를 지운다.
- `DATA_DIR/update/` 의 스테이징 폴더를 지운다. `last_error.log` 는 읽어서 보여준 뒤 지운다.
- 같은 폴더의 `<exe 이름>.old` 를 지운다.

### 7.4 Rust 앱 자체 업데이트

1. `https://api.github.com/repos/glglekdy/DCCON_Downloader/releases/latest` 를 인증 없이 부른다.
   404 는 "릴리즈 없음", 403 + `x-ratelimit-remaining: 0` 은 한도 초과 문구.
2. 태그 숫자 비교(`v1.2` == `1.2.0`, 접미사 무시). 설정의 `skipped_version` 과 같으면 시작 시 알림을 건너뛴다.
3. 자산 고르기: 이름이 `.exe` 로 끝나고 macos/darwin/mac- /-mac. 이 들어가지 않은 것, `win` 이 들어간 것 우선.
4. `DATA_DIR/update/<tag>/<자산>.part` 로 받으며 진행률 이벤트, 크기와 `digest`(sha256) 확인 후 이름 확정.
5. 적용: 실행 중인 exe 를 `<이름>.old` 로 바꾸고 → 새 exe 를 원래 경로로 옮긴다(다른 볼륨이면 복사) →
   새 exe 를 띄우고 종료. 옮기다 실패하면 `.old` 를 되돌리고 오류를 보여준다.
6. 쓰기 권한이 없거나(이름 바꾸기 실패) 맥이거나 개발 실행(`cargo tauri dev`)이면 릴리즈 페이지를 연다.
7. 이름 정리: 지금 exe 이름이 `dccon-downloader-X.Y.Z(-win64)?.exe` 꼴이면 `디시콘 다운로더.exe` 로 바꾼다.
   그 이름의 파일이 이미 있으면 그 exe 의 FileVersion 이 지금보다 높지 않을 때만 휴지통으로 보낸다.
   같은 폴더의 더 낮은 버전(받은 이름 그대로인 것)도 휴지통으로 보낸다.

### 7.5 데이터 호환

`DATA_DIR` = 윈도우 `%LOCALAPPDATA%/DcconDownloader`, 맥 `~/Library/Application Support/DcconDownloader`,
그 밖에 `$XDG_DATA_HOME/DcconDownloader` 또는 `~/.dccondownloader`.

| 파일 | 규칙 |
| --- | --- |
| `settings.json` | 키: `download_dir`, `concurrency`, `save_main_image`, `write_meta_json`, `reduce_motion`, `theme`, `animate_gifs`, `check_updates`, `skipped_version`, `recent_packages`. 모르는 키 무시, 빠진 키 기본값. `.tmp` 에 쓰고 바꾼다. 들여쓰기 2, UTF-8, 한글 그대로 |
| `cache/img/<키 앞 2자>/<키>.<ext>` | 키 = sha1(`no=` 값을 URL 디코딩한 것, 없으면 쿼리를 뗀 URL) |
| `cache/meta/<id>.json` | package_detail 응답 원문 |
| `arca_session.json` | `{user_agent, cookies: [{name, value, domain, path}]}`. Chrome 으로 받은 옛 세션은 써 보고 실패하면 다시 로그인 안내 |
| `webview/` | WebView2 데이터 폴더 (새로 생김) |
| `logs/` | 로그 (새로 생김) |

## 8. 오류 처리

- core 의 `Error`: `Network`, `RateLimited`, `Cancelled`, `LoginRequired`, `NotFound`, `Io`, `Parse`, `Update(String)`.
- 커맨드는 `{kind, message}` 로 직렬화한다. message 는 사용자에게 그대로 보여줄 한국어 문구.
- 프론트: `LoginRequired` 는 로그인 안내 모달, 목록 실패는 빈 화면 문구, 그 밖은 토스트.
- 다운로드는 항목별 실패를 모아 큐 내역에 보인다. 취소는 오류로 보이지 않는다.
- 릴리즈 빌드는 `windows_subsystem = "windows"`. panic hook 이 `logs/` 에 남긴다.
- WebView2 런타임이 없어 창을 못 만들면 네이티브 메시지 상자로 설치 링크를 안내하고 끝낸다.

## 9. 테스트

| 대상 | 방법 |
| --- | --- |
| naming, cache_key, parse_query(디시·아카), 버전 비교, `_meta.json` 형식, 설정 직렬화 | 파이썬 1.3.0 구현으로 뽑은 골든 값과 대조 |
| 디시콘·아카콘 파서 | 실측 응답을 `crates/core/tests/fixtures/` 에 저장해 대조. 기존 파이썬 테스트의 인라인 HTML 도 옮긴다 |
| HTTP 클라이언트 | wiremock: Referer·UA 헤더, 429 전역 일시정지, 5xx 재시도, 취소 |
| 다운로더 | 임시 폴더 + wiremock: 있으면 건너뛰기, `.part`, `_main` 확장자 판별, 실패 수집, 아카콘 하위 폴더 |
| updater | 자산 고르기(맥 zip 제외, win 우선), 크기·SHA 불일치, 교체·되돌리기(임시 폴더의 가짜 exe), 이전 흔적 정리, 이름 정리 |
| 프론트 순수 로직 | vitest: 이동 기록, 선택 |
| 이전 경로 | 1.3.0 빌드 사본(onefile, onedir)에서 옛 `_APPLY_SCRIPT` 를 그대로 돌려 2.0.0 자산으로 덮어쓰고, 창 `디시콘 다운로더` 가 뜨는지 확인. onedir 은 옛 `_extract_onedir` 검사도 통과하는지 확인 |
| 실행 | 빌드한 exe 가 6초 안에 창을 띄우는지 (CLAUDE.md 3단계와 같은 스크립트) |
| 외형 | 1.3.0 과 같은 화면(홈, 검색, 패키지, 다운로드 중, 설정, 라이트/다크) 스크린샷 비교 |

## 10. 빌드와 작업 규칙

- 툴체인: rustup(stable, MSVC), Visual Studio Build Tools(C++), Node LTS, `cargo install tauri-cli`.
- `build.ps1`: `-Clean`, `-Console`(콘솔 붙은 빌드), `-Release`(릴리즈 자산 생성). 산출물은 `dist/`:
  `dist/dccon-downloader.exe`, `-Release` 면 `dist/release/` 에 7.1 의 윈도우 자산 둘.
- `build.sh`: 맥에서 `.app` 과 `-macos.zip`.
- `.github/workflows/macos.yml`: 수동 실행으로 macos 러너에서 `.app` zip 을 만들어 아티팩트로 올린다.
- `CLAUDE.md` 의 커밋 전 절차를 바꾼다: `cargo test --workspace` + `npm --prefix ui test` → `./build.ps1` →
  exe 실행 확인. 코드 범위도 `crates/`, `src-tauri/`, `ui/`, 빌드 스크립트로 바꾼다.
- `.claude/skills/release/SKILL.md` 를 7.1 자산 규칙에 맞게 고친다.
- 파이썬 코드(`dccon/`, `run.py`, `dccon_boot.py`, spec, `pyproject.toml`, `uv.lock`, `tools/`, `tests/`)는
  골든 값을 뽑는 데 쓰고, 기능 동등과 이전 실측이 끝난 뒤 이 브랜치에서 지운다. README 도 새 구조로 고친다.

## 11. 구현 순서

1. 툴체인 설치, 워크스페이스·Tauri·Svelte 뼈대, 빈 창이 뜨는 exe
2. 아카콘 앱 내 로그인 스파이크 → 6절 방식 확정
3. core: error, config, naming, models, http, cache
4. core: dccon, arca 파서 + 픽스처
5. core: downloader
6. Tauri: 상태, 커맨드, img:// 프로토콜, 큐
7. 화면: 테마·레이아웃 → 그리드·카드 → 독·큐·글로우 → 모달 → 단축키·이동 기록
8. 아카콘 로그인 구현
9. updater, 이전 흔적 정리, 이름 정리
10. 빌드 스크립트, 맥 워크플로, CLAUDE.md, release 스킬
11. 이전 경로 실측, 외형 비교
12. 파이썬 코드 제거, README 갱신

## 12. 범위 밖

- 새 기능 추가(동등 이후에 따로).
- 코드 서명.
- 맥 자동 교체(지금처럼 릴리즈 페이지를 연다).
