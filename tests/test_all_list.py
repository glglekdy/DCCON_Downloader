"""전체 디시콘 목록 - 파싱과 화면 이동. 네트워크 없이."""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from unittest.mock import patch

import httpx
from PySide6.QtWidgets import QApplication

from dccon import api
from dccon.client import DcconClient
from dccon.config import Settings
from dccon.gui.main_window import MainWindow
from dccon.models import PackageBrief


def listing_html(page, last=6142, items=15, with_end=True):
    lis = "".join(
        f'<li class="div_package " package_idx="{1000 + i}">'
        f'<a class="link_product" href="#{1000 + i}">'
        f'<img class="thumb_img" src="https://dcimg5.dcinside.com/dccon.php?no=a{i}&amp;date=1">'
        f'<strong class="dcon_name">콘 {i}</strong><span class="dcon_seller">작가{i}</span></a></li>'
        for i in range(items)
    )
    links = "".join(f'<a href="https://dccon.dcinside.com/new/{n}">{n}</a>'
                    for n in range(page + 1, min(last, page + 9) + 1))
    end = (f'<a href="https://dccon.dcinside.com/new/{last}" '
           f'class="sp_pagingicon page_end">끝</a>') if with_end else ""
    return (f'<div class="total_num">총 디시콘 <em class="font_lightblue">92,133</em>개</div>'
            f'<ul>{lis}</ul><div class="bottom_paging_box iconpaging">'
            f'<em>{page}</em>{links}{end}</div>')


def client_serving(body):
    client = DcconClient()
    client._client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=body.encode("utf-8"))))
    return client


class ParseTests(unittest.TestCase):
    def test_first_page(self):
        client = client_serving(listing_html(1))
        rows, pages, total = api.fetch_all(client, 1)
        self.assertEqual((len(rows), pages, total), (15, 6142, 92133))
        self.assertEqual(rows[0].title, "콘 0")
        self.assertEqual(rows[0].seller, "작가0")
        self.assertIn("&date=1", rows[0].thumb_url)

    def test_last_pages_without_end_link(self):
        client = client_serving(listing_html(6140, with_end=False))
        _, pages, _ = api.fetch_all(client, 6140)
        self.assertEqual(pages, 6142)
        client = client_serving(listing_html(6142, items=9, with_end=False))
        rows, pages, _ = api.fetch_all(client, 6142)
        self.assertEqual((len(rows), pages), (9, 6142))

    def test_past_the_end_is_not_the_last_page(self):
        client = client_serving(listing_html(6145, items=0, with_end=False))
        rows, pages, _ = api.fetch_all(client, 6145)
        self.assertEqual(rows, [])
        self.assertLess(pages, 6145)


class AllTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        patches = [
            patch.object(Settings, "load", return_value=Settings()),
            patch.object(Settings, "save"),
            patch.object(MainWindow, "_startup_update_check"),
            # 작업을 스레드 풀 대신 그 자리에서 돌린다.
            patch.object(MainWindow, "_run", lambda self, work, done: done(work())),
            patch.object(api, "fetch_top", return_value=[]),
            patch.object(api, "fetch_all", side_effect=self._fake_all),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.requested = []
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.window._queue_thumb = lambda *a, **k: None

    def _fake_all(self, client, page):
        self.requested.append(page)
        rows = [PackageBrief(page * 100 + i, f"콘 {page}-{i}", "작가") for i in range(15)]
        return rows, 6142, 92133

    def test_tab_shows_first_page_with_pagination(self):
        self.window.show_home("all")
        self.assertTrue(self.window._tab_buttons["all"].isChecked())
        self.assertEqual(self.requested, [1])
        self.assertEqual(len(self.window._cards), 15)
        self.assertEqual(self.window.page_label.text(), "1 / 6142")
        self.assertFalse(self.window.prev_btn.isHidden())
        self.assertIn("92,133", self.window.view_hint.text())

    def test_next_prev_and_jump(self):
        self.window.show_home("all")
        self.window.next_btn.click()
        self.assertEqual(self.window.page_label.text(), "2 / 6142")
        self.window.prev_btn.click()
        self.assertFalse(self.window.prev_btn.isEnabled())
        with patch("dccon.gui.main_window.QInputDialog.getInt", return_value=(6142, True)):
            self.window.page_label.click()
        self.assertEqual(self.requested[-1], 6142)
        self.assertFalse(self.window.next_btn.isEnabled())

    def test_back_from_package_returns_to_same_page(self):
        self.window.show_all(37)
        self.window._history.append(self.window._snapshot())
        self.window.go_back()
        self.assertEqual(self.requested[-1], 37)
        self.assertTrue(self.window._tab_buttons["all"].isChecked())

    def test_other_tab_hides_pagination(self):
        self.window.show_home("all")
        self.window.show_home("week")
        self.assertTrue(self.window.prev_btn.isHidden())
        self.assertIsNone(self.window._all)


if __name__ == "__main__":
    unittest.main()
