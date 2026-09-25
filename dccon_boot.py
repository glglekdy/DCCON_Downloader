"""코드 업데이트 부트스트랩.

exe 를 통째로 바꾸지 않고 `dccon` 패키지만 새로 받아 쓰는 업데이트를 켠다.
이 파일은 exe 에 박혀 있고 코드 업데이트로는 바뀌지 않는다. 그래서 작고
단순하게 두고, 아래 폴더 구조를 바꾸지 않는다 - 새 코드의 updater 가 같은
구조로 쓴다.

    CODE_DIR/
        current.txt          지금 쓸 코드 버전 (예: 1.2.5)
        rejected.txt         시작하다 죽어서 버린 버전
        1.2.5/
            manifest.json    {"version": "1.2.5", "runtime": "<지문>"}
            dccon/...        패키지 전체 (assets 포함)
            .unconfirmed     설치 직후. 한 번 무사히 뜨면 지운다
            .tried           .unconfirmed 상태로 한 번 띄워 봤다

런타임 지문은 exe 에 든 `dccon` 밖의 모든 것(파이썬, Qt, 라이브러리,
이 파일)의 해시다. 빌드할 때 스펙이 build_info.json 에 적는다. 지문이
같아야만 받은 코드를 올린다 - 새 코드가 exe 에 없는 모듈을 찾다 죽지 않게.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

# dccon.config.DATA_DIR 과 같아야 한다 (dccon 을 import 하기 전이라 따로 계산).
_base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
DATA_DIR = Path(_base) / "DcconDownloader" if _base else Path.home() / ".dccondownloader"
CODE_DIR = DATA_DIR / "code"
CURRENT = CODE_DIR / "current.txt"
REJECTED = CODE_DIR / "rejected.txt"
UNCONFIRMED = ".unconfirmed"
TRIED = ".tried"

# 지금 올린 코드 버전. 없으면 exe 에 든 코드로 돌고 있다.
active: str | None = None


def build_info() -> dict:
    """exe 에 박힌 {"version", "runtime"}. 소스 실행이면 빈 dict."""
    meipass = getattr(sys, "_MEIPASS", None)
    if not getattr(sys, "frozen", False) or not meipass:
        return {}
    try:
        return json.loads((Path(meipass) / "build_info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _version(text: str) -> tuple[int, ...]:
    found = re.match(r"(\d+(?:\.\d+)*)", text or "")
    return tuple(int(p) for p in found.group(1).split(".")) if found else ()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def activate() -> str | None:
    """받아 둔 코드가 이 exe 에 맞으면 sys.path 맨 앞에 올린다."""
    global active
    info = build_info()
    version = _read(CURRENT)
    if not info.get("runtime") or not version:
        return None
    folder = CODE_DIR / version
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifest.get("runtime") != info["runtime"] or manifest.get("version") != version:
        return None
    if _version(version) <= _version(info.get("version", "")):
        return None  # exe 가 더 새것이다 (전체 업데이트를 받았다)
    if (folder / UNCONFIRMED).exists():
        if (folder / TRIED).exists():
            reject(version)  # 지난번에 뜨다가 죽었다
            return None
        try:
            (folder / TRIED).touch()
        except OSError:
            return None
    sys.path.insert(0, str(folder))
    active = version
    return version


def reject(version: str) -> None:
    """이 버전은 다시 쓰지 않는다. updater 도 이걸 보고 전체 업데이트로 간다."""
    try:
        CODE_DIR.mkdir(parents=True, exist_ok=True)
        REJECTED.write_text(version, encoding="utf-8")
        if _read(CURRENT) == version:
            CURRENT.unlink()
    except OSError:
        pass
    shutil.rmtree(CODE_DIR / version, ignore_errors=True)


def fall_back() -> None:
    """올린 코드를 버리고 exe 에 든 코드로 돌아간다. import 가 실패했을 때."""
    global active
    if active is None:
        return
    folder = str(CODE_DIR / active)
    reject(active)
    while folder in sys.path:
        sys.path.remove(folder)
    for name in [n for n in sys.modules if n == "dccon" or n.startswith("dccon.")]:
        del sys.modules[name]
    active = None


def confirm() -> None:
    """무사히 떴다. 다음부터는 시작하다 죽어도 버리지 않는다."""
    if active is None:
        return
    for marker in (UNCONFIRMED, TRIED):
        try:
            (CODE_DIR / active / marker).unlink(missing_ok=True)
        except OSError:
            pass
