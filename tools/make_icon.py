"""앱 아이콘 빌더.

`dccon/gui/assets/icon.png` 한 장을 받아 윈도우가 쓰는 크기별로 줄인 뒤
ICO 컨테이너로 싼다. 아이콘 원본은 그 PNG 하나뿐이고, 앱이 실행 중에
창 아이콘으로 쓰는 것도 같은 파일이다.

Qt의 ICO 플러그인은 읽기 전용이라 컨테이너를 직접 만든다.
(Vista 이후 Windows는 ICO 안에 PNG를 그대로 담는 걸 지원한다.)

    uv run python tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QImage

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "dccon" / "gui" / "assets" / "icon.png"
OUT = ROOT / "assets" / "icon.ico"

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(source: QImage, size: int) -> bytes:
    """원본을 한 변이 size인 PNG 바이트로 줄인다."""
    frame = source.scaled(
        size, size,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    # QBuffer는 넘겨받은 QByteArray를 포인터로 들고 있다. 임시 객체를 주면
    # 곧바로 소멸해서 세그폴트가 난다. 반드시 참조를 잡아둘 것.
    store = QByteArray()
    buf = QBuffer(store)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    frame.save(buf, "PNG")
    buf.close()
    return bytes(store)


def build_ico(frames: dict[int, bytes]) -> bytes:
    """ICONDIR + ICONDIRENTRY들 + PNG 데이터."""
    count = len(frames)
    header = struct.pack("<HHH", 0, 1, count)  # reserved, type=icon, count
    entries = bytearray()
    payload = bytearray()
    offset = 6 + 16 * count

    for size in sorted(frames):
        data = frames[size]
        dim = 0 if size >= 256 else size  # 0은 256을 뜻한다
        entries += struct.pack(
            "<BBBBHHII",
            dim, dim,      # width, height
            0,             # 팔레트 색 수 (트루컬러면 0)
            0,             # reserved
            1,             # color planes
            32,            # bits per pixel
            len(data),
            offset,
        )
        payload += data
        offset += len(data)

    return bytes(header + entries + payload)


def main() -> int:
    # QImage를 쓰려면 GUI 애플리케이션이 하나 있어야 한다.
    # 소멸 순서 때문에 죽는 일이 있어 끝까지 살려둔다.
    global _app
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    if not SOURCE.exists():
        print(f"원본이 없습니다: {SOURCE}", file=sys.stderr)
        return 1
    source = QImage(str(SOURCE))
    if source.isNull():
        print(f"원본을 읽을 수 없습니다: {SOURCE}", file=sys.stderr)
        return 1

    frames = {size: render(source, size) for size in SIZES}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_ico(frames))
    print(f"{OUT}  ({OUT.stat().st_size:,} bytes, "
          f"{len(frames)} sizes: {', '.join(map(str, SIZES))})")
    return 0


_app = None


if __name__ == "__main__":
    raise SystemExit(main())
