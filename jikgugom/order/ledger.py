"""발주 원장 포트 — 멱등 발주를 떠받치는 저장 추상화.

[What] FulfillmentLedger(ABC): 발주 레코드를 멱등키/내부 발주ID로 조회·저장.
[Why]  멱등성(같은 주문 두 번 매입 금지)은 '이미 매입했나?'를 어딘가에 기록해야
       성립한다. 그 저장소를 계약으로 추상화 → 메모리(기본)·SQL(api/)로 교체.
[How]  포트-어댑터(Hexagonal). 도메인(ManualFulfiller)은 이 ABC에만 의존하고,
       실제 영속화(SQL)는 운영 계층(api/)에서 구현 → 의존성 역전.

영속 구현(SqlFulfillmentLedger)은 운영 관심사라 api/에 둔다. 여기 InMemory는
키 없이도 전체가 돌아가게 하는 기본값(프로젝트 원칙: 외부 의존 없이 동작).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from jikgugom.order.models import FulfillmentRecord


class FulfillmentLedger(ABC):
    @abstractmethod
    def get(self, idempotency_key: str) -> FulfillmentRecord | None:
        """멱등키로 조회. 발주 전 '이미 매입했나'를 O(1) 확인하는 진입점."""

    @abstractmethod
    def get_by_fulfillment_id(self, fulfillment_id: str) -> FulfillmentRecord | None:
        """내부 발주ID로 조회 (운영자 매입 확정·배송추적에 사용)."""

    @abstractmethod
    def save(self, record: FulfillmentRecord) -> None:
        """레코드 신규 저장/갱신 (upsert)."""


class InMemoryFulfillmentLedger(FulfillmentLedger):
    """프로세스 메모리 원장 — 기본값/테스트용. 재시작 시 휘발.

    멱등키·발주ID 두 인덱스를 함께 유지해 양방향 조회를 O(1)로 한다.
    """

    def __init__(self) -> None:
        self._by_key: dict[str, FulfillmentRecord] = {}
        self._by_fid: dict[str, FulfillmentRecord] = {}

    def get(self, idempotency_key: str) -> FulfillmentRecord | None:
        return self._by_key.get(idempotency_key)

    def get_by_fulfillment_id(self, fulfillment_id: str) -> FulfillmentRecord | None:
        return self._by_fid.get(fulfillment_id)

    def save(self, record: FulfillmentRecord) -> None:
        self._by_key[record.idempotency_key] = record
        self._by_fid[record.fulfillment_id] = record
