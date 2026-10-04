"""앱 아이콘 모양 다듬기.

macOS 는 앱 아이콘을 알아서 둥글게 깎아 주지 않는다. 정사각형 원본을 그대로
쓰면 Dock 에서 혼자 각진 네모로 보인다. 그래서 애플 아이콘 격자대로
1024 캔버스 안 824 크기의 둥근 사각형에 원본을 담고 바깥은 투명하게 둔다.

tools/make_icon.py(빌드용 .icns)와 앱 실행 중 Dock 아이콘이 같이 쓴다.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QImage, QPainter, QPainterPath, QTransform

# 1024 기준 애플 격자: 사방 여백 100, 모서리 반지름은 몸통 한 변의 약 22.5%.
_INSET = 100 / 1024
_RADIUS = 0.225


def macos_icon(source: QImage, size: int) -> QImage:
    """원본을 한 변이 size인 macOS 모양 아이콘으로."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    inset = size * _INSET
    body = QRectF(inset, inset, size - inset * 2, size - inset * 2)
    scaled = source.scaled(
        round(body.width()), round(body.height()),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    # 클립 경로는 가장자리가 계단지므로, 원본을 브러시로 깔고 둥근 사각형을
    # 안티에일리어싱으로 칠한다.
    brush = QBrush(scaled)
    brush.setTransform(QTransform.fromTranslate(body.left(), body.top()))
    path = QPainterPath()
    radius = body.width() * _RADIUS
    path.addRoundedRect(body, radius, radius)

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(brush)
    p.drawPath(path)
    p.end()
    return image
