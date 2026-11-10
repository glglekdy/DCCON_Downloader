# 디시콘 다운로더 빌드 스크립트 (Windows)
#
#   ./build.ps1             -> dist/dccon-downloader.exe
#   ./build.ps1 -Clean      이전 빌드 산출물(dist/, ui/dist/) 먼저 정리
#   ./build.ps1 -Console    콘솔 창이 붙은 빌드 (오류 메시지 확인용)
#   ./build.ps1 -Release    dist/release/ 에 릴리즈 자산 둘을 만든다
#                           (dccon-downloader-<버전>.exe, dccon-downloader-<버전>-win64.zip)
#
# cargo/npm 은 진행 메시지를 stderr 로 찍는다. 그래서 ErrorActionPreference 에 기대지 않고
# 네이티브 명령마다 $LASTEXITCODE 를 직접 확인한다. 호출할 때 2>&1 을 붙이지 말 것.

param(
    [switch]$Clean,
    [switch]$Console,
    [switch]$Release
)

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

function Step([string]$msg) { Write-Host $msg -ForegroundColor Cyan }
function Check([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what 실패 (exit $LASTEXITCODE)" }
}

# 마이그레이션 zip 에 넣는 표식. 새 앱이 처음 뜰 때 이 파일 하나뿐인 _internal 을 지운다.
$MigratedText = "이전 버전에서 넘어올 때 쓰는 빈 폴더입니다. 지워도 됩니다."

if ($Clean) {
    Step "이전 빌드 정리..."
    foreach ($d in @("dist", "ui/dist")) {
        if (Test-Path $d) { Remove-Item -Recurse -Force $d }
    }
}

$meta = cargo metadata --no-deps --format-version 1 | ConvertFrom-Json
Check "cargo metadata"
$pkg = $meta.packages | Where-Object { $_.name -eq "dccon-downloader" } | Select-Object -First 1
if (-not $pkg) { throw "cargo metadata 에 dccon-downloader 패키지가 없습니다" }
$version = $pkg.version
$targetDir = $meta.target_directory

Step "프론트엔드 의존성 설치..."
npm --prefix ui ci
Check "npm ci"

$tauriArgs = @("tauri", "build", "--no-bundle")
if ($Console) { $tauriArgs += @("--", "--features", "console") }
Step ("앱 빌드 (v{0}{1})..." -f $version, $(if ($Console) { ", console" } else { "" }))
cargo @tauriArgs
Check "cargo tauri build"

$built = Join-Path $targetDir "release/dccon-downloader.exe"
if (-not (Test-Path $built)) { throw "빌드 산출물이 없습니다: $built" }

New-Item -ItemType Directory -Force dist | Out-Null
Copy-Item -Force $built "dist/dccon-downloader.exe"
$result = "dist/dccon-downloader.exe"

if ($Release) {
    Step "릴리즈 자산 만들기..."
    $rel = "dist/release"
    if (Test-Path $rel) { Remove-Item -Recurse -Force $rel }
    New-Item -ItemType Directory -Force $rel | Out-Null

    $exeAsset = "$rel/dccon-downloader-$version.exe"
    Copy-Item -Force $built $exeAsset

    # 옛 파이썬 앱(onedir)이 받는 이전용 zip. 구조가 배포된 앱과의 약속이다.
    #   dccon-downloader/dccon-downloader.exe
    #   dccon-downloader/_internal/MIGRATED.txt
    # Compress-Archive 는 PowerShell 5.1 에서 항목 이름에 역슬래시를 쓸 수 있어 .NET 으로 직접 만든다.
    Add-Type -AssemblyName System.IO.Compression
    $zipPath = Join-Path (Resolve-Path $rel).Path "dccon-downloader-$version-win64.zip"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $fs = [System.IO.File]::Open($zipPath, [System.IO.FileMode]::Create)
    try {
        $zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            $e = $zip.CreateEntry("dccon-downloader/dccon-downloader.exe", [System.IO.Compression.CompressionLevel]::Optimal)
            $es = $e.Open()
            try {
                $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $built).Path)
                $es.Write($bytes, 0, $bytes.Length)
            } finally { $es.Dispose() }

            $e = $zip.CreateEntry("dccon-downloader/_internal/MIGRATED.txt", [System.IO.Compression.CompressionLevel]::Optimal)
            $es = $e.Open()
            try {
                $bytes = $utf8.GetBytes($MigratedText)
                $es.Write($bytes, 0, $bytes.Length)
            } finally { $es.Dispose() }
        } finally { $zip.Dispose() }
    } finally { $fs.Dispose() }

    foreach ($f in Get-ChildItem $rel) {
        Write-Host ("  {0}  ({1:N2} MB)" -f $f.Name, ($f.Length / 1MB))
    }
    $result = $exeAsset
}

Write-Host ""
$mb = (Get-Item $result).Length / 1MB
Write-Host ("완료: {0}  ({1:N1} MB)" -f $result, $mb) -ForegroundColor Green
