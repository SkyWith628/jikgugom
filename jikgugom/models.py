"""공용 데이터 모델 (DTO) — Adapter 양끝과 파이프라인 사이를 흐르는 계약.

[What] 소스/채널 구현이 무엇을 주고받는지 정의하는 타입의 단일 출처.
[Why]  구현(amazon/naver)이 아니라 '데이터 모양'에 의존하게 만들어 결합도를 낮춘다.
       소스를 PA-API로, 채널을 쿠팡으로 바꿔도 이 DTO만 채우면 파이프라인은 그대로.
[How]  Adapter 패턴의 'port'(경계 데이터)에 해당. 외부 API 응답(raw)을 여기로 정규화한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


# ─────────────────────────────────────────────────────────────
# 소싱 (SourceAdapter → 파이프라인)
# ─────────────────────────────────────────────────────────────
@dataclass
class SourceProduct:
    """소스에서 수집한 원본 상품 1건. (컴플라이언스 필터의 입력이기도 함)

    raw_data에 원본 응답 전체를 보존해 추후 재가공/감사가 가능하게 한다.
    """

    source: str                       # "amazon" 등 어느 소스에서 왔는지
    source_id: str                    # 소스 내 식별자 (Amazon이면 ASIN)
    title: str
    description: str
    category_path: list[str]          # ["Electronics", "Chargers"]
    price: Decimal                    # 원본 통화 기준 가격
    currency: str                     # "USD"
    image_urls: list[str]             # 원본 이미지 (등록 전 CDN 재호스팅 대상)
    brand: str | None = None
    hs_code: str | None = None        # 없으면 컴플라이언스 단계가 추정
    attributes: dict = field(default_factory=dict)  # 배터리 포함 여부, 용량 등 raw
    raw_data: dict = field(default_factory=dict)     # 원본 응답 전체 보존


@dataclass
class AvailabilitySnapshot:
    """모니터 워커가 폴링하는 가격/재고 스냅샷.

    원본 품절·가격인상을 감지해 auto-pause/가격조정을 트리거하는 근거.
    """

    source_id: str
    price: Decimal
    currency: str
    in_stock: bool
    captured_at: datetime


# ─────────────────────────────────────────────────────────────
# 등록 (파이프라인 → ChannelAdapter)
# ─────────────────────────────────────────────────────────────
@dataclass
class ChannelCategory:
    """채널 측 카테고리 매핑 결과 (소스 카테고리 → 채널 카테고리 ID)."""

    channel_category_id: str
    channel_category_name: str
    confidence: float                 # 매핑 신뢰도 (낮으면 사람 검토)


@dataclass
class ListingDraft:
    """채널에 발행할 가공 완료 상품. (콘텐츠+마진 단계의 산출물)"""

    product_id: str                   # 내부 마스터 product id
    title_ko: str
    description_html: str
    image_urls_cdn: list[str]         # 자체 CDN 재호스팅된 이미지
    price_krw: Decimal                # 마진엔진이 산출한 채널 판매가
    category: ChannelCategory
    attributes: dict = field(default_factory=dict)


class PublishStatus(str, Enum):
    LISTED = "listed"                 # 발행 성공
    REJECTED = "rejected"             # 채널 심사 거절
    PENDING = "pending"               # 심사 대기


@dataclass
class PublishResult:
    """채널 발행 결과 — 발행 성공 시 채널 상품번호를 받아 모니터링/주문에 연결."""

    status: PublishStatus
    channel_product_no: str | None    # 발행 성공 시 채널이 부여한 번호
    message: str | None = None        # 거절/대기 사유


# ─────────────────────────────────────────────────────────────
# 주문 (ChannelAdapter → 파이프라인)
# ─────────────────────────────────────────────────────────────
@dataclass
class ChannelOrder:
    """채널에서 수집한 주문 1건. PCCC는 절대 평문 로깅 금지 → 발주 직전에만 복호화."""

    channel: str
    channel_order_no: str
    channel_product_no: str
    quantity: int
    buyer_name: str
    buyer_pccc_encrypted: str         # 개인통관고유부호 (암호화 상태로만 보관)
    shipping_address: dict
    ordered_at: datetime
