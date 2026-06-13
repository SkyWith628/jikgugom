"""마진엔진 — 전 비용을 반영해 채널 판매가/예상이익을 결정론적으로 산출.

[What] (상품가 + 통관유형 + HS) → 권장 판매가 + 비용분해 + 예상이익.
[Why]  '팔수록 적자'의 원인인 숨은 비용(관세·부가세·수수료·환율)을 전부 반영.
       LIST(목록통관) 면세를 살려 가격경쟁력을 확보하는 게 핵심 가치.
[How]  판매가 = 최종원가 / (1 - 마진 - 채널수수료 - 결제수수료) 역산. 모든 돈은 Decimal.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, ROUND_UP, Decimal

from sourcing_agent.compliance.models import ComplianceResult, CustomsType
from sourcing_agent.margin.config import MarginConfig, load_margin_config
from sourcing_agent.margin.models import CostBreakdown, MarginQuote
from sourcing_agent.models import SourceProduct

_WON = Decimal("1")


class MarginEngine:
    def __init__(self, config: MarginConfig | None = None) -> None:
        self._cfg = config or load_margin_config()

    def quote(
        self,
        product: SourceProduct,
        compliance: ComplianceResult,
        *,
        channel: str = "naver",
        fx_rate: Decimal | None = None,
    ) -> MarginQuote:
        if compliance.customs_type is CustomsType.PROHIBITED:
            raise ValueError("prohibited item cannot be priced")
        if product.currency != "USD":
            raise NotImplementedError(f"currency {product.currency} not supported (USD only)")
        price = Decimal(str(product.price))
        if price <= 0:
            raise ValueError("product price must be > 0")

        cfg = self._cfg
        fx = Decimal(str(fx_rate)) if fx_rate is not None else cfg.fx_rate_krw_per_usd
        fees = cfg.channel_fees(channel)

        # ── 상품원가 + 해외배송 ───────────────────────────────
        product_cost = price * fx * cfg.fx_buffer
        intl = cfg.intl_shipping_krw

        # ── 관세·수입부가세 (통관유형 분기) ───────────────────
        if compliance.customs_type is CustomsType.LIST:
            duty = Decimal(0)            # 목록통관 = 면세
            import_vat = Decimal(0)
        else:                            # GENERAL = 일반통관
            dutiable = product_cost + intl
            duty = dutiable * cfg.duty_rate(compliance.hs_code)
            import_vat = (dutiable + duty) * cfg.import_vat_rate

        landed = product_cost + intl + duty + import_vat

        # ── 국내배송 + 반품충당 → 최종원가 ────────────────────
        domestic = cfg.domestic_shipping_krw
        return_reserve = landed * cfg.return_reserve_rate
        final_cost = landed + domestic + return_reserve

        # ── 판매가 역산 ───────────────────────────────────────
        denom = 1 - cfg.target_margin_rate - fees.sales_fee_rate - fees.payment_fee_rate
        raw_price = final_cost / denom
        sale_price = self._round_up(raw_price, cfg.price_rounding_krw)

        # ── 실제 이익(올림 반영) ─────────────────────────────
        channel_cut = sale_price * (fees.sales_fee_rate + fees.payment_fee_rate)
        profit = (sale_price - channel_cut - final_cost).quantize(_WON, ROUND_HALF_UP)
        eff_margin = (profit / sale_price).quantize(Decimal("0.0001"), ROUND_HALF_UP)

        return MarginQuote(
            sale_price_krw=sale_price,
            profit_krw=profit,
            effective_margin_rate=eff_margin,
            channel=channel,
            fx_rate=fx,
            customs_type=compliance.customs_type.value,
            breakdown=CostBreakdown(
                product_cost_krw=self._won(product_cost),
                intl_shipping_krw=self._won(intl),
                duty_krw=self._won(duty),
                import_vat_krw=self._won(import_vat),
                domestic_shipping_krw=self._won(domestic),
                return_reserve_krw=self._won(return_reserve),
                landed_cost_krw=self._won(landed),
                final_cost_krw=self._won(final_cost),
            ),
        )

    @staticmethod
    def _won(v: Decimal) -> Decimal:
        return v.quantize(_WON, ROUND_HALF_UP)

    @staticmethod
    def _round_up(value: Decimal, unit: Decimal) -> Decimal:
        """판매가를 unit(예 100원) 단위로 올림 — 마진 보호 + 소매가 관행."""
        return (value / unit).quantize(_WON, ROUND_UP) * unit
