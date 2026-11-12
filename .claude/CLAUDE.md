# 디시콘 다운로더 작업 규칙

Rust(Tauri 2) + Svelte 5 앱이다. 구조: `crates/core`(다운로드·캐시·설정 등 핵심 로직),
`src-tauri/`(창과 커맨드), `ui/`(Svelte 프론트).

## 커밋하기 전에 반드시 확인

코드(`crates/`, `src-tauri/`, `ui/`, `Cargo.toml`, `build.ps1`, `build.sh`)를 건드렸으면
커밋 전에 아래를 **순서대로** 통과시킨다. 하나라도 실패하면 커밋하지 않고 고친다.

1. 테스트
   ```bash
   cargo test --workspace
   npm --prefix ui test -- --run
   ```
2. 빌드 (PowerShell)
   ```powershell
   ./build.ps1 -Clean      # -> dist/dccon-downloader.exe
   ```
   - **`2>&1`을 붙이지 말 것.** cargo/npm 이 stderr 로 찍는 진행 메시지가 오류로 바뀌어
     빌드가 멈춘다.
   - 끝에 `완료: ...` 줄이 나와야 성공이다.
3. 실행 확인 - 빌드된 exe 가 실제로 창을 띄우는지 본다.
   ```powershell
   $exe = "dist\dccon-downloader.exe"
   $p = Start-Process -FilePath $exe -PassThru; Start-Sleep -Seconds 6
   $win = Get-Process -Name dccon-downloader -EA SilentlyContinue | ? MainWindowTitle
   "$exe -> alive=$(-not $p.HasExited) window=$($win.MainWindowTitle)"
   Get-Process -Name dccon-downloader -EA SilentlyContinue | Stop-Process -Force
   ```
   `alive=True window=디시콘 다운로더` 여야 한다. 창이 안 뜨면 `./build.ps1 -Console` 로
   다시 빌드해서 콘솔에 찍히는 오류를 본다.
   - 릴리즈 빌드 exe 는 시작할 때 `%LOCALAPPDATA%/DcconDownloader` 의 `update/`, `code/` 를
     정리한다. 내 데이터가 걱정되면 `$env:LOCALAPPDATA` 를 임시 폴더로 바꿔서 실행한다.

### macOS 에서 작업할 때

PowerShell 빌드는 윈도우에서만 된다. 맥에서는 2~3 대신 아래를 한다.

```bash
./build.sh --clean
open "dist/디시콘 다운로더.app"   # 몇 초 뒤 창이 떠야 한다
```
끝에 `완료: ...` 줄이 나와야 성공이다. 맥이 없으면 `.github/workflows/macos.yml` 을
수동 실행(`gh workflow run macos.yml --ref <브랜치>`)해서 아티팩트를 받는다.
`build.ps1` 을 바꿨다면 윈도우 빌드는 확인하지 못한 상태라는 걸 커밋 메시지나
사용자에게 알린다.

문서(README 등)만 바꾼 커밋은 1~3을 건너뛰어도 된다.

## 릴리즈(업로드)

GitHub 릴리즈를 올릴 때는 `release` 스킬(`.claude/skills/release/SKILL.md`)의 절차를 따른다.
이미 깔린 1.3.0 앱의 자동 업데이트가 릴리즈 자산 이름과 zip 구조에 의존하므로 임의로 바꾸지 않는다.

## 알아둘 것

- 릴리즈 자산은 셋이다: `dccon-downloader-X.Y.Z.exe`, `dccon-downloader-X.Y.Z-win64.zip`,
  `dccon-downloader-X.Y.Z-macos.zip`. 이름은 ASCII 만 쓴다(깃허브가 한글을 지운다).
- `-win64.zip` 은 옛 파이썬 앱(onedir)이 2.0.0 으로 올라올 때 받는 **이전용** 이다.
  안에는 `dccon-downloader/dccon-downloader.exe` 와 `dccon-downloader/_internal/MIGRATED.txt`
  만 있다. 새 앱은 처음 뜰 때 `_internal/` 에 `MIGRATED.txt` 하나뿐이면 그 폴더를 지운다.
  zip 구조와 exe 이름, 표식 파일은 건드리지 않는다. `build.ps1 -Release` 가 만든다.
- 데이터 경로와 형식(`settings.json`, `cache/`, `arca_session.json` 등)은 이미 배포된 앱과의
  약속이다. 키 이름이나 파일 구조를 바꾸면 기존 사용자의 설정·캐시가 깨지니 호환되게 유지한다.
- 저장소 `glglekdy/DCCON_Downloader` 는 **공개**다. 앱의 업데이트 확인은 인증 없이
  GitHub API 를 부르므로 그대로 동작한다. 비공개로 돌리면 기존 사용자가 새 릴리즈를
  못 보고 항상 "최신 버전"이라고 하게 되니 주의.
- 빌드 산출물과 릴리즈용 파일은 저장소 밖(`dist/`, `target/` 은 gitignore 됨)에 둔다.
  저장소 루트에 `release/` 같은 폴더를 만들어 커밋하지 않는다.
