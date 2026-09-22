# 디시콘 다운로더 빌드 스크립트
#
#   ./build.ps1              onedir  -> dist/dccon-downloader/  (권장, 시작 빠름)
#   ./build.ps1 -OneFile     단일 exe -> dist/dccon-downloader.exe
#   ./build.ps1 -Console     콘솔 창을 띄워 오류 메시지를 볼 수 있게 (디버깅용)
#   ./build.ps1 -Clean       이전 빌드 산출물 먼저 정리
#
# PySide6-addons 가 QtWebEngine, Qt3D, QtCharts 등을 통째로 끌고 오는데
# 이 앱은 하나도 안 쓴다. 빼면 결과물이 수백 MB 줄어든다.

param(
    [switch]$OneFile,
    [switch]$Console,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Clean) {
    Write-Host "이전 빌드 정리..." -ForegroundColor Cyan
    foreach ($d in @("build", "dist")) {
        if (Test-Path $d) { Remove-Item -Recurse -Force $d }
    }
    # dccon-downloader.spec 는 지우지 않는다. 생성물이 아니라 소스다.
}

# 아이콘이 없으면 만들어 둔다.
if (-not (Test-Path "assets/icon.ico")) {
    Write-Host "아이콘 생성..." -ForegroundColor Cyan
    uv run python tools/make_icon.py
}

Write-Host "빌드 도구 준비..." -ForegroundColor Cyan
uv sync --group build
if ($LASTEXITCODE -ne 0) { throw "uv sync 실패" }

# 제외 목록과 DLL 필터는 dccon-downloader.spec 안에 있다.
# 스펙 파일을 쓰면 명령줄 옵션은 대부분 무시되므로 환경변수로 넘긴다.
$env:DCCON_ONEFILE = if ($OneFile) { "1" } else { "0" }
$env:DCCON_CONSOLE = if ($Console)  { "1" } else { "0" }

# 주의: $args 는 PowerShell 자동 변수라 여기에 대입하면 안 된다.
$pyiArgs = @("--noconfirm", "--clean", "dccon-downloader.spec")

$mode = if ($OneFile) { "onefile" } else { "onedir" }
Write-Host "PyInstaller 실행 ($mode)..." -ForegroundColor Cyan
uv run --group build pyinstaller @pyiArgs
if ($LASTEXITCODE -ne 0) { throw "빌드 실패 (exit $LASTEXITCODE)" }

Write-Host ""
if ($OneFile) {
    $exe = "dist/dccon-downloader.exe"
    $mb = (Get-Item $exe).Length / 1MB
    Write-Host ("완료: {0}  ({1:N0} MB)" -f $exe, $mb) -ForegroundColor Green
    Write-Host "실행할 때마다 임시 폴더에 풀리느라 onedir 보다 0.5~1초쯤 늦게 뜹니다."
} else {
    $dir = "dist/dccon-downloader"
    $mb = (Get-ChildItem -Recurse $dir | Measure-Object -Sum Length).Sum / 1MB
    Write-Host ("완료: {0}/dccon-downloader.exe  (폴더 {1:N0} MB)" -f $dir, $mb) -ForegroundColor Green
    Write-Host "이 폴더째 zip 으로 배포하세요."
}
