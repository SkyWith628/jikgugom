"""반자동(HITL) 발주 어댑터 — 멱등 원장 기반.

[What] FulfillmentAdapter 실구현. place_order는 '발주 의도'를 멱등 원장에 기록하고
       AWAITING_PURCHASE를 돌려준다. 실매입은 운영자가 confirm_purchase로 확정.
[Why]  Amazon은 제3자 공개 구매 API가 없다. 브라우저 자동결제는 ToS 위반·취약.
       '돈 구간은 사람 게이트' 원칙(프로젝트 일관) + 멱등성(중복결제 방지)을 둘 다
       지키는 정직한 설계. 가드를 통과한 주문만 여기 도달한다(processor가 보장).
[How]  HITL(Human-in-the-Loop): 비가역 지점(실결제)에만 사람을 끼운다. 기록·추적·
       멱등 판정은 전부 자동. 운영자는 '결제 버튼'만 누른다.

흐름:
    place_order(key)  → 원장에 없으면 AWAITING_PURCHASE 기록 / 있으면 기존결과 반환(멱등)
    confirm_purchase  → 운영자가 Amazon 실매입 후 주문번호·송장 기록 → PURCHASED
    update_shipment   → 배송 단계 갱신 (shipped/customs/delivered)
    track_shipment    → 원장의 현재 단계를 원시 문자열로 반환
"""

from __future__ import annotations

import hashlib

from jikgugom.order.fulfiller import FulfillmentAdapter
from jikgugom.order.ledger import FulfillmentLedger, InMemoryFulfillmentLedger
from jikgugom.order.models import (
    FulfillmentRecord,
    FulfillmentResult,
    FulfillmentStatus,
)


class ManualFulfiller(FulfillmentAdapter):
    name = "amazon-manual"

    def __init__(self, ledger: FulfillmentLedger | None = None, *,
                 name: str = "amazon-manual") -> None:
        # 원장 미주입 시 인메모리 기본값 → 키/외부의존 없이 동작
        self._ledger = ledger or InMemoryFulfillmentLedger()
        self.name = name

    # ── 계약 구현 ────────────────────────────────────────────
    def place_order(self, source_id: str, quantity: int,
                    shipping_address: dict, *,
                    idempotency_key: str) -> FulfillmentResult:
        existing = self._ledger.get(idempotency_key)
        if existing is not None:
            return self._result(existing)  # 멱등: 재시도해도 새 매입 없음

        record = FulfillmentRecord(
            idempotency_key=idempotency_key,
            fulfillment_id=self._make_id(idempotency_key),
            source_id=source_id,
            quantity=quantity,
            status=FulfillmentStatus.AWAITING_PURCHASE,
        )
        self._ledger.save(record)
        return self._result(record)

    def track_shipment(self, fulfillment_id: str) -> str:
        return self._require(fulfillment_id).status.value

    # ── 운영자(HITL) 액션 ────────────────────────────────────
    def confirm_purchase(self, fulfillment_id: str, amazon_order_no: str, *,
                         tracking_no: str | None = None) -> FulfillmentResult:
        """운영자가 Amazon에서 실매입을 마친 뒤 주문번호(·송장)를 기록 → PURCHASED."""
        record = self._require(fulfillment_id)
        record.amazon_order_no = amazon_order_no
        record.tracking_no = tracking_no
        record.status = FulfillmentStatus.PURCHASED
        self._ledger.save(record)
        return self._result(record)

    def update_shipment(self, fulfillment_id: str, status: FulfillmentStatus, *,
                        tracking_no: str | None = None) -> FulfillmentResult:
        """배송 단계 갱신 (shipped/customs/delivered)."""
        record = self._require(fulfillment_id)
        record.status = status
        if tracking_no is not None:
            record.tracking_no = tracking_no
        self._ledger.save(record)
        return self._result(record)

    # ── 내부 헬퍼 ────────────────────────────────────────────
    def _require(self, fulfillment_id: str) -> FulfillmentRecord:
        record = self._ledger.get_by_fulfillment_id(fulfillment_id)
        if record is None:
            raise KeyError(f"unknown fulfillment_id: {fulfillment_id}")
        return record

    @staticmethod
    def _result(record: FulfillmentRecord) -> FulfillmentResult:
        return FulfillmentResult(
            fulfillment_id=record.fulfillment_id,
            tracking_no=record.tracking_no,
            message=record.status.value,
        )

    @staticmethod
    def _make_id(idempotency_key: str) -> str:
        """멱등키에서 발주ID를 결정론적으로 파생 → 같은 키=같은 ID(추적 일관)."""
        digest = hashlib.sha1(idempotency_key.encode()).hexdigest()[:12].upper()
        return f"FF-{digest}"
