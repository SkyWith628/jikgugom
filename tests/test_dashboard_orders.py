"""대시보드 발주 HITL 흐름 — 승인 → 매입 대기 → 매입 확정.

서비스 계층에서 반자동(HITL) 생애주기와 멱등성이 지켜지는지 검증한다.
원장·저장소는 인메모리(DATABASE_URL=memory)로 두어 외부 의존 없이 돈다.
"""

from __future__ import annotations

import pytest

from api.repository import InMemoryRepository
from api.service import DashboardService


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "memory")   # 원장도 인메모리
    return DashboardService(InMemoryRepository())   # 시드(소싱+주문) 자동 실행


def _first_pending(service) -> str:
    pending = [o for o in service.repo.list_orders() if o.status == "pending_approval"]
    assert pending, "시드된 대기 주문이 있어야 한다"
    return pending[0].id


def test_approve_moves_to_awaiting_purchase(service):
    oid = _first_pending(service)
    rec = service.approve_order(oid)
    assert rec.status == "awaiting_purchase"
    assert rec.fulfillment_id and rec.fulfillment_id.startswith("FF-")


def test_confirm_purchase_records_amazon_order(service):
    oid = _first_pending(service)
    service.approve_order(oid)
    rec = service.confirm_purchase(oid, "AMZ-112-9", tracking_no="1Z999")
    assert rec.status == "purchased"
    assert rec.amazon_order_no == "AMZ-112-9" and rec.tracking_no == "1Z999"


def test_confirm_before_approve_rejected(service):
    oid = _first_pending(service)
    with pytest.raises(ValueError):   # 아직 발주 승인 전 → 매입 확정 불가
        service.confirm_purchase(oid, "AMZ-1")


def test_approve_is_idempotent(service):
    """승인 버튼 중복 클릭에도 같은 발주ID(원장 한 줄, 이중결제 없음)."""
    oid = _first_pending(service)
    first = service.approve_order(oid)
    second = service.approve_order(oid)
    assert first.fulfillment_id == second.fulfillment_id


# ── 멀티채널 동시등록 ────────────────────────────────────────
def test_approve_listing_fans_out_to_all_channels(service):
    ready = [l for l in service.repo.list_listings() if l.status == "ready"]
    assert ready, "발행 대기(ready) 상품이 있어야 한다"
    lid = ready[0].id
    rec = service.approve_listing(lid)

    assert rec.status == "published"
    pubs = {p.channel: p for p in service.repo.list_publications(lid)}
    assert set(pubs) == {"naver", "coupang"}          # 두 채널 모두 발행 기록
    assert pubs["naver"].status == "listed" and pubs["coupang"].status == "listed"
    assert pubs["naver"].channel_product_no.startswith("NV")
    assert pubs["coupang"].channel_product_no.startswith("CP")
    # 모니터 키는 primary(naver) 상품번호
    assert rec.channel_product_no == pubs["naver"].channel_product_no
