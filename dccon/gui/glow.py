"""독 주변의 빛과 그림자.

둘 다 블러 이펙트를 쓰지 않는다. QGraphicsDropShadowEffect는 소스가 바뀔
때마다 위젯 전체를 CPU에서 다시 합성하는데, 독 안에는 다운로드 중 계속
갱신되는 진행바가 들어 있어서 그 비용을 매 프레임 물게 된다. 카드가 쓰는
방식대로 둥근 사각형 몇 장을 겹쳐 그리는 쪽이 훨씬 싸고 결과도 비슷하다.

색은 paintEvent에서 theme을 읽는다. 테마가 바뀌면 다시 칠하기만 하면 된다.
"""

from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation,
                            QRectF, Qt)
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

from . import theme
from .motion import motion_duration


class DockShade(QWidget):
    """독이 떠 보이도록 뒤에 깔아주는 옅은 그림자."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._target: QWidget | None = None

    def follow(self, widget: QWidget) -> None:
        """그림자를 드리울 위젯. 실제 geometry를 따라가므로 여백과 무관하다."""
        self._target = widget

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._target is None:
            return
        base = QRectF(self._target.geometry())
        shade = theme.color("dock_shadow")
        # 어두운 바탕에서는 같은 알파로는 그림자가 보이지 않는다.
        boost = 2.2 if theme.is_dark() else 1.0
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for spread, alpha in ((10, 8), (6, 10), (3, 12)):
            painter.setBrush(QColor(shade.red(), shade.green(), shade.blue(),
                                    min(255, round(alpha * boost))))
            painter.drawRoundedRect(
                base.adjusted(-spread, -spread * 0.4, spread, spread + 2),
                20 + spread, 20 + spread)


class DownloadGlow(QWidget):
    """다운로드가 도는 동안 화면 바닥에서 숨쉬듯 번지는 그라데이션."""

    HEIGHT = 260

    # (위치, 알파) — 색은 테마의 glow 토큰에서 가져온다.
    STOPS = ((0.00, 0.26), (0.38, 0.13), (0.72, 0.04), (1.00, 0.00))

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # 빛일 뿐이니 클릭은 아래 위젯이 그대로 받아야 한다.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._strength = 0.0

        self._fade = QPropertyAnimation(self, b"strength", self)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._after_fade)

        self._pulse = QPropertyAnimation(self, b"strength", self)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.setLoopCount(-1)
        self._pulse.setStartValue(0.72)
        self._pulse.setKeyValueAt(0.5, 1.0)
        self._pulse.setEndValue(0.72)

        self.hide()

    # ---- 세기 ------------------------------------------------------------
    def _set_strength(self, value: float) -> None:
        self._strength = value
        self.update()

    strength = Property(float, lambda self: self._strength, _set_strength)

    # ---- 켜고 끄기 -------------------------------------------------------
    def start(self) -> None:
        self._pulse.stop()
        self._fade.stop()
        self.show()
        duration = motion_duration(420)
        if not duration:
            self._set_strength(1.0)
            return
        self._fade.setDuration(duration)
        self._fade.setStartValue(self._strength)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def stop(self) -> None:
        self._pulse.stop()
        self._fade.stop()
        duration = motion_duration(520)
        if not duration:
            self._set_strength(0.0)
            self.hide()
            return
        self._fade.setDuration(duration)
        self._fade.setStartValue(self._strength)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _after_fade(self) -> None:
        if self._strength <= 0.01:
            self.hide()
            return
        # 다 켜졌으면 그때부터 천천히 숨쉰다.
        duration = motion_duration(2600)
        if duration:
            self._pulse.setDuration(duration)
            self._pulse.start()

    # ---- 그리기 ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        if self._strength <= 0.01:
            return
        tint = theme.color("glow")
        # 어두운 바탕에서는 같은 알파가 거의 묻힌다.
        boost = 1.5 if theme.is_dark() else 1.0
        painter = QPainter(self)
        gradient = QLinearGradient(QPointF(0, self.height()), QPointF(0, 0))
        for stop, alpha in self.STOPS:
            gradient.setColorAt(stop, QColor(
                tint.red(), tint.green(), tint.blue(),
                min(255, round(255 * alpha * boost * self._strength))))
        painter.fillRect(self.rect(), gradient)
