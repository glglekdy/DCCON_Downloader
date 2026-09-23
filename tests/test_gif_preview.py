"""GIF 미리보기 재생과 설정 토글."""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from unittest.mock import patch

from PySide6.QtGui import QMovie
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dccon.config import Settings
from dccon.gui.cards import Card
from dccon.gui.settings_dialog import SettingsDialog


def _frame(pixel_data: bytes) -> bytes:
    # 그래픽 제어 확장(지연 5/100초) + 1x1 이미지 + LZW 데이터
    return (b"\x21\xf9\x04\x00\x05\x00\x00\x00"
            b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00"
            b"\x02\x02" + pixel_data + b"\x00")


# 1x1, 2색(검정/흰색), 무한 반복, 두 프레임(검정 → 흰색)
ANIMATED_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
    b"\x00\x00\x00\xff\xff\xff"
    b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
    + _frame(b"\x44\x01") + _frame(b"\x4c\x01") + b"\x3b"
)
STILL_GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
             + _frame(b"\x44\x01") + b"\x3b")


class GifPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(setattr, Card, "animate_gifs", True)

    def _card(self, data):
        card = Card("움짤", "GIF", checkable=True)
        card.show()
        card.set_image(data)
        self.addCleanup(card.deleteLater)
        return card

    def test_animated_gif_plays(self):
        card = self._card(ANIMATED_GIF)
        movie = card.thumb.movie
        self.assertIsNotNone(movie)
        self.assertEqual(movie.frameCount(), 2)
        self.assertEqual(movie.state(), QMovie.MovieState.Running)
        seen = {movie.currentFrameNumber()}
        for _ in range(40):
            QTest.qWait(20)
            seen.add(movie.currentFrameNumber())
        self.assertEqual(seen, {0, 1})
        self.assertFalse(card.thumb.source.isNull())

    def test_setting_off_shows_first_frame_only(self):
        Card.animate_gifs = False
        card = self._card(ANIMATED_GIF)
        self.assertEqual(card.thumb.movie.state(), QMovie.MovieState.NotRunning)
        self.assertFalse(card.thumb.source.isNull())

    def _shown_color(self, card):
        image = card.thumb.source.toImage()
        return image.pixelColor(image.width() // 2, image.height() // 2).name()

    def test_toggle_existing_card(self):
        card = self._card(ANIMATED_GIF)
        movie = card.thumb.movie
        # 두 번째(흰색) 프레임까지 간 뒤에 끈다.
        for _ in range(50):
            QTest.qWait(10)
            if movie.currentFrameNumber() == 1:
                break
        self.assertEqual(self._shown_color(card), "#ffffff")
        card.set_animated(False)
        self.assertNotEqual(movie.state(), QMovie.MovieState.Running)
        # 멈추면 첫 프레임(검정)으로 돌아와 있어야 한다.
        self.assertEqual(self._shown_color(card), "#000000")
        QTest.qWait(150)  # 멈춘 동안에는 프레임이 넘어가지 않는다
        self.assertEqual(self._shown_color(card), "#000000")
        # 다시 켜면 계속 돈다. 끈 상태로 만든 카드도 켜면 돈다.
        for _ in range(3):
            card.set_animated(True)
            self.assertEqual(movie.state(), QMovie.MovieState.Running)
            QTest.qWait(100)
            self.assertEqual(movie.state(), QMovie.MovieState.Running)
            card.set_animated(False)

    def test_created_off_then_turned_on(self):
        Card.animate_gifs = False
        card = self._card(ANIMATED_GIF)
        card.set_animated(True)
        QTest.qWait(100)
        self.assertEqual(card.thumb.movie.state(), QMovie.MovieState.Running)

    def test_single_frame_gif_does_not_run_a_timer(self):
        card = self._card(STILL_GIF)
        self.assertEqual(card.thumb.movie.state(), QMovie.MovieState.NotRunning)
        self.assertFalse(card.thumb.source.isNull())

    def test_broken_gif_falls_back_quietly(self):
        card = self._card(b"GIF89a-not-really")
        self.assertIsNone(card.thumb.movie)
        self.assertTrue(card.thumb.source.isNull())

    def test_settings_dialog_saves_toggle(self):
        settings = Settings(animate_gifs=True)
        cache = type("Cache", (), {"stats": lambda self: (0, 0)})()
        dialog = SettingsDialog(settings, cache)
        dialog.animate_gifs.setChecked(False)
        with patch("dccon.gui.settings_dialog.Path.mkdir"):
            dialog.apply_to(settings)
        self.assertFalse(settings.animate_gifs)


if __name__ == "__main__":
    unittest.main()
