"""SQL 영속 구현 — SQLAlchemy ORM + SqlRepository.

기본은 SQLite 파일(외부 서버 0, 즉시 영속). `DATABASE_URL=postgresql://...` 면 Postgres.
한 코드로 둘 다 도는 게 SQLAlchemy를 쓰는 이유.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from api.repository import Repository
from api.store import ListingRecord, OrderRecord
from jikgugom.models import ChannelCategory, ListingDraft


class Base(DeclarativeBase):
    pass


class ListingRow(Base):
    __tablename__ = "listings"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)
    note: Mapped[str] = mapped_column(String, default="")
    price_krw: Mapped[int | None] = mapped_column(nullable=True)
    market_score: Mapped[int | None] = mapped_column(nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_product_no: Mapped[str | None] = mapped_column(String, nullable=True)
    draft_json: Mapped[str | None] = mapped_column(String, nullable=True)
    source_currency: Mapped[str] = mapped_column(String, default="USD")
    hs_code: Mapped[str | None] = mapped_column(String, nullable=True)
    baseline_price_usd: Mapped[str | None] = mapped_column(String, nullable=True)


class OrderRow(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(default=1)
    buyer: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)
    guard_action: Mapped[str] = mapped_column(String)
    guard_reason: Mapped[str] = mapped_column(String)
    profit_krw: Mapped[int | None] = mapped_column(nullable=True)
    fulfillment_id: Mapped[str | None] = mapped_column(String, nullable=True)


# ── ListingDraft ↔ JSON (드래프트는 발행 재실행에 필요) ──────
def draft_to_json(draft: ListingDraft) -> str:
    return json.dumps({
        "product_id": draft.product_id, "title_ko": draft.title_ko,
        "description_html": draft.description_html,
        "image_urls_cdn": draft.image_urls_cdn,
        "price_krw": str(draft.price_krw),
        "category": {"id": draft.category.channel_category_id,
                     "name": draft.category.channel_category_name,
                     "confidence": draft.category.confidence},
        "attributes": draft.attributes,
    })


def draft_from_json(s: str | None) -> ListingDraft | None:
    if not s:
        return None
    d = json.loads(s)
    c = d["category"]
    return ListingDraft(
        product_id=d["product_id"], title_ko=d["title_ko"],
        description_html=d["description_html"], image_urls_cdn=d["image_urls_cdn"],
        price_krw=Decimal(d["price_krw"]),
        category=ChannelCategory(c["id"], c["name"], c["confidence"]),
        attributes=d.get("attributes", {}),
    )


def _to_listing(row: ListingRow) -> ListingRecord:
    return ListingRecord(
        id=row.id, title=row.title, status=row.status, note=row.note,
        price_krw=row.price_krw, market_score=row.market_score,
        recommendation=row.recommendation, channel_product_no=row.channel_product_no,
        source_currency=row.source_currency, hs_code=row.hs_code,
        baseline_price_usd=row.baseline_price_usd)


def _to_order(row: OrderRow) -> OrderRecord:
    return OrderRecord(
        id=row.id, product_id=row.product_id, quantity=row.quantity, buyer=row.buyer,
        status=row.status, guard_action=row.guard_action, guard_reason=row.guard_reason,
        profit_krw=row.profit_krw, fulfillment_id=row.fulfillment_id)


class SqlRepository(Repository):
    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args)
        Base.metadata.create_all(self._engine)

    # ── listings ─────────────────────────────────────────────
    def is_listings_empty(self) -> bool:
        with Session(self._engine) as s:
            return s.scalar(select(ListingRow).limit(1)) is None

    def clear_listings(self) -> None:
        with Session(self._engine) as s:
            for row in s.scalars(select(ListingRow)):
                s.delete(row)
            s.commit()

    def save_listing(self, rec: ListingRecord, draft: ListingDraft | None) -> None:
        with Session(self._engine) as s:
            row = s.get(ListingRow, rec.id) or ListingRow(id=rec.id)
            row.title, row.status, row.note = rec.title, rec.status, rec.note
            row.price_krw, row.market_score = rec.price_krw, rec.market_score
            row.recommendation = rec.recommendation
            row.channel_product_no = rec.channel_product_no
            row.source_currency = rec.source_currency
            row.hs_code = rec.hs_code
            row.baseline_price_usd = rec.baseline_price_usd
            if draft is not None:
                row.draft_json = draft_to_json(draft)
            s.merge(row)
            s.commit()

    def get_listing(self, listing_id: str) -> ListingRecord | None:
        with Session(self._engine) as s:
            row = s.get(ListingRow, listing_id)
            return _to_listing(row) if row else None

    def get_draft(self, listing_id: str) -> ListingDraft | None:
        with Session(self._engine) as s:
            row = s.get(ListingRow, listing_id)
            return draft_from_json(row.draft_json) if row else None

    def list_listings(self) -> list[ListingRecord]:
        with Session(self._engine) as s:
            return [_to_listing(r) for r in s.scalars(select(ListingRow))]

    # ── orders ───────────────────────────────────────────────
    def has_orders(self) -> bool:
        with Session(self._engine) as s:
            return s.scalar(select(OrderRow).limit(1)) is not None

    def save_order(self, rec: OrderRecord) -> None:
        with Session(self._engine) as s:
            row = s.get(OrderRow, rec.id) or OrderRow(id=rec.id)
            row.product_id, row.quantity, row.buyer = rec.product_id, rec.quantity, rec.buyer
            row.status, row.guard_action, row.guard_reason = rec.status, rec.guard_action, rec.guard_reason
            row.profit_krw, row.fulfillment_id = rec.profit_krw, rec.fulfillment_id
            s.merge(row)
            s.commit()

    def get_order(self, order_id: str) -> OrderRecord | None:
        with Session(self._engine) as s:
            row = s.get(OrderRow, order_id)
            return _to_order(row) if row else None

    def list_orders(self) -> list[OrderRecord]:
        with Session(self._engine) as s:
            return [_to_order(r) for r in s.scalars(select(OrderRow))]


def make_repository() -> Repository:
    """환경변수로 저장소 선택. DATABASE_URL 없으면 SQLite 파일(영속)."""
    url = os.getenv("DATABASE_URL", "sqlite:///./jikgugom.db")
    if url == "memory":
        from api.repository import InMemoryRepository
        return InMemoryRepository()
    return SqlRepository(url)
