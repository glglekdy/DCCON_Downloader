"""Shared colors and widget styles for the desktop application.

색은 전부 토큰으로 뽑아두고 라이트/다크 두 벌을 둔다. 스타일시트는 `$토큰`
자리에 값을 채워 만든다. 카드처럼 직접 그리는 위젯은 `color()` 로 읽는다.

테마 모드는 "system" / "light" / "dark". system 이면 OS 설정을 따르고
OS 에서 바꾸면 바로 따라간다. 창 제목 표시줄은 Qt 가 색 구성표를 보고 맞춘다.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

THEME_MODES = [("system", "시스템 설정 따르기"), ("light", "라이트"), ("dark", "다크")]

LIGHT = {
    "bg": "#f3f6fb",
    "glow": "#6c74e0",
    "dock_shadow": "#254070",
    "text": "#26354b",
    "heading": "#1c2d49",
    "muted": "#65748b",
    "tooltip_bg": "#26354b",
    "tooltip_fg": "#ffffff",
    "surface": "#ffffff",
    "topbar_border": "#dfe6f0",
    "brand": "#274ca0",
    "focus": "#274ca0",
    "selection": "#274ca0",
    "chip_bg": "#e4ebf7",
    "chip_fg": "#466089",
    "loading_chunk": "#7299e0",
    "tab_fg": "#596b83",
    "tab_hover": "#e5ecf8",
    "tab_checked_bg": "#e0eaff",
    "tab_checked_border": "#c5d5f4",
    "btn_bg": "#ffffff",
    "btn_fg": "#34465f",
    "btn_border": "#d6dfec",
    "btn_hover_bg": "#edf2fc",
    "btn_hover_border": "#9eafd0",
    "btn_pressed": "#dde7fa",
    "disabled_fg": "#8995a8",
    "disabled_bg": "#edf1f6",
    "disabled_border": "#e2e7ee",
    "primary_disabled_bg": "#e0e7f2",
    "primary_disabled_fg": "#7889a4",
    "input_bg": "#f8faff",
    "input_focus_bg": "#ffffff",
    "popup_bg": "#ffffff",
    "popup_sel_bg": "#e5edfc",
    "thumb_bg": "#f2f5fa",
    "thumb_fg": "#8b9bb1",
    "card_subtitle": "#697991",
    "check_bg": "#ffffff",
    "check_border": "#b8c6da",
    "accent": "#315fbc",
    "dock_0": "#ffffff",
    "dock_1": "#f4f8ff",
    "dock_2": "#efedfb",
    "dock_border": "#cfdcf0",
    "dock_bottom": "#d3ddef",
    "sel_label_bg": "#edf3ff",
    "queue_border": "#e0e7f3",
    "queue_status": "#526580",
    "percent": "#465b96",
    "tree_bg": "#ffffff",
    "tree_alt": "#f3f6fb",
    "header_bg": "#eaf0f8",
    "header_fg": "#526580",
    "track": "#d6e0ee",
    "dl_track": "#dfe6f4",
    "scroll_handle": "#bfccdf",
    "scroll_hover": "#8ca4c6",
    # 카드 (cards.py 가 직접 그린다)
    "card_bg": "#ffffff",
    "card_selected_bg": "#eaf1ff",
    "card_border": "#e0e7f1",
    "card_hover_border": "#a6bce5",
    "card_shadow": "#254070",
}

DARK = {
    "bg": "#11161f",
    "glow": "#8f9cff",
    "dock_shadow": "#000000",
    "text": "#dbe3ef",
    "heading": "#eef2f8",
    "muted": "#8d9ab0",
    "tooltip_bg": "#e6ecf5",
    "tooltip_fg": "#141a24",
    "surface": "#171d28",
    "topbar_border": "#252e3d",
    "brand": "#8fb0ff",
    "focus": "#6f95f0",
    "selection": "#3b5fb0",
    "chip_bg": "#202a3a",
    "chip_fg": "#a9bbdc",
    "loading_chunk": "#5d86dc",
    "tab_fg": "#9aa7bb",
    "tab_hover": "#1c2432",
    "tab_checked_bg": "#1f2d4d",
    "tab_checked_border": "#33497a",
    "btn_bg": "#1d2431",
    "btn_fg": "#d0d9e6",
    "btn_border": "#2e3a4d",
    "btn_hover_bg": "#253043",
    "btn_hover_border": "#4a5d7d",
    "btn_pressed": "#2c3a52",
    "disabled_fg": "#5d6a7e",
    "disabled_bg": "#161b24",
    "disabled_border": "#222a37",
    "primary_disabled_bg": "#222a37",
    "primary_disabled_fg": "#66748a",
    "input_bg": "#141a24",
    "input_focus_bg": "#19202c",
    "popup_bg": "#1a212d",
    "popup_sel_bg": "#24324c",
    "thumb_bg": "#1b222d",
    "thumb_fg": "#56647a",
    "card_subtitle": "#8391a7",
    "check_bg": "#141a24",
    "check_border": "#46546a",
    "accent": "#4a7ae0",
    "dock_0": "#19202b",
    "dock_1": "#1a2130",
    "dock_2": "#1d1e31",
    "dock_border": "#2a3547",
    "dock_bottom": "#222c3c",
    "sel_label_bg": "#1d2a45",
    "queue_border": "#253042",
    "queue_status": "#98a6bb",
    "percent": "#9db4ea",
    "tree_bg": "#151b25",
    "tree_alt": "#19202b",
    "header_bg": "#1b2230",
    "header_fg": "#98a6bb",
    "track": "#283344",
    "dl_track": "#253042",
    "scroll_handle": "#343f51",
    "scroll_hover": "#4d5d77",
    "card_bg": "#171e29",
    "card_selected_bg": "#1c2944",
    "card_border": "#252f3f",
    "card_hover_border": "#475c84",
    "card_shadow": "#000000",
}

_TEMPLATE = """
QWidget {
    font-family: "Malgun Gothic", "Segoe UI", sans-serif;
    font-size: 13px; color: $text;
}
QMainWindow, QDialog { background: $bg; }
QLabel { background: transparent; }
QToolTip { background: $tooltip_bg; color: $tooltip_fg; border: none; padding: 8px; }
QMenu { background: $popup_bg; color: $text; border: 1px solid $btn_border; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 4px; }
QMenu::item:selected { background: $popup_sel_bg; color: $brand; }
QMenu::item:disabled { color: $disabled_fg; }
QMenu::separator { height: 1px; background: $btn_border; margin: 4px 6px; }
#gridScroll, #gridHolder, #gridScroll > QWidget > QWidget { background: $bg; }
#gridScroll { border: none; }
#topBar { background: $surface; border-bottom: 1px solid $topbar_border; }
#brand { color: $brand; font-size: 25px; font-weight: 900; padding-right: 4px; }
#viewHeader, #tabBar { background: $bg; }
#crumb { font-size: 28px; font-weight: 700; color: $heading; }
#viewHint, #resultCount { color: $muted; font-size: 12px; }
#resultCount { background: $chip_bg; color: $chip_fg; border-radius: 10px; padding: 4px 10px; }
#loadingLine { background: $chip_bg; border: none; border-radius: 0; }
#loadingLine::chunk { background: $loading_chunk; border-radius: 0; }
#tabButton {
    border: 1px solid transparent; background: transparent;
    color: $tab_fg; padding: 9px 18px; border-radius: 10px;
}
#tabButton:hover { background: $tab_hover; }
#tabButton:checked { background: $tab_checked_bg; border-color: $tab_checked_border; color: $brand; font-weight: 700; }
QPushButton {
    background: $btn_bg; border: 1px solid $btn_border; border-radius: 8px;
    padding: 8px 12px; color: $btn_fg; min-height: 18px;
}
QPushButton:hover { background: $btn_hover_bg; border-color: $btn_hover_border; }
QPushButton:pressed { background: $btn_pressed; }
QPushButton:focus { border-color: $focus; }
QPushButton:disabled { color: $disabled_fg; background: $disabled_bg; border-color: $disabled_border; }
QPushButton#primary, QPushButton#searchButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #316bd3, stop:1 #6554be);
    border-color: #4b67bf; color: white; font-weight: 700;
}
QPushButton#primary {
    padding: 12px 26px; border-radius: 12px; font-size: 14px; min-width: 134px;
}
QPushButton#primary:hover, QPushButton#searchButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #285cc0, stop:1 #5544ad);
}
QPushButton#primary:focus, QPushButton#searchButton:focus { border: 1px solid #96bcff; }
QPushButton#primary:disabled { background: $primary_disabled_bg; border-color: $primary_disabled_bg; color: $primary_disabled_fg; }
QLineEdit, QComboBox {
    background: $input_bg; border: 1px solid $btn_border; border-radius: 8px;
    padding: 9px 12px; color: $text; selection-background-color: $selection;
    selection-color: white;
}
QLineEdit:focus, QComboBox:focus { border-color: $focus; background: $input_focus_bg; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $popup_bg; color: $text; border: 1px solid $btn_border;
    selection-background-color: $popup_sel_bg; selection-color: $brand;
    padding: 4px;
}
QTextBrowser {
    background: $input_bg; color: $text; border: 1px solid $btn_border;
    border-radius: 8px; padding: 6px; selection-background-color: $selection;
}
QFrame#card { background: transparent; border: none; }
#thumb { background: $thumb_bg; border-radius: 12px; color: $thumb_fg; font-size: 26px; }
#cardTitle { color: $text; font-size: 13px; font-weight: 700; }
#cardSubtitle { color: $card_subtitle; font-size: 11px; }
#cardCheck { background: transparent; spacing: 0; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked { background: $check_bg; border: 1px solid $check_border; border-radius: 5px; }
QCheckBox::indicator:checked { background: $accent; border: 1px solid $accent; border-radius: 5px; image: url("$check_icon"); }
QCheckBox::indicator:hover, QCheckBox::indicator:focus { border: 1px solid $focus; }
/* 다운로드 글로우가 독 주위로 비쳐야 해서 바탕을 깔지 않는다. */
#dockSpace { background: transparent; }
#dockToggle {
    background: $btn_bg; border: 1px solid $dock_border; border-radius: 13px;
    color: $text; font-size: 11px; padding: 3px 0;
}
#dockToggle:hover, #dockToggle:focus { border-color: $focus; }
#downloadDock {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $dock_0, stop:0.55 $dock_1, stop:1 $dock_2);
    border: 1px solid $dock_border; border-bottom: 3px solid $dock_bottom; border-radius: 20px;
}
#actionBar { background: transparent; border: none; }
#selLabel { color: $brand; font-weight: 700; padding: 6px 10px; background: $sel_label_bg; border-radius: 8px; }
#queueBar, #queueSummary { background: transparent; border: none; }
#queueBar { border-top: 1px solid $queue_border; }
#queueStatus { color: $queue_status; font-size: 12px; }
#progressPercent { color: $percent; font-size: 12px; font-weight: 700; }
#queueDetail { border: none; background: $tree_bg; alternate-background-color: $tree_alt; }
QTreeWidget::item { padding: 7px; }
QHeaderView::section { background: $header_bg; border: none; padding: 8px; color: $header_fg; }
QProgressBar { border: none; border-radius: 5px; background: $track; height: 10px; }
QProgressBar::chunk { background: $accent; border-radius: 5px; }
#downloadProgress { background: $dl_track; border: none; border-radius: 6px; }
#downloadProgress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #316bd3, stop:0.55 #5974dc, stop:1 #9870dc);
    border-radius: 6px;
}
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: $scroll_handle; border-radius: 3px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: $scroll_hover; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QSlider::groove:horizontal { height: 6px; background: $track; border-radius: 3px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; margin: -5px 0; background: $surface; border: 2px solid $accent; border-radius: 8px; }
#emptyState { color: $muted; font-size: 14px; padding: 32px; }
#hint { color: $muted; font-size: 12px; }
"""

_CHECK_ICON = (Path(__file__).parent / "assets" / "check.svg").as_posix()


def build_style(tokens: dict[str, str]) -> str:
    values = {**tokens, "check_icon": _CHECK_ICON}
    return re.sub(r"\$(\w+)", lambda m: values[m.group(1)], _TEMPLATE)


# 테마를 모르는 코드(테스트 등)를 위해 라이트 스타일시트를 그대로 내보낸다.
STYLE = build_style(LIGHT)

_mode = "system"
_active = LIGHT


def color(name: str) -> QColor:
    """지금 테마의 색. 직접 그리는 위젯이 paintEvent 안에서 읽는다."""
    return QColor(_active[name])


def is_dark() -> bool:
    return _active is DARK


def _wants_dark(app: QApplication) -> bool:
    if _mode == "dark":
        return True
    if _mode == "light":
        return False
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def _palette(t: dict[str, str]) -> QPalette:
    """스타일시트가 안 닿는 곳(메시지 상자, 기본 위젯)을 위한 팔레트."""
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: t["bg"],
        QPalette.ColorRole.WindowText: t["text"],
        QPalette.ColorRole.Base: t["input_bg"],
        QPalette.ColorRole.AlternateBase: t["tree_alt"],
        QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.Button: t["btn_bg"],
        QPalette.ColorRole.ButtonText: t["btn_fg"],
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: t["selection"],
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: t["tooltip_bg"],
        QPalette.ColorRole.ToolTipText: t["tooltip_fg"],
        QPalette.ColorRole.PlaceholderText: t["muted"],
        QPalette.ColorRole.Link: t["brand"],
        QPalette.ColorRole.LinkVisited: t["brand"],
        QPalette.ColorRole.Light: t["surface"],
        QPalette.ColorRole.Midlight: t["btn_hover_bg"],
        QPalette.ColorRole.Mid: t["btn_border"],
        QPalette.ColorRole.Dark: t["scroll_handle"],
        QPalette.ColorRole.Shadow: t["card_shadow"],
    }
    for role, value in roles.items():
        pal.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["disabled_fg"]))
    return pal


def _restyle(app: QApplication, *, force: bool = False) -> None:
    global _active
    tokens = DARK if _wants_dark(app) else LIGHT
    if tokens is _active and not force:
        return
    _active = tokens
    app.setPalette(_palette(tokens))
    # 스타일시트가 바뀌면 모든 위젯이 StyleChange 를 받아 다시 그려지므로
    # 카드처럼 직접 그리는 위젯도 새 토큰으로 칠해진다.
    # app.allWidgets() 를 돌며 update() 하지 말 것: 파이썬 객체가 먼저 사라진
    # 위젯이 섞여 있으면 PySide 가 래퍼를 만들다 프로세스째 죽는다.
    app.setStyleSheet(build_style(tokens))


def apply(app: QApplication, mode: str) -> None:
    """테마 모드를 정하고 바로 반영한다. 여러 번 불러도 된다."""
    global _mode
    _mode = mode if mode in {m for m, _ in THEME_MODES} else "system"
    hints = app.styleHints()
    if not app.property("themeWatching"):
        # OS 에서 라이트/다크를 바꾸면 따라간다. 강제 모드면 _restyle 이 무시한다.
        hints.colorSchemeChanged.connect(lambda *_: _restyle(app))
        app.setProperty("themeWatching", True)
    # 창 제목 표시줄 같은 플랫폼 쪽 색도 맞춘다. Unknown 은 'OS 를 따름'.
    scheme = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}
    hints.setColorScheme(scheme.get(_mode, Qt.ColorScheme.Unknown))
    _restyle(app, force=True)
