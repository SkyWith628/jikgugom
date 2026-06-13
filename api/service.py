"""대시보드 서비스 — 도메인(pipeline/order)을 묶어 상태를 만들고 조작.

저장은 Repository(인메모리/SQL)에 위임 → 영속 방식과 무관하게 동작.
서버 시작 시 비어 있을 때만 시드(재시작해도 기존 데이터 유지).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from api.db import make_repository
from api.repository import Repository
from api.store import ListingRecord, OrderRecord
from jikgugom.compliance import ComplianceEngine
from jikgugom.content import ContentAgent
from jikgugom.evaluation import EvaluationAgent
from jikgugom.margin import MarginEngine
from jikgugom.models import ChannelOrder, PublishStatus
from jikgugom.monitor import ListingState, MonitorAction, MonitorWorker
from jikgugom.order import OrderContext, OrderProcessor
from jikgugom.pipeline import ListingStatus, PipelineRunner
from jikgugom.samples import SampleChannel, SampleFulfiller, SampleSource

FX = Decimal("1380")


class DashboardService:
    def __init__(self, repository: Repository | None = None) -> None:
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
        self._monitor = MonitorWorker(
            self._source, self._channel, self._margin, self._compliance.customs_type_for)
        self.repo = repository or make_repository()
        if self.repo.is_listings_empty():   # 비어 있을 때만 시드 → 재시작 시 유지
            self.run_sourcing()
        if not self.repo.has_orders():
            self._seed_orders()

    # ── 소싱 파이프라인 실행 → listings 채우기 ───────────────
    def run_sourcing(self) -> None:
        self.repo.clear_listings()
        for o in self._runner.run("Best", pricing_channel="naver", fx_rate=FX):
            sp = self._source.get_product(o.source_id)   # 원본 기준가/통관 정보 보관(모니터링용)
            rec = ListingRecord(
                id=o.source_id, title=(o.draft.title_ko if o.draft else o.source_id),
                status=o.status.value, note=o.note,
                price_krw=int(o.quote.sale_price_krw) if o.quote else None,
                market_score=o.evaluation.market_score if o.evaluation else None,
                recommendation=o.evaluation.recommendation.value if o.evaluation else None,
                source_currency=sp.currency, hs_code=sp.hs_code,
                baseline_price_usd=str(sp.price),
            )
            self.repo.save_listing(rec, o.draft)

    def approve_listing(self, listing_id: str) -> ListingRecord:
        rec = self.repo.get_listing(listing_id)
        if rec is None:
            raise KeyError(listing_id)
        if rec.status != ListingStatus.READY.value:
            raise ValueError(f"listing {listing_id} is '{rec.status}', not ready")
        draft = self.repo.get_draft(listing_id)
        res = self._channel.publish(draft)
        if res.status is PublishStatus.LISTED:
            rec.status = ListingStatus.PUBLISHED.value
            rec.channel_product_no = res.channel_product_no
            rec.note = f"published as {res.channel_product_no}"
            self.repo.save_listing(rec, None)   # draft 유지(None=미변경)
        return rec

    # ── 주문 시드 + 발주 가드 ────────────────────────────────
    def _seed_orders(self) -> None:
        samples = [("ORD-001", "B01", "8518.30", "82900", "홍길동"),
                   ("ORD-002", "B03", "9617.00", "20000", "김영희")]
        for oid, pid, hs, sale, buyer in samples:
            order = ChannelOrder("naver", oid, "NV?", 1, buyer, "enc::pccc",
                                 {"zip": "06000"}, datetime.now(timezone.utc))
            ctx = OrderContext(pid, "USD", hs, "naver", Decimal(sale))
            guard = self._order_proc.evaluate_guard(ctx)
            self.repo.save_order(OrderRecord(
                id=oid, product_id=pid, quantity=order.quantity, buyer=buyer,
                status="pending_approval", guard_action=guard.action.value,
                guard_reason=guard.reason,
                profit_krw=int(guard.profit_krw) if guard.profit_krw is not None else None))

    def approve_order(self, order_id: str) -> OrderRecord:
        rec = self.repo.get_order(order_id)
        if rec is None:
            raise KeyError(order_id)
        res = self._fulfiller.place_order(rec.product_id, rec.quantity, {})
        rec.status = "amazon_ordered"
        rec.fulfillment_id = res.fulfillment_id
        self.repo.save_order(rec)
        return rec

    def reject_order(self, order_id: str) -> OrderRecord:
        rec = self.repo.get_order(order_id)
        if rec is None:
            raise KeyError(order_id)
        rec.status = "rejected"
        self.repo.save_order(rec)
        return rec

    # ── 가격·재고 점검 (스케줄러가 주기 호출) ────────────────
    def monitor_sweep(self) -> list[dict]:
        """발행/중지 상품의 원본가·재고를 점검 → pause/reprice/resume 반영. 변경분 반환."""
        recs_by_cpn: dict[str, ListingRecord] = {}
        states: list[ListingState] = []
        for rec in self.repo.list_listings():
            if (rec.status not in ("published", "paused") or not rec.channel_product_no
                    or not rec.baseline_price_usd or rec.price_krw is None):
                continue
            recs_by_cpn[rec.channel_product_no] = rec
            states.append(ListingState(
                channel="naver", channel_product_no=rec.channel_product_no, source_id=rec.id,
                baseline_price=Decimal(rec.baseline_price_usd), currency=rec.source_currency,
                hs_code=rec.hs_code, current_price_krw=Decimal(rec.price_krw),
                is_paused=(rec.status == "paused")))

        changes: list[dict] = []
        for d in self._monitor.run(states):           # 원본 폴링 + 채널 부수효과 적용
            if d.action is MonitorAction.NONE:
                continue
            rec = recs_by_cpn[d.channel_product_no]
            if d.action is MonitorAction.PAUSE:
                rec.status, rec.note = "paused", f"일시중지: {d.reason}"
            elif d.action is MonitorAction.REPRICE:
                rec.price_krw, rec.note = int(d.new_price_krw), f"가격조정: {d.reason}"
            elif d.action is MonitorAction.RESUME:
                rec.status, rec.price_krw, rec.note = "published", int(d.new_price_krw), "판매재개"
            self.repo.save_listing(rec, None)
            changes.append({"id": rec.id, "action": d.action.value, "reason": d.reason,
                            "new_price_krw": int(d.new_price_krw) if d.new_price_krw else None})
        return changes

    # ── 집계 ─────────────────────────────────────────────────
    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for r in self.repo.list_listings():
            counts[r.status] = counts.get(r.status, 0) + 1
        pending = sum(1 for o in self.repo.list_orders() if o.status == "pending_approval")
        return {"listings_total": len(self.repo.list_listings()),
                "by_status": counts, "orders_pending": pending}
