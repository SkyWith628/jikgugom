"""저장소 추상화(Repository) + 인메모리 구현.

[왜 Repository] 서비스가 '저장 방식'이 아니라 '계약'에 의존하게 해, 인메모리↔DB를
코드 변경 없이 교체(어댑터 패턴). SQL 구현은 db.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from api.store import ListingRecord, OrderRecord
from jikgugom.models import ListingDraft


class Repository(ABC):
    # ── listings ─────────────────────────────────────────────
    @abstractmethod
    def is_listings_empty(self) -> bool: ...

    @abstractmethod
    def clear_listings(self) -> None: ...

    @abstractmethod
    def save_listing(self, rec: ListingRecord, draft: ListingDraft | None) -> None: ...

    @abstractmethod
    def get_listing(self, listing_id: str) -> ListingRecord | None: ...

    @abstractmethod
    def get_draft(self, listing_id: str) -> ListingDraft | None: ...

    @abstractmethod
    def list_listings(self) -> list[ListingRecord]: ...

    # ── orders ───────────────────────────────────────────────
    @abstractmethod
    def has_orders(self) -> bool: ...

    @abstractmethod
    def save_order(self, rec: OrderRecord) -> None: ...

    @abstractmethod
    def get_order(self, order_id: str) -> OrderRecord | None: ...

    @abstractmethod
    def list_orders(self) -> list[OrderRecord]: ...


class InMemoryRepository(Repository):
    """딕셔너리 기반 (테스트·휘발성 데모). 삽입 순서 보존."""

    def __init__(self) -> None:
        self._listings: dict[str, ListingRecord] = {}
        self._drafts: dict[str, ListingDraft] = {}
        self._orders: dict[str, OrderRecord] = {}

    def is_listings_empty(self) -> bool:
        return not self._listings

    def clear_listings(self) -> None:
        self._listings.clear()
        self._drafts.clear()

    def save_listing(self, rec, draft):
        self._listings[rec.id] = rec
        if draft is not None:
            self._drafts[rec.id] = draft

    def get_listing(self, listing_id):
        return self._listings.get(listing_id)

    def get_draft(self, listing_id):
        return self._drafts.get(listing_id)

    def list_listings(self):
        return list(self._listings.values())

    def has_orders(self):
        return bool(self._orders)

    def save_order(self, rec):
        self._orders[rec.id] = rec

    def get_order(self, order_id):
        return self._orders.get(order_id)

    def list_orders(self):
        return list(self._orders.values())
