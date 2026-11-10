"""Rust 포팅용 골든 값과 픽스처를 파이썬 1.3.0 코드로 만든다.

실행: uv run python tools/gen_golden.py   (저장소 루트에서)
디시콘 서버에서 실측 픽스처 4개를 받는다(네트워크 필요).
"""

from __future__ import annotations

import os
import sys
import tempfile
import urllib.parse
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json  # noqa: E402

import httpx  # noqa: E402

import dccon.config as config  # noqa: E402
from dccon import api, arca  # noqa: E402
from dccon.cache import cache_key  # noqa: E402
from dccon.client import BASE, DcconClient  # noqa: E402
from dccon.downloader import _write_meta  # noqa: E402
from dccon.models import Package  # noqa: E402
from dccon.naming import item_filename, package_dirname, pad_width, sanitize  # noqa: E402
from dccon.updater import is_newer, parse_version  # noqa: E402
from tests.test_all_list import listing_html  # noqa: E402
from tests.test_arca import DETAIL_HTML, LIST_HTML  # noqa: E402

OUT = ROOT / "crates" / "core" / "tests"
GOLDEN = OUT / "golden"
FIX = OUT / "fixtures"


def dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")


def serving(body: bytes) -> DcconClient:
    client = DcconClient()
    client._client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    )
    return client


def briefs(rows) -> list[dict]:
    return [asdict(r) for r in rows]


def naming() -> None:
    names = ["", "a/b:c?", "CON", "con", "  hello   world  ", "끝점...", "x" * 85, "가" * 85,
             "😀콘", "tab\there", "a.", "NUL.txt", "<>|*\x01",
             "COM1", "lpt9.png", "정상 이름", "a  b\t\nc", "end . .", '"quoted"', "a\\b"]
    out = []
    for n in names:
        out.append({
            "name": n,
            "sanitize": sanitize(n),
            "dirname_idx": 7,
            "dirname": package_dirname(7, n),
            "item": {"sort": 3, "ext": ".PNG", "width": 2, "file": item_filename(3, n, ".PNG", 2)},
        })
    for n in ["", "a/b:c?", "😀콘", "x" * 85]:
        out.append({
            "name": n,
            "sanitize": sanitize(n),
            "dirname_idx": 7,
            "dirname": package_dirname(7, n),
            "item": {"sort": 12, "ext": "gif", "width": 3, "file": item_filename(12, n, "gif", 3)},
        })
    dump(GOLDEN / "naming.json", out)
    dump(GOLDEN / "pad_width.json", [[t, pad_width(t)] for t in (0, 1, 9, 99, 100, 999, 1000, 12345)])


def cache_keys() -> None:
    urls = [
        "https://dcimg5.dcinside.com/dccon.php?no=abc%2Fd&date=1",
        "https://dcimg5.dcinside.com/dccon.php?no=abc%2Fd&date=2",
        "https://dcimg5.dcinside.com/dccon.php?no=62b5df2be09d3ca567b1c5bc12d46b394bd0&date=1",
        "https://dcimg5.dcinside.com/dccon.php?date=1&no=한글",
        "https://ac.arca.live/a/1.png?expires=1&key=a",
        "https://ac.arca.live/a/1.png?expires=2&key=b",
        "https://ac.arca.live/20260922sac/aa.png?expires=1&key=k",
        "https://ac.arca.live/a/1.png",
        "https://example.com/plain/path.gif",
        "",
    ]
    dump(GOLDEN / "cache_key.json", [[u, cache_key(u)] for u in urls])


def queries() -> None:
    texts = ["멍뭉", "12345", "12345 83649, 94849", "12345 12345",
             "https://dccon.dcinside.com/hot/1#12345", "#777", "https://example.com/#5",
             "12 멍", "", "   ", "https://dccon.dcinside.com/?package_idx=555",
             "12345\n67890", "#12 #34"]
    res = []
    for t in texts:
        kind, value = api.parse_query(t)
        res.append([t, {"kind": kind, "value": value}])
    dump(GOLDEN / "parse_query.json", res)

    ids = ["https://arca.live/e/54566?p=1 123", "고양이", "123,456 123", "", "https://arca.live/b/x/1",
           "https://arca.live/e/9", "123 123", "https://arca.live/e/1 https://arca.live/e/2"]
    dump(GOLDEN / "arca_parse_ids.json", [[t, arca.parse_ids(t)] for t in ids])


def versions() -> None:
    parse_in = ["v1.2.3", "1.2", "1.2.0", "1.2.3-beta", "V2.0.0", "", "abc", "  v10.0.1",
                "0", "1.0.0.0", "v1.2.x"]
    newer = [("v2.0.0", "1.3.0"), ("1.3.0", "1.3.0"), ("1.3", "1.3.0"), ("1.2.9", "1.3.0"),
             ("v1.10.0", "1.9.9"), ("", "1.0.0"), ("2.0.0-beta", "1.3.0"), ("1.3.1", "1.3.0"),
             ("abc", "1.3.0")]
    dump(GOLDEN / "version.json", {
        "parse": [[t, list(parse_version(t))] for t in parse_in],
        "newer": [[r, loc, is_newer(r, loc)] for r, loc in newer],
    })


def settings() -> None:
    with tempfile.TemporaryDirectory() as td:
        orig = config.SETTINGS_PATH
        config.SETTINGS_PATH = Path(td) / "settings.json"
        try:
            config.Settings().save()
            data = config.SETTINGS_PATH.read_bytes()
        finally:
            config.SETTINGS_PATH = orig
    (GOLDEN / "settings_default.json").write_bytes(data)


def network_fixtures() -> None:
    client = DcconClient()
    try:
        new1 = client.get(f"{BASE}/new/1").content
        (FIX / "dccon_new_1.html").write_bytes(new1)
        quoted = urllib.parse.quote("멍뭉", safe="")
        hot = client.get(f"{BASE}/hot/1/title/{quoted}").content
        (FIX / "dccon_hot_search.html").write_bytes(hot)
        first = api._parse_list_page(new1.decode("utf-8", errors="replace"))[0].idx
        detail = client.post(api.PACKAGE_DETAIL_URL, data={"package_idx": str(first)},
                             headers={"X-Requested-With": "XMLHttpRequest"}).content
        (FIX / "dccon_detail.json").write_bytes(detail)
        top = client.get(api.TOP_LISTS["day"][1]).content
        (FIX / "dccon_top_day.txt").write_bytes(top)
    finally:
        client.close()


def synth_fixtures() -> None:
    # 이름 -> (listing_html 인자, fetch_all 에 넘길 페이지). tests/test_all_list.py 의 호출과 같다.
    cases = {
        "1": (dict(page=1), 1),
        "6141": (dict(page=6140, with_end=False), 6140),
        "6142": (dict(page=6142, items=9, with_end=False), 6142),
        "6145": (dict(page=6145, items=0, with_end=False), 6145),
    }
    for name, (kw, page) in cases.items():
        body = listing_html(**kw)
        write_text(FIX / f"dccon_new_synth_{name}.html", body)
        rows, pages, total = api.fetch_all(serving(body.encode("utf-8")), page)
        dump(GOLDEN / f"parsed_dccon_new_synth_{name}.json",
             {"page": page, "rows": briefs(rows), "pages": pages, "total": total})


def parsed() -> None:
    new1 = (FIX / "dccon_new_1.html").read_bytes()
    rows, pages, total = api.fetch_all(serving(new1), 1)
    dump(GOLDEN / "parsed_dccon_new_1.json", {"rows": briefs(rows), "pages": pages, "total": total})

    hot = (FIX / "dccon_hot_search.html").read_bytes()
    rows, pages = api.search_packages(serving(hot), "멍뭉", "title", 1)
    dump(GOLDEN / "parsed_dccon_hot_search.json", {"rows": briefs(rows), "pages": pages})

    detail_bytes = (FIX / "dccon_detail.json").read_bytes()
    pkg = Package.from_api(json.loads(detail_bytes.decode("utf-8")))
    dump(GOLDEN / "parsed_dccon_detail.json", asdict(pkg))
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        width = pad_width(max((i.sort for i in pkg.items), default=0))
        _write_meta(dest, pkg, width)
        (GOLDEN / "meta.json").write_bytes((dest / "_meta.json").read_bytes())

    top = (FIX / "dccon_top_day.txt").read_bytes()
    dump(GOLDEN / "parsed_dccon_top_day.json", {"rows": briefs(api.fetch_top(serving(top), "day"))})

    write_text(FIX / "arca_list.html", LIST_HTML)
    write_text(FIX / "arca_detail.html", DETAIL_HTML)
    dump(GOLDEN / "parsed_arca_list.json",
         {"rows": briefs(arca.parse_list(LIST_HTML)), "pages": arca.parse_pages(LIST_HTML, 1)})
    dump(GOLDEN / "parsed_arca_detail.json", asdict(arca.parse_package(48750, DETAIL_HTML)))


def main() -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    FIX.mkdir(parents=True, exist_ok=True)
    naming()
    cache_keys()
    queries()
    versions()
    settings()
    network_fixtures()
    synth_fixtures()
    parsed()
    print("done")


if __name__ == "__main__":
    main()
