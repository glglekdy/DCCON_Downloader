# 디시콘 다운로더 작업 규칙

## 커밋하기 전에 반드시 확인

코드(`dccon/`, `run.py`, `dccon_boot.py`, `dccon-downloader.spec`, `build.ps1`, `pyproject.toml`)를 건드렸으면
커밋 전에 아래를 **순서대로** 통과시킨다. 하나라도 실패하면 커밋하지 않고 고친다.

1. 테스트
   ```bash
   uv run python -m unittest discover -s tests -p "test_*.py"
   ```
2. 빌드 (PowerShell). 두 방식 다 확인한다 - 자동 업데이트가 둘 다 쓴다.
   ```powershell
   ./build.ps1 -Clean      # onedir -> dist/dccon-downloader/
   ./build.ps1 -OneFile    # onefile -> dist/dccon-downloader.exe
   ```
   - **`2>&1`을 붙이지 말 것.** `$ErrorActionPreference = "Stop"` 때문에 uv 가 stderr 로 찍는
     진행 메시지가 오류로 바뀌어 빌드가 멈춘다.
   - 끝에 `[spec] binaries ...` 와 `완료: ...` 줄이 나와야 성공이다.
3. 실행 확인 - 빌드된 exe 가 실제로 창을 띄우는지 본다.
   ```powershell
   foreach ($exe in @("dist\dccon-downloader\dccon-downloader.exe", "dist\dccon-downloader.exe")) {
     $p = Start-Process -FilePath $exe -PassThru; Start-Sleep -Seconds 6
     $win = Get-Process -Name dccon-downloader -EA SilentlyContinue | ? MainWindowTitle
     "$exe -> alive=$(-not $p.HasExited) window=$($win.MainWindowTitle)"
     Get-Process -Name dccon-downloader -EA SilentlyContinue | Stop-Process -Force; Start-Sleep 1
   }
   ```
   둘 다 `alive=True window=디시콘 다운로더` 여야 한다. 창이 안 뜨면 `./build.ps1 -Console` 로
   다시 빌드해서 콘솔에 찍히는 오류를 본다.

문서(README 등)만 바꾼 커밋은 1~3을 건너뛰어도 된다.

## 릴리즈(업로드)

GitHub 릴리즈를 올릴 때는 `release` 스킬(`.claude/skills/release/SKILL.md`)의 절차를 따른다.
앱의 자동 업데이트가 릴리즈 자산 이름과 zip 구조에 의존하므로 임의로 바꾸지 않는다.

## 알아둘 것

- 업데이트는 가능하면 **코드 업데이트**로 간다: `dccon/` 만 담은 작은 패키지를 받아
  `%LOCALAPPDATA%/DcconDownloader/code/` 에 두고, exe 안의 `dccon_boot.py` 가 다음 실행 때 올린다.
  `dccon_boot.py`, `run.py` 는 exe 에만 들어가고 코드 업데이트로는 **바뀌지 않는다**. 이 둘과
  `code/` 폴더 구조는 이미 배포된 exe 와의 약속이라 함부로 바꾸지 않는다.
- 저장소 `glglekdy/DCCON_Downloader` 는 **공개**다. 앱의 업데이트 확인은 인증 없이
  GitHub API 를 부르므로 그대로 동작한다. 비공개로 돌리면 기존 사용자가 새 릴리즈를
  못 보고 항상 "최신 버전"이라고 하게 되니 주의.
- 빌드 산출물과 릴리즈용 파일은 저장소 밖(`dist/` 는 gitignore 됨)에 둔다. 저장소 루트에
  `release/` 같은 폴더를 만들어 커밋하지 않는다.
