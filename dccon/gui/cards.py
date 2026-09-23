"""그리드에 들어가는 카드 위젯."""

from __future__ import annotations

from PySide6.QtCore import Property, QPropertyAnimation, QRectF, QSize, Qt, Signal, QSignalBlocker, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QCheckBox, QFrame, QLabel, QSizePolicy, QVBoxLayout

from . import theme
from .motion import animate

CARD_W = 180
THUMB = 152


def blend(first: QColor | str, second: QColor | str, amount: float) -> QColor:
    a, b = QColor(first), QColor(second)
    return QColor(*(round(x + (y - x) * amount) for x, y in zip(
        a.getRgb(), b.getRgb())))


class Preview(QLabel):
    def __init__(self):
        super().__init__("···")
        self.source = QPixmap()

    def set_source(self, pix):
        # Resample once on arrival, not on every hover/scroll animation frame.
        ratio = self.devicePixelRatioF()
        size = round((THUMB - 16) * ratio)
        self.source = pix.scaled(QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        self.source.setDevicePixelRatio(ratio)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        if self.source.isNull():
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 12, 12)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), theme.color("thumb_bg"))
        size = self.source.deviceIndependentSize()
        painter.drawPixmap(QPointF((self.width()-size.width())/2,
                                  (self.height()-size.height())/2), self.source)


class Card(QFrame):
    """썸네일 + 제목 + 부제. 체크박스는 선택적."""

    clicked = Signal()
    double_clicked = Signal()
    toggled = Signal(bool)

    def __init__(self, title: str, subtitle: str = "", checkable: bool = False,
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFixedWidth(CARD_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = 0.0
        self._selection = 0.0
        self._hover_motion = QPropertyAnimation(self, b"hoverAmount", self)
        self._select_motion = QPropertyAnimation(self, b"selectionAmount", self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(8)

        self.thumb = Preview()
        self.thumb.setFixedSize(THUMB, THUMB)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setObjectName("thumb")
        layout.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignHCenter)

        self.check: QCheckBox | None = None
        if checkable:
            self.check = QCheckBox(self)
            self.check.setObjectName("cardCheck")
            self.check.move(18, 22)
            self.check.setAccessibleName(f"{title} 선택")
            self.check.raise_()
            self.check.toggled.connect(self._on_toggled)

        self.title_label = QLabel()
        self.title_label.setObjectName("cardTitle")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.ensurePolished()
        self.title_label.setFixedWidth(THUMB)
        self.title_label.setToolTip(title)
        self._set_elided(self.title_label, title)
        layout.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignHCenter)

        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("cardSubtitle")
        self.subtitle_label.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle_label.ensurePolished()
        self.subtitle_label.setFixedWidth(THUMB)
        if subtitle:
            self._set_elided(self.subtitle_label, subtitle)
            self.subtitle_label.setToolTip(subtitle)
        layout.addWidget(self.subtitle_label, 0, Qt.AlignmentFlag.AlignHCenter)

    def _set_elided(self, label: QLabel, text: str) -> None:
        metrics = label.fontMetrics()
        label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, THUMB - 4))

    def _on_toggled(self, state: bool) -> None:
        if self.isVisible() and not self.visibleRegion().isEmpty():
            animate(self._select_motion, float(state), 160)
        else:
            self._select_motion.stop()
            self._set_selection(float(state))
        self.toggled.emit(state)

    def _set_hover(self, value):
        self._hover = value
        self.update()

    def _set_selection(self, value):
        self._selection = value
        self.update()

    hoverAmount = Property(float, lambda self: self._hover, _set_hover)
    selectionAmount = Property(float, lambda self: self._selection, _set_selection)

    def enterEvent(self, event):  # noqa: N802
        animate(self._hover_motion, 1.0, 180)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        animate(self._hover_motion, 0.0, 240)
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        surface = QRectF(2, 5 - self._hover * 3, self.width()-4, self.height()-10)
        painter.setPen(Qt.PenStyle.NoPen)
        shadow = theme.color("card_shadow")
        # 어두운 바탕에서는 그림자가 묻히니 더 진하게 깐다.
        depth = 4 if theme.is_dark() else 1
        for spread in (3, 2, 1):
            shadow.setAlpha(int((3 + self._hover * 4) * depth))
            painter.setBrush(shadow)
            painter.drawRoundedRect(surface.adjusted(-spread/2, 2, spread/2, spread+2), 16, 16)
        painter.setBrush(blend(theme.color("card_bg"), theme.color("card_selected_bg"),
                               self._selection))
        border = blend(theme.color("card_border"), theme.color("card_hover_border"), self._hover)
        border = blend(border, theme.color("accent"), self._selection)
        painter.setPen(QPen(border, 1 + self._selection))
        painter.drawRoundedRect(surface, 15, 15)

    # ---- 외부에서 쓰는 것들 ---------------------------------------------
    def set_image(self, data: bytes) -> None:
        pix = QPixmap()
        # GIF도 loadFromData 하면 첫 프레임만 들어온다. 그리드에서는 그게 낫다.
        if not pix.loadFromData(data):
            return
        self.thumb.set_source(pix)

    @property
    def checked(self) -> bool:
        return bool(self.check and self.check.isChecked())

    def set_checked(self, value: bool, *, animated: bool = True) -> None:
        if self.check:
            if animated:
                self.check.setChecked(value)
            else:
                changed = self.check.isChecked() != value
                with QSignalBlocker(self.check):
                    self.check.setChecked(value)
                self._select_motion.stop()
                self._set_selection(float(value))
                if changed:
                    self.toggled.emit(value)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self.check is not None:
                self.check.setChecked(not self.check.isChecked())
            else:
                self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        # PySide6는 가상 함수를 타입에서 찾는다. 인스턴스에 함수를 꽂아두면
        # 조용히 무시되므로 반드시 클래스에서 재정의해야 한다.
        if event.button() == Qt.MouseButton.LeftButton:
            # 더블클릭은 '열기'다. 앞선 press가 뒤집어 놓은 체크를 되돌린다.
            if self.check is not None:
                self.check.setChecked(not self.check.isChecked())
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)
