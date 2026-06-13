"""FastAPI 앱 — 대시보드용 JSON API.

    uvicorn api.main:app --reload --port 8000

라우트는 얇게: DashboardService에 위임. 상태는 인메모리(서버 재시작 시 초기화).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import ListingOut, OrderOut, StatsOut
from api.service import DashboardService

app = FastAPI(title="sourcing-agent admin API", version="0.1.0")

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

service = DashboardService()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/stats", response_model=StatsOut)
def get_stats() -> dict:
    return service.stats()


@app.get("/api/listings", response_model=list[ListingOut])
def list_listings() -> list:
    return list(service.store.listings.values())


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
    return list(service.store.listings.values())


@app.get("/api/orders", response_model=list[OrderOut])
def list_orders() -> list:
    return list(service.store.orders.values())


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
