"""아카콘(arca.live/e) 엔드포인트 (2026-10 기준 실측).

전부 서버 렌더 HTML 이고 로그인해야 보인다. 로그인 없이 부르면
/u/login?goto=... 로 넘어간다.

목록  : GET /e/?p={page}                 최신순
        GET /e/?rank=weekly|monthly&p=  인기순
검색  : GET /e/?target={title|nickname|tag}&keyword={word}&p={page}
상세  : GET /e/{id}
        .emoticons-wrapper 안에 <img class="emoticon" src=...> 또는
        움직이는 콘은 <video data-src="...mp4" poster="...thumbnail.jpg">.
        이미지 주소에는 ?expires=&key= 서명이 붙는다.
"""

from __future__ import annotations

import html
import re

import httpx

from .client import DcconClient
from .models import DcconItem, Package, PackageBrief

ARCA_BASE = "https://arca.live"
HEADERS = {"Referer": f"{ARCA_BASE}/e/"}

ARCA_TABS = [("new", "최신"), ("weekly", "주간 인기"), ("monthly", "월간 인기")]
SEARCH_TYPES = {"title": "제목", "nickname": "작가", "tag": "태그"}

# Task 는 예외를 문자열로만 넘긴다. 화면에서 이 문구로 로그인 필요를 알아본다.
LOGIN_REQUIRED_MSG = "아카라이브 로그인이 필요합니다."


class LoginRequired(RuntimeError):
    def __init__(self) -> None:
        super().__init__(LOGIN_REQUIRED_MSG)


_CARD_RE = re.compile(r'<a[^>]*href="/e/(\d+)[^"]*"[^>]*>\s*<div class="emoticon">(.*?)</a>', re.S)
_IMG_SRC_RE = re.compile(r'<img[^>]*\ssrc="((?:https?:)?//[^"]+)"')
_TITLE_RE = re.compile(r'class="title"[^>]*>(.*?)</div>', re.S)
_MAKER_RE = re.compile(r'class="maker"[^>]*>(.*?)</div>', re.S)
_AUTHOR_RE = re.compile(r'class="author"[^>]*>(.*?)</div>', re.S)
_INFO_TITLE_RE = re.compile(r'class="emoticon-info"[^>]*>\s*<div class="title"[^>]*>(.*?)</div>', re.S)
_ICON_RE = re.compile(r'class="emoticon-header-icon"[^>]*>\s*<img[^>]*\ssrc="([^"]+)"', re.S)
_PAGE_RE = re.compile(r'href="/e/\?[^"]*?\bp=(\d+)')
_MEDIA_RE = re.compile(r"<(img|video)\b([^>]*)>", re.S)
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
_TAG_RE = re.compile(r"<[^>]+>")
_ID_IN_URL = re.compile(r"arca\.live/e/(\d+)")


def _text(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub("", fragment)).strip()


def _url(src: str) -> str:
    src = html.unescape(src.strip())
    return "https:" + src if src.startswith("//") else src


def _get(client: DcconClient, path: str, params: dict | None = None, **kw) -> str:
    try:
        resp = client.get(f"{ARCA_BASE}{path}", params=params, **kw)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise LoginRequired() from exc
        raise
    if "/u/login" in resp.url.path:
        raise LoginRequired()
    return resp.content.decode("utf-8", errors="replace")


def fetch_list(client: DcconClient, kind: str = "new", page: int = 1,
               **kw) -> tuple[list[PackageBrief], int]:
    params: dict = {"p": max(1, page)}
    if kind in ("weekly", "monthly"):
        params["rank"] = kind
    body = _get(client, "/e/", params, **kw)
    return parse_list(body), parse_pages(body, page)


def search(client: DcconClient, word: str, target: str = "title", page: int = 1,
           **kw) -> tuple[list[PackageBrief], int]:
    if target not in SEARCH_TYPES:
        target = "title"
    params = {"target": target, "keyword": word, "p": max(1, page)}
    body = _get(client, "/e/", params, **kw)
    return parse_list(body), parse_pages(body, page)


def fetch_package(client: DcconClient, package_idx: int, **kw) -> Package:
    body = _get(client, f"/e/{package_idx}", **kw)
    package = parse_package(package_idx, body)
    if not package.items:
        raise LookupError(f"아카콘 {package_idx} 를 찾을 수 없습니다.")
    return package


def parse_list(body: str) -> list[PackageBrief]:
    out: list[PackageBrief] = []
    for idx, chunk in _CARD_RE.findall(body):
        # 별점 아이콘(/static/...)이 먼저 나오므로 CDN 주소인 첫 이미지를 고른다.
        thumb = _IMG_SRC_RE.search(chunk)
        title = _TITLE_RE.search(chunk)
        maker = _MAKER_RE.search(chunk)
        out.append(
            PackageBrief(
                idx=int(idx),
                title=_text(title.group(1)) if title else f"#{idx}",
                seller=_text(maker.group(1)) if maker else "",
                thumb_url=_url(thumb.group(1)) if thumb else "",
            )
        )
    return out


def parse_pages(body: str, page: int) -> int:
    return max([page, *(int(n) for n in _PAGE_RE.findall(body))])


def parse_package(package_idx: int, body: str) -> Package:
    title = _INFO_TITLE_RE.search(body)
    author = _AUTHOR_RE.search(body)
    icon = _ICON_RE.search(body)

    start = body.find('class="emoticons-wrapper"')
    end = body.find("</div>", start) if start >= 0 else -1
    wrapper = body[start:end] if start >= 0 else ""

    items: list[DcconItem] = []
    for tag, raw in _MEDIA_RE.findall(wrapper):
        attrs = dict(_ATTR_RE.findall(raw))
        src = attrs.get("data-src") or attrs.get("src") or ""
        if not src:
            continue
        url = _url(src)
        ext = url.split("?", 1)[0].rsplit(".", 1)[-1].lower() or "png"
        poster = attrs.get("poster", "")
        items.append(
            DcconItem(
                idx=int(attrs.get("data-id") or 0),
                title="",
                sort=len(items) + 1,
                ext="mp4" if tag == "video" and ext not in ("mp4", "webm") else ext,
                path=url,
                thumb=_url(poster) if poster else "",
            )
        )
    return Package(
        idx=package_idx,
        title=_text(title.group(1)) if title else f"아카콘 {package_idx}",
        seller=_text(author.group(1)) if author else "",
        main_img_path=_url(icon.group(1)) if icon else "",
        items=items,
    )


def parse_ids(text: str) -> list[int] | None:
    """아카콘 번호나 arca.live/e/ 주소들이면 번호 목록, 아니면 None."""
    tokens = [t for t in re.split(r"[\s,]+", (text or "").strip()) if t]
    ids: list[int] = []
    for token in tokens:
        if token.isdigit():
            ids.append(int(token))
            continue
        found = _ID_IN_URL.search(token)
        if not found:
            return None
        ids.append(int(found.group(1)))
    return list(dict.fromkeys(ids)) or None
