# 디시콘 다운로더

디시콘을 검색해서 미리 보고, 원하는 것만 골라 받는 데스크톱 앱. Windows 와 macOS 에서 돈다.

```
검색어 · 패키지 ID · URL  →  그리드로 미리보기  →  체크해서 저장
```

## 실행

필요한 것: Rust(stable), Node.js, `cargo install tauri-cli --version "^2"`, 윈도우는 WebView2 런타임(윈도우 11 에는 기본으로 있다).

```bash
npm --prefix ui ci
cargo tauri dev
```

테스트는 `cargo test --workspace` 와 `npm --prefix ui test -- --run`.

## 쓰는 법

상단 입력창 하나가 검색·ID·URL을 전부 받는다.

| 입력 | 동작 |
| --- | --- |
| `멍뭉` | 제목으로 검색 (콤보박스에서 작가·태그로 바꿀 수 있음) |
| `12345` | 그 패키지를 바로 열기 |
| `https://dccon.dcinside.com/hot/1#12345` | URL에서 ID를 뽑아 열기 |
| `12345 83649 94849` | 여러 개를 한꺼번에 큐에 넣고 바로 받기 |

홈의 `전체` 탭은 사이트에 올라온 모든 디시콘(9만 개 남짓)을 최신순으로 15개씩 보여준다.
가운데 `1 / 6142` 를 누르면 원하는 페이지로 바로 간다.

아카콘(arca.live)은 사이드바에서 고른다. 최신·인기는 로그인 없이 보이고, 로그인이 필요한 화면이 나오면
앱 안에 로그인 창이 뜬다(크롬이나 엣지를 따로 열지 않는다). 로그인이 끝나면 창이 닫히고 세션이 저장돼
다음부터는 묻지 않는다. 설정에서 로그아웃할 수 있다.

그리드에서 **클릭은 선택**(패키지 통째로 받기), **더블클릭은 열기**(안의 디시콘을 골라 받기)다.
`Ctrl+L`(맥은 `⌘L`)로 입력창에 바로 간다.

## 저장 결과

```
D:/dccon/
└─ 멍뭉이콘/
   ├─ _main.jpg        패키지 대표 이미지
   ├─ 01_안녕.png
   ├─ 02_화남.gif
   ├─ 03_안녕.png      제목이 겹쳐도 순번이 막아준다
   ├─ 04_.png          제목이 빈 경우
   └─ _meta.json       원본 제목·태그·작가 정보
```

이미 있는 파일은 **조용히 건너뛴다.** 중간에 끊겼어도 다시 실행하면 빠진 것만 채운다.

## 설정

`설정` 버튼에서 저장 폴더, 동시 다운로드 수(기본 3), 대표 이미지·`_meta.json` 저장 여부,
그리고 캐시 용량 확인과 비우기를 할 수 있다.

`GIF 미리보기 움직이기`(기본 켬)를 끄면 움직이는 디시콘도 첫 장면에서 멈춰 보인다.

`테마`는 `시스템 설정 따르기`(기본) · `라이트` · `다크` 중에서 고른다. 시스템을 따르면
윈도우나 맥에서 라이트/다크를 바꾸는 순간 앱도 같이 바뀐다. 색은 `ui/src/lib/theme.css`에 토큰으로
두 벌 정의돼 있다(1.3.0 의 `theme.py` 토큰을 그대로 옮겼다).

같은 창의 `업데이트 확인`은 GitHub 최신 릴리즈를 보고 새 버전이 있으면 변경 내역과 함께
받아서 앱을 다시 시작한다. `시작할 때 새 버전 확인`을 켜두면(기본) exe로 실행할 때 알아서
확인하고, 알림 창에서 `이 버전 건너뛰기`를 누르면 그 버전은 다시 묻지 않는다.

## 구조

Tauri 2(Rust) + Svelte 5. 2.0.0 부터 파이썬/PySide6 구현을 대체했다. GUI 를 걷어내도 `crates/core`
만으로 동작한다(Tauri 에 의존하지 않는다). CLI 를 붙이려면 여기에 껍데기만 씌우면 된다.

```
Cargo.toml              워크스페이스
crates/core/            dccon-core
  src/http.rs           클라이언트: 헤더·스로틀·429 일시정지·백오프·취소·세션 교체
  src/dccon.rs          package_detail, 검색, 전체, 인기·공식, parse_query
  src/arca.rs           목록·검색·상세 파서, parse_ids, 로그인 필요 판정
  src/models.rs         Package, Item, Brief, image_url
  src/naming.rs         파일명 정규화
  src/cache.rs          ImageCache, MetaCache
  src/downloader.rs     저장 로직, _meta.json
  src/config.rs         DATA_DIR 등 경로, Settings
  src/updater/          릴리즈 확인·받기·검증(mod.rs), exe 교체·이전 흔적 정리(apply.rs)
  src/error.rs          Error
  tests/fixtures/       실측 응답
  tests/golden/         1.3.0 파이썬 구현이 한 번 뽑아 둔 기준값(데이터. 다시 만들지 않는다)
src-tauri/              앱 크레이트 (얇게)
  src/main.rs           진입
  src/startup.rs        시작 처리 (WebView2 확인, 이전 흔적 정리, 창 준비)
  src/state.rs          AppState (설정, 클라이언트, 캐시, 세마포어, 화면 세대, 큐)
  src/commands.rs       프론트가 부르는 커맨드
  src/app_commands.rs   커맨드 목록 (ACL 과 맞춰 둔다)
  src/dto.rs            프론트와 주고받는 타입
  src/imgproto.rs       img:// 프로토콜
  src/queue.rs          다운로드 큐와 이벤트
  src/login.rs          아카콘 로그인 창
  src/acl_tests.rs      커맨드 권한 파일 점검
  tauri.conf.json
ui/                     Svelte 앱
  src/lib/theme.css     라이트/다크 토큰
  src/lib/components/   Sidebar, SearchBar, Heading, Grid, Card, Thumb, Dock, QueueBar, Glow, 모달들
  src/lib/stores/       history(뒤로/앞으로), selection, view, queue, settings ...
```

### 엔드포인트

실측으로 확인한 것들. 셋 다 로그인이 필요 없다.

| 용도 | 요청 |
| --- | --- |
| 패키지 상세 | `POST /index/package_detail` · body `package_idx=N` · `X-Requested-With: XMLHttpRequest` |
| 검색 | `GET /hot/{page}/{title\|nick_name\|tags}/{검색어}` — 서버 렌더 HTML |
| 전체 목록 | `GET /new/{page}` — 서버 렌더 HTML, 최신순 15개. 마지막 페이지는 `page_end` 링크 |
| 인기 목록 | `json2.dcinside.com/json1/dccon_{day,week,month}_top100.php` — JSON이 `(...)`로 감싸여 있음 |
| 이미지 | `dcimg5.dcinside.com/dccon.php?no={path}` |

**이미지 CDN은 `Referer: https://dccon.dcinside.com/` 가 없으면 403**을 준다. 이게 대부분의
디시콘 다운로더가 실패하는 지점이다.

상세 응답의 `detail[]`에 `ext`(png/gif)가 들어있어서 이미지 바이트를 뜯어 포맷을 판별할 필요가 없다.

### 설계 메모

- **캐시가 1급 저장소다.** 디시콘 한 장이 7~10KB짜리 100x100/200x200이라 캐시가 싸다.
  미리보기로 한 번 받아두면 '다운로드'는 네트워크가 아니라 캐시 → 저장 폴더 복사가 된다.
  캐시는 `%LOCALAPPDATA%/DcconDownloader/cache/`(맥은 `~/Library/Application Support/DcconDownloader/cache/`)에
  쌓이고 자동 삭제는 하지 않는다.
- **세마포어를 셋으로 나눴다.** 탐색(`nav`, 2) / 썸네일(`thumb`) / 다운로드(`download`). 하나로
  묶으면 썸네일 100장이 줄을 채워서 '패키지 열기'가 그 뒤에 선다.
- **`img://` 와 화면 세대.** 썸네일은 `img://localhost/?u=<url>&e=<ext>&g=<세대>` 로 받는다.
  화면을 바꿀 때마다 `begin_view` 가 세대를 올리고, 이전 세대의 요청은 캐시에 없으면 `204` 로 버린다.
  지나간 화면의 썸네일이 새 화면 요청을 막지 않는다. 캐시에 있으면 세대와 무관하게 바로 준다.
  mp4 는 `Range` 요청에 `206` 으로 답한다.
- **요청은 보수적으로.** 전역 스로틀에 지터를 섞고, 429를 만나면 잠깐 전체를 멈췄다 재개한다.

## 빌드

```powershell
./build.ps1              # -> dist/dccon-downloader.exe (단일 exe)
./build.ps1 -Clean       # 이전 산출물 정리 후 빌드
./build.ps1 -Console     # 콘솔 창이 붙은 빌드 (오류 확인용)
./build.ps1 -Release     # dist/release/ 에 릴리즈 자산 둘
```

`2>&1` 은 붙이지 않는다(cargo/npm 의 진행 메시지가 stderr 로 나온다).

Windows 11 / AMD Ryzen 9 7900 / 램 31 GB 에서 실측한 값:

| 항목 | 값 |
| --- | --- |
| 단일 exe | 10.7 MB (파이썬 onefile 30 MB) |
| 이전용 zip | 3.9 MB |
| 창이 뜰 때까지 | 콜드 1.2초, 이어지는 실행은 0.03~0.13초 |

창 시간은 프로세스의 `MainWindowTitle` 이 생길 때까지 잰 것이라 웹 화면이 다 그려진 시점은
아니다(창은 먼저 뜨고 화면이 채워진다). 윈도우 11 은 WebView2 가 기본으로 들어 있어 따로 깔 게 없다.

### macOS

```bash
./build.sh --clean    # -> dist/디시콘 다운로더.app
```

배포할 때는 이름에 `macos` 를 넣어 묶는다. 윈도우 앱의 자동 업데이트가 이 zip 을 집어가지 않게 하려는 것이다.
맥 빌드는 GitHub Actions(`.github/workflows/macos.yml`)에서도 돌릴 수 있다.

```bash
ditto -c -k --keepParent "dist/디시콘 다운로더.app" dist/dccon-downloader-X.Y.Z-macos.zip
```

코드 서명을 하지 않았으므로 처음 열 때 Gatekeeper 가 막는다. Finder 에서 앱을 **우클릭 → 열기** 하거나
`xattr -dr com.apple.quarantine "/Applications/디시콘 다운로더.app"` 로 격리 속성을 지운다.

## 릴리즈와 자동 업데이트

앱은 `api.github.com/repos/glglekdy/DCCON_Downloader/releases/latest` 를 인증 없이 본다.
그래서 **정식 릴리즈만** 대상이고 초안과 사전 릴리즈는 무시된다. 저장소는 공개로 둬야 한다.

절차는 `.claude/skills/release/SKILL.md` 에 있다. 버전은 루트 `Cargo.toml` 의
`[workspace.package] version` 한 군데이고, 태그는 `v2.0.0` 처럼 맞춘다(앱은 숫자만 비교한다).

자산은 셋이다. 이름과 zip 구조를 바꾸면 이미 깔린 1.3.0 앱이 업데이트를 못 받는다.

| 자산 | 받는 쪽 |
| --- | --- |
| `dccon-downloader-X.Y.Z.exe` | Rust 앱, 옛 파이썬 단일 exe 사용자 |
| `dccon-downloader-X.Y.Z-win64.zip` | 옛 파이썬 onedir 사용자(이전용) |
| `dccon-downloader-X.Y.Z-macos.zip` | 맥 `.app` |

이전용 zip 은 `dccon-downloader/dccon-downloader.exe` 와 `dccon-downloader/_internal/MIGRATED.txt`
뿐이다. 옛 onedir 앱이 `.zip` 을 받아 `_internal` 을 통째로 바꾸고 exe 를 덮어쓰면 Rust 앱이 된다.
Rust 앱은 처음 뜰 때 `MIGRATED.txt` 하나만 든 `_internal` 과 옛 `code/`·`update/` 폴더를 지운다.
`.pyz` 코드 패키지는 더 이상 올리지 않는다(옛 앱은 코드 자산이 없으면 전체 자산을 고른다).

### 업데이트 적용

```
받기   → %LOCALAPPDATA%/DcconDownloader/update/<tag>/  (크기·SHA-256 확인)
재시작 → 실행 중인 exe 를 <이름>.old 로 바꾸고 새 exe 를 그 자리에 옮겨 실행
```

옮기다 실패하면 `.old` 를 되돌리고 이유를 보여준다. 쓰기 권한이 없거나 맥이거나
`cargo tauri dev` 로 실행 중이면 자동 교체 대신 릴리즈 페이지를 연다.

### 데이터

설정·캐시·세션은 1.3.0 과 같은 자리(`%LOCALAPPDATA%/DcconDownloader/`, 맥은
`~/Library/Application Support/DcconDownloader/`)와 형식을 쓴다. 그래서 업데이트해도 설정과 캐시가
그대로 이어진다. WebView2 데이터는 같은 폴더의 `webview/` 에 쌓인다.

## 참고

개인 소장용으로 쓰세요. 받은 디시콘의 저작권은 원작자에게 있고, 재배포나 판매는 별개 문제입니다.
