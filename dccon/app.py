"""앱 진입점."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .config import DATA_DIR
from .gui.theme import STYLE


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName("디시콘 다운로더")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    # import를 늦춰서 QApplication이 먼저 만들어지게 한다.
    from .gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
