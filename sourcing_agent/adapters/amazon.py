"""Amazon 소스 어댑터 (골격).

1차: Rainforest API(서드파티)로 구현 예정. 추후 PA-API/Creators API로 교체해도
SourceAdapter 계약만 지키면 파이프라인은 무변경.

[현재 상태] 계약만 못박은 골격 — 실제 호출은 NotImplementedError.
"""

from __future__ import annotations

from sourcing_agent.adapters.base import SourceAdapter
from sourcing_agent.models import AvailabilitySnapshot, SourceProduct


class AmazonRainforestAdapter(SourceAdapter):
    """Rainforest API 기반 Amazon US 소싱 어댑터."""

    name = "amazon"

    def __init__(self, api_key: str, *, domain: str = "amazon.com") -> None:
        # api_key 는 Secrets Manager에서 주입 (코드·깃 금지)
        self._api_key = api_key
        self._domain = domain

    def fetch_bestsellers(
        self, category: str, *, limit: int = 50
    ) -> list[SourceProduct]:
        # TODO: Rainforest 'bestsellers' 타입 호출 → SourceProduct로 정규화
        raise NotImplementedError

    def get_product(self, source_id: str) -> SourceProduct:
        # TODO: Rainforest 'product' 타입 호출 (source_id = ASIN)
        raise NotImplementedError

    def check_availability(self, source_id: str) -> AvailabilitySnapshot:
        # TODO: 가격/재고만 가볍게 조회 (모니터 워커용 — 저비용 경로)
        raise NotImplementedError
