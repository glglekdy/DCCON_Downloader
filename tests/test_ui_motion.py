"""Offline regression checks for interruptible UI transitions."""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFontDatabase, QWheelEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dccon.config import Settings
from dccon.gui.main_window import MainWindow
from dccon.gui.theme import STYLE
from dccon.models import PackageBrief


class MotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        for font in ("malgun.ttf", "malgunbd.ttf"):
            path = "C:/Windows/Fonts/" + font
            if os.path.exists(path):
                QFontDatabase.addApplicationFont(path)
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.save = patch.object(Settings, "save")
        self.save.start()
        with patch.object(Settings, "load", return_value=Settings()), patch.object(MainWindow, "_run"):
            self.window = MainWindow()
        self.window._fill_packages(self.window._generation, [
            PackageBrief(i, f"테스트 디시콘 {i}", "작가") for i in range(30)
        ])
        self.window.show()
        QTest.qWait(300)

    def tearDown(self):
        self.window.close()
        self.save.stop()
        self.app.setProperty("reduceMotion", False)

    def test_hover_and_selection_reverse_without_stuck_state(self):
        card = self.window._cards[0][0]
        self.app.sendEvent(card, QEvent(QEvent.Type.Enter))
        QTest.qWait(60)
        self.assertGreater(card.hoverAmount, 0)
        self.app.sendEvent(card, QEvent(QEvent.Type.Leave))
        card.set_checked(True)
        QTest.qWait(40)
        card.set_checked(False)
        QTest.qWait(300)
        self.assertEqual(card.hoverAmount, 0)
        self.assertEqual(card.selectionAmount, 0)
        self.assertFalse(self.window.download_btn.isEnabled())

    def test_queue_reversal_and_progress_reset(self):
        queue = self.window.queue
        queue.expand_btn.click()
        QTest.qWait(65)
        self.assertGreater(queue.detail.maximumHeight(), 0)
        self.assertLess(queue.detail.maximumHeight(), 170)
        queue.expand_btn.click()
        QTest.qWait(300)
        self.assertTrue(queue.detail.isHidden())
        queue.start([(1, "테스트")])
        queue.set_overall(8, 10)
        QTest.qWait(70)
        self.assertGreater(queue.progress.value(), 0)
        self.assertLess(queue.progress.value(), 80)
        queue.set_idle()
        QTest.qWait(300)
        self.assertEqual(queue.progress.value(), 0)

    def test_scroll_and_navigation_stop(self):
        scroll = self.window.scroll
        event = QWheelEvent(QPointF(100, 100), QPointF(100, 100), QPoint(),
                            QPoint(0, -120), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        scroll.wheelEvent(event)
        QTest.qWait(50)
        self.assertGreater(scroll.verticalScrollBar().value(), 0)
        with patch.object(self.window, "_run"):
            self.window.show_home("week")
        QTest.qWait(220)
        self.assertEqual(scroll.verticalScrollBar().value(), 0)

    def test_reduced_motion_and_compact_search(self):
        self.app.setProperty("reduceMotion", True)
        card = self.window._cards[0][0]
        card.set_checked(True)
        self.assertEqual(card.selectionAmount, 1)
        self.window.queue.expand_btn.click()
        self.assertEqual(self.window.queue.detail.maximumHeight(), 170)
        self.window.queue.set_overall(5, 10)
        self.assertEqual(self.window.queue.progress.value(), 50)
        self.window._reveal_grid()
        self.assertFalse(self.window._title_effect.isEnabled())
        self.window.resize(780, 580)
        with patch.object(self.window, "_run"):
            self.window.show_search("고양이")
        self.window._set_page_label(1, 10)
        self.app.processEvents()
        self.assertEqual(self.window.width(), 780)

    def test_stale_navigation_callback_is_ignored(self):
        with patch.object(self.window.nav_pool, "start"):
            results = []
            self.window._run(lambda: None, results.append)
            task = next(iter(self.window._inflight))
            self.window._generation += 1
            task.signals.done.emit("stale")
            task.signals.error.emit("stale error")
        self.assertEqual(results, [])
        self.assertEqual(len(self.window._cards), 30)

    def test_batch_selection_updates_count_once_without_animations(self):
        with patch.object(self.window, "_update_selection",
                          wraps=self.window._update_selection) as update:
            self.window._set_all_checked(True)
            self.assertEqual(update.call_count, 1)
        for card, _ in self.window._cards:
            self.assertTrue(card.checked)
            self.assertEqual(card.selectionAmount, 1)
            self.assertEqual(card._select_motion.state(), card._select_motion.State.Stopped)
        self.assertTrue(self.window.download_btn.isEnabled())
        self.window._set_all_checked(False)
        self.assertFalse(self.window.download_btn.isEnabled())

    def test_list_has_no_offscreen_compositing_effect(self):
        self.window._reveal_grid()
        self.assertIsNone(self.window.scroll.widget().graphicsEffect())
        self.assertIs(self.window.crumb.graphicsEffect(), self.window._title_effect)

    def test_thumbnail_is_prescaled_and_reused(self):
        preview = self.window._cards[0][0].thumb
        source = QPixmap(1200, 800)
        source.fill(Qt.GlobalColor.blue)
        preview.set_source(source)
        self.assertLessEqual(preview.source.deviceIndependentSize().width(), 137)
        self.assertAlmostEqual(preview.source.width() / preview.source.height(), 1.5, delta=.02)
        key = preview.source.cacheKey()
        preview.grab()
        preview.grab()
        self.assertEqual(preview.source.cacheKey(), key)


if __name__ == "__main__":
    unittest.main()
