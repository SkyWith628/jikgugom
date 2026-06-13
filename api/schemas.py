"""API 응답 스키마 (Pydantic) — 프론트(Next.js)와의 계약."""

from __future__ import annotations

from pydantic import BaseModel


class ListingOut(BaseModel):
    id: str
    title: str
    status: str
    note: str
    price_krw: int | None = None
    market_score: int | None = None
    recommendation: str | None = None
    channel_product_no: str | None = None


class OrderOut(BaseModel):
    id: str
    product_id: str
    quantity: int
    buyer: str
    status: str
    guard_action: str
    guard_reason: str
    profit_krw: int | None = None
    fulfillment_id: str | None = None


class StatsOut(BaseModel):
    listings_total: int
    by_status: dict[str, int]
    orders_pending: int
