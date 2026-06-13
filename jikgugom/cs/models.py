"""CS 응대 에이전트 모델."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from jikgugom.order.models import OrderStatus


class Intent(str, Enum):
    ORDER_STATUS = "order_status"   # 주문 상태 문의
    SHIPPING = "shipping"           # 배송/추적 문의
    REFUND = "refund"               # 환불/반품/취소 (민감 → 에스컬레이션)
    COMPLAINT = "complaint"         # 불만/파손 (민감 → 에스컬레이션)
    GENERAL = "general"             # 일반 문의
    UNKNOWN = "unknown"             # 분류 불확실 → 에스컬레이션


class CSAction(str, Enum):
    AUTO_REPLY = "auto_reply"       # 정보성 → 자동 응답
    ESCALATE = "escalate"           # 민감/불확실 → 사람 인계


@dataclass(frozen=True)
class CSContext:
    """응대에 필요한 주문 사실 (실서비스는 DB/어댑터 조회 결과)."""

    order_no: str
    order_status: OrderStatus
    tracking_no: str | None = None
    fulfillment_id: str | None = None


@dataclass(frozen=True)
class CSResponse:
    intent: Intent
    action: CSAction
    reply: str                      # 고객에게 보낼(또는 보류) 응답 초안
    escalated: bool
    mode: str                       # "mock" | "real"
    escalation_reason: str | None = None
    policy_snippet: str | None = None  # 에스컬레이션 시 담당자 참고용
