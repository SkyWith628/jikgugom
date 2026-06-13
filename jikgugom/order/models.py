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


class FulfillmentStatus(str, Enum):
    """발주 원장 레코드의 생애주기. Amazon 구매 API 부재 → 반자동(HITL)."""

    AWAITING_PURCHASE = "awaiting_purchase"  # 원장 기록됨, 운영자 실매입 대기
    PURCHASED = "purchased"                  # 운영자가 Amazon 실매입 확정
    SHIPPED = "shipped"
    CUSTOMS = "customs"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


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


@dataclass
class FulfillmentRecord:
    """발주 원장의 한 줄 — 멱등키로 '이 주문 이미 매입했나'를 식별.

    mutable(frozen 아님): 운영자 매입 확정·배송 단계 변화로 status가 갱신된다.
    민감정보(PCCC·결제정보)는 저장하지 않는다 (개인정보보호·로그 금지 원칙).
    """

    idempotency_key: str        # = channel_order_no. 같은 주문은 영원히 한 번만 매입.
    fulfillment_id: str         # 우리 내부 발주 식별자 (멱등키에서 결정론적 파생)
    source_id: str
    quantity: int
    status: FulfillmentStatus
    amazon_order_no: str | None = None  # 운영자가 실매입 후 기록하는 Amazon 주문번호
    tracking_no: str | None = None
