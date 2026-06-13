"""모니터 워커 입출력 모델."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class MonitorAction(str, Enum):
    NONE = "none"        # 변화 없음 — 그대로 유지
    PAUSE = "pause"      # 품절/가격급등/마진붕괴 → 판매중지
    REPRICE = "reprice"  # 변동 흡수 → 판매가 갱신
    RESUME = "resume"    # 재입고+정상화 → 판매재개(신규가로)


@dataclass
class ListingState:
    """모니터링 대상 1건의 현재 상태(원장에서 읽어옴)."""

    channel: str
    channel_product_no: str
    source_id: str
    baseline_price: Decimal      # 등록 기준 원본가(USD)
    currency: str
    hs_code: str | None
    current_price_krw: Decimal   # 현재 채널 판매가
    is_paused: bool = False


@dataclass(frozen=True)
class MonitorDecision:
    """폴링 결과 판정. 워커가 이 결정에 따라 채널 API를 호출한다."""

    channel_product_no: str
    action: MonitorAction
    reason: str
    observed_price: Decimal       # 이번에 관측된 원본가
    new_price_krw: Decimal | None = None  # REPRICE/RESUME일 때만
