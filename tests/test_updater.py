"""GitHub 릴리즈 업데이트 - 네트워크 없이 도는 검사."""

import hashlib
import io
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx

from dccon import updater


def release_json(tag="v0.2.0", assets=()):
    return {
        "tag_name": tag,
        "name": f"디시콘 다운로더 {tag}",
        "body": "- 고친 것",
        "html_url": f"https://github.com/{updater.REPO}/releases/tag/{tag}",
        "assets": list(assets),
    }


def asset_json(name, data=b"", digest=True):
    return {
        "name": name,
        "browser_download_url": f"https://example.invalid/{name}",
        "size": len(data),
        "digest": "sha256:" + hashlib.sha256(data).hexdigest() if digest else None,
    }


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("1.2.0"), (1, 2))
        self.assertEqual(updater.parse_version("0.3.0-beta"), (0, 3))
        self.assertEqual(updater.parse_version("nightly"), ())

    def test_is_newer(self):
        self.assertTrue(updater.is_newer("v0.2.0", "0.1.0"))
        self.assertTrue(updater.is_newer("0.10.0", "0.9.9"))
        self.assertFalse(updater.is_newer("v0.1.0", "0.1.0"))
        self.assertFalse(updater.is_newer("v0.1", "0.1.0"))
        self.assertFalse(updater.is_newer("v0.0.9", "0.1.0"))
        self.assertFalse(updater.is_newer("latest", "0.1.0"))


class ReleaseTests(unittest.TestCase):
    def test_pick_asset_by_build_kind(self):
        release = updater.Release.from_api(release_json(assets=[
            asset_json("source.tar.gz"),
            asset_json("dccon-downloader.exe"),
            asset_json("dccon-downloader-0.2.0-win64.zip"),
        ]))
        self.assertEqual(release.version, "0.2.0")
        self.assertEqual(release.pick_asset("onefile").name, "dccon-downloader.exe")
        self.assertEqual(release.pick_asset("onedir").name, "dccon-downloader-0.2.0-win64.zip")
        self.assertIsNone(release.pick_asset(None))

    def test_fetch_latest(self):
        def handler(request):
            self.assertEqual(str(request.url), updater.LATEST_URL)
            return httpx.Response(200, json=release_json("v9.0.0"))

        with client_for(handler) as client:
            release = updater.fetch_latest(client)
        self.assertEqual(release.tag, "v9.0.0")

    def test_no_release_yet(self):
        with client_for(lambda r: httpx.Response(404)) as client:
            self.assertIsNone(updater.fetch_latest(client))

    def test_rate_limited(self):
        resp = httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
        with client_for(lambda r: resp) as client:
            with self.assertRaisesRegex(updater.UpdateError, "한도"):
                updater.fetch_latest(client)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _download(self, release, kind, payload, **kwargs):
        with client_for(lambda r: httpx.Response(200, content=payload)) as client:
            return updater.download(release, kind, client=client,
                                    staging_root=self.root, **kwargs)

    def test_onefile_is_renamed_to_running_exe(self):
        payload = b"MZ" + b"\0" * 5000
        release = updater.Release.from_api(release_json(assets=[
            asset_json("dccon-downloader.exe", payload),
        ]))
        seen = []
        with patch.object(sys, "executable", str(self.root / "내 디시콘.exe")):
            staged = self._download(release, "onefile", payload,
                                    progress=lambda d, t: seen.append((d, t)))
        self.assertEqual((staged.source / "내 디시콘.exe").read_bytes(), payload)
        self.assertEqual(seen[-1], (len(payload), len(payload)))

    def test_onedir_zip_descends_into_top_folder(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dccon-downloader/dccon-downloader.exe", b"MZ")
            zf.writestr("dccon-downloader/_internal/base_library.zip", b"x")
        payload = buf.getvalue()
        release = updater.Release.from_api(release_json(assets=[
            asset_json("dccon-downloader-win64.zip", payload),
        ]))
        staged = self._download(release, "onedir", payload)
        self.assertEqual(staged.source.name, "dccon-downloader")
        self.assertTrue((staged.source / "_internal" / "base_library.zip").exists())

    def test_onedir_zip_without_app_is_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", b"hi")
        payload = buf.getvalue()
        release = updater.Release.from_api(release_json(assets=[
            asset_json("app.zip", payload),
        ]))
        with self.assertRaisesRegex(updater.UpdateError, "_internal"):
            self._download(release, "onedir", payload)

    def test_digest_mismatch_is_rejected(self):
        release = updater.Release.from_api(release_json(assets=[
            asset_json("dccon-downloader.exe", b"good"),
        ]))
        with self.assertRaisesRegex(updater.UpdateError, "SHA-256"):
            self._download(release, "onefile", b"evil")
        self.assertEqual(list((self.root / "v0.2.0").iterdir()), [])

    def test_cancel_leaves_no_partial_file(self):
        release = updater.Release.from_api(release_json(assets=[
            asset_json("dccon-downloader.exe", b"x" * 10, digest=False),
        ]))
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(updater.UpdateCancelled):
            self._download(release, "onefile", b"x" * 10, cancel=cancel)
        self.assertEqual(list((self.root / "v0.2.0").iterdir()), [])

    def test_missing_asset(self):
        release = updater.Release.from_api(release_json())
        with self.assertRaisesRegex(updater.UpdateError, "맞는 파일"):
            self._download(release, "onefile", b"")


class BuildKindTests(unittest.TestCase):
    def test_source_run(self):
        self.assertIsNone(updater.build_kind())
        self.assertFalse(updater.can_self_update())

    def test_frozen_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "app" / "dccon-downloader.exe"
            with patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "executable", str(exe)):
                with patch.object(sys, "_MEIPASS", str(exe.parent / "_internal"), create=True):
                    self.assertEqual(updater.build_kind(), "onedir")
                with patch.object(sys, "_MEIPASS", str(Path(tmp) / "_MEI1234"), create=True):
                    self.assertEqual(updater.build_kind(), "onefile")


if __name__ == "__main__":
    unittest.main()
