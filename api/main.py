"""FastAPI 앱 — 대시보드용 JSON API.

    uvicorn api.main:app --reload --port 8000

라우트는 얇게: DashboardService에 위임. 상태는 인메모리(서버 재시작 시 초기화).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import ListingOut, OrderOut, StatsOut
from api.scheduler import MonitorScheduler
from api.service import DashboardService

service = DashboardService()
scheduler = MonitorScheduler(service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()       # 가격·재고 점검 주기 실행 시작
    yield
    scheduler.shutdown()


app = FastAPI(title="직구곰 admin API", version="0.2.0", lifespan=lifespan)

# Next.js dev 서버(3000)에서 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3100", "http://127.0.0.1:3100",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/stats", response_model=StatsOut)
def get_stats() -> dict:
    return service.stats()


@app.get("/api/listings", response_model=list[ListingOut])
def list_listings() -> list:
    return service.repo.list_listings()


@app.post("/api/listings/{listing_id}/approve", response_model=ListingOut)
def approve_listing(listing_id: str):
    try:
        return service.approve_listing(listing_id)
    except KeyError:
        raise HTTPException(404, f"listing {listing_id} not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/sourcing/run", response_model=list[ListingOut])
def run_sourcing() -> list:
    service.run_sourcing()
    return service.repo.list_listings()


@app.get("/api/orders", response_model=list[OrderOut])
def list_orders() -> list:
    return service.repo.list_orders()


@app.post("/api/orders/{order_id}/approve", response_model=OrderOut)
def approve_order(order_id: str):
    try:
        return service.approve_order(order_id)
    except KeyError:
        raise HTTPException(404, f"order {order_id} not found")


@app.post("/api/orders/{order_id}/reject", response_model=OrderOut)
def reject_order(order_id: str):
    try:
        return service.reject_order(order_id)
    except KeyError:
        raise HTTPException(404, f"order {order_id} not found")


@app.post("/api/monitor/run")
def run_monitor() -> dict:
    """가격·재고 점검을 즉시 실행(스케줄러와 동일 동작). 변경분 반환."""
    changes = service.monitor_sweep()
    return {"changed": len(changes), "changes": changes}


@app.get("/api/monitor/last")
def monitor_last() -> dict:
    """스케줄러의 마지막 자동 점검 결과."""
    return scheduler.last_run or {"at": None, "changed": 0, "changes": []}


@app.post("/api/dev/simulate/{listing_id}")
def dev_simulate(listing_id: str, event: str = "oos") -> dict:
    """[데모 전용] 원본가/재고 변동을 흉내 내 점검 동작을 시연한다.

    event: oos(품절) | restock(재입고) | drop(가격하락) | spike(가격급등)
    실서비스에는 없는 엔드포인트(SampleSource 시뮬레이션용).
    """
    src = service._source
    if not hasattr(src, "set_out_of_stock"):
        raise HTTPException(400, "simulation not supported on this source")
    base = src.get_product(listing_id).price       # 상품별 기준가 상대로 변동
    if event == "oos":
        src.set_out_of_stock(listing_id, True)
    elif event == "restock":
        src.set_out_of_stock(listing_id, False)
    elif event == "drop":
        src.set_source_price(listing_id, base * Decimal("0.7"))   # -30%
    elif event == "spike":
        src.set_source_price(listing_id, base * Decimal("1.3"))   # +30%
    else:
        raise HTTPException(400, f"unknown event '{event}'")
    return {"listing_id": listing_id, "event": event}
