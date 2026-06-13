"""대시보드 서비스 — 도메인(pipeline/order/cs)을 묶어 대시보드 상태를 만들고 조작.

라우트(main.py)는 얇게 유지하고 비즈니스 로직은 여기. 모든 작업은 Store(인메모리)에 반영.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from api.store import ListingRecord, OrderRecord, Store
from sourcing_agent.compliance import ComplianceEngine
from sourcing_agent.content import ContentAgent
from sourcing_agent.evaluation import EvaluationAgent
from sourcing_agent.margin import MarginEngine
from sourcing_agent.models import ChannelOrder, PublishStatus
from sourcing_agent.order import OrderContext, OrderProcessor
from sourcing_agent.pipeline import ListingStatus, PipelineRunner
from sourcing_agent.samples import SampleChannel, SampleFulfiller, SampleSource

FX = Decimal("1380")


class DashboardService:
    def __init__(self) -> None:
        self._source = SampleSource()
        self._channel = SampleChannel()
        self._fulfiller = SampleFulfiller()
        self._compliance = ComplianceEngine()
        self._margin = MarginEngine()
        self._runner = PipelineRunner(
            self._source, self._channel, self._compliance, self._margin,
            evaluator=EvaluationAgent(), content_builder=ContentAgent().build,
        )
        self._order_proc = OrderProcessor(
            self._source, self._fulfiller, self._margin, self._compliance.customs_type_for)
        self.store = Store()
        self.run_sourcing()
        self._seed_orders()

    # ── 소싱 파이프라인 실행 → listings 채우기 ───────────────
    def run_sourcing(self) -> None:
        self.store.listings.clear()
        self.store.drafts.clear()
        for o in self._runner.run("Best", pricing_channel="naver", fx_rate=FX):
            rec = ListingRecord(
                id=o.source_id, title=(o.draft.title_ko if o.draft else o.source_id),
                status=o.status.value, note=o.note,
                price_krw=int(o.quote.sale_price_krw) if o.quote else None,
                market_score=o.evaluation.market_score if o.evaluation else None,
                recommendation=o.evaluation.recommendation.value if o.evaluation else None,
            )
            self.store.listings[rec.id] = rec
            if o.draft is not None:
                self.store.drafts[rec.id] = o.draft

    def approve_listing(self, listing_id: str) -> ListingRecord:
        rec = self.store.listings.get(listing_id)
        if rec is None:
            raise KeyError(listing_id)
        if rec.status != ListingStatus.READY.value:
            raise ValueError(f"listing {listing_id} is '{rec.status}', not ready")
        res = self._channel.publish(self.store.drafts[listing_id])
        if res.status is PublishStatus.LISTED:
            rec.status = ListingStatus.PUBLISHED.value
            rec.channel_product_no = res.channel_product_no
            rec.note = f"published as {res.channel_product_no}"
        return rec

    # ── 주문 시드 + 발주 가드 ────────────────────────────────
    def _seed_orders(self) -> None:
        # (상품, 고객 결제가) — 하나는 정상, 하나는 저가에 팔려 적자(가드가 잡음)
        samples = [("ORD-001", "B01", "8518.30", "82900", "홍길동"),
                   ("ORD-002", "B03", "9617.00", "20000", "김영희")]
        for oid, pid, hs, sale, buyer in samples:
            order = ChannelOrder("naver", oid, "NV?", 1, buyer, "enc::pccc",
                                 {"zip": "06000"}, datetime.now(timezone.utc))
            ctx = OrderContext(pid, "USD", hs, "naver", Decimal(sale))
            guard = self._order_proc.evaluate_guard(ctx)  # 가드만 평가(발주는 승인 후)
            self.store.orders[oid] = OrderRecord(
                id=oid, product_id=pid, quantity=order.quantity, buyer=buyer,
                status="pending_approval", guard_action=guard.action.value,
                guard_reason=guard.reason,
                profit_krw=int(guard.profit_krw) if guard.profit_krw is not None else None,
            )

    def approve_order(self, order_id: str) -> OrderRecord:
        rec = self.store.orders.get(order_id)
        if rec is None:
            raise KeyError(order_id)
        res = self._fulfiller.place_order(rec.product_id, rec.quantity, {})
        rec.status = "amazon_ordered"
        rec.fulfillment_id = res.fulfillment_id
        return rec

    def reject_order(self, order_id: str) -> OrderRecord:
        rec = self.store.orders.get(order_id)
        if rec is None:
            raise KeyError(order_id)
        rec.status = "rejected"
        return rec

    # ── 집계 ─────────────────────────────────────────────────
    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for r in self.store.listings.values():
            counts[r.status] = counts.get(r.status, 0) + 1
        pending_orders = sum(1 for o in self.store.orders.values()
                             if o.status == "pending_approval")
        return {"listings_total": len(self.store.listings),
                "by_status": counts, "orders_pending": pending_orders}
