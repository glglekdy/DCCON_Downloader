"""코드 업데이트 - dccon 패키지만 받아 올리는 흐름. 네트워크 없이."""

import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import httpx

import dccon_boot
from dccon import config, updater

from test_updater import asset_json, client_for, release_json

RUNTIME = "ab" * 32
BASE = {"version": "1.0.0", "runtime": RUNTIME}


def code_zip(version="1.1.0", runtime=RUNTIME, with_package=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"version": version, "runtime": runtime}))
        if with_package:
            zf.writestr("dccon/__init__.py", f'__version__ = "{version}"\n')
            zf.writestr("dccon/gui/assets/icon.png", b"png")
    return buf.getvalue()


class CodeUpdateTestCase(unittest.TestCase):
    """CODE_DIR 을 임시 폴더로 돌리고 exe 에 박힌 build_info 를 흉내낸다."""

    info = BASE

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.code = self.root / "code"
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.addCleanup(self.tmp.cleanup)
        stack.enter_context(patch.object(dccon_boot, "CODE_DIR", self.code))
        stack.enter_context(patch.object(dccon_boot, "CURRENT", self.code / "current.txt"))
        stack.enter_context(patch.object(dccon_boot, "REJECTED", self.code / "rejected.txt"))
        stack.enter_context(patch.object(dccon_boot, "active", None))
        stack.enter_context(patch.object(dccon_boot, "build_info", lambda: dict(self.info)))
        stack.enter_context(patch.object(sys, "path", list(sys.path)))

    def place(self, version="1.1.0", runtime=RUNTIME, unconfirmed=False, tried=False):
        folder = self.code / version
        (folder / "dccon").mkdir(parents=True)
        (folder / "dccon" / "__init__.py").write_text("", encoding="utf-8")
        (folder / "manifest.json").write_text(
            json.dumps({"version": version, "runtime": runtime}), encoding="utf-8")
        if unconfirmed:
            (folder / dccon_boot.UNCONFIRMED).touch()
        if tried:
            (folder / dccon_boot.TRIED).touch()
        dccon_boot.CURRENT.write_text(version, encoding="utf-8")
        return folder


class BootTests(CodeUpdateTestCase):
    def test_data_dir_matches_config(self):
        self.assertEqual(dccon_boot.DATA_DIR, config.DATA_DIR)

    def test_activates_matching_code(self):
        folder = self.place()
        self.assertEqual(dccon_boot.activate(), "1.1.0")
        self.assertEqual(sys.path[0], str(folder))
        self.assertEqual(dccon_boot.active, "1.1.0")

    def test_source_run_does_nothing(self):
        self.place()
        with patch.object(dccon_boot, "build_info", lambda: {}):
            self.assertIsNone(dccon_boot.activate())

    def test_other_runtime_is_ignored(self):
        self.place(runtime="cd" * 32)
        self.assertIsNone(dccon_boot.activate())

    def test_exe_caught_up_is_ignored(self):
        self.place(version="1.0.0")
        self.assertIsNone(dccon_boot.activate())

    def test_first_run_is_marked_then_confirmed(self):
        folder = self.place(unconfirmed=True)
        self.assertEqual(dccon_boot.activate(), "1.1.0")
        self.assertTrue((folder / dccon_boot.TRIED).exists())
        dccon_boot.confirm()
        self.assertFalse((folder / dccon_boot.UNCONFIRMED).exists())
        self.assertFalse((folder / dccon_boot.TRIED).exists())

    def test_crashed_last_time_is_rejected(self):
        folder = self.place(unconfirmed=True, tried=True)
        self.assertIsNone(dccon_boot.activate())
        self.assertFalse(folder.exists())
        self.assertFalse(dccon_boot.CURRENT.exists())
        self.assertEqual(dccon_boot.REJECTED.read_text(encoding="utf-8"), "1.1.0")

    def test_fall_back_drops_path_and_modules(self):
        folder = self.place()
        dccon_boot.activate()
        with patch.dict(sys.modules):
            sys.modules["dccon.fake"] = object()
            dccon_boot.fall_back()
            self.assertNotIn("dccon", sys.modules)
            self.assertNotIn("dccon.fake", sys.modules)
        self.assertNotIn(str(folder), sys.path)
        self.assertIsNone(dccon_boot.active)
        self.assertEqual(dccon_boot.REJECTED.read_text(encoding="utf-8"), "1.1.0")


class ChooseAssetTests(CodeUpdateTestCase):
    def release(self, runtime=RUNTIME):
        return updater.Release.from_api(release_json("v1.1.0", assets=[
            asset_json("dccon-downloader-1.1.0.exe"),
            asset_json("dccon-downloader-1.1.0.zip"),
            asset_json(updater.code_asset_name("1.1.0", runtime)),
        ]))

    def test_same_runtime_takes_code(self):
        for kind in ("onefile", "onedir"):
            self.assertTrue(updater.choose_asset(self.release(), kind).name.endswith(".pyz"))

    def test_other_runtime_takes_full(self):
        release = self.release(runtime="cd" * 32)
        self.assertEqual(updater.choose_asset(release, "onefile").name, "dccon-downloader-1.1.0.exe")
        self.assertEqual(updater.choose_asset(release, "onedir").name, "dccon-downloader-1.1.0.zip")

    def test_rejected_version_takes_full(self):
        self.code.mkdir()
        dccon_boot.REJECTED.write_text("1.1.0", encoding="utf-8")
        self.assertEqual(updater.choose_asset(self.release(), "onefile").name,
                         "dccon-downloader-1.1.0.exe")

    def test_old_apps_never_pick_code(self):
        # 코드 업데이트를 모르는 옛 앱은 확장자로만 고른다.
        self.assertEqual(self.release().pick_asset("onedir").name, "dccon-downloader-1.1.0.zip")


class DownloadInstallTests(CodeUpdateTestCase):
    def download(self, payload):
        release = updater.Release.from_api(release_json("v1.1.0", assets=[
            asset_json("dccon-downloader-1.1.0.exe"),
            asset_json(updater.code_asset_name("1.1.0", RUNTIME), payload),
        ]))
        with client_for(lambda r: httpx.Response(200, content=payload)) as client:
            return updater.download(release, "onefile", client=client,
                                    staging_root=self.root / "staging")

    def test_download_install_then_boot(self):
        staged = self.download(code_zip())
        self.assertEqual(staged.kind, "code")
        folder = updater.install_code(staged)
        self.assertEqual(folder, self.code / "1.1.0")
        self.assertTrue((folder / "dccon" / "gui" / "assets" / "icon.png").exists())
        self.assertTrue((folder / dccon_boot.UNCONFIRMED).exists())
        # 다음 실행: 부트스트랩이 방금 설치한 코드를 올린다.
        self.assertEqual(dccon_boot.activate(), "1.1.0")
        self.assertEqual(sys.path[0], str(folder))

    def test_runtime_mismatch_in_manifest_is_rejected(self):
        with self.assertRaisesRegex(updater.UpdateError, "맞지 않"):
            self.download(code_zip(runtime="cd" * 32))

    def test_missing_package_is_rejected(self):
        with self.assertRaisesRegex(updater.UpdateError, "dccon 패키지"):
            self.download(code_zip(with_package=False))

    def test_cleanup_keeps_only_current(self):
        self.place(version="1.0.5")
        keep = self.place(version="1.1.0")
        updater.cleanup_code()
        self.assertEqual([p.name for p in self.code.iterdir() if p.is_dir()], [keep.name])

    def test_cleanup_after_full_update(self):
        self.place(version="1.1.0")
        self.info = {"version": "1.2.0", "runtime": "cd" * 32}
        updater.cleanup_code()
        self.assertFalse((self.code / "1.1.0").exists())
        self.assertFalse(dccon_boot.CURRENT.exists())


if __name__ == "__main__":
    unittest.main()
