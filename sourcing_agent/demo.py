"""실행 가능한 데모 — 키 없이 전체 흐름을 한 번에 본다.

    python -m sourcing_agent.demo

샘플 카탈로그(인메모리)로 소싱→컴플라이언스→마진→평가→콘텐츠→등록(승인 게이트)
→ 발주 가드 → CS 응대까지 한 줄로 흘려본다. 모든 에이전트는 mock 모드.
실제 운영은 아래 SampleSource/SampleChannel을 실 어댑터로 교체(README '실행' 참고).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sourcing_agent.adapters.base import ChannelAdapter, SourceAdapter
from sourcing_agent.content import ContentAgent
from sourcing_agent.compliance import ComplianceEngine
from sourcing_agent.cs import CSAgent, CSContext
from sourcing_agent.evaluation import EvaluationAgent
from sourcing_agent.margin import MarginEngine
from sourcing_agent.models import (
    AvailabilitySnapshot,
    ChannelCategory,
    ChannelOrder,
    PublishResult,
    PublishStatus,
    SourceProduct,
)
from sourcing_agent.order import OrderContext, OrderProcessor
from sourcing_agent.order.models import FulfillmentResult, OrderStatus
from sourcing_agent.pipeline import PipelineRunner

FX = Decimal("1380")

# ── 샘플 카탈로그 (실서비스는 Amazon에서 수집) ──────────────
_CATALOG = [
    SourceProduct("amazon", "B01", "Wireless Earbuds", "Bluetooth 5.3 earbuds with case",
                  ["Best", "Headphones"], Decimal("29"), "USD",
                  ["https://amazon.com/1.jpg"], brand="Acme", hs_code="8518.30",
                  attributes={"rating": 4.7, "review_count": 900}),
    SourceProduct("amazon", "B02", "USB Wall Charger", "65W fast charger",
                  ["Best", "Chargers"], Decimal("18"), "USD",
                  ["https://amazon.com/2.jpg"], attributes={"rating": 4.5, "review_count": 500}),
    SourceProduct("amazon", "B03", "Stainless Steel Water Bottle", "Insulated 500ml",
                  ["Best", "Kitchen"], Decimal("14"), "USD",
                  ["https://amazon.com/3.jpg"], hs_code="9617.00",
                  attributes={"rating": 4.3, "review_count": 210}),
]


class SampleSource(SourceAdapter):
    name = "amazon"

    def __init__(self) -> None:
        self._by_id = {p.source_id: p for p in _CATALOG}

    def fetch_bestsellers(self, category, *, limit=50):
        return [p for p in _CATALOG if category in p.category_path][:limit] or _CATALOG[:limit]

    def get_product(self, source_id):
        return self._by_id[source_id]

    def check_availability(self, source_id):
        p = self._by_id[source_id]
        return AvailabilitySnapshot(source_id, p.price, p.currency, True,
                                    datetime.now(timezone.utc))


class SampleChannel(ChannelAdapter):
    name = "naver"

    def __init__(self) -> None:
        self.published = {}
        self._seq = 0

    def map_category(self, path):
        return ChannelCategory("50000123", "/".join(path), 0.9)

    def publish(self, draft):
        self._seq += 1
        no = f"NV{self._seq:06d}"
        self.published[no] = draft
        return PublishResult(PublishStatus.LISTED, no)

    def update_price(self, no, price): ...
    def pause(self, no): ...
    def resume(self, no): ...
    def fetch_orders(self, *, since=None): return []


class SampleFulfiller:
    name = "sample-amazon"

    def place_order(self, source_id, quantity, shipping_address):
        return FulfillmentResult(f"AMZ-{source_id}", message="placed (demo)")

    def track_shipment(self, fulfillment_id):
        return "shipped"


def main() -> None:
    source, channel = SampleSource(), SampleChannel()
    compliance, margin = ComplianceEngine(), MarginEngine()
    runner = PipelineRunner(source, channel, compliance, margin,
                            evaluator=EvaluationAgent(),
                            content_builder=ContentAgent().build)

    print("=" * 64)
    print(" 1) 소싱 파이프라인  (소싱→컴플→마진→평가→콘텐츠→등록 게이트)")
    print("=" * 64)
    outcomes = runner.run("Best", pricing_channel="naver", fx_rate=FX)
    for o in outcomes:
        ev = f"시장성 {o.evaluation.market_score}" if o.evaluation else "—"
        price = f"{int(o.quote.sale_price_krw):,}원" if o.quote else "—"
        title = o.draft.title_ko if o.draft else "—"
        print(f"  [{o.status.value:14}] {o.source_id} | {price:>9} | {ev:>9} | {title} | {o.note}")

    print("\n" + "=" * 64)
    print(" 2) 발주 가드  (주문 들어옴 → 현재 원본가로 수익 재검증)")
    print("=" * 64)
    proc = OrderProcessor(source, SampleFulfiller(), margin, compliance.customs_type_for)
    order = ChannelOrder("naver", "ORD-001", "NV000001", 1, "홍길동", "enc::pccc",
                         {"zip": "06000"}, datetime.now(timezone.utc))
    ctx = OrderContext("B01", "USD", "8518.30", "naver", Decimal("82900"))
    result = proc.process(order, ctx)
    amz = result.fulfillment.fulfillment_id if result.fulfillment else "-"
    print(f"  주문 {order.channel_order_no} → [{result.status.value}] "
          f"({result.guard.reason}) 예상이익 {int(result.guard.profit_krw):,}원 | 발주 {amz}")

    print("\n" + "=" * 64)
    print(" 3) CS 응대  (자동응답 / 민감건 사람 인계)")
    print("=" * 64)
    cs = CSAgent(fulfiller=SampleFulfiller())
    cs_ctx = CSContext("ORD-001", OrderStatus.SHIPPED, tracking_no="1Z999",
                       fulfillment_id="AMZ-B01")
    for q in ["배송 언제 와요?", "환불하고 싶어요"]:
        r = cs.handle(q, cs_ctx)
        flag = "🧑 사람" if r.escalated else "🤖 자동"
        print(f"  Q: {q}\n     {flag} ({r.intent.value}) → {r.reply}")

    print("\n[demo] 모든 에이전트 mock 모드 — 실 API 키 없이 동작. 실행 끝.")


if __name__ == "__main__":
    main()
