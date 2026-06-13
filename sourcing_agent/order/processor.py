"""주문 처리기 — 가드 재검증 → 자동발주 / 사람 승인 큐.

[What] 채널 주문 1건을 받아 '지금 매입해도 수익이 남는가'를 재검증하고,
       통과 시에만 자동발주, 아니면 승인 큐로 보낸다.
[Why]  주문은 과거 가격에 팔렸다. 그 사이 원본 품절·가격인상이면 자동발주 = 손실 직결.
       비가역(돈) 행동 앞에 결정론 가드를 둔다(설계 결정 4).
[How]  decide()는 순수(가드 판정), process()가 부수효과(발주) 적용 — monitor와 같은 분리.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from sourcing_agent.adapters.base import SourceAdapter
from sourcing_agent.compliance.models import ComplianceResult, CustomsType, Verdict
from sourcing_agent.margin import MarginEngine
from sourcing_agent.models import AvailabilitySnapshot, ChannelOrder, SourceProduct
from sourcing_agent.order.fulfiller import FulfillmentAdapter
from sourcing_agent.order.models import (
    GuardAction,
    OrderContext,
    OrderGuardResult,
    OrderOutcome,
    OrderStatus,
)

CustomsResolver = Callable[[Decimal, str], CustomsType]


@dataclass
class OrderGuardConfig:
    min_margin_rate: Decimal = Decimal("0.03")  # 발주 후 실마진 이 밑이면 사람 검토
    # (적자=profit<=0은 무조건 승인. 이미 팔린 주문이라 floor는 신규등록보다 낮게)


class OrderProcessor:
    def __init__(
        self,
        source: SourceAdapter,
        fulfiller: FulfillmentAdapter,
        margin: MarginEngine,
        customs_resolver: CustomsResolver,
        config: OrderGuardConfig | None = None,
    ) -> None:
        self._src = source
        self._fulfiller = fulfiller
        self._margin = margin
        self._customs = customs_resolver
        self._cfg = config or OrderGuardConfig()

    # ── 가드 판정 ────────────────────────────────────────────
    def evaluate_guard(self, ctx: OrderContext) -> OrderGuardResult:
        snap = self._src.check_availability(ctx.source_id)
        return self._decide(ctx, snap)

    def _decide(self, ctx: OrderContext, snap: AvailabilitySnapshot) -> OrderGuardResult:
        if not snap.in_stock:
            return OrderGuardResult(GuardAction.APPROVAL_REQUIRED, "out_of_stock", snap.price)

        customs = self._customs(snap.price, snap.currency)
        product = SourceProduct(
            source=self._src.name, source_id=ctx.source_id, title="", description="",
            category_path=[], price=snap.price, currency=snap.currency,
            image_urls=[], hs_code=ctx.hs_code,
        )
        compliance = ComplianceResult(Verdict.PASS, [], customs_type=customs,
                                      hs_code=ctx.hs_code)
        check = self._margin.profit_at(ctx.sale_price_krw, product, compliance,
                                       channel=ctx.channel)

        if check.profit_krw <= 0:
            return OrderGuardResult(GuardAction.APPROVAL_REQUIRED, "would_sell_at_loss",
                                    snap.price, check.profit_krw, check.margin_rate)
        if check.margin_rate < self._cfg.min_margin_rate:
            return OrderGuardResult(GuardAction.APPROVAL_REQUIRED, "margin_below_floor",
                                    snap.price, check.profit_krw, check.margin_rate)
        return OrderGuardResult(GuardAction.AUTO_ORDER, "ok",
                                snap.price, check.profit_krw, check.margin_rate)

    # ── 처리(발주) ───────────────────────────────────────────
    def process(self, order: ChannelOrder, ctx: OrderContext,
                *, auto_order: bool = True) -> OrderOutcome:
        guard = self.evaluate_guard(ctx)

        if guard.action is GuardAction.APPROVAL_REQUIRED or not auto_order:
            return OrderOutcome(order.channel_order_no, OrderStatus.PENDING_APPROVAL, guard)

        result = self._fulfiller.place_order(
            ctx.source_id, order.quantity, order.shipping_address)
        return OrderOutcome(order.channel_order_no, OrderStatus.AMAZON_ORDERED,
                            guard, fulfillment=result)
