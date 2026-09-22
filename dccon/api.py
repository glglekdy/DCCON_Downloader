"""디시콘 엔드포인트 (2026-09 기준 실측).

package_detail : POST /index/package_detail  (JSON)
검색            : GET  /hot/{page}/{type}/{word}  (서버 렌더 HTML, UTF-8)
인기 목록        : json2.dcinside.com/json1/*.php  (JSON을 괄호로 감싼 응답)
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse

from .client import BASE, DcconClient
from .models import Package, PackageBrief

PACKAGE_DETAIL_URL = f"{BASE}/index/package_detail"

SEARCH_TYPES = {
    "title": "제목",
    "nick_name": "작가",
    "tags": "태그",
}

TOP_LISTS = {
    "day": ("일간 인기", "https://json2.dcinside.com/json1/dccon_day_top100.php"),
    "week": ("주간 인기", "https://json2.dcinside.com/json1/dccon_week_top100.php"),
    "month": ("월간 인기", "https://json2.dcinside.com/json1/dccon_month_top100.php"),
    "official": ("공식", "https://json2.dcinside.com/json1/dccon_official.php"),
}

# <li class="div_package " package_idx="83649"> ... </li>
_LI_RE = re.compile(r'<li[^>]*class="[^"]*div_package[^"]*"[^>]*package_idx="(\d+)"(.*?)</li>', re.S)
_THUMB_RE = re.compile(r'<img[^>]*class="[^"]*thumb_img[^"]*"[^>]*src="([^"]+)"', re.S)
_NAME_RE = re.compile(r'<strong[^>]*class="[^"]*dcon_name[^"]*"[^>]*>(.*?)</strong>', re.S)
_SELLER_RE = re.compile(r'<span[^>]*class="[^"]*dcon_seller[^"]*"[^>]*>(.*?)</span>', re.S)
_TOTAL_RE = re.compile(r'class="total_num"[^>]*>\s*([\d,]+)', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub("", fragment)).strip()


def fetch_package(client: DcconClient, package_idx: int, **kw) -> Package:
    resp = client.post(
        PACKAGE_DETAIL_URL,
        data={"package_idx": str(package_idx)},
        headers={"X-Requested-With": "XMLHttpRequest"},
        **kw,
    )
    payload = resp.json()
    if not payload or not payload.get("info"):
        raise LookupError(f"패키지 {package_idx} 를 찾을 수 없습니다.")
    return Package.from_api(payload)


def search_packages(
    client: DcconClient,
    word: str,
    search_type: str = "title",
    page: int = 1,
    **kw,
) -> tuple[list[PackageBrief], int]:
    """(결과, 전체 페이지 수)를 돌려준다."""
    if search_type not in SEARCH_TYPES:
        search_type = "title"
    quoted = urllib.parse.quote(word, safe="")
    url = f"{BASE}/hot/{page}/{search_type}/{quoted}"
    resp = client.get(url, **kw)
    body = resp.content.decode("utf-8", errors="replace")
    return _parse_list_page(body), _parse_total_pages(body)


def _parse_list_page(body: str) -> list[PackageBrief]:
    out: list[PackageBrief] = []
    for idx, chunk in _LI_RE.findall(body):
        thumb = _THUMB_RE.search(chunk)
        name = _NAME_RE.search(chunk)
        seller = _SELLER_RE.search(chunk)
        out.append(
            PackageBrief(
                idx=int(idx),
                title=_text(name.group(1)) if name else f"#{idx}",
                seller=_text(seller.group(1)) if seller else "",
                thumb_url=html.unescape(thumb.group(1)) if thumb else "",
            )
        )
    return out


def _parse_total_pages(body: str) -> int:
    m = _TOTAL_RE.search(body)
    if not m:
        return 1
    try:
        return max(1, int(m.group(1).replace(",", "")))
    except ValueError:
        return 1


def fetch_top(client: DcconClient, kind: str = "day", **kw) -> list[PackageBrief]:
    _, url = TOP_LISTS.get(kind, TOP_LISTS["day"])
    resp = client.get(url, **kw)
    text = resp.content.decode("utf-8", errors="replace").strip()
    # 응답이 `([{...}])` 처럼 괄호로 감싸여 있어 그대로는 JSON이 아니다.
    if text.startswith("("):
        text = text[1:]
    if text.endswith(")"):
        text = text[:-1]
    rows = json.loads(text)
    out: list[PackageBrief] = []
    for row in rows:
        img = row.get("img") or ""
        if img.startswith("//"):
            img = "https:" + img
        out.append(
            PackageBrief(
                idx=int(row.get("package_idx") or 0),
                title=(row.get("title") or "").strip(),
                seller=(row.get("nick_name") or "").strip(),
                thumb_url=img,
            )
        )
    return out


_ID_IN_URL = re.compile(r"(?:package_idx=|#)(\d+)")


def parse_query(text: str) -> tuple[str, object]:
    """검색창 한 줄을 해석한다.

    ("ids", [12345, ...])  숫자 / URL / 여러 줄 붙여넣기
    ("search", "멍뭉")      그 외 전부 검색어
    """
    raw = (text or "").strip()
    if not raw:
        return ("search", "")

    tokens = [t for t in re.split(r"[\s,]+", raw) if t]
    ids: list[int] = []
    for token in tokens:
        if token.isdigit():
            ids.append(int(token))
            continue
        found = _ID_IN_URL.search(token)
        if found and ("dcinside" in token or token.startswith("#")):
            ids.append(int(found.group(1)))
            continue
        # 하나라도 해석이 안 되면 전체를 검색어로 본다.
        return ("search", raw)
    if ids:
        # 순서 유지하며 중복 제거
        return ("ids", list(dict.fromkeys(ids)))
    return ("search", raw)
