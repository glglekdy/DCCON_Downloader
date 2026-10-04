#!/usr/bin/env bash
# 디시콘 다운로더 macOS 빌드 스크립트
#
#   ./build.sh            -> dist/디시콘 다운로더.app
#   ./build.sh --clean    이전 빌드 산출물 먼저 정리
#   ./build.sh --console  .app 대신 터미널에서 실행해 오류를 볼 수 있게 (디버깅용)
#
# 제외 목록과 Qt 프레임워크 필터는 dccon-downloader.spec 안에 있다.

set -euo pipefail
cd "$(dirname "$0")"

CLEAN=0
CONSOLE=0
for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=1 ;;
        --console) CONSOLE=1 ;;
        *) echo "알 수 없는 옵션: $arg" >&2; exit 2 ;;
    esac
done

if [[ $CLEAN == 1 ]]; then
    echo "이전 빌드 정리..."
    rm -rf build dist
fi

if [[ ! -f assets/icon.icns ]]; then
    echo "아이콘 생성..."
    uv run python tools/make_icon.py
fi

echo "빌드 도구 준비..."
uv sync --group build

export DCCON_ONEFILE=0
export DCCON_CONSOLE=$CONSOLE

echo "PyInstaller 실행 (macOS .app)..."
uv run --group build pyinstaller --noconfirm --clean dccon-downloader.spec

APP="dist/디시콘 다운로더.app"
echo
echo "완료: $APP  ($(du -sh "$APP" | cut -f1))"
echo "실행 파일만 따로: dist/dccon-downloader/dccon-downloader"
echo "배포할 때는 ditto -c -k --keepParent \"$APP\" dccon-downloader-macos.zip 로 묶으세요."
