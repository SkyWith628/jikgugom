"""인메모리 저장소 — 대시보드 상태(상품/주문)를 보관.

[왜 인메모리] DB(PostgreSQL)는 Phase 3 갭. 대시보드를 '지금' 띄우려고 Repository를
추상화해 메모리로 시작 → 추후 DB 구현체로 교체(어댑터 패턴 재사용).
서버 재시작하면 초기화된다(데모 목적).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jikgugom.models import ListingDraft


@dataclass
class ListingRecord:
    id: str
    title: str
    status: str                      # ready | published | review | blocked | margin_rejected
    note: str
    price_krw: int | None = None
    market_score: int | None = None
    recommendation: str | None = None
    channel_product_no: str | None = None


@dataclass
class OrderRecord:
    id: str
    product_id: str
    quantity: int
    buyer: str
    status: str                      # pending_approval | amazon_ordered | rejected
    guard_action: str                # auto_order | approval_required
    guard_reason: str
    profit_krw: int | None = None
    fulfillment_id: str | None = None


@dataclass
class Store:
    listings: dict[str, ListingRecord] = field(default_factory=dict)
    orders: dict[str, OrderRecord] = field(default_factory=dict)
    drafts: dict[str, ListingDraft] = field(default_factory=dict)  # 발행용 내부 보관

    def reset(self) -> None:
        self.listings.clear()
        self.orders.clear()
        self.drafts.clear()
