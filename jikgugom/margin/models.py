"""마진엔진 입출력 모델."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CostBreakdown:
    """판매가를 구성하는 비용 분해 — 감사/디버깅/대시보드 표시용.

    '팔수록 적자'를 막으려면 숨은 비용이 한 줄도 빠지지 않아야 한다.
    """

    product_cost_krw: Decimal      # 상품원가(환율·버퍼 반영)
    intl_shipping_krw: Decimal     # 해외배송
    duty_krw: Decimal              # 관세
    import_vat_krw: Decimal        # 수입부가세
    domestic_shipping_krw: Decimal  # 국내배송
    return_reserve_krw: Decimal    # 반품충당
    landed_cost_krw: Decimal       # 도착원가(상품+해외배송+관세+부가세)
    final_cost_krw: Decimal        # 최종원가(도착+국내배송+반품충당)


@dataclass(frozen=True)
class ProfitCheck:
    """고정 판매가 + 현재 원본가 기준 실수익 (발주 가드용)."""

    profit_krw: Decimal
    margin_rate: Decimal
    final_cost_krw: Decimal
    breakdown: "CostBreakdown"


@dataclass(frozen=True)
class MarginQuote:
    """마진 산출 결과. profit_krw가 음수면 등록 금지 신호."""

    sale_price_krw: Decimal        # 권장 판매가(올림 적용)
    profit_krw: Decimal            # 예상 순이익
    effective_margin_rate: Decimal  # 실제 마진율(판매가 대비)
    channel: str
    fx_rate: Decimal               # 산출에 사용한 환율
    customs_type: str              # list | general | prohibited
    breakdown: CostBreakdown
