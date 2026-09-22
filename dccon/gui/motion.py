"""Short, interruptible animations; no timers run while the UI is idle."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QApplication, QScrollArea


def motion_duration(milliseconds: int) -> int:
    app = QApplication.instance()
    return 0 if app and app.property("reduceMotion") else milliseconds


def animate(animation: QPropertyAnimation, target, duration: int = 200) -> None:
    animation.stop()
    animation.setDuration(motion_duration(duration))
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.setStartValue(animation.targetObject().property(
        bytes(animation.propertyName()).decode()
    ))
    animation.setEndValue(target)
    animation.start()


class SmoothScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        bar = self.verticalScrollBar()
        self._scroll_motion = QPropertyAnimation(bar, b"value", self)
        bar.sliderPressed.connect(self._scroll_motion.stop)
        bar.rangeChanged.connect(self._scroll_motion.stop)

    def stop_motion(self):
        self._scroll_motion.stop()

    def wheelEvent(self, event):  # noqa: N802
        # Trackpads already supply smooth pixel deltas. Preserve their native feel.
        if (not event.pixelDelta().isNull() or not motion_duration(180)
                or event.modifiers() or not event.angleDelta().y()):
            self.stop_motion()
            return super().wheelEvent(event)
        bar = self.verticalScrollBar()
        running = self._scroll_motion.state() == QPropertyAnimation.State.Running
        start = self._scroll_motion.endValue() if running else bar.value()
        target = max(bar.minimum(), min(bar.maximum(),
                     int(start - event.angleDelta().y())))
        animate(self._scroll_motion, target, 180)
        event.accept()
