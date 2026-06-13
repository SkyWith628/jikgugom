"""인메모리 Fake 어댑터 — 외부 API 없이 계약을 검증/시뮬레이션하기 위한 더미 구현.

[What] SourceAdapter/ChannelAdapter 계약을 실제 네트워크 없이 만족하는 가짜 구현.
[Why]  구현 전 '계약이 지켜지는가'를 테스트로 고정 + 파이프라인 통합 테스트의 받침대.
[How]  포트-어댑터에서 테스트 더블(test double)을 쓰는 정석. CI에서 빠르고 결정론적.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sourcing_agent.adapters.base import ChannelAdapter, SourceAdapter
from sourcing_agent.models import (
    AvailabilitySnapshot,
    ChannelCategory,
    ChannelOrder,
    ListingDraft,
    PublishResult,
    PublishStatus,
    SourceProduct,
)


def make_source_product(source_id: str = "B0TEST001", **over) -> SourceProduct:
    """테스트용 SourceProduct 팩토리 (필요한 필드만 override)."""
    base = dict(
        source="fake",
        source_id=source_id,
        title="Wireless Charger 15W",
        description="Fast charging pad",
        category_path=["Electronics", "Chargers"],
        price=Decimal("19.99"),
        currency="USD",
        image_urls=["https://example.com/a.jpg"],
        brand="Acme",
        hs_code=None,
        attributes={},
        raw_data={},
    )
    base.update(over)
    return SourceProduct(**base)  # type: ignore[arg-type]


class FakeSourceAdapter(SourceAdapter):
    """시드된 상품 목록을 반환하는 인메모리 소스."""

    name = "fake"

    def __init__(self, products: list[SourceProduct] | None = None) -> None:
        self._products = {p.source_id: p for p in (products or [make_source_product()])}
        self._in_stock: dict[str, bool] = {sid: True for sid in self._products}

    def fetch_bestsellers(self, category: str, *, limit: int = 50) -> list[SourceProduct]:
        items = [p for p in self._products.values() if category in p.category_path]
        return items[:limit] if items else list(self._products.values())[:limit]

    def get_product(self, source_id: str) -> SourceProduct:
        return self._products[source_id]

    def check_availability(self, source_id: str) -> AvailabilitySnapshot:
        p = self._products[source_id]
        return AvailabilitySnapshot(
            source_id=source_id,
            price=p.price,
            currency=p.currency,
            in_stock=self._in_stock[source_id],
            captured_at=datetime(2026, 6, 13, 12, 0, 0),
        )

    # 테스트 조작용 헬퍼 (계약 외)
    def set_out_of_stock(self, source_id: str) -> None:
        self._in_stock[source_id] = False


class FakeChannelAdapter(ChannelAdapter):
    """발행/가격/일시중지/주문을 메모리에 기록하는 인메모리 채널."""

    name = "fake"

    def __init__(self, seeded_orders: list[ChannelOrder] | None = None) -> None:
        self.published: dict[str, ListingDraft] = {}
        self.prices: dict[str, Decimal] = {}
        self.paused: set[str] = set()
        self._orders = seeded_orders or []
        self._seq = 0

    def map_category(self, source_category_path: list[str]) -> ChannelCategory:
        return ChannelCategory(
            channel_category_id="50000123",
            channel_category_name="/".join(source_category_path),
            confidence=0.9,
        )

    def publish(self, draft: ListingDraft) -> PublishResult:
        # 멱등: 같은 product_id 재발행 시 기존 번호 반환
        for no, d in self.published.items():
            if d.product_id == draft.product_id:
                return PublishResult(PublishStatus.LISTED, no, "already listed")
        self._seq += 1
        no = f"NV{self._seq:06d}"
        self.published[no] = draft
        self.prices[no] = draft.price_krw
        return PublishResult(PublishStatus.LISTED, no)

    def update_price(self, channel_product_no: str, price_krw: Decimal) -> None:
        self.prices[channel_product_no] = price_krw

    def pause(self, channel_product_no: str) -> None:
        self.paused.add(channel_product_no)

    def resume(self, channel_product_no: str) -> None:
        self.paused.discard(channel_product_no)

    def fetch_orders(self, *, since: str | None = None) -> list[ChannelOrder]:
        return list(self._orders)


class FakeFulfiller:
    """인메모리 발주 어댑터 — 발주를 기록만 (실제 매입 없음)."""

    name = "fake-amazon"

    def __init__(self) -> None:
        self.orders: list[tuple[str, int, dict]] = []
        self._seq = 0

    def place_order(self, source_id: str, quantity: int, shipping_address: dict):
        from sourcing_agent.order.models import FulfillmentResult
        self._seq += 1
        self.orders.append((source_id, quantity, shipping_address))
        return FulfillmentResult(fulfillment_id=f"AMZ{self._seq:06d}",
                                 tracking_no=None, message="placed")

    def track_shipment(self, fulfillment_id: str) -> str:
        return "shipped"
