"""주문→발주 모듈 모델."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class OrderStatus(str, Enum):
    RECEIVED = "received"
    PENDING_APPROVAL = "pending_approval"  # 가드 미통과 → 사람 승인 대기
    AMAZON_ORDERED = "amazon_ordered"      # 자동발주 완료
    SHIPPED = "shipped"
    CUSTOMS = "customs"
    DELIVERED = "delivered"
    REFUND_REQUESTED = "refund_requested"
    REFUNDED = "refunded"


class GuardAction(str, Enum):
    AUTO_ORDER = "auto_order"              # 수익 OK + 재고 OK → 자동발주
    APPROVAL_REQUIRED = "approval_required"  # 품절/적자/박한 마진 → 사람 검토


@dataclass(frozen=True)
class OrderContext:
    """주문을 원본·판매가에 연결하는 정보 (실서비스는 listings/orders 조인에서 옴)."""

    source_id: str
    currency: str               # "USD"
    hs_code: str | None
    channel: str                # "naver"
    sale_price_krw: Decimal     # 고객이 결제한 판매가(고정)


@dataclass(frozen=True)
class OrderGuardResult:
    action: GuardAction
    reason: str
    observed_price: Decimal     # 이번에 관측한 원본가
    profit_krw: Decimal | None = None  # 현재 매입가 기준 예상 실수익
    margin_rate: Decimal | None = None


@dataclass(frozen=True)
class FulfillmentResult:
    """발주 결과 — 자동발주 시 외부(Amazon) 주문번호."""

    fulfillment_id: str
    tracking_no: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class OrderOutcome:
    channel_order_no: str
    status: OrderStatus
    guard: OrderGuardResult
    fulfillment: FulfillmentResult | None = None
