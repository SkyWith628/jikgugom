"""마진엔진 테스트 — 비용 분해 정확성 + 통관유형 분기 + 가드."""

from __future__ import annotations

from decimal import Decimal

import pytest

from sourcing_agent.compliance.models import ComplianceResult, CustomsType, Reason, Verdict
from sourcing_agent.margin import MarginEngine
from tests.fakes import make_source_product


@pytest.fixture(scope="module")
def engine() -> MarginEngine:
    return MarginEngine()


def _pass(customs: CustomsType, hs_code: str | None = None) -> ComplianceResult:
    if customs is CustomsType.GENERAL:
        return ComplianceResult(Verdict.REVIEW, [Reason("X", "general")],
                                customs_type=customs, hs_code=hs_code)
    return ComplianceResult(Verdict.PASS, [], customs_type=customs, hs_code=hs_code)


def test_list_clearance_is_duty_free(engine):
    p = make_source_product(price=Decimal("20.00"))  # USD
    q = engine.quote(p, _pass(CustomsType.LIST), fx_rate=Decimal("1380"))
    assert q.breakdown.duty_krw == 0
    assert q.breakdown.import_vat_krw == 0
    # 상품원가 = 20 * 1380 * 1.05 = 28,980
    assert q.breakdown.product_cost_krw == Decimal("28980")


def test_general_clearance_applies_duty_and_vat(engine):
    p = make_source_product(price=Decimal("300.00"))
    q = engine.quote(p, _pass(CustomsType.GENERAL, hs_code="8518.30"), fx_rate=Decimal("1380"))
    assert q.breakdown.duty_krw > 0
    assert q.breakdown.import_vat_krw > 0
    assert q.customs_type == "general"


def test_general_more_expensive_than_list(engine):
    """동일 상품이면 일반통관(관세+부가세)이 목록통관보다 비싸야 한다."""
    p = make_source_product(price=Decimal("100.00"))
    list_q = engine.quote(p, _pass(CustomsType.LIST), fx_rate=Decimal("1380"))
    gen_q = engine.quote(p, _pass(CustomsType.GENERAL, hs_code="8518.30"), fx_rate=Decimal("1380"))
    assert gen_q.sale_price_krw > list_q.sale_price_krw


def test_sale_price_rounded_up_to_100(engine):
    p = make_source_product(price=Decimal("17.33"))
    q = engine.quote(p, _pass(CustomsType.LIST), fx_rate=Decimal("1380"))
    assert q.sale_price_krw % 100 == 0


def test_profit_is_positive_and_close_to_target(engine):
    p = make_source_product(price=Decimal("25.00"))
    q = engine.quote(p, _pass(CustomsType.LIST), fx_rate=Decimal("1380"))
    assert q.profit_krw > 0
    # 올림 때문에 목표 25%보다 약간 높아야(같거나) 한다
    assert q.effective_margin_rate >= Decimal("0.25")


def test_breakdown_sums_consistently(engine):
    p = make_source_product(price=Decimal("50.00"))
    q = engine.quote(p, _pass(CustomsType.GENERAL, hs_code="8504.40"), fx_rate=Decimal("1380"))
    b = q.breakdown
    # 도착원가 = 상품 + 해외배송 + 관세 + 부가세 (반올림 오차 ±1)
    expected_landed = (b.product_cost_krw + b.intl_shipping_krw
                       + b.duty_krw + b.import_vat_krw)
    assert abs(b.landed_cost_krw - expected_landed) <= 1
    expected_final = b.landed_cost_krw + b.domestic_shipping_krw + b.return_reserve_krw
    assert abs(b.final_cost_krw - expected_final) <= 1


def test_prohibited_cannot_be_priced(engine):
    p = make_source_product(price=Decimal("10"))
    blocked = ComplianceResult(Verdict.BLOCK, [Reason("PROHIBITED_ITEM", "x")],
                               customs_type=CustomsType.PROHIBITED)
    with pytest.raises(ValueError):
        engine.quote(p, blocked)


def test_non_usd_rejected(engine):
    p = make_source_product(price=Decimal("10"), currency="EUR")
    with pytest.raises(NotImplementedError):
        engine.quote(p, _pass(CustomsType.LIST))


def test_zero_price_rejected(engine):
    p = make_source_product(price=Decimal("0"))
    with pytest.raises(ValueError):
        engine.quote(p, _pass(CustomsType.LIST))


def test_unknown_channel_rejected(engine):
    p = make_source_product(price=Decimal("10"))
    with pytest.raises(KeyError):
        engine.quote(p, _pass(CustomsType.LIST), channel="coupang")
