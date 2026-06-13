"""실행 가능한 데모 — 키 없이 전체 흐름을 한 번에 본다.

    python -m sourcing_agent.demo

샘플 카탈로그(인메모리)로 소싱→컴플라이언스→마진→평가→콘텐츠→등록(승인 게이트)
→ 발주 가드 → CS 응대까지 한 줄로 흘려본다. 모든 에이전트는 mock 모드.
실제 운영은 아래 SampleSource/SampleChannel을 실 어댑터로 교체(README '실행' 참고).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sourcing_agent.content import ContentAgent
from sourcing_agent.compliance import ComplianceEngine
from sourcing_agent.cs import CSAgent, CSContext
from sourcing_agent.evaluation import EvaluationAgent
from sourcing_agent.margin import MarginEngine
from sourcing_agent.models import ChannelOrder
from sourcing_agent.order import OrderContext, OrderProcessor
from sourcing_agent.order.models import OrderStatus
from sourcing_agent.pipeline import PipelineRunner
from sourcing_agent.samples import SampleChannel, SampleFulfiller, SampleSource

FX = Decimal("1380")


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
