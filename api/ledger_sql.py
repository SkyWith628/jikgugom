"""발주 원장 SQL 영속 구현 — SqlFulfillmentLedger.

[What] FulfillmentLedger(ABC, order/)의 SQL 구현. 발주 레코드를 DB에 영속화해
       재시작해도 멱등 판정·발주 추적이 살아남게 한다.
[Why]  멱등성(같은 주문 두 번 매입 금지)은 '이미 매입했나'를 영속 저장소에 기록해야
       프로세스 재시작 후에도 성립한다. 인메모리 원장은 재시작 시 휘발 → 재매입 위험.
[How]  포트-어댑터. 도메인은 ABC만 의존(ledger.py), 영속화는 운영계층(api/)에서 구현
       → 의존성 역전. db.py의 Base를 공유해 listings/orders와 같은 DB 파일에 둔다.

idempotency_key에 unique 제약을 걸어 '같은 채널주문 = 한 줄'을 DB가 물리적으로 보장
(이중결제의 마지막 방어선). PCCC·결제정보는 저장하지 않는다(개인정보보호 원칙).
"""

from __future__ import annotations

import os

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from api.db import Base
from jikgugom.order import FulfillmentLedger, FulfillmentRecord, FulfillmentStatus


class FulfillmentRow(Base):
    __tablename__ = "fulfillments"
    # PK는 내부 발주ID(추적·배송 갱신의 키). idempotency_key는 멱등 조회용 unique.
    fulfillment_id: Mapped[str] = mapped_column(String, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    source_id: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String, index=True)
    amazon_order_no: Mapped[str | None] = mapped_column(String, nullable=True)
    tracking_no: Mapped[str | None] = mapped_column(String, nullable=True)


def _to_record(row: FulfillmentRow) -> FulfillmentRecord:
    return FulfillmentRecord(
        idempotency_key=row.idempotency_key,
        fulfillment_id=row.fulfillment_id,
        source_id=row.source_id,
        quantity=row.quantity,
        status=FulfillmentStatus(row.status),
        amazon_order_no=row.amazon_order_no,
        tracking_no=row.tracking_no,
    )


class SqlFulfillmentLedger(FulfillmentLedger):
    """SQLAlchemy 영속 원장. 기본 SQLite 파일, DATABASE_URL이면 Postgres."""

    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args)
        Base.metadata.create_all(self._engine)   # fulfillments 테이블 보장(멱등)

    def get(self, idempotency_key: str) -> FulfillmentRecord | None:
        with Session(self._engine) as s:
            row = s.scalars(
                select(FulfillmentRow).where(
                    FulfillmentRow.idempotency_key == idempotency_key)
            ).first()
            return _to_record(row) if row else None

    def get_by_fulfillment_id(self, fulfillment_id: str) -> FulfillmentRecord | None:
        with Session(self._engine) as s:
            row = s.get(FulfillmentRow, fulfillment_id)
            return _to_record(row) if row else None

    def save(self, record: FulfillmentRecord) -> None:
        with Session(self._engine) as s:
            row = s.get(FulfillmentRow, record.fulfillment_id) \
                or FulfillmentRow(fulfillment_id=record.fulfillment_id)
            row.idempotency_key = record.idempotency_key
            row.source_id = record.source_id
            row.quantity = record.quantity
            row.status = record.status.value
            row.amazon_order_no = record.amazon_order_no
            row.tracking_no = record.tracking_no
            s.merge(row)
            s.commit()


def make_fulfillment_ledger() -> FulfillmentLedger:
    """환경변수로 원장 선택. DATABASE_URL 없으면 SQLite 파일(영속), 'memory'면 휘발."""
    url = os.getenv("DATABASE_URL", "sqlite:///./jikgugom.db")
    if url == "memory":
        from jikgugom.order import InMemoryFulfillmentLedger
        return InMemoryFulfillmentLedger()
    return SqlFulfillmentLedger(url)
