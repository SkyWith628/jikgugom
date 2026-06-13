"""모니터 워커 테스트 — 품절/급등/리프라이싱/재개 판정 + 부수효과."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from sourcing_agent.compliance import ComplianceEngine, CustomsType
from sourcing_agent.margin import MarginEngine
from sourcing_agent.models import AvailabilitySnapshot
from sourcing_agent.monitor import ListingState, MonitorAction, MonitorWorker
from sourcing_agent.monitor.worker import MonitorConfig
from tests.fakes import FakeChannelAdapter, FakeSourceAdapter, make_source_product

FX = Decimal("1380")
BASE_USD = Decimal("20.00")


@pytest.fixture(scope="module")
def margin() -> MarginEngine:
    return MarginEngine()


@pytest.fixture(scope="module")
def resolver():
    return ComplianceEngine().customs_type_for


def _baseline_price_krw(margin: MarginEngine) -> Decimal:
    from sourcing_agent.compliance.models import ComplianceResult, Verdict
    p = make_source_product(price=BASE_USD)
    c = ComplianceResult(Verdict.PASS, [], customs_type=CustomsType.LIST)
    return margin.quote(p, c, fx_rate=FX).sale_price_krw


def _state(margin, *, paused=False) -> ListingState:
    return ListingState(
        channel="naver", channel_product_no="NV000001", source_id="B0X",
        baseline_price=BASE_USD, currency="USD", hs_code="8518.30",
        current_price_krw=_baseline_price_krw(margin), is_paused=paused,
    )


def _snap(price: Decimal, *, in_stock=True) -> AvailabilitySnapshot:
    return AvailabilitySnapshot("B0X", price, "USD", in_stock, datetime(2026, 6, 13))


def _worker(margin, resolver, *, source=None, channel=None, cfg=None) -> MonitorWorker:
    return MonitorWorker(
        source or FakeSourceAdapter([make_source_product("B0X", price=BASE_USD)]),
        channel or FakeChannelAdapter(),
        margin, resolver, cfg,
    )


def test_stable_no_change(margin, resolver):
    w = _worker(margin, resolver)
    d = w.decide(_state(margin), _snap(BASE_USD))
    assert d.action is MonitorAction.NONE and d.reason == "stable"


def test_out_of_stock_pauses(margin, resolver):
    w = _worker(margin, resolver)
    d = w.decide(_state(margin), _snap(BASE_USD, in_stock=False))
    assert d.action is MonitorAction.PAUSE and d.reason == "out_of_stock"


def test_price_spike_pauses(margin, resolver):
    w = _worker(margin, resolver)
    d = w.decide(_state(margin), _snap(Decimal("22.50")))  # +12.5%
    assert d.action is MonitorAction.PAUSE and d.reason == "source_price_spike"


def test_price_drop_reprices_lower(margin, resolver):
    w = _worker(margin, resolver)
    state = _state(margin)
    d = w.decide(state, _snap(Decimal("15.00")))  # -25%
    assert d.action is MonitorAction.REPRICE
    assert d.new_price_krw < state.current_price_krw


def test_recovered_resumes(margin, resolver):
    w = _worker(margin, resolver)
    d = w.decide(_state(margin, paused=True), _snap(BASE_USD))
    assert d.action is MonitorAction.RESUME and d.new_price_krw is not None


def test_margin_floor_pauses(margin, resolver):
    w = _worker(margin, resolver, cfg=MonitorConfig(min_margin_rate=Decimal("0.99")))
    d = w.decide(_state(margin), _snap(BASE_USD))
    assert d.action is MonitorAction.PAUSE and d.reason == "margin_below_floor"


# ── run(): 부수효과가 채널 어댑터에 적용되는지 ──────────────
def test_run_applies_pause_on_out_of_stock(margin, resolver):
    src = FakeSourceAdapter([make_source_product("B0X", price=BASE_USD)])
    src.set_out_of_stock("B0X")
    ch = FakeChannelAdapter()
    w = _worker(margin, resolver, source=src, channel=ch)
    w.run([_state(margin)])
    assert "NV000001" in ch.paused


def test_run_applies_reprice(margin, resolver):
    src = FakeSourceAdapter([make_source_product("B0X", price=Decimal("15.00"))])
    ch = FakeChannelAdapter()
    w = _worker(margin, resolver, source=src, channel=ch)
    [d] = w.run([_state(margin)])
    assert d.action is MonitorAction.REPRICE
    assert ch.prices["NV000001"] == d.new_price_krw


def test_run_resume_unpauses_and_prices(margin, resolver):
    src = FakeSourceAdapter([make_source_product("B0X", price=BASE_USD)])
    ch = FakeChannelAdapter()
    ch.paused.add("NV000001")
    w = _worker(margin, resolver, source=src, channel=ch)
    [d] = w.run([_state(margin, paused=True)])
    assert d.action is MonitorAction.RESUME
    assert "NV000001" not in ch.paused
    assert ch.prices["NV000001"] == d.new_price_krw
