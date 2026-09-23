"""앱 진입점."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config import DATA_DIR, Settings
from .gui import theme


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName("디시콘 다운로더")
    # 소스 실행에서도 창·작업 표시줄에 아이콘이 붙게 한다.
    # (빌드된 exe 는 스펙의 icon= 으로 따로 박힌다.)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "gui" / "assets" / "icon.png")))
    app.setStyle("Fusion")
    # 창이 뜨기 전에 입혀야 흰 화면이 번쩍이지 않는다.
    theme.apply(app, Settings.load().theme)

    # import를 늦춰서 QApplication이 먼저 만들어지게 한다.
    from .gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
