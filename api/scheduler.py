"""스케줄러 — 가격·재고 점검(monitor_sweep)을 주기 실행.

[왜 APScheduler] 단일 인스턴스 인프로세스 스케줄러(브로커 0). 잡 자체(monitor_sweep)는
broker-agnostic이라 추후 Celery Beat로 그대로 옮길 수 있다.
[설정] MONITOR_INTERVAL_SECONDS=0 이면 자동 실행 끔(수동 엔드포인트만).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from api.service import DashboardService

log = logging.getLogger("jikgugom.scheduler")
DEFAULT_INTERVAL = int(os.getenv("MONITOR_INTERVAL_SECONDS", "300"))


class MonitorScheduler:
    def __init__(self, service: DashboardService, interval_seconds: int = DEFAULT_INTERVAL) -> None:
        self._service = service
        self._interval = interval_seconds
        self._scheduler = BackgroundScheduler(daemon=True)
        self.last_run: dict | None = None

    def start(self) -> None:
        if self._interval <= 0:
            log.info("monitor scheduler disabled (interval<=0)")
            return
        self._scheduler.add_job(self._tick, "interval", seconds=self._interval,
                                id="monitor_sweep", max_instances=1, coalesce=True)
        self._scheduler.start()
        log.info("monitor scheduler started (every %ss)", self._interval)

    def _tick(self) -> None:
        changes = self._service.monitor_sweep()
        self.last_run = {"at": datetime.now(timezone.utc).isoformat(),
                         "changed": len(changes), "changes": changes}
        if changes:
            log.info("monitor sweep: %d change(s) %s", len(changes), changes)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
