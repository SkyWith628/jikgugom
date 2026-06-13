"""대시보드 레코드 — 저장소(Repository)가 주고받는 평면 데이터.

도메인(jikgugom)과 영속 계층 사이의 DTO. ListingDraft는 발행 재실행에 필요해 함께 보관.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ListingRecord:
    id: str
    title: str
    status: str                      # ready | published | paused | review | blocked | margin_rejected
    note: str
    price_krw: int | None = None
    market_score: int | None = None
    recommendation: str | None = None
    channel_product_no: str | None = None
    # 모니터링용 — 발행된 상품의 원본가/통관 기준 (가격·재고 점검에 필요)
    source_currency: str = "USD"
    hs_code: str | None = None
    baseline_price_usd: str | None = None  # Decimal을 문자열로 보관


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
