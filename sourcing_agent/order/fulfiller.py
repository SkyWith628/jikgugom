"""발주 어댑터 계약 — 무재고 발주(해외 매입)를 추상화.

Amazon은 제3자용 공개 '구매 API'가 없어 실제 발주는 자동화(장바구니/체크아웃)나
대행 매입 서비스로 구현된다 → 구현체는 환경에 종속. 여기선 계약만 못박는다.
가드를 통과한 주문만 이 어댑터에 도달한다(비가역 행동이므로).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sourcing_agent.order.models import FulfillmentResult


class FulfillmentAdapter(ABC):
    name: str

    @abstractmethod
    def place_order(self, source_id: str, quantity: int,
                    shipping_address: dict) -> FulfillmentResult:
        """원본(Amazon)에 발주. 멱등키로 중복발주(이중결제) 방지 권장."""

    @abstractmethod
    def track_shipment(self, fulfillment_id: str) -> str:
        """배송 단계 추적 (shipped/customs/delivered 등 원시 상태 반환)."""
