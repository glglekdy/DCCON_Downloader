"""라이트/다크 테마 전환."""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from dccon.config import Settings
from dccon.gui import theme
from dccon.gui.settings_dialog import SettingsDialog


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        # 다른 테스트가 라이트를 전제하므로 되돌려 둔다.
        theme.apply(self.app, "light")

    def test_token_sets_match(self):
        self.assertEqual(set(theme.LIGHT), set(theme.DARK))
        for tokens in (theme.LIGHT, theme.DARK):
            self.assertNotIn("$", theme.build_style(tokens))

    def test_forced_modes(self):
        theme.apply(self.app, "dark")
        self.assertTrue(theme.is_dark())
        self.assertIn(theme.DARK["bg"], self.app.styleSheet())
        self.assertEqual(self.app.palette().color(QPalette.ColorRole.Window).name(),
                         theme.DARK["bg"])
        self.assertEqual(theme.color("card_bg").name(), theme.DARK["card_bg"])

        theme.apply(self.app, "light")
        self.assertFalse(theme.is_dark())
        self.assertEqual(self.app.styleSheet(), theme.STYLE)

    def test_system_mode_follows_os(self):
        hints = self.app.styleHints()
        with patch.object(type(hints), "colorScheme", return_value=Qt.ColorScheme.Dark):
            theme.apply(self.app, "system")
            self.assertTrue(theme.is_dark())
        with patch.object(type(hints), "colorScheme", return_value=Qt.ColorScheme.Light):
            theme._restyle(self.app)  # OS 에서 바꿨을 때 불리는 경로
            self.assertFalse(theme.is_dark())

    def test_unknown_mode_falls_back_to_system(self):
        with patch.object(type(self.app.styleHints()), "colorScheme",
                          return_value=Qt.ColorScheme.Light):
            theme.apply(self.app, "neon")
        self.assertEqual(theme._mode, "system")

    def test_settings_dialog_saves_theme(self):
        settings = Settings(theme="system")
        cache = type("Cache", (), {"stats": lambda self: (0, 0)})()
        dialog = SettingsDialog(settings, cache)
        dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("dark"))
        with patch("dccon.gui.settings_dialog.Path.mkdir"):
            dialog.apply_to(settings)
        self.assertEqual(settings.theme, "dark")


if __name__ == "__main__":
    unittest.main()
