"""발주 원장 테스트 — InMemory와 SQL 구현이 같은 계약을 만족하는지.

같은 테스트를 두 구현에 돌려 '원장 교체 가능'을 보증하고, SQL이 프로세스
재시작(=새 인스턴스)을 넘어 멱등 판정을 유지하는지(영속)를 따로 증명한다.
"""

from __future__ import annotations

import pytest

from api.ledger_sql import SqlFulfillmentLedger
from jikgugom.order import (
    FulfillmentRecord,
    FulfillmentStatus,
    InMemoryFulfillmentLedger,
    ManualFulfiller,
)

ADDR = {"zip": "06000"}


@pytest.fixture(params=["memory", "sqlite"])
def ledger(request):
    if request.param == "memory":
        return InMemoryFulfillmentLedger()
    return SqlFulfillmentLedger("sqlite:///:memory:")   # 프로세스 내 임시 DB


def _record(key="O1", fid="FF-001", status=FulfillmentStatus.AWAITING_PURCHASE):
    return FulfillmentRecord(idempotency_key=key, fulfillment_id=fid,
                             source_id="B0X", quantity=1, status=status)


# ── 계약: 양방향 조회 + upsert ───────────────────────────────
def test_save_and_get_by_key(ledger):
    ledger.save(_record())
    got = ledger.get("O1")
    assert got is not None and got.fulfillment_id == "FF-001"
    assert got.status is FulfillmentStatus.AWAITING_PURCHASE


def test_get_by_fulfillment_id(ledger):
    ledger.save(_record())
    got = ledger.get_by_fulfillment_id("FF-001")
    assert got is not None and got.idempotency_key == "O1"


def test_missing_returns_none(ledger):
    assert ledger.get("nope") is None
    assert ledger.get_by_fulfillment_id("FF-NOPE") is None


def test_save_is_upsert(ledger):
    ledger.save(_record())
    rec = ledger.get("O1")
    rec.status = FulfillmentStatus.PURCHASED
    rec.amazon_order_no = "AMZ-9"
    rec.tracking_no = "1Z999"
    ledger.save(rec)
    got = ledger.get_by_fulfillment_id("FF-001")
    assert got.status is FulfillmentStatus.PURCHASED
    assert got.amazon_order_no == "AMZ-9" and got.tracking_no == "1Z999"


# ── ManualFulfiller가 SQL 원장 위에서 멱등을 지키는지 ────────
def test_manual_fulfiller_idempotent_over_ledger(ledger):
    f = ManualFulfiller(ledger)
    first = f.place_order("B0X", 1, ADDR, idempotency_key="ORD-7")
    second = f.place_order("B0X", 1, ADDR, idempotency_key="ORD-7")  # 재시도
    assert first.fulfillment_id == second.fulfillment_id
    assert ledger.get("ORD-7") is not None


# ── SQL 영속: 새 인스턴스(=재시작)가 멱등키를 읽는다 ──────────
def test_sql_persists_across_instances(tmp_path):
    url = f"sqlite:///{tmp_path / 'ledger.db'}"
    f = ManualFulfiller(SqlFulfillmentLedger(url))
    res = f.place_order("B0X", 1, ADDR, idempotency_key="ORD-7")
    f.confirm_purchase(res.fulfillment_id, "AMZ-112-9", tracking_no="1Z999")

    # 재시작 모사: 같은 파일을 가리키는 새 원장/발주기
    reopened = ManualFulfiller(SqlFulfillmentLedger(url))
    again = reopened.place_order("B0X", 1, ADDR, idempotency_key="ORD-7")
    assert again.fulfillment_id == res.fulfillment_id     # 재매입 아님
    assert again.message == FulfillmentStatus.PURCHASED.value
    assert again.tracking_no == "1Z999"
