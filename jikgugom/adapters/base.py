"""Adapter 계약 — 소스/채널을 공통 인터페이스로 추상화.

[What] SourceAdapter(소싱)·ChannelAdapter(판매채널)의 추상 기반 클래스.
[Why]  파이프라인이 amazon/naver 같은 '구현'이 아니라 '계약'에만 의존하게 한다.
       → 소스를 Rainforest→PA-API, 채널을 네이버→쿠팡으로 코드 결합 없이 교체.
[How]  포트-어댑터(Hexagonal/Ports & Adapters) 패턴. 면접 어필 포인트.

ABC(Abstract Base Class): 직접 인스턴스화 못 하고, @abstractmethod를 전부 구현한
하위 클래스만 생성 가능. 구현을 강제하는 '계약서' 역할.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from jikgugom.models import (
    AvailabilitySnapshot,
    ChannelCategory,
    ChannelOrder,
    ListingDraft,
    PublishResult,
    SourceProduct,
)


class SourceAdapter(ABC):
    """소싱 소스(Amazon 등)를 추상화. 구현체: AmazonRainforestAdapter.

    파이프라인 진입점. 모든 메서드는 외부 API 응답을 SourceProduct/
    AvailabilitySnapshot으로 '정규화'해서 반환해야 한다 (raw 누출 금지).
    """

    #: 소스 식별자 (예: "amazon"). SourceProduct.source 에 기록됨.
    name: str

    @abstractmethod
    def fetch_bestsellers(
        self, category: str, *, limit: int = 50
    ) -> list[SourceProduct]:
        """카테고리별 인기상품을 수집한다. (소싱 1단계)

        Args:
            category: 소스 기준 카테고리 식별자/경로.
            limit: 최대 수집 개수 (rate limit·비용 통제).
        Returns:
            정규화된 SourceProduct 목록.
        """

    @abstractmethod
    def get_product(self, source_id: str) -> SourceProduct:
        """단건 상세 조회 (source_id = ASIN). 등록 직전 최신화에 사용."""

    @abstractmethod
    def check_availability(self, source_id: str) -> AvailabilitySnapshot:
        """가격/재고 현황만 가볍게 조회. 모니터 워커가 주기 폴링하는 진입점.

        전체 상세(get_product)보다 싸야 한다 — 호출 빈도가 높기 때문.
        """


class ChannelAdapter(ABC):
    """판매 채널(네이버 스마트스토어 등)을 추상화. 구현체: NaverSmartstoreAdapter.

    파이프라인 출구(등록) + 주문 수집 입구. 채널별 카테고리/수수료/심사 정책
    차이를 이 경계 안에 가둔다.
    """

    #: 채널 식별자 (예: "naver"). ChannelOrder.channel 등에 기록됨.
    name: str

    @abstractmethod
    def map_category(self, source_category_path: list[str]) -> ChannelCategory:
        """소스 카테고리 → 채널 카테고리 매핑. 신뢰도 낮으면 사람 검토로 라우팅."""

    @abstractmethod
    def publish(self, draft: ListingDraft) -> PublishResult:
        """가공 완료 상품을 채널에 발행. 멱등 처리 권장(같은 product_id 중복발행 방지)."""

    @abstractmethod
    def update_price(self, channel_product_no: str, price_krw: Decimal) -> None:
        """모니터 결과에 따른 판매가 갱신 (동적 리프라이싱)."""

    @abstractmethod
    def pause(self, channel_product_no: str) -> None:
        """원본 품절/가격급등 시 채널 노출 일시중지(auto-pause). 손실·클레임 방지."""

    @abstractmethod
    def resume(self, channel_product_no: str) -> None:
        """재입고·가격 정상화 시 판매 재개(pause의 대칭)."""

    @abstractmethod
    def fetch_orders(self, *, since: str | None = None) -> list[ChannelOrder]:
        """신규 주문 수집. 발주 파이프라인의 입구.

        Args:
            since: 이 시각 이후 주문만 (증분 수집 커서). None이면 구현체 기본값.
        """
