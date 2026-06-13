"""주문→발주 가드 테스트 — 자동발주 / 적자·품절·박한마진 → 승인 큐."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from jikgugom.compliance import ComplianceEngine
from jikgugom.margin import MarginEngine
from jikgugom.models import ChannelOrder
from jikgugom.order import GuardAction, OrderContext, OrderProcessor, OrderStatus
from tests.fakes import FakeFulfiller, FakeSourceAdapter, make_source_product

FX_NOTE = "환율은 기본 config(1380) 사용 — 가드는 기본 환율로 현재가 재평가"


@pytest.fixture(scope="module")
def margin() -> MarginEngine:
    return MarginEngine()


@pytest.fixture(scope="module")
def resolver():
    return ComplianceEngine().customs_type_for


def _order(no="O1", qty=1) -> ChannelOrder:
    return ChannelOrder(
        channel="naver", channel_order_no=no, channel_product_no="NV1",
        quantity=qty, buyer_name="홍길동", buyer_pccc_encrypted="enc::x",
        shipping_address={"zip": "06000"}, ordered_at=datetime(2026, 6, 13),
    )


def _ctx(sale_price="85000", source_id="B0X") -> OrderContext:
    return OrderContext(source_id=source_id, currency="USD", hs_code="8518.30",
                        channel="naver", sale_price_krw=Decimal(sale_price))


def _processor(margin, resolver, *, source_price="29", in_stock=True):
    src = FakeSourceAdapter([make_source_product("B0X", price=Decimal(source_price))])
    if not in_stock:
        src.set_out_of_stock("B0X")
    return OrderProcessor(src, FakeFulfiller(), margin, resolver), src


def test_auto_order_when_profitable(margin, resolver):
    proc, _ = _processor(margin, resolver, source_price="29")  # 팔린가 85,000원이면 충분
    out = proc.process(_order(), _ctx("85000"))
    assert out.status is OrderStatus.AMAZON_ORDERED
    assert out.guard.action is GuardAction.AUTO_ORDER
    assert out.fulfillment.fulfillment_id.startswith("AMZ")


def test_out_of_stock_routes_to_approval(margin, resolver):
    proc, _ = _processor(margin, resolver, in_stock=False)
    out = proc.process(_order(), _ctx("85000"))
    assert out.status is OrderStatus.PENDING_APPROVAL
    assert out.guard.reason == "out_of_stock"
    assert out.fulfillment is None


def test_loss_routes_to_approval(margin, resolver):
    """원본가 급등으로 매입원가 > 판매가면 적자 → 승인 큐."""
    proc, _ = _processor(margin, resolver, source_price="80")  # 원가 급등
    out = proc.process(_order(), _ctx("85000"))                # 낮은 판매가에 팔림
    assert out.status is OrderStatus.PENDING_APPROVAL
    assert out.guard.reason in ("would_sell_at_loss", "margin_below_floor")
    assert out.guard.profit_krw is not None


def test_no_fulfillment_when_approval_required(margin, resolver):
    proc, _ = _processor(margin, resolver, in_stock=False)
    fulfiller = proc._fulfiller
    proc.process(_order(), _ctx())
    assert fulfiller.orders == []          # 승인 필요 시 발주 호출 없음


def test_auto_order_flag_off_holds_for_approval(margin, resolver):
    """auto_order=False면 가드 통과라도 발주 안 하고 승인 대기."""
    proc, _ = _processor(margin, resolver, source_price="29")
    out = proc.process(_order(), _ctx("85000"), auto_order=False)
    assert out.status is OrderStatus.PENDING_APPROVAL
    assert out.guard.action is GuardAction.AUTO_ORDER  # 가드 자체는 통과였음


def test_guard_attaches_profit_estimate(margin, resolver):
    proc, _ = _processor(margin, resolver, source_price="29")
    g = proc.evaluate_guard(_ctx("85000"))
    assert g.profit_krw is not None and g.margin_rate is not None
