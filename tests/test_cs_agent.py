"""CS 에이전트 테스트 — 의도 분류 + 결정론 에스컬레이션 가드(돈/민감→사람)."""

from __future__ import annotations

import pytest

from sourcing_agent.cs import CSAction, CSAgent, CSContext, Intent
from sourcing_agent.cs.tools import search_refund_policy
from sourcing_agent.order.models import OrderStatus


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _ctx(status=OrderStatus.SHIPPED) -> CSContext:
    return CSContext(order_no="O123", order_status=status,
                     tracking_no="123456789", fulfillment_id="AMZ000001")


def test_mock_mode_without_key():
    assert CSAgent().mode == "mock"


def test_order_status_auto_replies():
    r = CSAgent().handle("내 주문 상태 확인해줘", _ctx(OrderStatus.AMAZON_ORDERED))
    assert r.intent is Intent.ORDER_STATUS
    assert r.action is CSAction.AUTO_REPLY and r.escalated is False
    assert "해외 발주 완료" in r.reply


def test_shipping_auto_replies_with_status():
    r = CSAgent().handle("배송 언제 도착하나요?", _ctx(OrderStatus.CUSTOMS))
    assert r.intent is Intent.SHIPPING and r.action is CSAction.AUTO_REPLY
    assert "통관" in r.reply


def test_refund_always_escalates():
    r = CSAgent().handle("이거 환불하고 싶어요", _ctx())
    assert r.intent is Intent.REFUND
    assert r.action is CSAction.ESCALATE and r.escalated is True
    assert r.escalation_reason == "sensitive_intent"
    assert r.policy_snippet is not None          # 담당자 참고용 정책 첨부


def test_complaint_always_escalates():
    r = CSAgent().handle("상품이 파손되어 왔어요 최악이에요", _ctx())
    assert r.intent is Intent.COMPLAINT and r.escalated is True


def test_unknown_escalates_low_confidence():
    r = CSAgent().handle("음 그냥 궁금한게 있는데", _ctx())
    assert r.intent is Intent.UNKNOWN
    assert r.action is CSAction.ESCALATE
    assert r.escalation_reason == "low_confidence"


def test_shipping_uses_fulfiller_when_available():
    from tests.fakes import FakeFulfiller
    r = CSAgent(fulfiller=FakeFulfiller()).handle("송장 추적", _ctx())
    assert "배송 중" in r.reply                   # FakeFulfiller.track_shipment → "shipped"


def test_refund_policy_search_matches():
    assert "불량" in search_refund_policy("상품 불량으로 환불 원해요") or \
           "재발송" in search_refund_policy("상품 불량으로 환불 원해요")
    assert "7일" in search_refund_policy("단순 변심 반품 가능한가요")


def test_deterministic_classification():
    a = CSAgent()
    r1 = a.handle("환불해주세요", _ctx())
    r2 = a.handle("환불해주세요", _ctx())
    assert r1.intent == r2.intent and r1.action == r2.action
