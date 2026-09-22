"""앱 아이콘 생성기.

단순한 도형만 쓴 오리지널 디자인 - 둥근 사각형 바탕에 다운로드 화살표.
Qt의 ICO 플러그인은 읽기 전용이라 PNG를 그린 뒤 ICO 컨테이너로 직접 싼다.
(Vista 이후 Windows는 ICO 안에 PNG를 그대로 담는 걸 지원한다.)

    uv run python tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
)

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUT = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"

BLUE_TOP = QColor("#4d86ff")
BLUE_BOTTOM = QColor("#1f5ae0")
WHITE = QColor("#ffffff")


def render(size: int) -> bytes:
    """한 변이 size인 PNG 바이트를 만든다."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    s = float(size)
    # 바탕: 둥근 사각형에 세로 그라데이션
    margin = s * 0.06
    radius = s * 0.22
    body = QRectF(margin, margin, s - margin * 2, s - margin * 2)
    grad = QLinearGradient(QPointF(0, body.top()), QPointF(0, body.bottom()))
    grad.setColorAt(0.0, BLUE_TOP)
    grad.setColorAt(1.0, BLUE_BOTTOM)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(body, radius, radius)

    # 화살표 기둥
    cx = s / 2
    shaft_w = max(1.0, s * 0.11)
    shaft_top = s * 0.26
    shaft_bottom = s * 0.56
    p.setBrush(QBrush(WHITE))
    p.drawRoundedRect(
        QRectF(cx - shaft_w / 2, shaft_top, shaft_w, shaft_bottom - shaft_top),
        shaft_w / 2, shaft_w / 2,
    )

    # 화살촉
    head = QPainterPath()
    half = s * 0.17
    tip_y = s * 0.70
    head.moveTo(cx - half, shaft_bottom - s * 0.02)
    head.lineTo(cx + half, shaft_bottom - s * 0.02)
    head.lineTo(cx, tip_y)
    head.closeSubpath()
    p.drawPath(head)

    # 받침대
    tray_w = s * 0.46
    tray_h = max(1.0, s * 0.085)
    tray_y = s * 0.76
    p.drawRoundedRect(
        QRectF(cx - tray_w / 2, tray_y, tray_w, tray_h),
        tray_h / 2, tray_h / 2,
    )
    p.end()

    # QBuffer는 넘겨받은 QByteArray를 포인터로 들고 있다. 임시 객체를 주면
    # 곧바로 소멸해서 세그폴트가 난다. 반드시 참조를 잡아둘 것.
    store = QByteArray()
    buf = QBuffer(store)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
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
    # QPainter를 쓰려면 GUI 애플리케이션이 하나 있어야 한다.
    # 소멸 순서 때문에 죽는 일이 있어 끝까지 살려둔다.
    global _app
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    frames = {size: render(size) for size in SIZES}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_ico(frames))
    total = OUT.stat().st_size
    print(f"{OUT}  ({total:,} bytes, {len(frames)} sizes: {', '.join(map(str, SIZES))})")
    return 0


_app = None


if __name__ == "__main__":
    raise SystemExit(main())
