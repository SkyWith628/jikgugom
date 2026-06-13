"""가격·재고 점검(monitor_sweep) + 스케줄러 테스트 — 영속 listing을 훑어 반영."""

from __future__ import annotations

import pytest

from api.repository import InMemoryRepository
from api.scheduler import MonitorScheduler
from api.service import DashboardService


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)


def _service_with_published() -> DashboardService:
    s = DashboardService(InMemoryRepository())
    s.approve_listing("B01")          # ready → published (모니터 대상)
    return s


def test_sweep_no_change_when_stable():
    s = _service_with_published()
    assert s.monitor_sweep() == []    # 원본 변동 없음 → 변경 0


def test_sweep_pauses_on_out_of_stock():
    s = _service_with_published()
    s._source.set_out_of_stock("B01")
    [chg] = s.monitor_sweep()
    assert chg["id"] == "B01" and chg["action"] == "pause" and chg["reason"] == "out_of_stock"
    assert s.repo.get_listing("B01").status == "paused"


def test_sweep_reprices_on_price_drop():
    s = _service_with_published()
    before = s.repo.get_listing("B01").price_krw
    s._source.set_source_price("B01", "15")     # 원본가 하락(29→15)
    [chg] = s.monitor_sweep()
    assert chg["action"] == "reprice"
    after = s.repo.get_listing("B01").price_krw
    assert after < before and after == chg["new_price_krw"]


def test_sweep_pauses_on_price_spike():
    s = _service_with_published()
    s._source.set_source_price("B01", "45")     # 급등 → 사람 검토(일시중지)
    [chg] = s.monitor_sweep()
    assert chg["action"] == "pause" and chg["reason"] == "source_price_spike"


def test_sweep_resumes_after_recovery():
    s = _service_with_published()
    s._source.set_out_of_stock("B01")
    s.monitor_sweep()                            # paused
    assert s.repo.get_listing("B01").status == "paused"
    s._source.set_out_of_stock("B01", False)     # 재입고
    [chg] = s.monitor_sweep()
    assert chg["action"] == "resume"
    assert s.repo.get_listing("B01").status == "published"


def test_only_published_listings_are_swept():
    s = DashboardService(InMemoryRepository())   # 아무것도 승인 안 함
    s._source.set_out_of_stock("B01")
    assert s.monitor_sweep() == []               # ready 상태는 점검 대상 아님


def test_scheduler_disabled_when_interval_zero():
    s = _service_with_published()
    sched = MonitorScheduler(s, interval_seconds=0)
    sched.start()                                # 예외 없이 비활성
    assert sched.last_run is None


def test_scheduler_tick_records_last_run():
    s = _service_with_published()
    s._source.set_out_of_stock("B01")
    sched = MonitorScheduler(s, interval_seconds=300)
    sched._tick()                                # 1회 실행 모사
    assert sched.last_run is not None and sched.last_run["changed"] == 1
