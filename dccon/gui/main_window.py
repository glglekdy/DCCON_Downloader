"""메인 윈도우.

왼쪽 사이드바에서 사이트와 목록을 고르고, 오른쪽에서 홈 / 검색결과 /
패키지 내부로 드릴다운한다. 선택과 진행 상황은 아래에 뜬 독이 맡는다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import (
    Qt, QThreadPool, QTimer, Signal, QPropertyAnimation, QSignalBlocker,
    QEvent, QEasingCurve, QVariantAnimation,
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
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QProgressBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import api, arca, arca_login, updater
from ..arca_login import ArcaSession
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
from .motion import SmoothScrollArea, animate, motion_duration
from .glow import DockShade, DownloadGlow

HOME_TABS = [("day", "일간 인기"), ("week", "주간 인기"),
             ("month", "월간 인기"), ("official", "공식"), ("all", "전체 목록")]
# 사이드바에서 디시콘 메뉴를 묶는 구역. (제목, 탭 키들)
DC_SECTIONS = [("인기", ("day", "week", "month")), ("둘러보기", ("official", "all"))]
SITES = [("dccon", "디시콘"), ("arca", "아카콘")]
# 아카콘은 디시콘과 섞이지 않게 저장 폴더 안의 하위 폴더에 둔다.
ARCA_SUBDIR = "arcacon"


class ClickableLabel(QLabel):
    """클릭을 받는 라벨. 상단 로고를 홈 버튼으로 쓰려고 만들었다."""

    clicked = Signal()

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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
        # 마우스 4·5번 버튼은 자식 위젯이 먼저 삼키므로 앱 전역에서 가로챈다.
        QApplication.instance().installEventFilter(self)
        Card.animate_gifs = self.settings.animate_gifs
        self.site = "dccon"
        self.dc_client = DcconClient(throttle=self._make_throttle())
        self.arca_client = DcconClient(throttle=self._make_throttle(), headers=arca.HEADERS)
        self.arca_session = ArcaSession.load()
        if self.arca_session is not None:
            self.arca_client.set_session(self.arca_session.user_agent, self.arca_session.jar())
        self._login_task = None
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
        self._forward: list[tuple] = []
        # 뒤로/앞으로 복원 중에는 앞으로 스택을 비우지 않는다.
        self._navigating = False

        self._cancel = threading.Event()
        self._dl_progress: dict[int, tuple[int, int]] = {}
        self._dl_remaining = 0
        self._dl_results: list = []

        self._build_ui()
        self._show_dock_page(0)
        self.show_home(self._home_kind)
        # 첫 화면 요청이 먼저 나가도록 조금 늦춘다.
        QTimer.singleShot(1500, self._startup_update_check)

    @property
    def client(self) -> DcconClient:
        """지금 보고 있는 사이트의 클라이언트."""
        return self.arca_client if self.site == "arca" else self.dc_client

    def _client_for(self, site: str) -> DcconClient:
        return self.arca_client if site == "arca" else self.dc_client

    # ------------------------------------------------------------------ UI
    def _make_throttle(self) -> Throttle:
        # 동시성을 올리면 간격을 좁혀 전체 처리량이 따라오게 한다.
        interval = 0.18 / max(1, self.settings.concurrency)
        return Throttle(min_interval=interval, jitter=interval * 0.8)

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        main = QWidget()
        main.setObjectName("mainArea")
        root = QVBoxLayout(main)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        outer.addWidget(main, 1)

        root.addWidget(self._build_searchbar())

        self.loading = QProgressBar()
        self.loading.setObjectName("loadingLine")
        self.loading.setFixedHeight(2)
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
        # 제목도 스크롤 안에 둔다. 내리면 같이 올라가 카드 자리가 넓어진다.
        content = QVBoxLayout(holder)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self._build_heading())

        cards = QWidget()
        self.grid = FlowLayout(cards, margin=22, spacing=10)
        self.grid.setContentsMargins(22, 4, 22, 24)
        content.addWidget(cards)
        # 떠 있는 다운로드 독에 마지막 줄이 가리지 않도록 그만큼 비워둔다.
        self._dock_pad = QWidget()
        content.addWidget(self._dock_pad)
        content.addStretch(1)
        self.scroll.setWidget(holder)
        # Never composite the entire scrolling holder: it includes offscreen cards.
        self._title_effect = QGraphicsOpacityEffect(self.crumb)
        self.crumb.setGraphicsEffect(self._title_effect)
        self._title_effect.setOpacity(1)
        self._title_effect.setEnabled(False)
        self._title_motion = QPropertyAnimation(self._title_effect, b"opacity", self)
        self._title_motion.finished.connect(lambda: self._title_effect.setEnabled(False))
        root.addWidget(self.scroll, 1)

        # 독은 레이아웃에 넣지 않고 그리드 위에 띄운다. 자리는 _place_dock 이 잡는다.
        dock_space = DockShade(main)
        dock_space.setObjectName("dockSpace")
        dock_margin = QVBoxLayout(dock_space)
        dock_margin.setContentsMargins(28, 8, 28, 16)
        dock = QFrame()
        dock.setObjectName("downloadDock")
        dock.setMaximumWidth(620)
        dock_layout = QVBoxLayout(dock)
        dock_layout.setContentsMargins(1, 1, 1, 1)
        dock_layout.setSpacing(0)
        # 평소엔 선택 줄, 받는 동안엔 진행 줄. 한 번에 하나만 보인다.
        self.dock_pages = QStackedWidget()
        self.dock_pages.addWidget(self._build_actionbar())

        self.queue = QueueBar()
        self.queue.cancel_requested.connect(self._cancel_downloads)
        self.queue.pause_toggled.connect(self._set_paused)
        self.queue.dismissed.connect(lambda: self._show_dock_page(0))
        self.dock_pages.addWidget(self.queue)
        self.dock_pages.currentChanged.connect(lambda _: self._place_dock())
        dock_layout.addWidget(self.dock_pages)

        # 독 위에 붙는 손잡이. 눌러서 다운로드 바를 아래로 숨긴다.
        handle_row = QHBoxLayout()
        handle_row.setContentsMargins(0, 0, 0, 6)
        handle_row.addStretch(1)
        self.dock_toggle = QPushButton("▼")
        self.dock_toggle.setObjectName("dockToggle")
        self.dock_toggle.setCheckable(True)
        # 높이는 스타일시트의 CSS 박스(내용 14 + 패딩 4 + 테두리 2)와 맞춰야
        # 한다. 어긋나면 스타일시트가 나중에 최소 높이를 덮어써 찌그러진다.
        self.dock_toggle.setFixedSize(44, 20)
        self.dock_toggle.setToolTip("다운로드 바 숨기기 / 보이기")
        self.dock_toggle.setAccessibleName("다운로드 바 숨기기 / 보이기")
        self.dock_toggle.toggled.connect(self._toggle_dock)
        handle_row.addWidget(self.dock_toggle)
        handle_row.addStretch(1)
        dock_margin.addLayout(handle_row)
        dock_row = QHBoxLayout()
        dock_row.addStretch(1)
        dock_row.addWidget(dock, 100)
        dock_row.addStretch(1)
        dock_margin.addLayout(dock_row)

        self.dock = dock
        self.dock_space = dock_space
        dock_space.follow(dock)
        # 독 높이가 바뀌면(큐 내역 펼치기 등) 레이아웃 요청이 여기로 올라온다.
        dock_space.installEventFilter(self)
        # 숨기기는 독을 접지 않고 통째로 창 아래로 미끄러뜨린다.
        # 0 이면 다 보이고 1 이면 손잡이만 남는다.
        self._dock_hidden = 0.0
        self._dock_motion = QVariantAnimation(self)
        self._dock_motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._dock_motion.valueChanged.connect(self._set_dock_hidden)
        dock_space.raise_()

        # 그리드 위로는 번지고 독 아래로는 깔리도록 사이에 끼운다.
        self.glow = DownloadGlow(main)
        self.glow.stackUnder(dock_space)
        self._main = main

        self.setCentralWidget(central)

        focus = QAction(self)
        focus.setShortcut(QKeySequence("Ctrl+L"))
        focus.triggered.connect(lambda: (self.omnibox.setFocus(),
                                         self.omnibox.selectAll()))
        self.addAction(focus)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._place_dock()
        self._place_glow()

    def _place_dock(self) -> None:
        central = getattr(self, "_main", None)
        if central is None or not hasattr(self, "dock_space"):
            return
        height = self.dock_space.sizeHint().height()
        # 다 숨겨도 손잡이(위 여백 + 버튼)와 그 아래 12px 는 남긴다.
        handle = self.dock_toggle.geometry().bottom() + 1 + 12
        shift = round(max(0, height - handle) * self._dock_hidden)
        self.dock_space.setGeometry(0, central.height() - height + shift,
                                    central.width(), height)
        self._dock_pad.setFixedHeight(height - shift)

    def _place_glow(self) -> None:
        central = getattr(self, "_main", None)
        if central is None or not hasattr(self, "glow"):
            return
        height = min(DownloadGlow.HEIGHT, central.height())
        self.glow.setGeometry(0, central.height() - height,
                              central.width(), height)

    def _toggle_dock(self, hidden: bool) -> None:
        self._dock_motion.stop()
        self.dock_toggle.setText("▲" if hidden else "▼")
        target = 1.0 if hidden else 0.0
        duration = motion_duration(260)
        if not duration:
            self._set_dock_hidden(target)
            return
        self._dock_motion.setDuration(duration)
        self._dock_motion.setStartValue(self._dock_hidden)
        self._dock_motion.setEndValue(target)
        self._dock_motion.start()

    def _set_dock_hidden(self, value: float) -> None:
        self._dock_hidden = float(value)
        self._place_dock()

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(210)
        col = QVBoxLayout(side)
        col.setContentsMargins(12, 16, 12, 16)
        col.setSpacing(2)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 0, 0, 14)
        brand_row.setSpacing(10)
        brand = ClickableLabel("dccon")
        mark = ClickableLabel()
        # 앱 아이콘과 같은 로고. 고해상도 화면에서도 선명하도록 배율만큼 크게 줄인다.
        ratio = self.devicePixelRatioF()
        logo = QPixmap(str(Path(__file__).parent / "assets" / "icon.png")).scaled(
            round(28 * ratio), round(28 * ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        logo.setDevicePixelRatio(ratio)
        mark.setPixmap(logo)
        mark.setFixedSize(28, 28)
        brand.setObjectName("brand")
        brand_row.addWidget(mark)
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        # 로고가 홈 버튼을 겸한다. 뒤로/앞으로는 마우스 4·5번 버튼이 맡는다.
        for widget in (mark, brand):
            widget.setToolTip("홈으로")
            widget.setAccessibleName("홈으로")
            widget.clicked.connect(lambda: self.show_home(self._home_kind))
        col.addLayout(brand_row)

        seg = QFrame()
        seg.setObjectName("segment")
        seg_row = QHBoxLayout(seg)
        seg_row.setContentsMargins(3, 3, 3, 3)
        seg_row.setSpacing(2)
        self._site_buttons: dict[str, QPushButton] = {}
        for key, label in SITES:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == self.site)
            btn.setObjectName("segButton")
            btn.clicked.connect(lambda _=False, k=key: self._switch_site(k))
            seg_row.addWidget(btn, 1)
            self._site_buttons[key] = btn
        col.addWidget(seg)
        col.addSpacing(10)

        # 사이트마다 메뉴가 다르다. 둘 다 만들어 두고 보이는 쪽만 바꾼다.
        self._tab_buttons: dict[str, QPushButton] = {}
        self._arca_tab_buttons: dict[str, QPushButton] = {}
        labels = dict(HOME_TABS)
        self._dc_nav = QWidget()
        dc_col = QVBoxLayout(self._dc_nav)
        dc_col.setContentsMargins(0, 0, 0, 0)
        dc_col.setSpacing(2)
        for title, keys in DC_SECTIONS:
            dc_col.addWidget(self._nav_section(title))
            for key in keys:
                btn = self._nav_button(labels[key])
                btn.clicked.connect(lambda _=False, k=key: self.show_home(k))
                dc_col.addWidget(btn)
                self._tab_buttons[key] = btn
        col.addWidget(self._dc_nav)

        self._arca_nav = QWidget()
        arca_col = QVBoxLayout(self._arca_nav)
        arca_col.setContentsMargins(0, 0, 0, 0)
        arca_col.setSpacing(2)
        arca_col.addWidget(self._nav_section("아카콘"))
        for key, label in arca.ARCA_TABS:
            btn = self._nav_button(label)
            btn.clicked.connect(lambda _=False, k=key: self.show_home(k))
            arca_col.addWidget(btn)
            self._arca_tab_buttons[key] = btn
        self._arca_nav.hide()
        col.addWidget(self._arca_nav)

        col.addStretch(1)
        folder = self._nav_button("폴더 열기", checkable=False)
        folder.clicked.connect(self._open_download_folder)
        col.addWidget(folder)
        cfg = self._nav_button("설정", checkable=False)
        cfg.clicked.connect(self._open_settings)
        col.addWidget(cfg)
        return side

    @staticmethod
    def _nav_section(title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("navSection")
        return label

    @staticmethod
    def _nav_button(label: str, *, checkable: bool = True) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("navItem")
        btn.setCheckable(checkable)
        return btn

    def _build_searchbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("searchBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(22, 14, 22, 6)
        row.setSpacing(8)

        self.search_type = QComboBox()
        self.search_type.setMinimumWidth(76)
        for key, label in api.SEARCH_TYPES.items():
            self.search_type.addItem(label, key)
        row.addWidget(self.search_type)

        self.omnibox = QLineEdit()
        self.omnibox.setPlaceholderText("검색어, 패키지 ID 또는 디시콘 URL")
        self.omnibox.setMinimumWidth(180)
        self.omnibox.setClearButtonEnabled(True)
        self.omnibox.setAccessibleName("디시콘 검색")
        self.omnibox.setToolTip("검색어, 패키지 ID 또는 URL을 입력하고 Enter. Ctrl+L로 바로 이동")
        self.omnibox.returnPressed.connect(self._on_omnibox)
        row.addWidget(self.omnibox, 1)
        return bar

    def _build_heading(self) -> QWidget:
        heading = QFrame()
        heading.setObjectName("viewHeader")
        col = QVBoxLayout(heading)
        col.setContentsMargins(28, 18, 28, 12)
        col.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.crumb = QLabel()
        self.crumb.setObjectName("crumb")
        self.crumb.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.crumb, 0, Qt.AlignmentFlag.AlignBottom)
        self.result_label = QLabel()
        self.result_label.setObjectName("resultCount")
        row.addWidget(self.result_label, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)

        self.prev_btn = QPushButton("‹")
        self.prev_btn.setObjectName("ghost")
        self.prev_btn.setFixedWidth(32)
        self.prev_btn.setToolTip("이전 페이지")
        self.prev_btn.clicked.connect(lambda: self._step_page(-1))
        row.addWidget(self.prev_btn)
        # 전체 목록은 6천 페이지가 넘어서 이전/다음만으로는 못 다닌다.
        self.page_label = QPushButton("")
        self.page_label.setObjectName("ghost")
        self.page_label.setToolTip("눌러서 원하는 페이지로 이동")
        self.page_label.clicked.connect(self._jump_page)
        row.addWidget(self.page_label)
        self.next_btn = QPushButton("›")
        self.next_btn.setObjectName("ghost")
        self.next_btn.setFixedWidth(32)
        self.next_btn.setToolTip("다음 페이지")
        self.next_btn.clicked.connect(lambda: self._step_page(1))
        row.addWidget(self.next_btn)
        col.addLayout(row)

        self.view_hint = QLabel()
        self.view_hint.setObjectName("viewHint")
        self.view_hint.setWordWrap(True)
        col.addWidget(self.view_hint)
        return heading

    def _build_actionbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("actionBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 8, 8, 8)
        row.setSpacing(6)

        self.sel_label = QLabel("0개 선택")
        self.sel_label.setObjectName("selLabel")
        row.addWidget(self.sel_label)
        row.addStretch(1)

        self.clear_sel_btn = QPushButton("선택 해제")
        self.clear_sel_btn.setObjectName("ghost")
        self.clear_sel_btn.clicked.connect(lambda: self._set_all_checked(False))
        row.addWidget(self.clear_sel_btn)

        self.select_all_btn = QPushButton("전체 선택")
        self.select_all_btn.setObjectName("ghost")
        self.select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        row.addWidget(self.select_all_btn)

        self.download_btn = QPushButton("다운로드")
        self.download_btn.setObjectName("primary")
        self.download_btn.clicked.connect(self._on_download)
        row.addWidget(self.download_btn)
        return bar

    def _show_dock_page(self, index: int) -> None:
        self.dock_pages.setCurrentIndex(index)
        # 쌓인 위젯 중 큰 쪽 높이를 따르지 않게 지금 페이지 크기로 맞춘다.
        for i in range(self.dock_pages.count()):
            page = self.dock_pages.widget(i)
            policy = QSizePolicy.Policy.Preferred if i == index else QSizePolicy.Policy.Ignored
            page.setSizePolicy(QSizePolicy.Policy.Preferred, policy)
        self.dock_pages.adjustSize()
        self._place_dock()

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
        # 안내 문구는 패키지 안에서만 보인다(작가·개수 표시).
        self.view_hint.setText("저장할 디시콘을 선택한 뒤 다운로드하세요.")
        self.view_hint.setVisible(self._view == "package")
        self.scroll.verticalScrollBar().setValue(0)
        self._update_selection()
        return self._generation

    def show_home(self, kind: str = "day") -> None:
        if self.site == "arca":
            self.show_arca(kind if kind in dict(arca.ARCA_TABS) else "new", 1)
            return
        if kind == "all":
            self.show_all(1)
            return
        self._view = "home"
        if not self._navigating:
            self._forward.clear()
        self._home_kind = kind
        self._search = None
        self._all = None
        self._package = None
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
        if not self._navigating:
            self._forward.clear()
        self._home_kind = "all"
        self._search = None
        self._package = None
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
            if not rows:
                self._show_empty("이 페이지에는 디시콘이 없습니다.")
                return
            self._fill_packages(gen, rows)
            if total:
                self.result_label.setText(f"전체 {total:,}개 패키지")

        self._run(lambda: api.fetch_all(self.client, page), done)

    def show_arca(self, kind: str = "new", page: int = 1) -> None:
        """아카콘 목록. 탭마다 페이지가 있다."""
        if self._home_kind != kind:
            self._all = None
        self._view = "home"
        self._home_kind = kind
        self._search = None
        self._package = None
        for key, btn in self._arca_tab_buttons.items():
            btn.setChecked(key == kind)
        gen = self._begin_view(f"{dict(arca.ARCA_TABS).get(kind, '최신')} 아카콘")
        self._set_pagination(visible=True)
        known = self._all[1] if self._all else page
        self._all = (page, max(page, known))
        self._set_page_label(*self._all)
        client = self.client

        def done(payload):
            rows, pages = payload
            self._all = (page, max(pages, self._all[1] if self._all else pages))
            self._set_page_label(*self._all)
            if not rows:
                self._show_empty("이 페이지에는 아카콘이 없습니다.")
                return
            self._fill_packages(gen, rows)

        self._run(lambda: arca.fetch_list(client, kind, page), done)

    def show_search(self, word: str, search_type: str = "title", page: int = 1) -> None:
        self._view = "search"
        if not self._navigating:
            self._forward.clear()
        self._all = None
        self._package = None
        gen = self._begin_view(f"“{word}” 검색 결과")
        self._set_pagination(visible=True)
        site, client = self.site, self.client

        def work():
            if site == "arca":
                return arca.search(client, word, search_type, page)
            return api.search_packages(client, word, search_type, page)

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
        self._open_package(package_idx, record=True)

    def _open_package(self, package_idx: int, *, record: bool = True) -> None:
        if record and self._view in ("home", "search"):
            self._history.append(self._snapshot())
            self._forward.clear()
        self._view = "package"
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

        site = self.site
        self._run(lambda: self._load_package(package_idx, site=site), done)

    def _snapshot(self) -> tuple:
        if self._view == "package" and self._package:
            return ("package", self._package.idx)
        if self._view == "search" and self._search:
            word, stype, page, _ = self._search
            return ("search", word, stype, page)
        if self.site == "arca":
            return ("arca", self._home_kind, self._all[0] if self._all else 1)
        if self._home_kind == "all" and self._all:
            return ("all", self._all[0])
        return ("home", self._home_kind)

    def _restore(self, state: tuple) -> None:
        self._navigating = True
        try:
            if state[0] == "search":
                self.show_search(state[1], state[2], state[3])
            elif state[0] == "all":
                self.show_all(state[1])
            elif state[0] == "package":
                self._open_package(state[1], record=False)
            elif state[0] == "arca":
                self.show_arca(state[1], state[2])
            else:
                self.show_home(state[1])
        finally:
            self._navigating = False

    def go_back(self) -> None:
        if not self._history:
            return
        self._forward.append(self._snapshot())
        self._restore(self._history.pop())

    def go_forward(self) -> None:
        if not self._forward:
            return
        self._history.append(self._snapshot())
        self._restore(self._forward.pop())

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is getattr(self, "dock_space", None):
            if event.type() == QEvent.Type.LayoutRequest:
                self._place_dock()
            elif event.type() == QEvent.Type.Wheel:
                # 독 옆 빈자리에서 굴려도 그리드가 스크롤되게 넘겨준다.
                self.scroll.wheelEvent(event)
                return True
        # 마우스 4번(뒤로) · 5번(앞으로). 브라우저와 같은 동작.
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.BackButton:
                self.go_back()
                return True
            if event.button() == Qt.MouseButton.ForwardButton:
                self.go_forward()
                return True
        return super().eventFilter(obj, event)

    def _current_pages(self) -> tuple[int, int] | None:
        if self._view == "search" and self._search:
            return self._search[2], self._search[3]
        if self._view == "home" and self._all and (
                self.site == "arca" or self._home_kind == "all"):
            return self._all
        return None

    def _go_page(self, target: int) -> None:
        if self._view == "search" and self._search:
            word, stype, _, _ = self._search
            self.show_search(word, stype, target)
        elif self.site == "arca":
            self.show_arca(self._home_kind, target)
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
            if item.thumb:
                self._queue_thumb(gen, card, item.thumb, "jpg")
            else:
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
        client = self.client
        task = ThumbTask(
            self.thumb_signals, gen, key,
            lambda: self.images.get(client, url, ext, cancel=None),
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
        self.sel_label.setText(f"{count}{noun} 선택")
        self.download_btn.setEnabled(count > 0)

    # ------------------------------------------------------- 검색창 해석
    def _on_omnibox(self) -> None:
        if self.site == "arca":
            text = self.omnibox.text().strip()
            ids = arca.parse_ids(text)
            if ids and len(ids) == 1:
                self.open_package(ids[0])
            elif ids:
                self._start_downloads([(i, f"#{i}", None) for i in ids])
            elif text:
                self.show_search(text, self.search_type.currentData(), 1)
            return
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
        site = self.site
        dest = Path(self.settings.download_dir)
        if site == "arca":
            dest = dest / ARCA_SUBDIR
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
        self._show_dock_page(1)
        if self.dock_toggle.isChecked():
            self.dock_toggle.setChecked(False)
        self.glow.start()
        self._resume_clients()

        for package_idx, _title, sorts in jobs:
            task = Task(
                self._download_one, site, package_idx, sorts, dest, self._cancel,
                parent=self,
            )
            task.signals.finished.connect(self._inflight.discard)
            self._inflight.add(task)
            self.dl_pool.start(task)

    def _download_one(self, site: str, package_idx: int, sorts, dest: Path,
                      cancel: threading.Event) -> None:
        """워커 스레드. UI는 시그널로만 건드린다."""
        try:
            package = self._load_package(package_idx, cancel=cancel, site=site)
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
                self._client_for(site),
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

    def _load_package(self, package_idx: int, cancel=None, site: str = "dccon") -> Package:
        if site == "arca":
            # 이미지 주소 서명이 만료되므로 상세는 캐시하지 않는다.
            return arca.fetch_package(self.arca_client, package_idx, cancel=cancel)
        cached = self.meta.load(package_idx)
        if cached:
            return Package.from_api(cached)
        resp = self.dc_client.post(
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
        self.glow.stop()

    def _cancel_downloads(self) -> None:
        self._cancel.set()
        self._resume_clients()
        self.queue.set_idle("중단하는 중…")
        self.glow.stop()

    def _resume_clients(self) -> None:
        for client in (self.dc_client, self.arca_client):
            client.resume()

    def _set_paused(self, paused: bool) -> None:
        # 받는 중인 사이트가 지금 보는 사이트와 다를 수 있어 둘 다 건드린다.
        for client in (self.dc_client, self.arca_client):
            client.pause() if paused else client.resume()

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
        if message == arca.LOGIN_REQUIRED_MSG:
            # 저장해 둔 쿠키가 만료됐다. 버리고 다시 로그인시킨다.
            self.arca_session = None
            ArcaSession.forget()
            self._show_empty("아카라이브 로그인이 만료되었습니다.")
            self._require_login()
            return
        self._show_empty(f"불러오지 못했습니다.\n{message}")

    # ------------------------------------------------------- 사이트 전환
    def _sync_site_buttons(self) -> None:
        for key, btn in self._site_buttons.items():
            btn.setChecked(key == self.site)

    def _switch_site(self, site: str) -> None:
        if site == "arca" and self.arca_session is None:
            self._sync_site_buttons()
            self._require_login()
            return
        if site != self.site:
            self._set_site(site)
        self._sync_site_buttons()

    def _set_site(self, site: str) -> None:
        self.site = site
        self._history.clear()
        self._all = None
        self._sync_site_buttons()
        is_arca = site == "arca"
        self._dc_nav.setVisible(not is_arca)
        self._arca_nav.setVisible(is_arca)
        with QSignalBlocker(self.search_type):
            self.search_type.clear()
            for key, label in (arca.SEARCH_TYPES if is_arca else api.SEARCH_TYPES).items():
                self.search_type.addItem(label, key)
        self.omnibox.setPlaceholderText(
            "검색어, 아카콘 번호 또는 arca.live/e/ 주소" if is_arca
            else "검색어, 패키지 ID 또는 디시콘 URL"
        )
        self._home_kind = "new" if is_arca else "day"
        self.show_home(self._home_kind)

    def _require_login(self) -> None:
        """로그인 알림창 -> 브라우저 로그인 -> 쿠키 저장 -> 아카콘 화면."""
        if self._login_task is not None:
            return
        answer = QMessageBox.information(
            self, "아카콘 로그인",
            "아카콘을 보려면 아카라이브 로그인이 필요합니다.\n\n"
            "확인을 누르면 로그인 창(Chrome 또는 Edge)이 열립니다.\n"
            "로그인을 마친 뒤 브라우저 창을 닫으면 아카콘 화면으로 넘어갑니다.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            if self.site == "arca":
                self._set_site("dccon")
            return

        cancel = threading.Event()
        progress = QProgressDialog("열린 브라우저 창에서 아카라이브에 로그인한 뒤 창을 닫아 주세요…",
                                   "취소", 0, 0, self)
        progress.setWindowTitle("아카콘 로그인")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.canceled.connect(cancel.set)
        progress.show()

        task = Task(arca_login.login, cancel, parent=self)
        task.cancel = cancel
        self._login_task = task

        def finish():
            self._login_task = None
            progress.reset()
            progress.deleteLater()

        def done(session: ArcaSession) -> None:
            finish()
            session.save()
            self.arca_session = session
            self.arca_client.set_session(session.user_agent, session.jar())
            if self.site == "arca":
                self.show_home(self._home_kind)
            else:
                self._set_site("arca")

        def failed(message: str) -> None:
            finish()
            if not cancel.is_set():
                QMessageBox.warning(self, "아카콘 로그인", f"로그인하지 못했습니다.\n{message}")
            if self.site == "arca":
                self._set_site("dccon")

        task.signals.done.connect(done)
        task.signals.error.connect(failed)
        # 몇 분씩 걸릴 수 있어 화면 요청용 풀을 막지 않게 따로 돌린다.
        QThreadPool.globalInstance().start(task)

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

        # 업데이트로 갈아탄 뒤 남은 예전 버전 파일 정리.
        # 업데이트 확인을 꺼둬도 해야 하므로 아래 guard 보다 앞에 둔다.
        tidy = Task(updater.tidy_sibling_builds, parent=self)
        tidy.signals.finished.connect(self._inflight.discard)
        self._inflight.add(tidy)
        self.nav_pool.start(tidy)
        # 소스로 돌릴 때는 조용히 넘어간다. 설정에서 직접 확인은 된다.
        if not self.settings.check_updates or updater.build_kind() is None:
            return

        def work():
            updater.cleanup_staging()
            updater.cleanup_code()
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
        self._resume_clients()
        if self._login_task is not None:
            self._login_task.cancel.set()
        for pool in (self.thumb_pool, self.nav_pool, self.dl_pool):
            pool.clear()
        self.settings.save()
        # 돌고 있는 작업이 끝나기를 잠깐 기다린다. 안 기다리면 워커가
        # 이미 사라진 시그널 객체에 emit 하면서 시끄럽게 죽는다.
        for pool in (self.thumb_pool, self.nav_pool, self.dl_pool):
            pool.waitForDone(2000)
        self.dc_client.close()
        self.arca_client.close()
        super().closeEvent(event)
