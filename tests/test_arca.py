"""아카콘 - 파싱, 로그인 만료 감지, 사이트 전환. 네트워크 없이."""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from unittest.mock import patch

import httpx
from PySide6.QtWidgets import QApplication

from dccon import arca
from dccon.cache import cache_key
from dccon.client import DcconClient
from dccon.config import Settings
from dccon.gui.main_window import MainWindow
from dccon.models import PackageBrief

LIST_HTML = """
<a href="/e/54566?p=1">
  <div class="emoticon">
    <span class="stars"><img src="/static/assets/images/star-yellow.svg?v=1" alt="Star"></span>
    <img loading="lazy" src="//ac.arca.live/20260922sac/aa.png?expires=1&amp;key=k">
    <div><div class="title">고양이 &amp; 밴시</div><div class="maker">작가1</div>
    <div class="count">판매 <span>9425</span></div></div>
  </div>
</a>
<a href="/e/48750?p=1"><div class="emoticon">
  <img loading="lazy" src="//ac.arca.live/x/bb.gif?expires=1&amp;key=k">
  <div><div class="title">움짤콘</div><div class="maker">작가2</div></div></div></a>
<ul class="pagination">
  <li><a class="page-link" href="/e/?p=1">1</a></li>
  <li><a class="page-link" href="/e/?rank=weekly&amp;p=12">12</a></li>
</ul>
"""

DETAIL_HTML = """
<div class="emoticon-header">
  <div class="emoticon-header-icon"><img loading="lazy" class="emoticon" src="//ac.arca.live/a/icon.png?expires=1&amp;key=k" data-id=""></div>
  <div class="emoticon-info"><div class="title">움짤콘</div><div class="author"> 작가2 </div></div>
</div>
<div class="article-body emoticon-body"><div class="emoticons-wrapper">
  <img loading="lazy" class="emoticon" src="//ac.arca.live/a/1.png?expires=1&amp;key=k" data-id="11">
  <video loading="lazy" autoplay loop muted class="emoticon" data-src="//ac.arca.live/a/2.mp4?expires=1&amp;key=k" poster="//ac.arca.live/a/2.thumbnail.jpg?expires=1&amp;key=k" data-id="22"></video>
</div></div>
<div class="sidebar"><img class="emoticon" src="//ac.arca.live/other.png" data-id="99"></div>
"""


def client_with(handler):
    client = DcconClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return client


class ParseTest(unittest.TestCase):
    def test_list(self):
        rows = arca.parse_list(LIST_HTML)
        self.assertEqual([r.idx for r in rows], [54566, 48750])
        self.assertEqual(rows[0].title, "고양이 & 밴시")
        self.assertEqual(rows[0].seller, "작가1")
        # 별점 아이콘이 아니라 CDN 썸네일을 골라야 한다.
        self.assertEqual(rows[0].thumb_url,
                         "https://ac.arca.live/20260922sac/aa.png?expires=1&key=k")
        self.assertEqual(arca.parse_pages(LIST_HTML, 1), 12)

    def test_detail_images_and_videos(self):
        package = arca.parse_package(48750, DETAIL_HTML)
        self.assertEqual(package.title, "움짤콘")
        self.assertEqual(package.seller, "작가2")
        self.assertEqual(package.main_url, "https://ac.arca.live/a/icon.png?expires=1&key=k")
        self.assertEqual([(i.sort, i.idx, i.ext) for i in package.items],
                         [(1, 11, "png"), (2, 22, "mp4")])
        video = package.items[1]
        self.assertEqual(video.url, "https://ac.arca.live/a/2.mp4?expires=1&key=k")
        self.assertTrue(video.thumb.endswith("2.thumbnail.jpg?expires=1&key=k"))

    def test_cache_key_ignores_signature(self):
        self.assertEqual(cache_key("https://ac.arca.live/a/1.png?expires=1&key=a"),
                         cache_key("https://ac.arca.live/a/1.png?expires=2&key=b"))

    def test_parse_ids(self):
        self.assertEqual(arca.parse_ids("https://arca.live/e/54566?p=1 123"), [54566, 123])
        self.assertIsNone(arca.parse_ids("고양이"))


class LoginDetectTest(unittest.TestCase):
    def test_redirect_to_login_raises(self):
        def handler(request):
            if request.url.path == "/u/login":
                return httpx.Response(200, text="login")
            return httpx.Response(302, headers={"Location": "/u/login?goto=/e/"})

        with self.assertRaises(arca.LoginRequired):
            arca.fetch_list(client_with(handler), "new", 1)

    def test_list_request_params(self):
        seen = []

        def handler(request):
            seen.append(dict(request.url.params))
            return httpx.Response(200, text=LIST_HTML)

        client = client_with(handler)
        arca.fetch_list(client, "weekly", 3)
        arca.search(client, "고양이", "tag", 2)
        self.assertEqual(seen[0], {"p": "3", "rank": "weekly"})
        self.assertEqual(seen[1], {"target": "tag", "keyword": "고양이", "p": "2"})


class SiteSwitchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, session):
        patches = [
            patch.object(Settings, "load", return_value=Settings()),
            patch.object(Settings, "save"),
            patch("dccon.gui.main_window.ArcaSession.load", return_value=session),
            patch("dccon.api.fetch_top", return_value=[]),
            patch.object(MainWindow, "_startup_update_check"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        window = MainWindow()
        self.addCleanup(window.close)
        return window

    def test_arca_without_session_asks_login(self):
        window = self.make_window(None)
        with patch.object(window, "_require_login") as ask:
            window._site_buttons["arca"].click()
        ask.assert_called_once()
        self.assertEqual(window.site, "dccon")
        self.assertTrue(window._site_buttons["dccon"].isChecked())

    def test_arca_with_session_shows_list(self):
        from dccon.arca_login import ArcaSession
        window = self.make_window(ArcaSession("UA", [{"name": "a", "value": "b",
                                                       "domain": "arca.live", "path": "/"}]))
        rows = [PackageBrief(1, "콘", "작가")]
        with patch("dccon.arca.fetch_list", return_value=(rows, 5)) as fetch:
            window._site_buttons["arca"].click()
            window.nav_pool.waitForDone(3000)
            self.app.processEvents()
        fetch.assert_called_once()
        self.assertEqual(window.site, "arca")
        self.assertIs(window.client, window.arca_client)
        self.assertEqual(window.search_type.currentData(), "title")
        self.assertTrue(window._arca_tab_buttons["new"].isChecked())
        self.assertEqual(window._all, (1, 5))
        self.assertEqual(window.arca_client._client.headers["User-Agent"], "UA")

    def test_expired_session_asks_login_again(self):
        window = self.make_window(None)
        with patch.object(window, "_require_login") as ask, \
                patch("dccon.gui.main_window.ArcaSession.forget") as forget:
            window._on_nav_error(arca.LOGIN_REQUIRED_MSG)
        ask.assert_called_once()
        forget.assert_called_once()


if __name__ == "__main__":
    unittest.main()
