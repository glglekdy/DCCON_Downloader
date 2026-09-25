"""dist/ 빌드로 릴리즈 자산 세 개를 dist/release/ 에 만든다.

    uv run python tools/make_release_assets.py

build.ps1 -Clean 과 -OneFile 을 둘 다 돌린 뒤에 쓴다. 다시 빌드하지 않는다.

    dccon-downloader-X.Y.Z.exe           단일 exe
    dccon-downloader-X.Y.Z.zip           폴더(onedir) - 안에 dccon-downloader/ 하나
    dccon-code-X.Y.Z-<지문 12자>.pyz     코드 업데이트 - manifest.json + dccon/
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dccon import __version__  # noqa: E402
from dccon.updater import code_asset_name, release_name  # noqa: E402

DIST = ROOT / "dist"
ONEDIR = DIST / "dccon-downloader"
ONEFILE = DIST / "dccon-downloader.exe"
OUT = DIST / "release"


def main() -> int:
    info = json.loads((ONEDIR / "_internal" / "build_info.json").read_text(encoding="utf-8"))
    if info["version"] != __version__:
        raise SystemExit(f"dist 빌드({info['version']})가 지금 버전({__version__})과 다릅니다. 다시 빌드하세요.")
    version, runtime = info["version"], info["runtime"]

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()

    shutil.copy(ONEFILE, OUT / release_name(version))

    with zipfile.ZipFile(OUT / f"dccon-downloader-{version}.zip", "w",
                         zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(ONEDIR.rglob("*")):
            if path.is_file():
                zf.write(path, Path("dccon-downloader") / path.relative_to(ONEDIR))

    # 코드는 빌드에 들어간 것과 같은 작업 트리에서 가져온다.
    manifest = {"version": version, "runtime": runtime}
    with zipfile.ZipFile(OUT / code_asset_name(version, runtime), "w",
                         zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for path in sorted((ROOT / "dccon").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                zf.write(path, path.relative_to(ROOT).as_posix())

    for path in sorted(OUT.iterdir()):
        print(f"{path.name}  {path.stat().st_size / 1048576:,.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
