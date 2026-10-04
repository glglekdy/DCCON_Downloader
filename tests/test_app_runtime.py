import gc
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from dccon import app as app_module
from dccon.gui.appicon import macos_icon


class AppRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_gc_runs_on_gui_thread_timer(self):
        was_enabled = gc.isenabled()
        try:
            timer = app_module._collect_garbage_on_gui_thread(self.app)
            self.assertFalse(gc.isenabled())
            self.assertTrue(timer.isActive())
            timer.stop()
            timer.deleteLater()
        finally:
            if was_enabled:
                gc.enable()

    def test_macos_icon_is_rounded_with_margin(self):
        source = QImage(64, 64, QImage.Format.Format_ARGB32)
        source.fill(QColor("#3366ff"))
        icon = macos_icon(source, 256)
        self.assertEqual((icon.width(), icon.height()), (256, 256))
        # 바깥 여백과 둥근 모서리는 투명, 가운데는 원본 색.
        self.assertEqual(icon.pixelColor(5, 5).alpha(), 0)
        self.assertEqual(icon.pixelColor(28, 28).alpha(), 0)
        self.assertEqual(icon.pixelColor(128, 128).name(), "#3366ff")


if __name__ == "__main__":
    unittest.main()
