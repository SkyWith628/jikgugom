"""샘플 인메모리 어댑터/카탈로그 — 데모·API가 키 없이 도는 데 쓰는 더미 데이터.

실서비스는 SampleSource→AmazonRainforestAdapter, SampleChannel→NaverSmartstoreAdapter로 교체.
(테스트용 Fake와 달리, 이건 '데모/시드 데이터'로 패키지에 포함된다.)
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sourcing_agent.adapters.base import ChannelAdapter, SourceAdapter
from sourcing_agent.models import (
    AvailabilitySnapshot,
    ChannelCategory,
    PublishResult,
    PublishStatus,
    SourceProduct,
)
from sourcing_agent.order.models import FulfillmentResult

SAMPLE_CATALOG = [
    SourceProduct("amazon", "B01", "Wireless Earbuds", "Bluetooth 5.3 earbuds with charging case",
                  ["Best", "Headphones"], Decimal("29"), "USD",
                  ["https://amazon.com/1.jpg"], brand="Acme", hs_code="8518.30",
                  attributes={"rating": 4.7, "review_count": 900}),
    SourceProduct("amazon", "B02", "USB Wall Charger", "65W GaN fast charger",
                  ["Best", "Chargers"], Decimal("18"), "USD",
                  ["https://amazon.com/2.jpg"], attributes={"rating": 4.5, "review_count": 500}),
    SourceProduct("amazon", "B03", "Stainless Steel Water Bottle", "Insulated 500ml vacuum bottle",
                  ["Best", "Kitchen"], Decimal("14"), "USD",
                  ["https://amazon.com/3.jpg"], hs_code="9617.00",
                  attributes={"rating": 4.3, "review_count": 210}),
    SourceProduct("amazon", "B04", "Nike Running Shoes", "Lightweight runners",
                  ["Best", "Shoes"], Decimal("40"), "USD",
                  ["https://amazon.com/4.jpg"], brand="Nike", hs_code="6404.11",
                  attributes={"rating": 4.6, "review_count": 1500}),
    SourceProduct("amazon", "B05", "Generic Phone Holder", "Desk stand",
                  ["Best", "Accessories"], Decimal("9"), "USD",
                  ["https://amazon.com/5.jpg"], hs_code="3926.90",
                  attributes={"rating": 2.1, "review_count": 8}),
]


class SampleSource(SourceAdapter):
    name = "amazon"

    def __init__(self, catalog=None) -> None:
        self._catalog = catalog or SAMPLE_CATALOG
        self._by_id = {p.source_id: p for p in self._catalog}

    def fetch_bestsellers(self, category, *, limit=50):
        hit = [p for p in self._catalog if category in p.category_path]
        return (hit or self._catalog)[:limit]

    def get_product(self, source_id):
        return self._by_id[source_id]

    def check_availability(self, source_id):
        p = self._by_id[source_id]
        return AvailabilitySnapshot(source_id, p.price, p.currency, True,
                                    datetime.now(timezone.utc))


class SampleChannel(ChannelAdapter):
    name = "naver"

    def __init__(self) -> None:
        self.published: dict = {}
        self._seq = 0

    def map_category(self, path):
        return ChannelCategory("50000123", "/".join(path), 0.9)

    def publish(self, draft):
        self._seq += 1
        no = f"NV{self._seq:06d}"
        self.published[no] = draft
        return PublishResult(PublishStatus.LISTED, no)

    def update_price(self, no, price): ...
    def pause(self, no): ...
    def resume(self, no): ...
    def fetch_orders(self, *, since=None): return []


class SampleFulfiller:
    name = "sample-amazon"

    def place_order(self, source_id, quantity, shipping_address):
        return FulfillmentResult(f"AMZ-{source_id}", message="placed (demo)")

    def track_shipment(self, fulfillment_id):
        return "shipped"
