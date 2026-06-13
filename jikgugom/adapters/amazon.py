"""Amazon 소스 어댑터 — Rainforest API 구현.

1차 소스. Rainforest API(서드파티)로 Amazon US를 조회한다. PA-API/Creators API로
교체해도 SourceAdapter 계약만 지키면 파이프라인은 무변경.

[테스트] 모든 외부 호출은 _request() 단일 메서드를 거친다 → 테스트는 _request를
대체해 네트워크 없이 매핑 로직(_map_*)을 검증한다.
[비밀] api_key는 Secrets Manager에서 주입(코드·깃 금지).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from jikgugom.adapters._http import request_json
from jikgugom.adapters.base import SourceAdapter
from jikgugom.models import AvailabilitySnapshot, SourceProduct

BASE_URL = "https://api.rainforestapi.com/request"


class AmazonRainforestAdapter(SourceAdapter):
    name = "amazon"

    def __init__(self, api_key: str, *, domain: str = "amazon.com",
                 timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._domain = domain
        self._timeout = timeout

    # ── 단일 네트워크 경유점 (테스트는 이걸 대체) ────────────
    def _request(self, params: dict[str, Any]) -> dict:
        return request_json(
            BASE_URL,
            params={"api_key": self._api_key, "amazon_domain": self._domain, **params},
            timeout=self._timeout,
        )

    # ── 계약 구현 ────────────────────────────────────────────
    def fetch_bestsellers(self, category: str, *, limit: int = 50) -> list[SourceProduct]:
        data = self._request({"type": "bestsellers", "category_id": category})
        items = data.get("bestsellers", [])[:limit]
        return [self._map_bestseller(it, category) for it in items]

    def get_product(self, source_id: str) -> SourceProduct:
        data = self._request({"type": "product", "asin": source_id})
        return self._map_product(data["product"])

    def check_availability(self, source_id: str) -> AvailabilitySnapshot:
        data = self._request({"type": "product", "asin": source_id})
        product = data["product"]
        price, currency = self._extract_price(product)
        return AvailabilitySnapshot(
            source_id=source_id,
            price=price,
            currency=currency,
            in_stock=self._extract_in_stock(product),
            captured_at=datetime.now(timezone.utc),
        )

    # ── 매핑 (순수, 테스트 대상) ─────────────────────────────
    @classmethod
    def _map_product(cls, p: dict) -> SourceProduct:
        price, currency = cls._extract_price(p)
        images = [img["link"] for img in p.get("images", []) if img.get("link")]
        if not images and p.get("main_image", {}).get("link"):
            images = [p["main_image"]["link"]]
        return SourceProduct(
            source="amazon",
            source_id=p["asin"],
            title=p.get("title", ""),
            description=cls._description(p),
            category_path=[c["name"] for c in p.get("categories", []) if c.get("name")],
            price=price,
            currency=currency,
            image_urls=images,
            brand=p.get("brand"),
            hs_code=None,
            attributes={
                "rating": p.get("rating", 0),
                "review_count": p.get("ratings_total", 0),
            },
            raw_data=p,
        )

    @staticmethod
    def _map_bestseller(item: dict, category: str) -> SourceProduct:
        # bestsellers 응답은 가벼움(상세 없음) — 상세는 get_product로 보강
        price = item.get("price", {})
        return SourceProduct(
            source="amazon",
            source_id=item["asin"],
            title=item.get("title", ""),
            description="",
            category_path=[category],
            price=Decimal(str(price.get("value", 0))),
            currency=price.get("currency", "USD"),
            image_urls=[item["image"]] if item.get("image") else [],
            attributes={},
            raw_data=item,
        )

    @staticmethod
    def _extract_price(p: dict) -> tuple[Decimal, str]:
        box = p.get("buybox_winner", {}) or {}
        price = box.get("price", {}) or {}
        value = price.get("value")
        return (Decimal(str(value)) if value is not None else Decimal(0),
                price.get("currency", "USD"))

    @staticmethod
    def _extract_in_stock(p: dict) -> bool:
        box = p.get("buybox_winner", {}) or {}
        availability = (box.get("availability", {}) or {}).get("raw", "")
        return bool(box) and "out of stock" not in availability.lower()

    @staticmethod
    def _description(p: dict) -> str:
        if p.get("description"):
            return p["description"]
        bullets = p.get("feature_bullets", [])
        return " ".join(bullets) if bullets else ""
