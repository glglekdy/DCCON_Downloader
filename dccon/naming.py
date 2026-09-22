"""파일명 정규화.

디시콘 제목에는 `/`, `:`, `?`, 이모지가 그대로 들어있고 빈 문자열인 경우도
흔하다. Windows에서 그대로 쓰면 바로 깨지므로 전부 여기서 걸러낸다.
"""

from __future__ import annotations

import re

# Windows에서 파일명에 못 쓰는 문자 + 제어문자
_FORBIDDEN = re.compile(r'[<>:"/\|?*\x00-\x1f]')
# 장치 이름은 확장자를 붙여도 예약어라 파일을 만들 수 없다.
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_COMPONENT = 80


def sanitize(name: str, fallback: str = "untitled") -> str:
    """경로 한 조각(폴더명 또는 파일명 본체)을 안전하게 만든다."""
    cleaned = _FORBIDDEN.sub("_", name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 끝의 점과 공백은 탐색기가 조용히 잘라먹어 이름 충돌을 만든다.
    cleaned = cleaned.rstrip(". ")
    if len(cleaned) > _MAX_COMPONENT:
        cleaned = cleaned[:_MAX_COMPONENT].rstrip(". ")
    if cleaned.upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned or fallback


def package_dirname(idx: int, title: str) -> str:
    """패키지 폴더명. 제목이 겹쳐도 ID가 다르면 섞이지 않게 한다."""
    safe = sanitize(title, fallback=f"package_{idx}")
    return safe


def pad_width(total: int) -> int:
    """100개 넘는 패키지에서도 탐색기 정렬이 맞도록 자릿수를 맞춘다."""
    return max(2, len(str(max(total, 1))))


def item_filename(sort: int, title: str, ext: str, width: int = 2) -> str:
    """`01_안녕.png` 형태. 제목이 비면 `01_.png`가 된다."""
    safe = _FORBIDDEN.sub("_", title or "").strip().rstrip(". ")
    safe = re.sub(r"\s+", " ", safe)
    if len(safe) > _MAX_COMPONENT:
        safe = safe[:_MAX_COMPONENT].rstrip(". ")
    ext = (ext or "png").lower().lstrip(".")
    return f"{sort:0{width}d}_{safe}.{ext}"
