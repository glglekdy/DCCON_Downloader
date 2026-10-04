"""앱 진입점."""

from __future__ import annotations

import gc
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from .config import DATA_DIR, Settings
from .gui import theme


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName("디시콘 다운로더")
    app.setWindowIcon(_app_icon())
    _collect_garbage_on_gui_thread(app)
    app.setStyle("Fusion")
    # 창이 뜨기 전에 입혀야 흰 화면이 번쩍이지 않는다.
    theme.apply(app, Settings.load().theme)

    # import를 늦춰서 QApplication이 먼저 만들어지게 한다.
    from .gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    # 코드 업데이트로 받은 코드가 창까지 띄웠으면 믿을 만하다.
    QTimer.singleShot(1000, _confirm_code)
    code = app.exec()
    _confirm_code()
    return code


def _app_icon() -> QIcon:
    """소스 실행에서도 창·작업 표시줄에 아이콘이 붙게 한다.

    (빌드된 exe 는 스펙의 icon= 으로 따로 박힌다.) 맥에서는 이 아이콘이 Dock
    아이콘을 덮어쓰므로 .icns 와 같은 둥근 모양으로 만들어 준다.
    """
    path = Path(__file__).parent / "gui" / "assets" / "icon.png"
    if sys.platform != "darwin":
        return QIcon(str(path))
    from .gui.appicon import macos_icon
    return QIcon(QPixmap.fromImage(macos_icon(QImage(str(path)), 512)))


def _collect_garbage_on_gui_thread(app: QApplication) -> QTimer:
    """순환 참조 수거(GC)를 GUI 스레드에서만 돌린다.

    자동 GC 는 그때 객체를 만들던 스레드에서 돈다. 썸네일·다운로드 작업
    스레드에서 돌다가 파이썬이 쥔 Qt 위젯을 지우면, 같은 순간 GUI 스레드가
    그 위젯에 이벤트를 보내다 세그폴트로 죽는다 (맥에서 실제로 났다).
    그래서 자동 GC 를 끄고, 같은 문턱값 규칙으로 GUI 스레드 타이머가 대신 돈다.
    """
    gc.disable()

    def collect() -> None:
        counts = gc.get_count()
        thresholds = gc.get_threshold()
        if counts[0] <= thresholds[0]:
            return
        generation = 0
        while generation < 2 and counts[generation + 1] > thresholds[generation + 1]:
            generation += 1
        gc.collect(generation)

    timer = QTimer(app)
    timer.timeout.connect(collect)
    timer.start(500)
    return timer


def _confirm_code() -> None:
    try:
        import dccon_boot
    except ImportError:  # 테스트 등 run.py 를 거치지 않은 실행
        return
    dccon_boot.confirm()


if __name__ == "__main__":
    raise SystemExit(main())
