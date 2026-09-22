"""디시콘 API 응답을 감싸는 자료형."""

from __future__ import annotations

from dataclasses import dataclass, field

IMAGE_BASE = "https://dcimg5.dcinside.com/dccon.php?no="


def image_url(path: str) -> str:
    return IMAGE_BASE + path


@dataclass(frozen=True)
class DcconItem:
    """패키지 안의 낱개 디시콘."""

    idx: int
    title: str
    sort: int
    ext: str
    path: str

    @property
    def url(self) -> str:
        return image_url(self.path)

    @classmethod
    def from_api(cls, row: dict) -> "DcconItem":
        return cls(
            idx=int(row.get("idx") or 0),
            title=(row.get("title") or "").strip(),
            sort=int(row.get("sort") or 0),
            # 서버가 ext를 주므로 바이트를 뜯어볼 필요가 없다.
            ext=(row.get("ext") or "png").lower().lstrip("."),
            path=row.get("path") or "",
        )


@dataclass
class Package:
    """package_detail 응답 전체."""

    idx: int
    title: str
    description: str = ""
    seller: str = ""
    price: str = "0"
    reg_date: str = ""
    main_img_path: str = ""
    list_img_path: str = ""
    items: list[DcconItem] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def main_url(self) -> str:
        return image_url(self.main_img_path) if self.main_img_path else ""

    @classmethod
    def from_api(cls, payload: dict) -> "Package":
        info = payload.get("info") or {}
        items = [DcconItem.from_api(r) for r in (payload.get("detail") or [])]
        items.sort(key=lambda i: i.sort)
        return cls(
            idx=int(info.get("package_idx") or 0),
            title=(info.get("title") or "").strip(),
            description=(info.get("description") or "").strip(),
            seller=(info.get("seller_name") or "").strip(),
            price=str(info.get("price") or "0"),
            reg_date=info.get("reg_date") or "",
            main_img_path=info.get("main_img_path") or "",
            list_img_path=info.get("list_img_path") or "",
            items=items,
            tags=[t.get("tag", "") for t in (payload.get("tags") or []) if t.get("tag")],
        )


@dataclass(frozen=True)
class PackageBrief:
    """검색 결과나 인기 목록의 한 줄. 상세를 아직 안 받은 상태."""

    idx: int
    title: str
    seller: str = ""
    thumb_url: str = ""
