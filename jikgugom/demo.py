"""실행 가능한 데모 — 키 유무에 따라 mock/real로 전체 흐름을 한 번에 본다.

    python -m jikgugom.demo

소싱→컴플라이언스→마진→평가→콘텐츠→등록(승인 게이트)→ 발주 가드 → CS 응대까지
한 줄로 흘려본다. 환경변수(.env)에 키가 있으면 해당 레이어는 자동으로 real로 붙는다
(없으면 mock). 어댑터 선택은 build_adapters 팩토리가 담당한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from jikgugom.adapters.factory import build_adapters
from jikgugom.content import ContentAgent
from jikgugom.compliance import ComplianceEngine
from jikgugom.core import llm_modes, load_settings
from jikgugom.cs import CSAgent, CSContext
from jikgugom.evaluation import EvaluationAgent
from jikgugom.margin import MarginEngine
from jikgugom.models import ChannelOrder
from jikgugom.order import OrderContext, OrderProcessor
from jikgugom.order.models import OrderStatus
from jikgugom.pipeline import PipelineRunner
from jikgugom.samples import SampleFulfiller


def main() -> None:
    settings = load_settings()
    settings.validate()
    adapters = build_adapters(settings)
    source = adapters.source
    channel = next((c for c in adapters.channels if c.name == settings.primary_channel),
                   adapters.channels[0])
    modes = {**adapters.modes, **llm_modes(settings)}
    fx = settings.fx_rate

    print(f"[demo] 모드: {modes} | FX={fx} | 채널={list(settings.channels)}")
    compliance, margin = ComplianceEngine(), MarginEngine()
    runner = PipelineRunner(source, channel, compliance, margin,
                            evaluator=EvaluationAgent(),
                            content_builder=ContentAgent().build)

    print("=" * 64)
    print(" 1) 소싱 파이프라인  (소싱→컴플→마진→평가→콘텐츠→등록 게이트)")
    print("=" * 64)
    outcomes = runner.run(settings.sourcing_category,
                          pricing_channel=channel.name, fx_rate=fx)
    for o in outcomes:
        ev = f"시장성 {o.evaluation.market_score}" if o.evaluation else "—"
        price = f"{int(o.quote.sale_price_krw):,}원" if o.quote else "—"
        title = o.draft.title_ko if o.draft else "—"
        print(f"  [{o.status.value:14}] {o.source_id} | {price:>9} | {ev:>9} | {title} | {o.note}")

    print("\n" + "=" * 64)
    print(" 2) 발주 가드  (주문 들어옴 → 현재 원본가로 수익 재검증)")
    print("=" * 64)
    # 방금 소싱된 상품 중 가격이 산출된 첫 건으로 발주 가드를 시연(real 소스에서도 동작)
    priced = next((o for o in outcomes if o.quote is not None), None)
    if priced is None:
        print("  (가격 산출된 상품이 없어 발주 가드 데모를 건너뜁니다)")
    else:
        proc = OrderProcessor(source, SampleFulfiller(), margin, compliance.customs_type_for)
        order = ChannelOrder("naver", "ORD-001", "NV000001", 1, "홍길동", "enc::pccc",
                             {"zip": "06000"}, datetime.now(timezone.utc))
        sp = source.get_product(priced.source_id)
        ctx = OrderContext(priced.source_id, sp.currency, sp.hs_code, channel.name,
                           Decimal(priced.quote.sale_price_krw))
        result = proc.process(order, ctx)
        amz = result.fulfillment.fulfillment_id if result.fulfillment else "-"
        print(f"  주문 {order.channel_order_no} ({priced.source_id}) → [{result.status.value}] "
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

    print(f"\n[demo] 끝. 현재 모드: {modes} (키 없으면 mock, 있으면 real 자동 전환)")


if __name__ == "__main__":
    main()
