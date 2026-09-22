"""선택한 디시콘을 저장 폴더에 쓴다."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .cache import ImageCache
from .client import CancelledError, DcconClient
from .models import Package
from .naming import item_filename, package_dirname, pad_width

ProgressCb = Callable[[int, int, str], None]


@dataclass
class DownloadResult:
    package_idx: int
    package_title: str
    dest: Path
    saved: int = 0
    skipped: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.saved + self.skipped + len(self.failed)


def _sniff_ext(data: bytes, default: str = "png") -> str:
    """대표 이미지는 ext를 안 알려줘서 매직 바이트로 판별한다."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"GIF":
        return "gif"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return default


def download_package(
    client: DcconClient,
    cache: ImageCache,
    package: Package,
    dest_root: Path,
    *,
    only_sorts: Iterable[int] | None = None,
    save_main_image: bool = True,
    write_meta: bool = True,
    progress: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> DownloadResult:
    wanted = set(only_sorts) if only_sorts is not None else None
    items = [i for i in package.items if wanted is None or i.sort in wanted]

    dest = Path(dest_root) / package_dirname(package.idx, package.title)
    dest.mkdir(parents=True, exist_ok=True)
    result = DownloadResult(package.idx, package.title, dest)

    width = pad_width(max((i.sort for i in package.items), default=len(items)))
    total = len(items) + (1 if save_main_image and package.main_img_path else 0)
    done = 0

    if save_main_image and package.main_img_path:
        try:
            data = cache.get(client, package.main_url, "jpg", cancel=cancel)
            target = dest / f"_main.{_sniff_ext(data, 'jpg')}"
            if target.exists():
                result.skipped += 1
            else:
                target.write_bytes(data)
                result.saved += 1
        except CancelledError:
            raise
        except Exception as exc:
            result.failed.append(("_main", str(exc)))
        done += 1
        if progress:
            progress(done, total, "_main")

    for item in items:
        if cancel is not None and cancel.is_set():
            raise CancelledError()
        name = item_filename(item.sort, item.title, item.ext, width)
        target = dest / name
        try:
            if target.exists():
                # 이미 있으면 조용히 건너뛴다 -> 중단 후 재실행이 안전해진다.
                result.skipped += 1
            else:
                data = cache.get(client, item.url, item.ext, cancel=cancel)
                tmp = target.with_suffix(target.suffix + ".part")
                tmp.write_bytes(data)
                tmp.replace(target)
                result.saved += 1
        except CancelledError:
            raise
        except Exception as exc:
            result.failed.append((name, str(exc)))
        done += 1
        if progress:
            progress(done, total, name)

    if write_meta:
        _write_meta(dest, package, width)
    return result


def _write_meta(dest: Path, package: Package, width: int) -> None:
    meta = {
        "package_idx": package.idx,
        "title": package.title,
        "description": package.description,
        "seller": package.seller,
        "reg_date": package.reg_date,
        "tags": package.tags,
        "items": [
            {
                "sort": i.sort,
                "title": i.title,
                "ext": i.ext,
                "file": item_filename(i.sort, i.title, i.ext, width),
            }
            for i in package.items
        ],
    }
    try:
        (dest / "_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass
