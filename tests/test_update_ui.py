"""업데이트 창 흐름 - 실제 다운로드 없이."""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dccon import updater
from dccon.gui.update_dialog import UpdateDialog


def wait_for(predicate, timeout_ms=3000):
    for _ in range(timeout_ms // 20):
        if predicate():
            return
        QTest.qWait(20)
    raise AssertionError("시간 안에 조건이 채워지지 않음")


RELEASE = updater.Release(
    tag="v9.0.0", name="v9.0.0", notes="## 바뀐 점\n- 업데이트 기능",
    page_url="https://example.invalid/release",
    assets=[updater.Asset("dccon-downloader.exe", "https://example.invalid/a.exe", 3)],
)


class UpdateDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_download_then_accept(self):
        staged = updater.StagedUpdate(RELEASE, "onefile", Path("."))

        def fake_download(release, kind, *, progress, cancel):
            progress(1, 3)
            progress(3, 3)
            return staged

        with patch.object(updater, "can_self_update", return_value=True), \
             patch.object(updater, "build_kind", return_value="onefile"), \
             patch.object(updater, "download", side_effect=fake_download):
            dialog = UpdateDialog(RELEASE, offer_skip=True)
            dialog.show()
            dialog.go.click()
            wait_for(lambda: dialog.staged is not None)
        self.assertIs(dialog.staged, staged)
        self.assertEqual(dialog.result(), UpdateDialog.DialogCode.Accepted)

    def test_error_allows_retry(self):
        with patch.object(updater, "can_self_update", return_value=True), \
             patch.object(updater, "build_kind", return_value="onefile"), \
             patch.object(updater, "download", side_effect=updater.UpdateError("끊김")):
            dialog = UpdateDialog(RELEASE)
            dialog.show()
            dialog.go.click()
            wait_for(dialog.go.isEnabled)
        self.assertIn("끊김", dialog.status.text())
        self.assertEqual(dialog.go.text(), "다시 시도")
        self.assertIsNone(dialog.staged)

    def test_source_run_offers_release_page(self):
        dialog = UpdateDialog(RELEASE)  # 테스트는 소스 실행이라 자동 업데이트 불가
        self.assertEqual(dialog.go.text(), "릴리즈 페이지 열기")


if __name__ == "__main__":
    unittest.main()
