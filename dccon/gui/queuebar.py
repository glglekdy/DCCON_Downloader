"""하단 진행 상태 바. 접었다 폈다 한다."""

from __future__ import annotations

from PySide6.QtCore import Signal, QPropertyAnimation, Qt
from .motion import animate
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class QueueBar(QFrame):
    cancel_requested = Signal()
    pause_toggled = Signal(bool)
    open_folder_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("queueBar")
        self._rows: dict[int, QTreeWidgetItem] = {}
        self._paused = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.detail = QTreeWidget()
        self.detail.setObjectName("queueDetail")
        self.detail.setHeaderLabels(["패키지", "상태"])
        self.detail.setRootIsDecorated(False)
        self.detail.setColumnWidth(0, 340)
        self.detail.setMaximumHeight(170)
        self.detail.hide()
        self._detail_motion = QPropertyAnimation(self.detail, b"maximumHeight", self)
        self._detail_motion.finished.connect(self._finish_detail_motion)
        outer.addWidget(self.detail)

        row = QFrame()
        row.setObjectName("queueSummary")
        summary_layout = QVBoxLayout(row)
        summary_layout.setContentsMargins(20, 12, 20, 18)
        summary_layout.setSpacing(12)
        bar = QHBoxLayout()
        bar.setSpacing(10)
        summary_layout.addLayout(bar)

        self.status = QLabel("다운로드 준비 완료")
        self.status.setObjectName("queueStatus")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        bar.addWidget(self.status, 1)

        self.progress = QProgressBar()
        self.progress.setObjectName("downloadProgress")
        self.progress.setMinimumWidth(100)
        self.progress.setFixedHeight(12)
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName("전체 다운로드 진행률")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._progress_motion = QPropertyAnimation(self.progress, b"value", self)
        track = QHBoxLayout()
        track.setSpacing(12)
        track.addWidget(self.progress, 1)
        self.percent = QLabel("0%")
        self.percent.setObjectName("progressPercent")
        self.percent.setFixedWidth(44)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.progress.valueChanged.connect(lambda value: self.percent.setText(f"{value}%"))
        track.addWidget(self.percent)
        summary_layout.addLayout(track)

        self.folder_btn = QPushButton("폴더 열기")
        self.folder_btn.clicked.connect(self.open_folder_requested)
        bar.addWidget(self.folder_btn)

        self.pause_btn = QPushButton("일시정지")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._toggle_pause)
        bar.addWidget(self.pause_btn)

        self.cancel_btn = QPushButton("중단")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_requested)
        bar.addWidget(self.cancel_btn)

        self.expand_btn = QPushButton("▲")
        self.expand_btn.setFixedWidth(34)
        self.expand_btn.setToolTip("다운로드 내역 펼치기 / 접기")
        self.expand_btn.setAccessibleName("다운로드 내역 펼치기 / 접기")
        self.expand_btn.setCheckable(True)
        self.expand_btn.toggled.connect(self._toggle_detail)
        bar.addWidget(self.expand_btn)

        outer.addWidget(row)

    # ---- 표시 전환 ------------------------------------------------------
    def _toggle_detail(self, shown: bool) -> None:
        self._detail_motion.stop()
        if shown and self.detail.isHidden():
            self.detail.setMaximumHeight(0)
            self.detail.show()
        animate(self._detail_motion, 170 if shown else 0, 240)
        self.expand_btn.setText("▼" if shown else "▲")

    def _finish_detail_motion(self) -> None:
        if not self.expand_btn.isChecked():
            self.detail.hide()

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_btn.setText("재개" if self._paused else "일시정지")
        self.pause_toggled.emit(self._paused)

    # ---- 진행 상태 ------------------------------------------------------
    def start(self, packages: list[tuple[int, str]]) -> None:
        self.detail.clear()
        self._rows.clear()
        for idx, title in packages:
            item = QTreeWidgetItem([title, "대기"])
            self.detail.addTopLevelItem(item)
            self._rows[idx] = item
        self._progress_motion.stop()
        self.progress.setValue(0)
        self.cancel_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self._paused = False
        self.pause_btn.setText("일시정지")
        self.status.setText(f"{len(packages)}개 패키지 진행 중")

    def update_package(self, package_idx: int, done: int, total: int,
                       note: str = "") -> None:
        item = self._rows.get(package_idx)
        if item is not None:
            item.setText(1, f"{done}/{total}" + (f"  {note}" if note else ""))

    def finish_package(self, package_idx: int, text: str) -> None:
        item = self._rows.get(package_idx)
        if item is not None:
            item.setText(1, text)

    def set_overall(self, done: int, total: int) -> None:
        pct = int(done * 100 / total) if total else 0
        animate(self._progress_motion, pct, 260)
        self.status.setText(f"{done}/{total} 항목  ({pct}%)")

    def finish(self, summary: str) -> None:
        animate(self._progress_motion, 100, 260)
        self.status.setText(summary)
        self.cancel_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self._paused = False
        self.pause_btn.setText("일시정지")

    def set_idle(self, text: str = "대기 중") -> None:
        self.status.setText(text)
        self._progress_motion.stop()
        self.progress.setValue(0)
        self.cancel_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
