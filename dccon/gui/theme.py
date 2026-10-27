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

# RCM 편집기와 같은 결: 무채색 회색 단계 + 보라 강조색, 테두리 없는 납작한 버튼.
LIGHT = {
    "bg": "#f5f5f5",
    "glow": "#8b5cf6",
    "dock_shadow": "#000000",
    "text": "#1f1f1f",
    "heading": "#141414",
    "muted": "#737373",
    "tooltip_bg": "#232323",
    "tooltip_fg": "#e6e6e6",
    "surface": "#ffffff",
    "topbar_border": "#e5e5e5",
    "brand": "#7c3aed",
    "focus": "#8b5cf6",
    "selection": "#8b5cf6",
    "chip_bg": "#ede9fe",
    "chip_fg": "#6d28d9",
    "loading_chunk": "#8b5cf6",
    "tab_fg": "#737373",
    "tab_hover": "#ebebeb",
    "tab_checked_bg": "#ffffff",
    "tab_checked_border": "#e5e5e5",
    "btn_bg": "#ebebeb",
    "btn_fg": "#1f1f1f",
    "btn_border": "#e5e5e5",
    "btn_hover_bg": "#e0e0e0",
    "btn_hover_border": "#e0e0e0",
    "btn_pressed": "#d6d6d6",
    "disabled_fg": "#a3a3a3",
    "disabled_bg": "#f0f0f0",
    "disabled_border": "#f0f0f0",
    "primary_disabled_bg": "#ddd6fe",
    "primary_disabled_fg": "#ffffff",
    "input_bg": "#ebebeb",
    "input_focus_bg": "#ffffff",
    "popup_bg": "#ffffff",
    "popup_sel_bg": "#ede9fe",
    "thumb_bg": "#f0f0f0",
    "thumb_fg": "#a3a3a3",
    "card_subtitle": "#737373",
    "check_bg": "#ffffff",
    "check_border": "#c4c4c4",
    "accent": "#8b5cf6",
    "dock_0": "#ffffff",
    "dock_1": "#ffffff",
    "dock_2": "#ffffff",
    "dock_border": "#e5e5e5",
    "dock_bottom": "#e5e5e5",
    "sel_label_bg": "#ede9fe",
    "queue_border": "#e5e5e5",
    "queue_status": "#737373",
    "percent": "#7c3aed",
    "tree_bg": "#ffffff",
    "tree_alt": "#f7f7f7",
    "header_bg": "#f0f0f0",
    "header_fg": "#737373",
    "track": "#e5e5e5",
    "dl_track": "#e5e5e5",
    "scroll_handle": "#d4d4d4",
    "scroll_hover": "#a3a3a3",
    # 카드 (cards.py 가 직접 그린다)
    "card_bg": "#ffffff",
    "card_selected_bg": "#f5f3ff",
    "card_border": "#e5e5e5",
    "card_hover_border": "#c4b5fd",
    "card_shadow": "#000000",
}

# RCM tokens.css 값을 바탕으로 한다.
DARK = {
    "bg": "#141414",
    "glow": "#a78bfa",
    "dock_shadow": "#000000",
    "text": "#e6e6e6",
    "heading": "#f0f0f0",
    "muted": "#8c8c8c",
    "tooltip_bg": "#2c2c2c",
    "tooltip_fg": "#e6e6e6",
    "surface": "#1c1c1c",
    "topbar_border": "#2e2e2e",
    "brand": "#a78bfa",
    "focus": "#8b5cf6",
    "selection": "#8b5cf6",
    "chip_bg": "#2c2c2c",
    "chip_fg": "#c4b5fd",
    "loading_chunk": "#8b5cf6",
    "tab_fg": "#8c8c8c",
    "tab_hover": "#333333",
    "tab_checked_bg": "#232323",
    "tab_checked_border": "#2e2e2e",
    "btn_bg": "#2c2c2c",
    "btn_fg": "#e6e6e6",
    "btn_border": "#2e2e2e",
    "btn_hover_bg": "#333333",
    "btn_hover_border": "#333333",
    "btn_pressed": "#3a3a3a",
    "disabled_fg": "#5c5c5c",
    "disabled_bg": "#1f1f1f",
    "disabled_border": "#1f1f1f",
    "primary_disabled_bg": "#3b2d63",
    "primary_disabled_fg": "#8c8c8c",
    "input_bg": "#2c2c2c",
    "input_focus_bg": "#2c2c2c",
    "popup_bg": "#232323",
    "popup_sel_bg": "#333333",
    "thumb_bg": "#1a1a1a",
    "thumb_fg": "#5c5c5c",
    "card_subtitle": "#8c8c8c",
    "check_bg": "#2c2c2c",
    "check_border": "#4a4a4a",
    "accent": "#8b5cf6",
    "dock_0": "#1c1c1c",
    "dock_1": "#1c1c1c",
    "dock_2": "#1c1c1c",
    "dock_border": "#2e2e2e",
    "dock_bottom": "#2e2e2e",
    "sel_label_bg": "#2a2340",
    "queue_border": "#2e2e2e",
    "queue_status": "#8c8c8c",
    "percent": "#a78bfa",
    "tree_bg": "#1c1c1c",
    "tree_alt": "#202020",
    "header_bg": "#232323",
    "header_fg": "#8c8c8c",
    "track": "#2c2c2c",
    "dl_track": "#2c2c2c",
    "scroll_handle": "#2c2c2c",
    "scroll_hover": "#3a3a3a",
    "card_bg": "#232323",
    "card_selected_bg": "#2a2340",
    "card_border": "#2e2e2e",
    "card_hover_border": "#4a4a4a",
    "card_shadow": "#000000",
}

_TEMPLATE = """
QWidget {
    font-family: "Pretendard Variable", "Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Segoe UI", sans-serif;
    font-size: 13px; color: $text;
}
QMainWindow, QDialog { background: $bg; }
QLabel { background: transparent; }
QToolTip { background: $tooltip_bg; color: $tooltip_fg; border: 1px solid $btn_border; border-radius: 6px; padding: 6px 8px; }
QMenu { background: $popup_bg; color: $text; border: 1px solid $btn_border; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 16px; border-radius: 6px; }
QMenu::item:selected { background: $popup_sel_bg; color: $text; }
QMenu::item:disabled { color: $disabled_fg; }
QMenu::separator { height: 1px; background: $btn_border; margin: 4px 6px; }
#gridScroll, #gridHolder, #gridScroll > QWidget > QWidget { background: $bg; }
#gridScroll { border: none; }
#mainArea, #searchBar { background: $bg; }
#sidebar { background: $surface; border-right: 1px solid $topbar_border; }
#brand { color: $text; font-size: 16px; font-weight: 700; }
#segment { background: $input_bg; border-radius: 6px; }
QPushButton#segButton {
    background: transparent; color: $muted; border-radius: 4px; padding: 5px 0; min-height: 14px;
}
QPushButton#segButton:hover { color: $text; }
QPushButton#segButton:checked { background: $btn_hover_bg; color: $text; }
#navSection { color: $muted; font-size: 11px; padding: 10px 8px 4px; }
QPushButton#navItem {
    background: transparent; color: $muted; text-align: left; font-weight: 400;
    border: none; border-left: 3px solid transparent; border-radius: 6px;
    padding: 8px 10px; min-height: 16px;
}
QPushButton#navItem:hover { background: $tab_hover; color: $text; }
QPushButton#navItem:checked { background: $tab_checked_bg; border-left-color: $accent; color: $text; font-weight: 500; }
QPushButton#ghost { background: transparent; color: $muted; }
QPushButton#ghost:hover { background: $btn_hover_bg; color: $text; }
QPushButton#ghost:checked { background: $btn_hover_bg; color: $text; }
QPushButton#ghost:disabled { background: transparent; color: $disabled_fg; }
#viewHeader { background: $bg; }
#crumb { font-size: 22px; font-weight: 600; color: $heading; }
#viewHint { color: $muted; font-size: 12px; }
#resultCount { color: $muted; font-size: 12px; padding-bottom: 3px; }
#loadingLine { background: transparent; border: none; border-radius: 0; }
#loadingLine::chunk { background: $loading_chunk; border-radius: 0; }
QPushButton {
    background: $btn_bg; border: none; border-radius: 6px;
    padding: 6px 12px; color: $btn_fg; font-weight: 500; min-height: 16px;
}
QPushButton:hover { background: $btn_hover_bg; }
QPushButton:pressed { background: $btn_pressed; }
QPushButton:disabled { color: $disabled_fg; background: $disabled_bg; }
QPushButton#primary, QPushButton#searchButton {
    background: $accent; color: white; font-weight: 600;
}
QPushButton#primary { padding: 6px 16px; }
QPushButton#primary:hover, QPushButton#searchButton:hover { background: #9d74f8; }
QPushButton#primary:pressed, QPushButton#searchButton:pressed { background: #7c4ff0; }
QPushButton#primary:disabled { background: $primary_disabled_bg; color: $primary_disabled_fg; }
QLineEdit, QComboBox {
    background: $input_bg; border: 1px solid transparent; border-radius: 6px;
    padding: 6px 8px; color: $text; font-weight: 500;
    selection-background-color: $selection; selection-color: white;
}
QLineEdit:focus, QComboBox:focus { border-color: $focus; background: $input_focus_bg; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $popup_bg; color: $text; border: 1px solid $btn_border;
    selection-background-color: $popup_sel_bg; selection-color: $text;
    padding: 4px; outline: none;
}
QTextBrowser {
    background: $tree_bg; color: $text; border: 1px solid $btn_border;
    border-radius: 8px; padding: 8px; selection-background-color: $selection;
}
QFrame#card { background: transparent; border: none; }
#thumb { background: $thumb_bg; border-radius: 6px; color: $thumb_fg; font-size: 26px; }
#cardTitle { color: $text; font-size: 13px; font-weight: 500; }
#cardSubtitle { color: $card_subtitle; font-size: 11px; }
#cardCheck { background: transparent; spacing: 0; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QCheckBox::indicator:unchecked { background: $check_bg; border: 1px solid $check_border; border-radius: 4px; }
QCheckBox::indicator:checked { background: $accent; border: 1px solid $accent; border-radius: 4px; image: url("$check_icon"); }
QCheckBox::indicator:hover, QCheckBox::indicator:focus { border: 1px solid $focus; }
/* 다운로드 글로우가 독 주위로 비쳐야 해서 바탕을 깔지 않는다. */
#dockSpace { background: transparent; }
#dockToggle {
    background: $btn_bg; border: 1px solid $dock_border; border-radius: 6px;
    color: $muted; font-size: 9px; padding: 2px 0; min-height: 14px;
}
#dockToggle:hover, #dockToggle:focus { border-color: $focus; color: $text; }
#downloadDock { background: $card_bg; border: 1px solid $dock_border; border-radius: 12px; }
#actionBar { background: transparent; border: none; }
#selLabel { color: $text; font-weight: 600; }
#queueBar { background: transparent; border: none; }
#queueStatus { color: $text; font-size: 12px; font-weight: 500; }
#progressPercent { color: $percent; font-size: 12px; font-weight: 600; }
#queueDetail { border: none; background: $tree_bg; alternate-background-color: $tree_alt; }
QTreeWidget::item { padding: 6px; }
QHeaderView::section { background: $header_bg; border: none; padding: 6px 8px; color: $header_fg; font-size: 12px; }
QProgressBar { border: none; border-radius: 3px; background: $track; height: 6px; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
#downloadProgress { background: $dl_track; border: none; border-radius: 3px; }
#downloadProgress::chunk { background: $accent; border-radius: 3px; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px 1px; }
QScrollBar::handle:vertical { background: $scroll_handle; border-radius: 3px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: $scroll_hover; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QSlider::groove:horizontal { height: 4px; background: $track; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #ffffff; border: none; border-radius: 7px; }
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
