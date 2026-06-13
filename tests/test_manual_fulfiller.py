"""반자동 발주(ManualFulfiller) 테스트 — 멱등성 + HITL 생애주기.

핵심 불변식: 같은 멱등키로 몇 번을 발주해도 실매입은 단 한 번(이중결제 금지).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from jikgugom.compliance import ComplianceEngine
from jikgugom.margin import MarginEngine
from jikgugom.models import ChannelOrder
from jikgugom.order import (
    FulfillmentStatus,
    InMemoryFulfillmentLedger,
    ManualFulfiller,
    OrderContext,
    OrderProcessor,
    OrderStatus,
)
from tests.fakes import FakeSourceAdapter, make_source_product

ADDR = {"zip": "06000"}


# ── 멱등성 (핵심) ────────────────────────────────────────────
def test_place_order_records_awaiting_purchase():
    f = ManualFulfiller()
    res = f.place_order("B0X", 1, ADDR, idempotency_key="O1")
    assert res.fulfillment_id.startswith("FF-")
    assert res.message == FulfillmentStatus.AWAITING_PURCHASE.value
    assert f.track_shipment(res.fulfillment_id) == "awaiting_purchase"


def test_same_key_is_idempotent_no_second_purchase():
    ledger = InMemoryFulfillmentLedger()
    f = ManualFulfiller(ledger)

    first = f.place_order("B0X", 1, ADDR, idempotency_key="O1")
    second = f.place_order("B0X", 1, ADDR, idempotency_key="O1")  # 재시도

    assert first.fulfillment_id == second.fulfillment_id     # 같은 발주
    assert ledger.get("O1") is not None
    # 같은 키는 원장에 한 줄만 (이중결제 없음)
    assert ledger.get_by_fulfillment_id(first.fulfillment_id) is ledger.get("O1")


def test_idempotency_survives_after_purchase_confirmed():
    """매입 확정 후 재요청이 와도 다시 매입하지 않고 확정 상태를 반환."""
    f = ManualFulfiller()
    first = f.place_order("B0X", 1, ADDR, idempotency_key="O1")
    f.confirm_purchase(first.fulfillment_id, "AMZ-112-9", tracking_no="1Z999")

    again = f.place_order("B0X", 1, ADDR, idempotency_key="O1")
    assert again.fulfillment_id == first.fulfillment_id
    assert again.message == FulfillmentStatus.PURCHASED.value  # 재매입 아님
    assert again.tracking_no == "1Z999"


def test_different_keys_create_distinct_orders():
    f = ManualFulfiller()
    a = f.place_order("B0X", 1, ADDR, idempotency_key="O1")
    b = f.place_order("B0X", 1, ADDR, idempotency_key="O2")
    assert a.fulfillment_id != b.fulfillment_id


# ── HITL 생애주기 ────────────────────────────────────────────
def test_confirm_purchase_advances_status():
    f = ManualFulfiller()
    res = f.place_order("B0X", 1, ADDR, idempotency_key="O1")
    out = f.confirm_purchase(res.fulfillment_id, "AMZ-112-9", tracking_no="1Z999")
    assert out.message == "purchased"
    assert out.tracking_no == "1Z999"


def test_update_shipment_tracks_phases():
    f = ManualFulfiller()
    res = f.place_order("B0X", 1, ADDR, idempotency_key="O1")
    f.confirm_purchase(res.fulfillment_id, "AMZ-1")
    f.update_shipment(res.fulfillment_id, FulfillmentStatus.SHIPPED, tracking_no="1Z1")
    assert f.track_shipment(res.fulfillment_id) == "shipped"
    f.update_shipment(res.fulfillment_id, FulfillmentStatus.DELIVERED)
    assert f.track_shipment(res.fulfillment_id) == "delivered"


def test_unknown_fulfillment_id_raises():
    f = ManualFulfiller()
    with pytest.raises(KeyError):
        f.track_shipment("FF-NOPE")
    with pytest.raises(KeyError):
        f.confirm_purchase("FF-NOPE", "AMZ-1")


# ── processor 통합: 가드 통과 → 멱등 발주 ────────────────────
def _order(no="O1", qty=1) -> ChannelOrder:
    return ChannelOrder(
        channel="naver", channel_order_no=no, channel_product_no="NV1",
        quantity=qty, buyer_name="홍길동", buyer_pccc_encrypted="enc::x",
        shipping_address=ADDR, ordered_at=datetime(2026, 6, 13),
    )


def _ctx(sale="85000") -> OrderContext:
    return OrderContext(source_id="B0X", currency="USD", hs_code="8518.30",
                        channel="naver", sale_price_krw=Decimal(sale))


def test_processor_uses_channel_order_no_as_idempotency_key():
    src = FakeSourceAdapter([make_source_product("B0X", price=Decimal("29"))])
    ledger = InMemoryFulfillmentLedger()
    proc = OrderProcessor(src, ManualFulfiller(ledger), MarginEngine(),
                          ComplianceEngine().customs_type_for)

    out1 = proc.process(_order("ORD-7"), _ctx())
    out2 = proc.process(_order("ORD-7"), _ctx())  # 같은 채널주문 재처리

    assert out1.status is OrderStatus.AMAZON_ORDERED
    assert out1.fulfillment.fulfillment_id == out2.fulfillment.fulfillment_id
    assert ledger.get("ORD-7") is not None  # 멱등키=channel_order_no로 기록
