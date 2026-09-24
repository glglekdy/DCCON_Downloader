"""GitHub 릴리즈로 자기 자신을 업데이트한다.

흐름은 셋으로 나뉜다.

1. `fetch_latest()`  - releases/latest 를 읽어 지금보다 새 버전인지 본다.
2. `download()`      - 이 빌드 방식에 맞는 자산을 받아 스테이징 폴더에 풀어둔다.
3. `launch_apply()`  - 도우미 스크립트를 띄우고 앱은 종료한다. 스크립트가
                       앱이 완전히 끝나기를 기다렸다가 파일을 덮어쓰고 다시 띄운다.

실행 중인 exe 와 `_internal` 의 DLL 은 윈도우가 잠그고 있어서 앱이 스스로
덮어쓸 수 없다. 그래서 마지막 단계만큼은 바깥 프로세스가 맡는다.

릴리즈 자산 이름 규칙 (build.ps1 산출물을 그대로 올리면 된다):
    *.exe   단일 exe 빌드용
    *.zip   onedir 빌드용 (dccon-downloader 폴더를 통째로 압축한 것)
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from . import __version__
from .config import DATA_DIR

REPO = "glglekdy/DCCON_Downloader"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"

UPDATE_DIR = DATA_DIR / "update"
ERROR_LOG = UPDATE_DIR / "last_error.log"


class UpdateError(RuntimeError):
    """사용자에게 그대로 보여줄 수 있는 업데이트 실패."""


class UpdateCancelled(Exception):
    pass


# ---------------------------------------------------------------- 버전
def parse_version(text: str) -> tuple[int, ...]:
    """`v1.2.3`, `1.2`, `1.2.3-beta` 모두 숫자 부분만 비교한다."""
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    if not match:
        return ()
    parts = [int(p) for p in match.group(1).split(".")]
    # 1.2 와 1.2.0 을 같게 본다.
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(remote: str, local: str = __version__) -> bool:
    remote_v = parse_version(remote)
    return bool(remote_v) and remote_v > parse_version(local)


# ---------------------------------------------------------- 실행 형태
def build_kind() -> str | None:
    """'onefile', 'onedir', 또는 소스 실행이면 None.

    PyInstaller 6 onedir 은 `_MEIPASS` 가 exe 옆의 `_internal` 이고,
    onefile 은 임시 폴더라 exe 위치와 무관하다.
    """
    if not getattr(sys, "frozen", False):
        return None
    meipass = getattr(sys, "_MEIPASS", None)
    exe_dir = Path(sys.executable).resolve().parent
    if meipass and exe_dir in Path(meipass).resolve().parents:
        return "onedir"
    return "onefile"


def can_self_update() -> bool:
    return sys.platform == "win32" and build_kind() is not None


# ---------------------------------------------------------------- 릴리즈
@dataclass
class Asset:
    name: str
    url: str
    size: int
    digest: str = ""  # "sha256:..." (GitHub 가 2025년부터 채워준다)


@dataclass
class Release:
    tag: str
    name: str
    notes: str
    page_url: str
    assets: list[Asset]

    @property
    def version(self) -> str:
        return self.tag.lstrip("vV")

    @classmethod
    def from_api(cls, data: dict) -> "Release":
        return cls(
            tag=data.get("tag_name") or "",
            name=data.get("name") or data.get("tag_name") or "",
            notes=data.get("body") or "",
            page_url=data.get("html_url") or RELEASES_PAGE,
            assets=[
                Asset(
                    name=a.get("name") or "",
                    url=a.get("browser_download_url") or "",
                    size=int(a.get("size") or 0),
                    digest=a.get("digest") or "",
                )
                for a in data.get("assets") or []
            ],
        )

    def pick_asset(self, kind: str | None) -> Asset | None:
        suffix = {"onefile": ".exe", "onedir": ".zip"}.get(kind or "")
        if not suffix:
            return None
        matches = [a for a in self.assets if a.name.lower().endswith(suffix) and a.url]
        # 여러 개면 이름에 win 이 들어간 쪽을 먼저 본다.
        matches.sort(key=lambda a: "win" not in a.name.lower())
        return matches[0] if matches else None


def _http(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": f"dccon-downloader/{__version__}",
            "Accept": "application/vnd.github+json",
        },
    )


def fetch_latest(client: httpx.Client | None = None) -> Release | None:
    """최신 정식 릴리즈. 릴리즈가 하나도 없으면 None."""
    owns = client is None
    client = client or _http()
    try:
        resp = client.get(LATEST_URL)
    except httpx.HTTPError as exc:
        raise UpdateError(f"GitHub 에 연결하지 못했습니다. ({exc.__class__.__name__})") from exc
    finally:
        if owns:
            client.close()
    if resp.status_code == 404:
        return None
    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        raise UpdateError("GitHub 요청 한도를 넘었습니다. 잠시 뒤 다시 시도하세요.")
    if resp.status_code >= 400:
        raise UpdateError(f"릴리즈 정보를 가져오지 못했습니다. (HTTP {resp.status_code})")
    return Release.from_api(resp.json())


# ------------------------------------------------------------ 다운로드
@dataclass
class StagedUpdate:
    release: Release
    kind: str
    source: Path   # 설치 폴더에 그대로 덮어쓸 내용이 들어있는 폴더


def download(
    release: Release,
    kind: str,
    *,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
    client: httpx.Client | None = None,
    staging_root: Path = UPDATE_DIR,
) -> StagedUpdate:
    asset = release.pick_asset(kind)
    if asset is None:
        raise UpdateError("이 릴리즈에는 이 빌드에 맞는 파일이 없습니다.")

    work = staging_root / release.tag
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    target = work / asset.name
    part = target.with_name(target.name + ".part")

    owns = client is None
    client = client or _http(timeout=60.0)
    hasher = hashlib.sha256()
    try:
        try:
            _stream_to(client, asset, part, hasher, progress, cancel)
        except httpx.HTTPError as exc:
            raise UpdateError(f"다운로드가 끊겼습니다. ({exc.__class__.__name__})") from exc
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    finally:
        if owns:
            client.close()

    if asset.size and part.stat().st_size != asset.size:
        part.unlink(missing_ok=True)
        raise UpdateError("받은 파일 크기가 맞지 않습니다. 다시 시도하세요.")
    algo, _, expected = asset.digest.partition(":")
    if algo == "sha256" and expected and hasher.hexdigest() != expected.lower():
        part.unlink(missing_ok=True)
        raise UpdateError("받은 파일이 손상되었습니다. (SHA-256 불일치)")
    part.replace(target)

    source = work / "app"
    if kind == "onefile":
        # 사용자가 exe 이름을 바꿔 썼을 수도 있으니 지금 이름에 맞춘다.
        source.mkdir()
        shutil.move(str(target), source / Path(sys.executable).name)
    else:
        source = _extract_onedir(target, source)
    return StagedUpdate(release=release, kind=kind, source=source)


def _stream_to(client: httpx.Client, asset: Asset, part: Path, hasher,
               progress, cancel) -> None:
    with client.stream("GET", asset.url) as resp:
        if resp.status_code >= 400:
            raise UpdateError(f"파일을 받지 못했습니다. (HTTP {resp.status_code})")
        total = int(resp.headers.get("content-length") or asset.size or 0)
        done = 0
        with part.open("wb") as fh:
            for chunk in resp.iter_bytes(64 * 1024):
                if cancel is not None and cancel.is_set():
                    raise UpdateCancelled()
                fh.write(chunk)
                hasher.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)


def _extract_onedir(archive: Path, dest: Path) -> Path:
    try:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)  # zipfile 이 절대경로와 .. 를 걸러준다
    except zipfile.BadZipFile as exc:
        raise UpdateError("받은 압축 파일이 올바르지 않습니다.") from exc
    archive.unlink(missing_ok=True)

    # 폴더째 압축했으면 한 단계 내려간다.
    root = dest
    entries = list(root.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        root = entries[0]
    if not (root / "_internal").is_dir() or not any(root.glob("*.exe")):
        raise UpdateError("압축 안에 실행 파일과 _internal 폴더가 없습니다.")
    return root


# ------------------------------------------------------------- 적용
# 앱이 끝나기를 기다렸다가 덮어쓰고 다시 띄운다. 실패하면 되돌리고
# 로그를 남긴 뒤 옛 버전을 띄운다 - 다음 실행 때 앱이 로그를 보여준다.
_APPLY_SCRIPT = r"""
param(
    [string]$WaitPids,
    [string]$Source,
    [string]$Target,
    [string]$Exe,
    [string]$Log
)
$ErrorActionPreference = 'Stop'

foreach ($p in $WaitPids.Split(',')) {
    if ($p) { Wait-Process -Id ([int]$p) -Timeout 120 -ErrorAction SilentlyContinue }
}
foreach ($p in $WaitPids.Split(',')) {
    if ($p -and (Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue)) {
        '앱이 종료되지 않아 업데이트를 취소했습니다.' | Out-File $Log -Encoding utf8
        exit 1
    }
}

# 프로세스가 끝나도 파일 핸들이 늦게 풀리는 경우가 있어 몇 번 더 시도한다.
function Retry([scriptblock]$Action) {
    for ($i = 0; $i -lt 20; $i++) {
        try { & $Action; return } catch {
            if ($i -eq 19) { throw }
            Start-Sleep -Milliseconds 500
        }
    }
}

$internal = Join-Path $Target '_internal'
$backup = Join-Path $Target '_internal.old'
$newInternal = Join-Path $Source '_internal'

try {
    # onedir: _internal 은 섞지 않고 통째로 바꾼다. 옛 파일이 남으면 꼬인다.
    # exe 보다 먼저 바꿔야 실패했을 때 옛 exe + 옛 _internal 로 되돌릴 수 있다.
    if (Test-Path $newInternal) {
        if (Test-Path $backup) { Remove-Item $backup -Recurse -Force }
        if (Test-Path $internal) { Retry { Rename-Item $internal '_internal.old' } }
        Retry {
            if (Test-Path $internal) { Remove-Item $internal -Recurse -Force }
            Copy-Item $newInternal $Target -Recurse -Force
        }
    }
    Retry {
        Get-ChildItem $Source | Where-Object { $_.Name -ne '_internal' } |
            Copy-Item -Destination $Target -Recurse -Force
    }
    if (Test-Path $backup) { Remove-Item $backup -Recurse -Force -ErrorAction SilentlyContinue }
} catch {
    "업데이트를 적용하지 못했습니다.`r`n$_" | Out-File $Log -Encoding utf8
    if (Test-Path $backup) {
        Remove-Item $internal -Recurse -Force -ErrorAction SilentlyContinue
        Rename-Item $backup '_internal' -ErrorAction SilentlyContinue
    }
}

Start-Process -FilePath $Exe -WorkingDirectory $Target
"""


def launch_apply(staged: StagedUpdate) -> None:
    """도우미를 띄운다. 호출한 쪽은 곧바로 앱을 종료해야 한다."""
    if not can_self_update():
        raise UpdateError("설치된 exe 에서만 자동 업데이트할 수 있습니다.")
    exe = Path(sys.executable).resolve()
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    script = UPDATE_DIR / "apply_update.ps1"
    # PowerShell 5.1 은 BOM 이 없으면 ANSI 로 읽어 한글이 깨진다.
    script.write_text(_APPLY_SCRIPT, encoding="utf-8-sig")
    ERROR_LOG.unlink(missing_ok=True)

    pids = [os.getpid()]
    if staged.kind == "onefile":
        # onefile 은 부트로더 부모 프로세스가 exe 를 잡고 있다.
        pids.append(os.getppid())

    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
            "-File", str(script),
            "-WaitPids", ",".join(str(p) for p in pids),
            "-Source", str(staged.source),
            "-Target", str(exe.parent),
            "-Exe", str(exe),
            "-Log", str(ERROR_LOG),
        ],
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def take_last_error() -> str | None:
    """지난 업데이트가 실패했으면 그 내용을 돌려주고 흔적을 지운다."""
    try:
        text = ERROR_LOG.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None
    ERROR_LOG.unlink(missing_ok=True)
    return text or None


# 릴리즈 자산 이름. 1.2.2 까지는 -win64 가 붙어 탐색기에 뜨는 이름이 길었다.
# 한글 이름도 시도했지만 깃허브가 자산 이름에서 비ASCII 를 지워버린다
# ("디시콘 다운로더 1.2.2.exe" -> "1.2.2.exe"). 그래서 ASCII 로 줄였다.
# 앱 이름 자체는 exe 의 버전 리소스(FileDescription)가 들고 있다.
# 이미 받아 둔 옛 파일도 정리해야 하므로 -win64 가 붙은 것도 알아본다.
_BUILD_NAME = re.compile(
    r"^dccon-downloader-(\d+\.\d+\.\d+)(?:-win64)?\.exe$", re.IGNORECASE)
_BUILD_GLOBS = ("dccon-downloader-*.exe",)


def release_name(version: str | None = None) -> str:
    """릴리즈에 올리는 단일 exe 이름.

    기본 인자에 __version__ 을 직접 두면 정의 시점 값이 굳어버린다.
    호출할 때 읽도록 None 을 받는다.
    """
    return f"dccon-downloader-{version or __version__}.exe"


def _named_version(name: str) -> str | None:
    """파일 이름에서 버전을 뽑는다. 우리 자산 형식이 아니면 None."""
    found = _BUILD_NAME.match(name)
    return found.group(1) if found else None


def _recycle(path: Path) -> bool:
    """휴지통으로 보낸다. 사용자 파일이라 완전 삭제는 하지 않는다."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_SILENT = 0x0004
    FOF_NOCONFIRMATION = 0x0010
    FOF_ALLOWUNDO = 0x0040        # 이게 휴지통으로 보내는 플래그다
    FOF_NOERRORUI = 0x0400

    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    # pFrom 은 널로 끝나는 목록이라 끝에 널이 하나 더 붙어야 한다.
    op.pFrom = str(path) + "\0\0"
    op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI
    try:
        return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0
    except OSError:
        return False


def tidy_sibling_builds() -> list[str]:
    """업데이트로 갈아탄 뒤 남은 예전 버전 exe 를 치운다.

    onefile 은 실행 중이던 exe 를 그 이름 그대로 덮어쓴다. 그래서
    dccon-downloader-1.1.0-win64.exe 를 받아 쓰던 사람은 1.2.0 이 들어간
    뒤에도 파일명이 1.1.0 으로 남는다. 이름을 지금 버전에 맞추고, 같은
    폴더에 남은 더 낮은 버전은 휴지통으로 보낸다.

    릴리즈 자산 이름 형식에 정확히 맞는 파일만 건드린다. 사용자가 직접
    이름을 붙인 exe 는 형식이 달라 걸리지 않는다.
    """
    if build_kind() != "onefile":
        return []
    exe = Path(sys.executable).resolve()
    folder = exe.parent

    # 1) 실행 파일 이름을 지금 버전·형식에 맞춘다. 버전이 같아도 예전
    #    이름이면 새 이름으로 옮긴다. 윈도우는 실행 중인 exe 도 이름
    #    바꾸기는 허용한다(삭제만 막는다).
    wanted = release_name()
    if _named_version(exe.name) and exe.name != wanted:
        target = folder / wanted
        try:
            if target.exists():
                # 같은 이름이 이미 있으면 그건 지금 우리와 같은 버전이다.
                _recycle(target)
            if not target.exists():
                exe.rename(target)
                exe = target
        except OSError:
            pass  # 이름은 못 바꿔도 아래 정리는 계속한다.

    # 2) 같은 폴더의 더 낮은 버전을 휴지통으로.
    removed: list[str] = []
    here = parse_version(__version__)
    seen: set[Path] = set()
    for pattern in _BUILD_GLOBS:
        for entry in sorted(folder.glob(pattern)):
            if entry in seen:
                continue
            seen.add(entry)
            found = _named_version(entry.name)
            if not found or entry.resolve() == exe:
                continue
            if parse_version(found) < here and _recycle(entry):
                removed.append(entry.name)
    return removed


def cleanup_staging() -> None:
    """적용이 끝난 스테이징 폴더를 치운다. 로그는 남긴다."""
    if not UPDATE_DIR.is_dir():
        return
    for entry in UPDATE_DIR.iterdir():
        if entry == ERROR_LOG:
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)
