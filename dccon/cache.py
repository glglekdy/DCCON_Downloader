"""디스크 캐시.

디시콘 한 장은 7~10KB짜리 100x100 / 200x200 이미지라 캐시가 아주 싸다.
그래서 미리보기로 한 번 받아두면 '다운로드'는 네트워크가 아니라
캐시에서 저장 폴더로 복사하는 작업이 된다.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.parse
from pathlib import Path

from .client import DcconClient
from .config import IMAGE_CACHE_DIR, META_CACHE_DIR

_NO_PARAM = re.compile(r"[?&]no=([^&]+)")


def cache_key(url_or_path: str) -> str:
    """`no=` 값만 뽑아 키로 쓴다. 뒤에 붙는 &date= 는 무시."""
    m = _NO_PARAM.search(url_or_path)
    token = m.group(1) if m else url_or_path
    token = urllib.parse.unquote(token)
    return hashlib.sha1(token.encode("utf-8")).hexdigest()


class ImageCache:
    def __init__(self, root: Path = IMAGE_CACHE_DIR) -> None:
        self.root = root
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _path(self, key: str, ext: str) -> Path:
        return self.root / key[:2] / f"{key}.{ext.lower().lstrip('.')}"

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())

    def peek(self, url: str, ext: str) -> bytes | None:
        p = self._path(cache_key(url), ext)
        try:
            return p.read_bytes()
        except OSError:
            return None

    def get(self, client: DcconClient, url: str, ext: str = "png", **kw) -> bytes:
        """캐시에 있으면 그대로, 없으면 받아서 저장한 뒤 돌려준다."""
        key = cache_key(url)
        path = self._path(key, ext)
        try:
            return path.read_bytes()
        except OSError:
            pass
        with self._lock_for(key):
            # 락을 기다리는 사이 다른 스레드가 받아놨을 수 있다.
            try:
                return path.read_bytes()
            except OSError:
                pass
            data = client.get(url, **kw).content
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(path)
            return data

    # ---- 관리 ---------------------------------------------------------
    def stats(self) -> tuple[int, int]:
        """(파일 수, 총 바이트)."""
        count = total = 0
        if not self.root.exists():
            return (0, 0)
        for p in self.root.rglob("*"):
            if p.is_file():
                count += 1
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return (count, total)

    def clear(self) -> None:
        import shutil

        for target in (self.root, META_CACHE_DIR):
            shutil.rmtree(target, ignore_errors=True)


class MetaCache:
    """package_detail 응답을 그대로 보관한다."""

    def __init__(self, root: Path = META_CACHE_DIR) -> None:
        self.root = root

    def _path(self, package_idx: int) -> Path:
        return self.root / f"{package_idx}.json"

    def load(self, package_idx: int) -> dict | None:
        try:
            return json.loads(self._path(package_idx).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def store(self, package_idx: int, payload: dict) -> None:
        p = self._path(package_idx)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
