"""메인 윈도우.

화면은 하나뿐이고 그 안에서 홈 / 검색결과 / 패키지 내부로 드릴다운한다.
진행 상황은 하단 바가 맡는다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import (
    Qt, QThreadPool, QTimer, Signal, QPropertyAnimation, QSignalBlocker,
)
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from .. import api, updater
from ..cache import ImageCache, MetaCache, cache_key
from ..client import CancelledError, DcconClient, Throttle
from ..config import Settings
from ..downloader import download_package
from ..models import Package, PackageBrief
from . import theme
from .cards import Card
from .flowlayout import FlowLayout
from .queuebar import QueueBar
from .settings_dialog import SettingsDialog
from .update_dialog import UpdateDialog
from .workers import DownloadSignals, Task, ThumbSignals, ThumbTask
from .motion import SmoothScrollArea, animate

HOME_TABS = [("day", "일간 인기"), ("week", "주간 인기"),
             ("month", "월간 인기"), ("official", "공식"), ("all", "전체")]


class MainWindow(QMainWindow):
    _status = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("디시콘 다운로더")
        self.resize(1080, 760)
        self.setMinimumSize(780, 580)

        self.settings = Settings.load()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().setProperty("reduceMotion", self.settings.reduce_motion)
        Card.animate_gifs = self.settings.animate_gifs
        self.client = DcconClient(throttle=self._make_throttle())
        self.images = ImageCache()
        self.meta = MetaCache()

        # 풀을 나눠둔다. 썸네일 100장이 한 풀을 채우면 그 뒤에 줄 선
        # '패키지 열기' 요청이 끝날 때까지 화면이 안 바뀐다.
        self.nav_pool = QThreadPool()
        self.nav_pool.setMaxThreadCount(2)
        self.thumb_pool = QThreadPool()
        self.thumb_pool.setMaxThreadCount(max(2, self.settings.concurrency))
        self.dl_pool = QThreadPool()
        self.dl_pool.setMaxThreadCount(self.settings.concurrency)

        # QThreadPool에 넘긴 작업은 파이썬 쪽에서 붙잡고 있지 않으면 GC되고,
        # 그러면 결과 시그널이 통째로 사라진다. 끝날 때까지 여기 담아둔다.
        self._inflight: set = set()

        self.thumb_signals = ThumbSignals(self)
        self.thumb_signals.loaded.connect(self._on_thumb_loaded)
        self.thumb_signals.finished.connect(self._inflight.discard)
        self.dl_signals = DownloadSignals(self)
        self.dl_signals.item_progress.connect(self._on_item_progress)
        self.dl_signals.package_done.connect(self._on_package_done)
        self.dl_signals.package_error.connect(self._on_package_error)
        self.dl_signals.all_done.connect(self._on_all_done)

        # 화면이 바뀌면 세대를 올려 옛 썸네일 결과를 버린다.
        self._generation = 0
        self._cards: list[tuple[Card, object]] = []
        self._pending_thumbs: dict[str, list[Card]] = {}
        self._view = "home"
        self._home_kind = "day"
        self._search: tuple[str, str, int, int] | None = None  # word, type, page, pages
        self._all: tuple[int, int] | None = None  # 전체 목록 page, pages
        self._package: Package | None = None
        self._history: list[tuple] = []

        self._cancel = threading.Event()
        self._dl_progress: dict[int, tuple[int, int]] = {}
        self._dl_remaining = 0
        self._dl_results: list = []

        self._build_ui()
        self.show_home(self._home_kind)
        # 첫 화면 요청이 먼저 나가도록 조금 늦춘다.
        QTimer.singleShot(1500, self._startup_update_check)

    # ------------------------------------------------------------------ UI
    def _make_throttle(self) -> Throttle:
        # 동시성을 올리면 간격을 좁혀 전체 처리량이 따라오게 한다.
        interval = 0.18 / max(1, self.settings.concurrency)
        return Throttle(min_interval=interval, jitter=interval * 0.8)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())
        heading = QFrame()
        heading.setObjectName("viewHeader")
        heading_row = QVBoxLayout(heading)
        heading_row.setContentsMargins(28, 22, 28, 14)
        heading_row.setSpacing(6)
        self.crumb = QLabel()
        self.crumb.setObjectName("crumb")
        self.crumb.setWordWrap(True)
        self.crumb.setTextFormat(Qt.TextFormat.PlainText)
        heading_row.addWidget(self.crumb)
        self.view_hint = QLabel("마음에 드는 패키지를 선택하세요. 더블클릭하면 안의 디시콘을 볼 수 있어요.")
        self.view_hint.setObjectName("viewHint")
        self.view_hint.setWordWrap(True)
        heading_row.addWidget(self.view_hint)
        root.addWidget(heading)
        root.addWidget(self._build_tabs())

        self.loading = QProgressBar()
        self.loading.setObjectName("loadingLine")
        self.loading.setFixedHeight(3)
        self.loading.setTextVisible(False)
        self.loading.setRange(0, 0)
        root.addWidget(self.loading)
        self.scroll = SmoothScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("gridScroll")
        holder = QWidget()
        holder.setObjectName("gridHolder")
        # 스타일시트만으로는 스크롤 영역 안쪽 위젯이 칠해지지 않아 까맣게 뜬다.
        holder.setAutoFillBackground(True)
        self.grid = FlowLayout(holder, margin=28, spacing=16)
        self.scroll.setWidget(holder)
        # Never composite the entire scrolling holder: it includes offscreen cards.
        self._title_effect = QGraphicsOpacityEffect(self.crumb)
        self.crumb.setGraphicsEffect(self._title_effect)
        self._title_effect.setOpacity(1)
        self._title_effect.setEnabled(False)
        self._title_motion = QPropertyAnimation(self._title_effect, b"opacity", self)
        self._title_motion.finished.connect(lambda: self._title_effect.setEnabled(False))
        root.addWidget(self.scroll, 1)

        dock_space = QWidget()
        dock_space.setObjectName("dockSpace")
        dock_margin = QVBoxLayout(dock_space)
        dock_margin.setContentsMargins(20, 8, 20, 16)
        dock = QFrame()
        dock.setObjectName("downloadDock")
        dock_layout = QVBoxLayout(dock)
        dock_layout.setContentsMargins(1, 1, 1, 1)
        dock_layout.setSpacing(0)
        dock_layout.addWidget(self._build_actionbar())

        self.queue = QueueBar()
        self.queue.cancel_requested.connect(self._cancel_downloads)
        self.queue.pause_toggled.connect(self._set_paused)
        self.queue.open_folder_requested.connect(self._open_download_folder)
        dock_layout.addWidget(self.queue)
        dock_margin.addWidget(dock)
        root.addWidget(dock_space)

        self.setCentralWidget(central)

        focus = QAction(self)
        focus.setShortcut(QKeySequence("Ctrl+L"))
        focus.triggered.connect(lambda: (self.omnibox.setFocus(),
                                         self.omnibox.selectAll()))
        self.addAction(focus)

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 18, 24, 18)
        row.setSpacing(8)

        brand = QLabel("dccon")
        mark = QLabel()
        mark.setPixmap(QPixmap(str(Path(__file__).parent / "assets" / "brand.svg")))
        mark.setFixedSize(34, 34)
        row.addWidget(mark)
        brand.setObjectName("brand")
        row.addWidget(brand)
        row.addSpacing(12)
        self.back_btn = QPushButton("←")
        self.back_btn.setFixedWidth(36)
        self.back_btn.setToolTip("뒤로")
        self.back_btn.setAccessibleName("뒤로 가기")
        self.back_btn.clicked.connect(self.go_back)
        row.addWidget(self.back_btn)

        self.home_btn = QPushButton("홈")
        self.home_btn.clicked.connect(lambda: self.show_home(self._home_kind))
        row.addWidget(self.home_btn)

        self.search_type = QComboBox()
        self.search_type.setMinimumWidth(84)
        for key, label in api.SEARCH_TYPES.items():
            self.search_type.addItem(label, key)
        row.addWidget(self.search_type)

        self.omnibox = QLineEdit()
        self.omnibox.setPlaceholderText("검색어, 패키지 ID 또는 디시콘 URL")
        self.omnibox.setMinimumWidth(180)
        self.omnibox.setClearButtonEnabled(True)
        self.omnibox.setAccessibleName("디시콘 검색")
        self.omnibox.setToolTip("검색어, 패키지 ID 또는 URL을 입력하세요. Ctrl+L로 바로 이동")
        self.omnibox.returnPressed.connect(self._on_omnibox)
        row.addWidget(self.omnibox, 1)

        go = QPushButton("검색")
        go.setObjectName("searchButton")
        go.clicked.connect(self._on_omnibox)
        row.addWidget(go)

        cfg = QPushButton("설정")
        cfg.clicked.connect(self._open_settings)
        row.addWidget(cfg)
        return bar

    def _build_tabs(self) -> QWidget:
        self.tabs = QFrame()
        self.tabs.setObjectName("tabBar")
        row = QHBoxLayout(self.tabs)
        row.setContentsMargins(28, 0, 28, 14)
        row.setSpacing(6)
        self._tab_buttons: dict[str, QPushButton] = {}
        for key, label in HOME_TABS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName("tabButton")
            btn.clicked.connect(lambda _=False, k=key: self.show_home(k))
            row.addWidget(btn)
            self._tab_buttons[key] = btn
        row.addStretch(1)
        self.result_label = QLabel()
        self.result_label.setObjectName("resultCount")
        row.addWidget(self.result_label)
        return self.tabs

    def _build_actionbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("actionBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 14, 24, 14)
        row.setSpacing(8)

        self.select_all_btn = QPushButton("전체 선택")
        self.select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        row.addWidget(self.select_all_btn)

        self.clear_sel_btn = QPushButton("선택 해제")
        self.clear_sel_btn.clicked.connect(lambda: self._set_all_checked(False))
        row.addWidget(self.clear_sel_btn)

        row.addStretch(1)

        self.prev_btn = QPushButton("◀ 이전")
        self.prev_btn.clicked.connect(lambda: self._step_page(-1))
        row.addWidget(self.prev_btn)
        # 전체 목록은 6천 페이지가 넘어서 이전/다음만으로는 못 다닌다.
        self.page_label = QPushButton("")
        self.page_label.setToolTip("눌러서 원하는 페이지로 이동")
        self.page_label.clicked.connect(self._jump_page)
        row.addWidget(self.page_label)
        self.next_btn = QPushButton("다음 ▶")
        self.next_btn.clicked.connect(lambda: self._step_page(1))
        row.addWidget(self.next_btn)

        row.addStretch(1)

        self.sel_label = QLabel("선택 0개")
        self.sel_label.setObjectName("selLabel")
        row.addWidget(self.sel_label)

        self.download_btn = QPushButton("선택 다운로드")
        self.download_btn.setObjectName("primary")
        self.download_btn.clicked.connect(self._on_download)
        row.addWidget(self.download_btn)
        return bar

    # ---------------------------------------------------------- 네비게이션
    def _begin_view(self, crumb: str) -> int:
        self._generation += 1
        self._title_motion.stop()
        self._title_effect.setEnabled(False)
        self.loading.setRange(0, 1 if self.settings.reduce_motion else 0)
        self.loading.show()
        self.scroll.stop_motion()
        # 아직 시작 안 한 썸네일 작업은 버린다. 안 그러면 이전 화면의
        # 이미지 수백 장이 새 화면 요청보다 먼저 처리된다.
        self.thumb_pool.clear()
        self._cards.clear()
        self._pending_thumbs.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.crumb.setText(crumb)
        self.result_label.clear()
        self.view_hint.setText(
            "저장할 디시콘을 선택한 뒤 다운로드하세요."
            if self._view == "package" else
            "마음에 드는 패키지를 선택하세요. 더블클릭하면 안의 디시콘을 볼 수 있어요."
        )
        self.scroll.verticalScrollBar().setValue(0)
        self._update_selection()
        return self._generation

    def show_home(self, kind: str = "day") -> None:
        if kind == "all":
            self.show_all(1)
            return
        self._view = "home"
        self._home_kind = kind
        self._search = None
        self._all = None
        self._package = None
        self.tabs.show()
        for key, btn in self._tab_buttons.items():
            btn.setChecked(key == kind)
        self._set_pagination(visible=False)
        label = dict(HOME_TABS).get(kind, "인기")
        gen = self._begin_view(f"{label} 디시콘")
        self._run(
            lambda: api.fetch_top(self.client, kind),
            lambda rows: self._fill_packages(gen, rows),
        )

    def show_all(self, page: int = 1) -> None:
        """사이트에 올라온 모든 디시콘. 최신순으로 15개씩."""
        self._view = "home"
        self._home_kind = "all"
        self._search = None
        self._package = None
        self.tabs.show()
        for key, btn in self._tab_buttons.items():
            btn.setChecked(key == "all")
        gen = self._begin_view("전체 디시콘")
        self._set_pagination(visible=True)
        known = self._all[1] if self._all else page
        self._all = (page, max(page, known))
        self._set_page_label(*self._all)

        def done(payload):
            rows, pages, total = payload
            self._all = (page, pages)
            self._set_page_label(page, pages)
            if total:
                self.view_hint.setText(
                    f"사이트에 올라온 디시콘 {total:,}개를 최신순으로 보여줘요. "
                    "더블클릭하면 안의 디시콘을 볼 수 있어요."
                )
            if not rows:
                self._show_empty("이 페이지에는 디시콘이 없습니다.")
                return
            self._fill_packages(gen, rows)

        self._run(lambda: api.fetch_all(self.client, page), done)

    def show_search(self, word: str, search_type: str = "title", page: int = 1) -> None:
        self._view = "search"
        self._all = None
        self._package = None
        self.tabs.hide()
        gen = self._begin_view(f"“{word}” 검색 결과")
        self._set_pagination(visible=True)

        def work():
            return api.search_packages(self.client, word, search_type, page)

        def done(payload):
            rows, pages = payload
            self._search = (word, search_type, page, pages)
            self._set_page_label(page, pages)
            if not rows:
                self._show_empty(f"“{word}” 검색 결과가 없습니다.")
                return
            self._fill_packages(gen, rows)

        self._run(work, done)

    def open_package(self, package_idx: int) -> None:
        if self._view in ("home", "search"):
            self._history.append(self._snapshot())
        self._view = "package"
        self.tabs.hide()
        self._set_pagination(visible=False)
        gen = self._begin_view("불러오는 중…")

        def done(package: Package) -> None:
            self._package = package
            self.settings.remember(package.idx)
            self.settings.save()
            sub = f"{len(package.items)}개"
            if package.seller:
                sub += f" · {package.seller}"
            self.crumb.setText(package.title)
            self.view_hint.setText(f"{sub} · 저장할 디시콘을 선택하세요.")
            self._fill_items(gen, package)

        self._run(lambda: self._load_package(package_idx), done)

    def _snapshot(self) -> tuple:
        if self._view == "search" and self._search:
            word, stype, page, _ = self._search
            return ("search", word, stype, page)
        if self._home_kind == "all" and self._all:
            return ("all", self._all[0])
        return ("home", self._home_kind)

    def go_back(self) -> None:
        if self._history:
            state = self._history.pop()
            if state[0] == "search":
                self.show_search(state[1], state[2], state[3])
            elif state[0] == "all":
                self.show_all(state[1])
            else:
                self.show_home(state[1])
        else:
            self.show_home(self._home_kind)

    def _current_pages(self) -> tuple[int, int] | None:
        if self._view == "search" and self._search:
            return self._search[2], self._search[3]
        if self._view == "home" and self._home_kind == "all" and self._all:
            return self._all
        return None

    def _go_page(self, target: int) -> None:
        if self._view == "search" and self._search:
            word, stype, _, _ = self._search
            self.show_search(word, stype, target)
        elif self._home_kind == "all":
            self.show_all(target)

    def _step_page(self, delta: int) -> None:
        current = self._current_pages()
        if not current:
            return
        page, pages = current
        target = max(1, min(pages, page + delta))
        if target != page:
            self._go_page(target)

    def _jump_page(self) -> None:
        current = self._current_pages()
        if not current or current[1] <= 1:
            return
        page, pages = current
        target, ok = QInputDialog.getInt(
            self, "페이지 이동", f"이동할 페이지 (1 ~ {pages:,})", page, 1, pages
        )
        if ok and target != page:
            self._go_page(target)

    def _set_pagination(self, visible: bool) -> None:
        for w in (self.prev_btn, self.next_btn, self.page_label):
            w.setVisible(visible)

    def _set_page_label(self, page: int, pages: int) -> None:
        self.page_label.setText(f"{page} / {pages}")
        self.prev_btn.setEnabled(page > 1)
        self.next_btn.setEnabled(page < pages)

    # ------------------------------------------------------------- 그리드
    def _fill_packages(self, gen: int, rows: list[PackageBrief]) -> None:
        if gen != self._generation:
            return
        self.result_label.setText(f"{len(rows)}개 패키지")
        if not rows:
            self._show_empty("아직 표시할 패키지가 없습니다. 다른 인기 목록이나 검색을 이용해 보세요.")
            return
        for brief in rows:
            card = Card(brief.title, brief.seller, checkable=True)
            card.check.setToolTip("선택하면 패키지 전체를 받습니다")
            card.toggled.connect(self._update_selection)
            card.double_clicked.connect(
                lambda i=brief.idx: self.open_package(i)
            )
            card.setToolTip(
                f"{brief.title}\n클릭: 선택 (패키지 전체 받기)\n더블클릭: 안을 열어보기"
            )
            self.grid.addWidget(card)
            self._cards.append((card, brief))
            if brief.thumb_url:
                self._queue_thumb(gen, card, brief.thumb_url, "png")
        self._update_selection()
        self._reveal_grid()

    def _fill_items(self, gen: int, package: Package) -> None:
        if gen != self._generation:
            return
        for item in package.items:
            label = item.title or f"#{item.sort}"
            card = Card(label, item.ext.upper(), checkable=True)
            card.set_checked(True, animated=False)
            card.toggled.connect(self._update_selection)
            self.grid.addWidget(card)
            self._cards.append((card, item))
            self._queue_thumb(gen, card, item.url, item.ext)
        self._update_selection()
        self._reveal_grid()

    def _reveal_grid(self) -> None:
        self.loading.hide()
        self._title_motion.stop()
        self._title_effect.setEnabled(True)
        self._title_effect.setOpacity(0.25)
        animate(self._title_motion, 1.0, 240)

    def _show_empty(self, message: str) -> None:
        label = QLabel(message)
        label.setObjectName("emptyState")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grid.addWidget(label)
        self._reveal_grid()

    def _queue_thumb(self, gen: int, card: Card, url: str, ext: str) -> None:
        key = cache_key(url)
        cached = self.images.peek(url, ext)
        if cached:
            card.set_image(cached)
            return
        waiting = self._pending_thumbs.setdefault(key, [])
        waiting.append(card)
        if len(waiting) > 1:
            return  # 같은 이미지는 한 번만 받는다
        task = ThumbTask(
            self.thumb_signals, gen, key,
            lambda: self.images.get(self.client, url, ext, cancel=None),
        )
        self._inflight.add(task)
        self.thumb_pool.start(task)

    def _on_thumb_loaded(self, gen: int, key: str, data: bytes) -> None:
        if gen != self._generation:
            return
        for card in self._pending_thumbs.pop(key, []):
            try:
                card.set_image(data)
            except RuntimeError:
                pass  # 이미 사라진 카드

    # ------------------------------------------------------------- 선택
    def _set_all_checked(self, value: bool) -> None:
        for card, _ in self._cards:
            # One count update for the batch, without hundreds of animations.
            with QSignalBlocker(card):
                card.set_checked(value, animated=False)
        self._update_selection()

    def _update_selection(self, *_) -> None:
        count = sum(1 for card, _ in self._cards if card.checked)
        noun = "개" if self._view == "package" else "개 패키지"
        self.sel_label.setText(f"선택 {count}{noun}")
        self.download_btn.setEnabled(count > 0)

    # ------------------------------------------------------- 검색창 해석
    def _on_omnibox(self) -> None:
        kind, value = api.parse_query(self.omnibox.text())
        if kind == "ids":
            ids = list(value)
            if len(ids) == 1:
                self.open_package(ids[0])
            else:
                self._start_downloads([(i, f"#{i}", None) for i in ids])
            return
        if not value:
            return
        self.show_search(value, self.search_type.currentData(), 1)

    # ---------------------------------------------------------- 다운로드
    def _on_download(self) -> None:
        if self._view == "package" and self._package is not None:
            sorts = [item.sort for card, item in self._cards if card.checked]
            if not sorts:
                return
            self._start_downloads(
                [(self._package.idx, self._package.title, sorts)]
            )
            return
        jobs = [
            (brief.idx, brief.title, None)
            for card, brief in self._cards
            if card.checked
        ]
        if jobs:
            self._start_downloads(jobs)

    def _start_downloads(self, jobs: list[tuple[int, str, list[int] | None]]) -> None:
        dest = Path(self.settings.download_dir)
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "저장 폴더", f"폴더를 만들 수 없습니다.\n{exc}")
            return

        self._cancel = threading.Event()
        self._dl_progress.clear()
        self._dl_results.clear()
        self._dl_remaining = len(jobs)
        self.queue.start([(idx, title) for idx, title, _ in jobs])
        self.client.resume()

        for package_idx, _title, sorts in jobs:
            task = Task(
                self._download_one, package_idx, sorts, dest, self._cancel,
                parent=self,
            )
            task.signals.finished.connect(self._inflight.discard)
            self._inflight.add(task)
            self.dl_pool.start(task)

    def _download_one(self, package_idx: int, sorts, dest: Path,
                      cancel: threading.Event) -> None:
        """워커 스레드. UI는 시그널로만 건드린다."""
        try:
            package = self._load_package(package_idx, cancel=cancel)
        except CancelledError:
            self.dl_signals.package_error.emit(package_idx, "중단됨")
            self._finish_one()
            return
        except Exception as exc:  # noqa: BLE001
            self.dl_signals.package_error.emit(package_idx, str(exc))
            self._finish_one()
            return

        def progress(done: int, total: int, name: str) -> None:
            self.dl_signals.item_progress.emit(package_idx, done, total, name)

        try:
            result = download_package(
                self.client,
                self.images,
                package,
                dest,
                only_sorts=sorts,
                save_main_image=self.settings.save_main_image,
                write_meta=self.settings.write_meta_json,
                progress=progress,
                cancel=cancel,
            )
        except CancelledError:
            self.dl_signals.package_error.emit(package_idx, "중단됨")
        except Exception as exc:  # noqa: BLE001
            self.dl_signals.package_error.emit(package_idx, str(exc))
        else:
            self.dl_signals.package_done.emit(result)
        self._finish_one()

    def _finish_one(self) -> None:
        self._dl_remaining -= 1
        if self._dl_remaining <= 0:
            self.dl_signals.all_done.emit()

    def _load_package(self, package_idx: int, cancel=None) -> Package:
        cached = self.meta.load(package_idx)
        if cached:
            return Package.from_api(cached)
        resp = self.client.post(
            api.PACKAGE_DETAIL_URL,
            data={"package_idx": str(package_idx)},
            headers={"X-Requested-With": "XMLHttpRequest"},
            cancel=cancel,
        )
        payload = resp.json()
        if not payload or not payload.get("info"):
            raise LookupError(f"패키지 {package_idx} 를 찾을 수 없습니다.")
        self.meta.store(package_idx, payload)
        return Package.from_api(payload)

    def _on_item_progress(self, package_idx: int, done: int, total: int,
                          name: str) -> None:
        self._dl_progress[package_idx] = (done, total)
        self.queue.update_package(package_idx, done, total, name)
        agg_done = sum(d for d, _ in self._dl_progress.values())
        agg_total = sum(t for _, t in self._dl_progress.values())
        self.queue.set_overall(agg_done, agg_total)

    def _on_package_done(self, result) -> None:
        self._dl_results.append(result)
        parts = [f"저장 {result.saved}"]
        if result.skipped:
            parts.append(f"건너뜀 {result.skipped}")
        if result.failed:
            parts.append(f"실패 {len(result.failed)}")
        self.queue.finish_package(result.package_idx, "  ".join(parts))

    def _on_package_error(self, package_idx: int, message: str) -> None:
        self.queue.finish_package(package_idx, f"오류: {message}")

    def _on_all_done(self) -> None:
        saved = sum(r.saved for r in self._dl_results)
        skipped = sum(r.skipped for r in self._dl_results)
        failed = sum(len(r.failed) for r in self._dl_results)
        summary = f"완료 · 저장 {saved}개"
        if skipped:
            summary += f", 건너뜀 {skipped}개"
        if failed:
            summary += f", 실패 {failed}개"
        self.queue.finish(summary)

    def _cancel_downloads(self) -> None:
        self._cancel.set()
        self.client.resume()
        self.queue.set_idle("중단하는 중…")

    def _set_paused(self, paused: bool) -> None:
        if paused:
            self.client.pause()
        else:
            self.client.resume()

    def _open_download_folder(self) -> None:
        path = Path(self.settings.download_dir)
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    # ------------------------------------------------------------- 기타
    def _run(self, work, done) -> None:
        generation = self._generation
        task = Task(work, parent=self)
        task.signals.done.connect(
            lambda result: done(result) if generation == self._generation else None
        )
        task.signals.error.connect(
            lambda message: self._on_nav_error(message) if generation == self._generation else None
        )
        task.signals.finished.connect(self._inflight.discard)
        self._inflight.add(task)
        self.nav_pool.start(task)

    def _on_nav_error(self, message: str) -> None:
        self._show_empty(f"불러오지 못했습니다.\n{message}")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.images, self)
        if dialog.exec():
            dialog.apply_to(self.settings)
            from PySide6.QtWidgets import QApplication
            QApplication.instance().setProperty("reduceMotion", self.settings.reduce_motion)
            theme.apply(QApplication.instance(), self.settings.theme)
            if Card.animate_gifs != self.settings.animate_gifs:
                Card.animate_gifs = self.settings.animate_gifs
                for card, _ in self._cards:
                    card.set_animated(self.settings.animate_gifs)
            self.settings.save()
            self.dl_pool.setMaxThreadCount(self.settings.concurrency)
            self.thumb_pool.setMaxThreadCount(max(2, self.settings.concurrency))
        if dialog.staged_update is not None:
            self._apply_update(dialog.staged_update)

    # ---------------------------------------------------------- 업데이트
    def _startup_update_check(self) -> None:
        failure = updater.take_last_error()
        if failure:
            QMessageBox.warning(self, "업데이트", failure)
        # 소스로 돌릴 때는 조용히 넘어간다. 설정에서 직접 확인은 된다.
        if not self.settings.check_updates or updater.build_kind() is None:
            return

        def work():
            updater.cleanup_staging()
            return updater.fetch_latest()

        task = Task(work, parent=self)
        task.signals.done.connect(self._on_startup_release)
        # 시작할 때 확인은 실패해도 알리지 않는다. 오프라인일 수도 있다.
        task.signals.finished.connect(self._inflight.discard)
        self._inflight.add(task)
        self.nav_pool.start(task)

    def _on_startup_release(self, release) -> None:
        if release is None or not updater.is_newer(release.tag):
            return
        if release.version == self.settings.skipped_version:
            return
        dialog = UpdateDialog(release, self, offer_skip=True)
        if dialog.exec() and dialog.staged is not None:
            self._apply_update(dialog.staged)
        elif dialog.skipped:
            self.settings.skipped_version = release.version
            self.settings.save()

    def _apply_update(self, staged) -> None:
        if self._dl_remaining > 0:
            confirm = QMessageBox.question(
                self, "업데이트",
                "다운로드가 진행 중입니다. 중단하고 다시 시작할까요?\n"
                "받다 만 패키지는 다음에 다시 받으면 빠진 것만 채워집니다.",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        try:
            updater.launch_apply(staged)
        except (OSError, updater.UpdateError) as exc:
            QMessageBox.warning(self, "업데이트", f"업데이트를 시작하지 못했습니다.\n{exc}")
            return
        # 도우미가 이 프로세스가 끝나기를 기다리고 있다.
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._cancel.set()
        self.client.resume()
        for pool in (self.thumb_pool, self.nav_pool, self.dl_pool):
            pool.clear()
        self.settings.save()
        # 돌고 있는 작업이 끝나기를 잠깐 기다린다. 안 기다리면 워커가
        # 이미 사라진 시그널 객체에 emit 하면서 시끄럽게 죽는다.
        for pool in (self.thumb_pool, self.nav_pool, self.dl_pool):
            pool.waitForDone(2000)
        self.client.close()
        super().closeEvent(event)
