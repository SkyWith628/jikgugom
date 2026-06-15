"""대시보드 서비스 — 도메인(pipeline/order)을 묶어 상태를 만들고 조작.

저장은 Repository(인메모리/SQL)에 위임 → 영속 방식과 무관하게 동작.
서버 시작 시 비어 있을 때만 시드(재시작해도 기존 데이터 유지).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from api.db import make_repository
from api.ledger_sql import make_fulfillment_ledger
from api.repository import Repository
from api.store import ListingRecord, OrderRecord, PublicationRecord
from jikgugom.adapters.factory import build_adapters
from jikgugom.compliance import ComplianceEngine
from jikgugom.content import ContentAgent
from jikgugom.core import Settings, llm_modes, load_settings
from jikgugom.evaluation import EvaluationAgent
from jikgugom.margin import MarginEngine
from jikgugom.models import ChannelOrder, PublishStatus
from jikgugom.monitor import ListingState, MonitorAction, MonitorWorker
from jikgugom.order import ManualFulfiller, OrderContext, OrderProcessor
from jikgugom.pipeline import ListingStatus, MultiChannelPublisher, PipelineRunner


class DashboardService:
    def __init__(self, repository: Repository | None = None,
                 settings: Settings | None = None) -> None:
        # 설정 로딩·검증(fail-fast) → 키 유무로 real/mock 어댑터 조립
        self._settings = settings or load_settings()
        self._settings.validate()
        adapters = build_adapters(self._settings)
        self.modes = {**adapters.modes, **llm_modes(self._settings)}
        self._fx = self._settings.fx_rate

        self._source = adapters.source
        # primary 채널(가격기준·모니터 키) — 보통 naver
        self._channel = next(
            (c for c in adapters.channels if c.name == self._settings.primary_channel),
            adapters.channels[0])
        # 멀티채널 동시등록: 승인 시 등록 채널들에 팬아웃 발행
        self._publisher = MultiChannelPublisher(adapters.channels)
        # 반자동(HITL) 발주 + SQL 영속 원장 → 재시작해도 멱등·매입추적 유지
        self._fulfiller = ManualFulfiller(make_fulfillment_ledger())
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
        for o in self._runner.run(self._settings.sourcing_category,
                                  pricing_channel=self._channel.name, fx_rate=self._fx):
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
        results = self._publisher.publish(draft)   # naver+coupang 동시 발행
        for channel, res in results.items():
            self.repo.save_publication(PublicationRecord(
                listing_id=listing_id, channel=channel, status=res.status.value,
                channel_product_no=res.channel_product_no, note=res.message or ""))

        listed = {ch: r for ch, r in results.items() if r.status is PublishStatus.LISTED}
        if listed:   # 한 채널이라도 성공하면 발행됨(부분 성공 허용)
            rec.status = ListingStatus.PUBLISHED.value
            # 모니터는 primary(naver) 상품번호에 키잉 → primary 우선, 없으면 첫 성공 채널
            primary = results.get(self._channel.name)
            rec.channel_product_no = (
                primary.channel_product_no
                if primary and primary.status is PublishStatus.LISTED
                else next(iter(listed.values())).channel_product_no)
            rec.note = f"발행 {len(listed)}/{len(results)}채널: {', '.join(listed)}"
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
        """발주 승인 — 멱등 원장에 매입 의도 기록(AWAITING_PURCHASE). 실매입은 운영자가."""
        rec = self.repo.get_order(order_id)
        if rec is None:
            raise KeyError(order_id)
        # 멱등키 = order_id: 승인 버튼 중복 클릭에도 원장엔 한 줄만(이중결제 방지)
        res = self._fulfiller.place_order(rec.product_id, rec.quantity, {},
                                          idempotency_key=order_id)
        rec.status = "awaiting_purchase"   # Amazon 구매 API 부재 → 운영자 실매입 대기
        rec.fulfillment_id = res.fulfillment_id
        self.repo.save_order(rec)
        return rec

    def confirm_purchase(self, order_id: str, amazon_order_no: str, *,
                         tracking_no: str | None = None) -> OrderRecord:
        """운영자가 Amazon 실매입을 마친 뒤 주문번호(·송장)를 기록 → PURCHASED.

        반자동(HITL)의 마지막 인간 단계: '결제 버튼'은 사람이 누르고 그 증빙을 여기 남긴다.
        """
        rec = self.repo.get_order(order_id)
        if rec is None:
            raise KeyError(order_id)
        if rec.fulfillment_id is None:
            raise ValueError(f"order {order_id} is '{rec.status}', not awaiting purchase")
        # 원장(멱등 원천)에 확정 기록 → 표시용으로 OrderRecord에도 동기
        self._fulfiller.confirm_purchase(rec.fulfillment_id, amazon_order_no,
                                         tracking_no=tracking_no)
        rec.status = "purchased"
        rec.amazon_order_no = amazon_order_no
        rec.tracking_no = tracking_no
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

    # ── 운영 설정/모드 가시화 ────────────────────────────────
    def config(self) -> dict:
        """현재 어댑터·LLM 모드(real/mock)와 운영 파라미터 — 키 노출 없음.

        google_client_id는 프론트 Google 로그인 버튼에 필요한 공개값이라 포함한다.
        """
        return {
            "modes": self.modes,
            "fx_rate": str(self._fx),
            "channels": list(self._settings.channels),
            "sourcing_category": self._settings.sourcing_category,
            "auth_enabled": self._settings.auth_enabled,
            "google_client_id": self._settings.google_client_id,
        }

    @property
    def settings(self) -> Settings:
        return self._settings

    # ── 집계 ─────────────────────────────────────────────────
    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for r in self.repo.list_listings():
            counts[r.status] = counts.get(r.status, 0) + 1
        pending = sum(1 for o in self.repo.list_orders() if o.status == "pending_approval")
        return {"listings_total": len(self.repo.list_listings()),
                "by_status": counts, "orders_pending": pending}
