"""Shared colors and widget styles for the desktop application."""

from pathlib import Path

STYLE = """
QWidget {
    font-family: "Malgun Gothic", "Segoe UI", sans-serif;
    font-size: 13px; color: #26354b;
}
QMainWindow, QDialog { background: #f3f6fb; }
QLabel { background: transparent; }
QToolTip { background: #26354b; color: white; border: none; padding: 8px; }
#gridScroll, #gridHolder, #gridScroll > QWidget > QWidget { background: #f3f6fb; }
#gridScroll { border: none; }
#topBar { background: #ffffff; border-bottom: 1px solid #dfe6f0; }
#brand { color: #274ca0; font-size: 25px; font-weight: 900; padding-right: 4px; }
#viewHeader, #tabBar { background: #f3f6fb; }
#crumb { font-size: 28px; font-weight: 700; color: #1c2d49; }
#viewHint, #resultCount { color: #65748b; font-size: 12px; }
#resultCount { background: #e4ebf7; color: #466089; border-radius: 10px; padding: 4px 10px; }
#loadingLine { background: #e4ebf7; border: none; border-radius: 0; }
#loadingLine::chunk { background: #7299e0; border-radius: 0; }
#tabButton {
    border: 1px solid transparent; background: transparent;
    color: #596b83; padding: 9px 18px; border-radius: 10px;
}
#tabButton:hover { background: #e5ecf8; }
#tabButton:checked { background: #e0eaff; border-color: #c5d5f4; color: #274ca0; font-weight: 700; }
QPushButton {
    background: #ffffff; border: 1px solid #d6dfec; border-radius: 8px;
    padding: 8px 12px; color: #34465f; min-height: 18px;
}
QPushButton:hover { background: #edf2fc; border-color: #9eafd0; }
QPushButton:pressed { background: #dde7fa; }
QPushButton:focus { border-color: #274ca0; }
QPushButton:disabled { color: #8995a8; background: #edf1f6; border-color: #e2e7ee; }
QPushButton#primary, QPushButton#searchButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #316bd3, stop:1 #6554be);
    border-color: #4b67bf; color: white; font-weight: 700;
}
QPushButton#primary { padding: 10px 22px; }
QPushButton#primary:hover, QPushButton#searchButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #285cc0, stop:1 #5544ad);
}
QPushButton#primary:focus, QPushButton#searchButton:focus { border: 1px solid #96bcff; }
QPushButton#primary:disabled { background: #e0e7f2; border-color: #e0e7f2; color: #7889a4; }
QLineEdit, QComboBox {
    background: #f8faff; border: 1px solid #d6dfec; border-radius: 8px;
    padding: 9px 12px; color: #26354b; selection-background-color: #274ca0;
}
QLineEdit:focus, QComboBox:focus { border-color: #274ca0; background: white; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: white; color: #26354b; border: 1px solid #d6dfec;
    selection-background-color: #e5edfc; selection-color: #274ca0;
    padding: 4px;
}
QFrame#card { background: transparent; border: none; }
#thumb { background: #f2f5fa; border-radius: 12px; color: #8b9bb1; font-size: 26px; }
#cardTitle { color: #26354b; font-size: 13px; font-weight: 700; }
#cardSubtitle { color: #697991; font-size: 11px; }
#cardCheck { background: transparent; spacing: 0; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked { background: white; border: 1px solid #b8c6da; border-radius: 5px; }
QCheckBox::indicator:checked { background: #315fbc; border: 1px solid #315fbc; border-radius: 5px; image: url("CHECK_ICON"); }
QCheckBox::indicator:hover, QCheckBox::indicator:focus { border: 1px solid #274ca0; }
#dockSpace { background: #f3f6fb; }
#downloadDock {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffffff, stop:0.55 #f4f8ff, stop:1 #efedfb);
    border: 1px solid #cfdcf0; border-bottom: 3px solid #d3ddef; border-radius: 20px;
}
#actionBar { background: transparent; border: none; }
#selLabel { color: #274ca0; font-weight: 700; padding: 6px 10px; background: #edf3ff; border-radius: 8px; }
#queueBar, #queueSummary { background: transparent; border: none; }
#queueBar { border-top: 1px solid #e0e7f3; }
#queueStatus { color: #526580; font-size: 12px; }
#progressPercent { color: #465b96; font-size: 12px; font-weight: 700; }
#queueDetail { border: none; background: white; alternate-background-color: #f3f6fb; }
QTreeWidget::item { padding: 7px; }
QHeaderView::section { background: #eaf0f8; border: none; padding: 8px; color: #526580; }
QProgressBar { border: none; border-radius: 5px; background: #d6e0ee; height: 10px; }
QProgressBar::chunk { background: #315fbc; border-radius: 5px; }
#downloadProgress { background: #dfe6f4; border: none; border-radius: 6px; }
#downloadProgress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #316bd3, stop:0.55 #5974dc, stop:1 #9870dc);
    border-radius: 6px;
}
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: #bfccdf; border-radius: 3px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: #8ca4c6; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QSlider::groove:horizontal { height: 6px; background: #d6e0ee; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #315fbc; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; margin: -5px 0; background: white; border: 2px solid #315fbc; border-radius: 8px; }
#emptyState { color: #65748b; font-size: 14px; padding: 32px; }
#hint { color: #65748b; font-size: 12px; }
"""

STYLE = STYLE.replace("CHECK_ICON", (Path(__file__).parent / "assets" / "check.svg").as_posix())
