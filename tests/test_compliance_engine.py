"""컴플라이언스 엔진 테스트 — COMPLIANCE_FILTER.md §6 엣지 케이스 고정."""

from __future__ import annotations

from decimal import Decimal

import pytest

from sourcing_agent.compliance import ComplianceEngine, CustomsType, Verdict
from tests.fakes import make_source_product


@pytest.fixture(scope="module")
def engine() -> ComplianceEngine:
    return ComplianceEngine()  # 실제 rules/*.yaml 로드


def test_pass_normal_item(engine):
    p = make_source_product(
        title="Stainless Steel Water Bottle", description="500ml insulated",
        category_path=["Home", "Kitchen"], price=Decimal("12.00"), brand="Acme",
        hs_code="9617.00",
    )
    r = engine.evaluate(p)
    assert r.verdict is Verdict.PASS and r.reasons == []
    assert r.customs_type is CustomsType.LIST


def test_block_prohibited_keyword_short_circuits(engine):
    p = make_source_product(title="Prescription medicine refill",
                            category_path=["Health"], hs_code="3004.90")
    r = engine.evaluate(p)
    assert r.verdict is Verdict.BLOCK
    assert r.reasons[0].rule_id == "PROHIBITED_ITEM"
    assert len(r.reasons) == 1  # 단락: 사유 1건만


def test_block_prohibited_category(engine):
    p = make_source_product(title="Folding knife", category_path=["Weapons"])
    r = engine.evaluate(p)
    assert r.verdict is Verdict.BLOCK
    assert r.customs_type is CustomsType.PROHIBITED


def test_block_kc_required_charger(engine):
    p = make_source_product(category_path=["Electronics", "Chargers"])  # KC=block
    r = engine.evaluate(p)
    assert r.verdict is Verdict.BLOCK
    assert r.requires_kc is True
    assert r.reasons[0].rule_id == "KC_REQUIRED"


def test_block_banned_keyword_case_insensitive(engine):
    p = make_source_product(title="Pain relief patch FDA approved",
                            category_path=["Home"], hs_code="3005.10")
    r = engine.evaluate(p)
    assert r.verdict is Verdict.BLOCK
    assert r.reasons[0].rule_id == "BANNED_KEYWORD"


def test_block_counterfeit_brand(engine):
    p = make_source_product(title="Running shoes", brand="Nike",
                            category_path=["Shoes"], hs_code="6404.11")
    r = engine.evaluate(p)
    assert r.verdict is Verdict.BLOCK
    assert r.reasons[0].rule_id == "COUNTERFEIT_BRAND"


def test_review_power_bank(engine):
    p = make_source_product(title="20000mAh Power Bank",
                            category_path=["Electronics", "Power Banks"])  # KC=review
    r = engine.evaluate(p)
    assert r.verdict is Verdict.REVIEW
    assert any(x.rule_id == "KC_REQUIRED" for x in r.reasons)
    assert r.requires_kc is True


def test_review_hs_undetermined(engine):
    p = make_source_product(title="Novelty gadget thing",
                            category_path=["Misc"], hs_code=None, brand="Acme")
    r = engine.evaluate(p)
    assert r.verdict is Verdict.REVIEW
    assert any(x.rule_id == "HS_UNDETERMINED" for x in r.reasons)


def test_review_over_clearance_limit(engine):
    p = make_source_product(title="Premium headphones",
                            category_path=["Headphones"], price=Decimal("350.00"))
    r = engine.evaluate(p)
    assert r.verdict is Verdict.REVIEW
    assert r.customs_type is CustomsType.GENERAL
    assert any(x.rule_id == "PRICE_OUT_OF_RANGE" for x in r.reasons)


def test_empty_inputs_do_not_crash(engine):
    p = make_source_product(title="", description="", brand=None,
                            category_path=[], hs_code=None, price=Decimal("5"))
    r = engine.evaluate(p)
    assert r.verdict in (Verdict.PASS, Verdict.REVIEW)  # 크래시 없이 판정


def test_result_invariant_block_requires_reason():
    """엔진 버그 가드: BLOCK/REVIEW인데 사유가 비면 즉시 예외."""
    from sourcing_agent.compliance.models import ComplianceResult

    with pytest.raises(ValueError):
        ComplianceResult(verdict=Verdict.BLOCK, reasons=[])
