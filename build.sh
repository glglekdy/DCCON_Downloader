#!/usr/bin/env bash
# 디시콘 다운로더 macOS 빌드 스크립트
#
#   ./build.sh            -> dist/디시콘 다운로더.app (유니버설), dist/dccon-downloader-<버전>-macos.zip
#   ./build.sh --clean    이전 빌드 산출물(dist/, ui/dist/) 먼저 정리

set -euo pipefail
cd "$(dirname "$0")"

CLEAN=0
for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=1 ;;
        *) echo "알 수 없는 옵션: $arg" >&2; exit 2 ;;
    esac
done

if [[ $CLEAN == 1 ]]; then
    echo "이전 빌드 정리..."
    rm -rf dist ui/dist
fi

VERSION=$(cargo metadata --no-deps --format-version 1 \
    | python3 -c 'import json,sys; print(next(p["version"] for p in json.load(sys.stdin)["packages"] if p["name"]=="dccon-downloader"))')
TARGET_DIR=$(cargo metadata --no-deps --format-version 1 \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["target_directory"])')

echo "프론트엔드 의존성 설치..."
npm --prefix ui ci

echo "앱 빌드 (v$VERSION, macOS 유니버설 .app: Apple Silicon + Intel)..."
# 두 아키텍처를 한 .app 에 담는다 (Intel 맥에서도 뜨게). 두 타깃이 깔려 있어야 한다.
if command -v rustup >/dev/null; then
    rustup target add aarch64-apple-darwin x86_64-apple-darwin
fi
cargo tauri build --target universal-apple-darwin --bundles app

SRC=$(ls -d "$TARGET_DIR"/universal-apple-darwin/release/bundle/macos/*.app | head -n 1)
APP="dist/디시콘 다운로더.app"
mkdir -p dist
rm -rf "$APP"
ditto "$SRC" "$APP"

ZIP="dist/dccon-downloader-$VERSION-macos.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"

echo
echo "완료: $ZIP  ($(du -sh "$ZIP" | cut -f1))"
echo "앱: $APP"
