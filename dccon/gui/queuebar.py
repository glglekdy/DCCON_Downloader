"""다운로드 중에 독을 채우는 진행 표시. 한 줄 요약 + 얇은 진행바.

패키지별 내역은 '내역' 버튼으로 위에 펼친다.
"""

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
    # 끝난 뒤 '확인'을 누르면 독이 선택 모드로 돌아간다.
    dismissed = Signal()

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
        self.detail.setColumnWidth(0, 300)
        self.detail.setMaximumHeight(170)
        self.detail.hide()
        self._detail_motion = QPropertyAnimation(self.detail, b"maximumHeight", self)
        self._detail_motion.finished.connect(self._finish_detail_motion)
        outer.addWidget(self.detail)

        row = QHBoxLayout()
        row.setContentsMargins(16, 8, 8, 8)
        row.setSpacing(6)

        text = QVBoxLayout()
        text.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.status = QLabel("다운로드 준비 완료")
        self.status.setObjectName("queueStatus")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        head.addWidget(self.status, 1)
        self.percent = QLabel("0%")
        self.percent.setObjectName("progressPercent")
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.percent)
        text.addLayout(head)

        self.progress = QProgressBar()
        self.progress.setObjectName("downloadProgress")
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName("전체 다운로드 진행률")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._progress_motion = QPropertyAnimation(self.progress, b"value", self)
        self.progress.valueChanged.connect(lambda value: self.percent.setText(f"{value}%"))
        text.addWidget(self.progress)
        row.addLayout(text, 1)
        row.addSpacing(8)

        self.expand_btn = QPushButton("내역")
        self.expand_btn.setObjectName("ghost")
        self.expand_btn.setToolTip("패키지별 진행 내역 펼치기 / 접기")
        self.expand_btn.setAccessibleName("다운로드 내역 펼치기 / 접기")
        self.expand_btn.setCheckable(True)
        self.expand_btn.toggled.connect(self._toggle_detail)
        row.addWidget(self.expand_btn)

        self.pause_btn = QPushButton("일시정지")
        self.pause_btn.setObjectName("ghost")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._toggle_pause)
        row.addWidget(self.pause_btn)

        self.cancel_btn = QPushButton("중단")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_requested)
        row.addWidget(self.cancel_btn)

        self.done_btn = QPushButton("확인")
        self.done_btn.setObjectName("primary")
        self.done_btn.clicked.connect(self.dismissed)
        self.done_btn.hide()
        row.addWidget(self.done_btn)

        outer.addLayout(row)

    # ---- 표시 전환 ------------------------------------------------------
    def _toggle_detail(self, shown: bool) -> None:
        self._detail_motion.stop()
        if shown and self.detail.isHidden():
            self.detail.setMaximumHeight(0)
            self.detail.show()
        animate(self._detail_motion, 170 if shown else 0, 240)

    def _finish_detail_motion(self) -> None:
        if not self.expand_btn.isChecked():
            self.detail.hide()

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_btn.setText("재개" if self._paused else "일시정지")
        self.pause_toggled.emit(self._paused)

    def _set_running(self, running: bool) -> None:
        self.cancel_btn.setEnabled(running)
        self.pause_btn.setEnabled(running)
        self.cancel_btn.setVisible(running)
        self.pause_btn.setVisible(running)
        self.done_btn.setVisible(not running)
        self._paused = False
        self.pause_btn.setText("일시정지")

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
        self._set_running(True)
        self.status.setText(f"{len(packages)}개 패키지 받는 중")

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
        self.status.setText(f"{done} / {total}개 받는 중")

    def finish(self, summary: str) -> None:
        animate(self._progress_motion, 100, 260)
        self.status.setText(summary)
        self._set_running(False)

    def set_idle(self, text: str = "대기 중") -> None:
        self.status.setText(text)
        self._progress_motion.stop()
        self.progress.setValue(0)
        self.cancel_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
