"""앱 경로와 사용자 설정."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path

APP_NAME = "DcconDownloader"


def _data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


DATA_DIR = _data_dir()
CACHE_DIR = DATA_DIR / "cache"
IMAGE_CACHE_DIR = CACHE_DIR / "img"
META_CACHE_DIR = CACHE_DIR / "meta"
SETTINGS_PATH = DATA_DIR / "settings.json"


def default_download_dir() -> Path:
    return Path.home() / "Downloads" / "dccon"


@dataclass
class Settings:
    download_dir: str = field(default_factory=lambda: str(default_download_dir()))
    # 보수적 기본값. 디시 서버에 무리 주지 않는 선.
    concurrency: int = 3
    save_main_image: bool = True
    write_meta_json: bool = True
    reduce_motion: bool = False
    theme: str = "system"  # system / light / dark
    check_updates: bool = True
    skipped_version: str = ""
    recent_packages: list[int] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(SETTINGS_PATH)

    def remember(self, package_idx: int, limit: int = 24) -> None:
        recent = [i for i in self.recent_packages if i != package_idx]
        recent.insert(0, package_idx)
        self.recent_packages = recent[:limit]
