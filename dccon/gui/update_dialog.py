"""새 버전 안내 + 다운로드 창.

받기까지만 여기서 한다. 실제 교체는 앱이 꺼져야 하므로 메인 윈도우가
`staged` 를 받아 `updater.launch_apply()` 후 스스로 닫는다.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from .. import __version__, updater
from .workers import Task


class UpdateDialog(QDialog):
    _progress = Signal(int, int)

    def __init__(self, release: updater.Release, parent=None, *,
                 offer_skip: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("업데이트")
        self.setMinimumSize(520, 420)
        self.release = release
        self.staged: updater.StagedUpdate | None = None
        self.skipped = False
        self._cancel = threading.Event()
        self._task: Task | None = None

        kind = updater.build_kind()
        self._asset = release.pick_asset(kind) if updater.can_self_update() else None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)
        title = QLabel(f"새 버전 {release.version}")
        title.setObjectName("crumb")
        outer.addWidget(title)
        sub = QLabel(f"지금 쓰는 버전은 {__version__} 입니다.")
        sub.setObjectName("viewHint")
        outer.addWidget(sub)

        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release.notes.strip() or "_변경 내역이 없습니다._")
        outer.addWidget(notes, 1)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.hide()
        outer.addWidget(self.bar)
        self.status = QLabel()
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        if self._asset is None:
            self.status.setText(
                "이 실행 방식에서는 자동 업데이트를 할 수 없습니다. 릴리즈 페이지에서 받아주세요."
            )

        row = QHBoxLayout()
        if offer_skip:
            skip = QPushButton("이 버전 건너뛰기")
            skip.clicked.connect(self._skip)
            row.addWidget(skip)
        row.addStretch(1)
        self.later = QPushButton("나중에")
        self.later.clicked.connect(self.reject)
        row.addWidget(self.later)
        self.go = QPushButton("지금 업데이트" if self._asset else "릴리즈 페이지 열기")
        self.go.setObjectName("primary")
        self.go.setDefault(True)
        self.go.clicked.connect(self._start)
        row.addWidget(self.go)
        outer.addLayout(row)

        self._progress.connect(self._on_progress)

    # ------------------------------------------------------------------
    def _skip(self) -> None:
        self.skipped = True
        self.reject()

    def _start(self) -> None:
        if self._asset is None:
            QDesktopServices.openUrl(QUrl(self.release.page_url))
            self.reject()
            return

        self.go.setEnabled(False)
        self.later.setText("취소")
        self.bar.setRange(0, 0)
        self.bar.show()
        self.status.setText(f"{self._asset.name} 받는 중…")

        def work():
            return updater.download(
                self.release, updater.build_kind(),
                progress=self._emit_progress, cancel=self._cancel,
            )

        task = Task(work, parent=self)
        task.signals.done.connect(self._on_done)
        task.signals.error.connect(self._on_error)
        # 창이 먼저 닫혀도 작업이 끝날 때까지 파이썬 참조를 붙잡아 둔다.
        self._task = task
        QThreadPool.globalInstance().start(task)

    def _emit_progress(self, done: int, total: int) -> None:
        try:
            self._progress.emit(done, total)
        except RuntimeError:
            pass  # 창이 이미 사라짐

    def _on_progress(self, done: int, total: int) -> None:
        if total <= 0:
            return
        if self.bar.maximum() != 1000:
            self.bar.setRange(0, 1000)
        self.bar.setValue(int(done * 1000 / total))
        self.status.setText(
            f"{self._asset.name}  {done / 1048576:,.1f} / {total / 1048576:,.1f} MB"
        )

    def _on_done(self, staged: updater.StagedUpdate) -> None:
        if self._cancel.is_set():
            return
        self.staged = staged
        self.accept()

    def _on_error(self, message: str) -> None:
        if self._cancel.is_set():
            return
        self.bar.hide()
        self.status.setText(f"업데이트를 받지 못했습니다.\n{message}")
        self.go.setEnabled(True)
        self.go.setText("다시 시도")
        self.later.setText("닫기")

    def reject(self) -> None:
        self._cancel.set()
        super().reject()
