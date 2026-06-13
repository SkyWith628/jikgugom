"""모니터 워커 — 원본 가격·재고 폴링 → auto-pause / 리프라이싱 / 재개.

[What] 등록된 상품의 원본(Amazon) 가격·재고를 주기적으로 확인하고, 변동에 대응.
[Why]  무재고 모델의 최대 리스크 = 원본 품절/가격인상인데 주문받는 것. 자동 대응 없으면
       곧바로 손실+클레임. (실서비스 AutoDS/DSers의 핵심 기능)
[How]  decide()는 순수 함수(IO 없음)로 분리해 테스트 가능. run()이 어댑터로 부수효과 적용.
       돈 직결 판단은 마진엔진·통관 재산정을 재사용해 정확하게.

운영 시: Celery Beat가 ListingState 배치를 N분 주기로 run()에 흘려보낸다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from sourcing_agent.adapters.base import ChannelAdapter, SourceAdapter
from sourcing_agent.compliance.models import ComplianceResult, CustomsType, Verdict
from sourcing_agent.margin import MarginEngine
from sourcing_agent.models import AvailabilitySnapshot, SourceProduct
from sourcing_agent.monitor.models import ListingState, MonitorAction, MonitorDecision

# 새 가격·통화 → 통관유형 (ComplianceEngine.customs_type_for 주입)
CustomsResolver = Callable[[Decimal, str], CustomsType]


@dataclass
class MonitorConfig:
    pause_on_increase_rate: Decimal = Decimal("0.05")   # 원본가 +5% 초과 → 급등으로 보고 중지
    reprice_min_change_rate: Decimal = Decimal("0.02")  # 판매가 2% 이상 변할 때만 갱신(잡음 무시)
    min_margin_rate: Decimal = Decimal("0.10")          # 이 마진 밑이면 팔지 않음(중지)


class MonitorWorker:
    def __init__(
        self,
        source: SourceAdapter,
        channel: ChannelAdapter,
        margin: MarginEngine,
        customs_resolver: CustomsResolver,
        config: MonitorConfig | None = None,
    ) -> None:
        self._src = source
        self._ch = channel
        self._margin = margin
        self._customs = customs_resolver
        self._cfg = config or MonitorConfig()

    # ── 순수 판정 (IO 없음) ──────────────────────────────────
    def decide(self, state: ListingState, snap: AvailabilitySnapshot) -> MonitorDecision:
        cfg = self._cfg

        # 1) 품절 → 중지 (이미 중지면 변화 없음)
        if not snap.in_stock:
            action = MonitorAction.NONE if state.is_paused else MonitorAction.PAUSE
            return MonitorDecision(state.channel_product_no, action,
                                   "out_of_stock", snap.price)

        # 2) 재고 있음 → 새 가격으로 마진 재계산 (통관유형도 재산정)
        quote = self._requote(state, snap.price, snap.currency)

        # 3) 마진 붕괴 → 중지
        if quote.effective_margin_rate < cfg.min_margin_rate:
            action = MonitorAction.NONE if state.is_paused else MonitorAction.PAUSE
            return MonitorDecision(state.channel_product_no, action,
                                   "margin_below_floor", snap.price)

        # 4) 원본가 급등 → 중지(사람 검토). 자동 인상발행은 하지 않음
        rise = (snap.price - state.baseline_price) / state.baseline_price
        if rise > cfg.pause_on_increase_rate:
            action = MonitorAction.NONE if state.is_paused else MonitorAction.PAUSE
            return MonitorDecision(state.channel_product_no, action,
                                   "source_price_spike", snap.price)

        # 5) 중지 상태였는데 정상화 → 재개(신규가)
        if state.is_paused:
            return MonitorDecision(state.channel_product_no, MonitorAction.RESUME,
                                   "recovered", snap.price, quote.sale_price_krw)

        # 6) 판매가 변동 흡수 → 임계치 이상이면 갱신
        delta = abs(quote.sale_price_krw - state.current_price_krw) / state.current_price_krw
        if delta >= cfg.reprice_min_change_rate:
            return MonitorDecision(state.channel_product_no, MonitorAction.REPRICE,
                                   "price_drift", snap.price, quote.sale_price_krw)

        return MonitorDecision(state.channel_product_no, MonitorAction.NONE,
                               "stable", snap.price)

    # ── 폴링 + 부수효과 적용 ─────────────────────────────────
    def run(self, states: list[ListingState]) -> list[MonitorDecision]:
        decisions: list[MonitorDecision] = []
        for state in states:
            snap = self._src.check_availability(state.source_id)
            decision = self.decide(state, snap)
            self._apply(decision)
            decisions.append(decision)
        return decisions

    def _apply(self, d: MonitorDecision) -> None:
        if d.action is MonitorAction.PAUSE:
            self._ch.pause(d.channel_product_no)
        elif d.action is MonitorAction.REPRICE:
            self._ch.update_price(d.channel_product_no, d.new_price_krw)  # type: ignore[arg-type]
        elif d.action is MonitorAction.RESUME:
            self._ch.update_price(d.channel_product_no, d.new_price_krw)  # type: ignore[arg-type]
            self._ch.resume(d.channel_product_no)

    def _requote(self, state: ListingState, price: Decimal, currency: str):
        customs = self._customs(price, currency)
        product = SourceProduct(
            source=self._src.name, source_id=state.source_id, title="", description="",
            category_path=[], price=price, currency=currency, image_urls=[],
            hs_code=state.hs_code,
        )
        compliance = ComplianceResult(
            verdict=Verdict.PASS, reasons=[],
            customs_type=customs, hs_code=state.hs_code,
        )
        return self._margin.quote(product, compliance, channel=state.channel)
