"""네이버 스마트스토어 채널 어댑터 (골격).

1차 판매 채널. 네이버 커머스 API + OAuth2 토큰(자동 갱신)으로 구현 예정.
추후 쿠팡 등 추가 채널도 ChannelAdapter를 구현해 나란히 붙인다.

[현재 상태] 계약만 못박은 골격 — 실제 호출은 NotImplementedError.
"""

from __future__ import annotations

from decimal import Decimal

from sourcing_agent.adapters.base import ChannelAdapter
from sourcing_agent.models import (
    ChannelCategory,
    ChannelOrder,
    ListingDraft,
    PublishResult,
)


class NaverSmartstoreAdapter(ChannelAdapter):
    """네이버 커머스 API 기반 스마트스토어 어댑터."""

    name = "naver"

    def __init__(self, client_id: str, client_secret: str) -> None:
        # OAuth2 자격증명은 Secrets Manager 주입. 토큰은 만료 전 자동 갱신.
        self._client_id = client_id
        self._client_secret = client_secret

    def map_category(self, source_category_path: list[str]) -> ChannelCategory:
        # TODO: Amazon 카테고리 → 네이버 카테고리 매핑 (사전 + 신뢰도)
        raise NotImplementedError

    def publish(self, draft: ListingDraft) -> PublishResult:
        # TODO: 상품 등록 API 호출 (멱등키로 중복발행 방지)
        raise NotImplementedError

    def update_price(self, channel_product_no: str, price_krw: Decimal) -> None:
        # TODO: 판매가 수정 API
        raise NotImplementedError

    def pause(self, channel_product_no: str) -> None:
        # TODO: 판매중지(품절) 처리 API
        raise NotImplementedError

    def resume(self, channel_product_no: str) -> None:
        # TODO: 판매재개 API
        raise NotImplementedError

    def fetch_orders(self, *, since: str | None = None) -> list[ChannelOrder]:
        # TODO: 신규 주문 조회 → ChannelOrder 정규화 (PCCC 암호화 유지)
        raise NotImplementedError
