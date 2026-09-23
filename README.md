# 디시콘 다운로더

디시콘을 검색해서 미리 보고, 원하는 것만 골라 받는 데스크톱 앱.

```
검색어 · 패키지 ID · URL  →  그리드로 미리보기  →  체크해서 저장
```

## 실행

```bash
uv sync
uv run dccon-downloader
```

## 쓰는 법

상단 입력창 하나가 검색·ID·URL을 전부 받는다.

| 입력 | 동작 |
| --- | --- |
| `멍뭉` | 제목으로 검색 (콤보박스에서 작가·태그로 바꿀 수 있음) |
| `12345` | 그 패키지를 바로 열기 |
| `https://dccon.dcinside.com/hot/1#12345` | URL에서 ID를 뽑아 열기 |
| `12345 83649 94849` | 여러 개를 한꺼번에 큐에 넣고 바로 받기 |

그리드에서 **클릭은 선택**(패키지 통째로 받기), **더블클릭은 열기**(안의 디시콘을 골라 받기)다.
`Ctrl+L`로 입력창에 바로 간다.

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

`테마`는 `시스템 설정 따르기`(기본) · `라이트` · `다크` 중에서 고른다. 시스템을 따르면
윈도우에서 라이트/다크를 바꾸는 순간 앱도 같이 바뀐다. 색은 `gui/theme.py`에 토큰으로
두 벌 정의돼 있고, 스타일시트와 카드 그리기가 같은 토큰을 쓴다.

같은 창의 `업데이트 확인`은 GitHub 최신 릴리즈를 보고 새 버전이 있으면 변경 내역과 함께
받아서 앱을 다시 시작한다. `시작할 때 새 버전 확인`을 켜두면(기본) exe로 실행할 때 알아서
확인하고, 알림 창에서 `이 버전 건너뛰기`를 누르면 그 버전은 다시 묻지 않는다.

## 구조

GUI를 걷어내도 `dccon/` 아래 코어만으로 동작한다. CLI를 붙이려면 여기에 껍데기만 씌우면 된다.

```
dccon/
  client.py      세션·헤더·스로틀·백오프
  api.py         엔드포인트 (아래 표)
  models.py      Package / DcconItem
  naming.py      파일명 정규화
  cache.py       디스크 캐시
  downloader.py  저장 로직
  updater.py     GitHub 릴리즈 확인·받기·교체
  gui/           PySide6 (얇게)
```

### 엔드포인트

실측으로 확인한 것들. 셋 다 로그인이 필요 없다.

| 용도 | 요청 |
| --- | --- |
| 패키지 상세 | `POST /index/package_detail` · body `package_idx=N` · `X-Requested-With: XMLHttpRequest` |
| 검색 | `GET /hot/{page}/{title\|nick_name\|tags}/{검색어}` — 서버 렌더 HTML |
| 인기 목록 | `json2.dcinside.com/json1/dccon_{day,week,month}_top100.php` — JSON이 `(...)`로 감싸여 있음 |
| 이미지 | `dcimg5.dcinside.com/dccon.php?no={path}` |

**이미지 CDN은 `Referer: https://dccon.dcinside.com/` 가 없으면 403**을 준다. 이게 대부분의
디시콘 다운로더가 실패하는 지점이다.

상세 응답의 `detail[]`에 `ext`(png/gif)가 들어있어서 이미지 바이트를 뜯어 포맷을 판별할 필요가 없다.

### 설계 메모

- **캐시가 1급 저장소다.** 디시콘 한 장이 7~10KB짜리 100x100/200x200이라 캐시가 싸다.
  미리보기로 한 번 받아두면 '다운로드'는 네트워크가 아니라 캐시 → 저장 폴더 복사가 된다.
  캐시는 `%LOCALAPPDATA%/DcconDownloader/cache/`에 쌓이고 자동 삭제는 하지 않는다.
- **스레드 풀을 셋으로 나눴다.** 탐색 / 썸네일 / 다운로드. 한 풀이면 썸네일 100장이 큐를
  채워서 '패키지 열기'가 그 뒤에 줄 선다.
- **QThreadPool에 넘긴 작업은 참조를 잡고 있어야 한다.** 파이썬 객체가 GC되면 딸린 signals가
  같이 사라져서 `emit`이 아무데도 도착하지 않는다. `MainWindow._inflight`가 그 역할.
- **요청은 보수적으로.** 전역 스로틀에 지터를 섞고, 429를 만나면 잠깐 전체를 멈췄다 재개한다.

## 빌드

```powershell
./build.ps1              # onedir  -> dist/dccon-downloader/
./build.ps1 -OneFile     # 단일 exe -> dist/dccon-downloader.exe
./build.ps1 -Console     # 콘솔 창을 띄워 오류를 보며 디버깅
./build.ps1 -Clean       # 이전 산출물 정리 후 빌드
```

Windows 11 / Python 3.13 / PyInstaller 6.22 에서 실측한 값:

| 방식 | 크기 | 창 뜰 때까지 |
| --- | --- | --- |
| onedir | 78 MB (폴더) | 1.1초 |
| onefile | 30 MB (단일 exe) | 1.9초 |

배포가 편한 쪽은 단일 exe고, 차이는 0.7초 남짓이다. 다만 단일 exe는
백신 오탐이 상대적으로 잦은 편이니 그런 신고가 들어오면 onedir 폴더를 zip으로 주면 된다.

### 빌드 설정이 spec 에 있는 이유

`--exclude-module` 은 **파이썬 모듈만** 거르고 Qt DLL 은 그대로 남는다. 기본 수집에는
안 쓰는 Qml·Quick·Pdf 와 소프트웨어 OpenGL 폴백(`opengl32sw.dll`, 20MB)까지 들어와
115 MB 가 나왔다. 그래서 `dccon-downloader.spec` 에서 수집이 끝난 뒤 바이너리 목록을
직접 걸러 78 MB 로 줄였다.

건드리면 안 되는 것: `plugins/imageformats` (특히 `qgif.dll`, `qjpeg.dll`). 지우면
썸네일이 그려지지 않는다. `opengl32sw.dll` 은 QtWidgets 가 래스터 엔진을 쓰므로 뺐는데,
혹시 그래픽이 깨지는 환경이 나오면 spec 의 `DROP_BINARIES` 에서 그 항목만 빼면 된다.

아이콘은 `tools/make_icon.py` 가 도형만으로 그려서 ICO(7개 사이즈)로 저장한다.
`assets/icon.ico` 가 없으면 빌드 스크립트가 알아서 만든다.

## 릴리즈와 자동 업데이트

앱은 `api.github.com/repos/glglekdy/DCCON_Downloader/releases/latest`를 본다.
그래서 **정식 릴리즈만** 대상이고, 초안(draft)과 사전 릴리즈(pre-release)는 무시된다.

릴리즈를 낼 때 지킬 것:

1. `dccon/__init__.py`의 `__version__`(과 `pyproject.toml`의 `version`)을 올린다.
2. 태그는 `v0.2.0`처럼 그 버전과 맞춘다. 앱은 태그의 숫자만 비교한다.
3. 빌드 방식별로 자산을 올린다. 앱은 자기가 어떤 방식으로 빌드됐는지 보고 맞는 걸 고른다.

| 자산 | 받는 쪽 |
| --- | --- |
| `*.exe` (`./build.ps1 -OneFile` 결과) | 단일 exe로 쓰는 사람 |
| `*.zip` (`dist/dccon-downloader/` 폴더째 압축) | onedir 폴더로 쓰는 사람 |

zip 안에는 exe와 `_internal/`이 있어야 한다(한 겹 폴더로 감싸져 있어도 된다). 둘 중 하나만
올리면 다른 방식 사용자는 '릴리즈 페이지 열기'로 안내된다.

적용은 이렇게 된다. 실행 중인 exe와 DLL은 윈도우가 잠그고 있어서 앱이 스스로 덮어쓸 수 없다.

```
받기  → %LOCALAPPDATA%/DcconDownloader/update/<tag>/  (크기·SHA-256 확인)
재시작 → 숨은 PowerShell 도우미가 앱 종료를 기다림
       → _internal 은 통째로 교체, exe 덮어쓰기 → 새 버전 실행
```

교체에 실패하면 옛 `_internal`로 되돌리고 옛 버전을 띄운 뒤, 다음 실행 때 이유를 보여준다.
소스로 실행(`uv run`) 중이면 자동 교체 대신 릴리즈 페이지를 연다.

## 참고

개인 소장용으로 쓰세요. 받은 디시콘의 저작권은 원작자에게 있고, 재배포나 판매는 별개 문제입니다.
