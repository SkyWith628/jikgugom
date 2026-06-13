"""파이프라인 러너 테스트 — 한 배치가 상태별로 정확히 갈리는지 + 승인 게이트."""

from __future__ import annotations

from decimal import Decimal

import pytest

from sourcing_agent.pipeline import ListingStatus, PipelineConfig, PipelineRunner
from tests.fakes import FakeChannelAdapter, FakeSourceAdapter, make_source_product

FX = Decimal("1380")


def _catalog():
    return [
        make_source_product("OK", title="Wireless Earbuds",
                            category_path=["Best", "Headphones"], price=Decimal("29"),
                            hs_code="8518.30"),                       # PASS → READY
        make_source_product("KC", title="USB Charger",
                            category_path=["Best", "Chargers"], price=Decimal("18")),  # BLOCK
        make_source_product("PB", title="Power Bank 20000mAh",
                            category_path=["Best", "Power Banks"], price=Decimal("25")),  # REVIEW
        make_source_product("EXP", title="Studio Headphones",
                            category_path=["Best", "Headphones"], price=Decimal("300"),
                            hs_code="8518.30"),                       # REVIEW(일반통관)
    ]


def _runner(channel=None):
    return PipelineRunner(FakeSourceAdapter(_catalog()), channel or FakeChannelAdapter())


def _by_id(outcomes):
    return {o.source_id: o for o in outcomes}


def test_run_classifies_each_status():
    out = _by_id(_runner().run("Best", pricing_channel="naver", fx_rate=FX))
    assert out["OK"].status is ListingStatus.READY
    assert out["KC"].status is ListingStatus.BLOCKED
    assert out["PB"].status is ListingStatus.REVIEW
    assert out["EXP"].status is ListingStatus.REVIEW


def test_ready_is_not_published_by_default():
    ch = FakeChannelAdapter()
    out = _by_id(_runner(ch).run("Best", pricing_channel="naver", fx_rate=FX))
    assert out["OK"].draft is not None       # 초안은 만들되
    assert ch.published == {}                 # 발행은 안 함(승인 게이트)


def test_auto_publish_publishes_ready_items():
    ch = FakeChannelAdapter()
    out = _by_id(_runner(ch).run("Best", auto_publish=True, pricing_channel="naver", fx_rate=FX))
    assert out["OK"].status is ListingStatus.PUBLISHED
    assert out["OK"].publish.channel_product_no
    assert len(ch.published) == 1             # PASS분만 발행, BLOCK/REVIEW는 제외


def test_blocked_carries_no_quote():
    out = _by_id(_runner().run("Best", pricing_channel="naver", fx_rate=FX))
    assert out["KC"].quote is None
    assert "KC" in out["KC"].note or "인증" in out["KC"].note


def test_review_carries_quote_for_human():
    out = _by_id(_runner().run("Best", pricing_channel="naver", fx_rate=FX))
    assert out["PB"].quote is not None        # 검토자에게 가격 정보 제공


def test_draft_price_matches_quote():
    out = _by_id(_runner().run("Best", pricing_channel="naver", fx_rate=FX))
    o = out["OK"]
    assert o.draft.price_krw == o.quote.sale_price_krw


def test_margin_rejected_when_floor_too_high():
    runner = PipelineRunner(
        FakeSourceAdapter(_catalog()), FakeChannelAdapter(),
        config=PipelineConfig(min_margin_rate=Decimal("0.99")),
    )
    out = _by_id(runner.run("Best", pricing_channel="naver", fx_rate=FX))
    assert out["OK"].status is ListingStatus.MARGIN_REJECTED


def test_one_bad_item_does_not_block_batch():
    """KC 차단 상품이 있어도 정상 상품은 끝까지 처리된다."""
    out = _by_id(_runner().run("Best", pricing_channel="naver", fx_rate=FX))
    assert out["OK"].status is ListingStatus.READY
    assert len(out) == 4


# ── 평가 에이전트 통합 (stage 2.5) ──────────────────────────
def test_evaluator_attaches_score_to_ready(monkeypatch):
    from sourcing_agent.evaluation import EvaluationAgent
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    catalog = [make_source_product("OK", title="Wireless Earbuds",
                                   category_path=["Best", "Headphones"], price=Decimal("29"),
                                   hs_code="8518.30", attributes={"rating": 4.7, "review_count": 900})]
    runner = PipelineRunner(FakeSourceAdapter(catalog), FakeChannelAdapter(),
                            evaluator=EvaluationAgent())
    [o] = runner.run("Best", pricing_channel="naver", fx_rate=FX)
    assert o.status is ListingStatus.READY
    assert o.evaluation is not None and o.evaluation.market_score >= 0


def test_skip_recommendation_routes_to_review(monkeypatch):
    """시장성 낮은(SKIP) 상품은 자동 READY가 아니라 사람 검토로."""
    from sourcing_agent.evaluation import EvaluationAgent
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    catalog = [make_source_product("DUD", title="Generic Widget",
                                   category_path=["Best", "Misc"], price=Decimal("20"),
                                   hs_code="3926.90", attributes={"rating": 1.5, "review_count": 3})]
    runner = PipelineRunner(FakeSourceAdapter(catalog), FakeChannelAdapter(),
                            evaluator=EvaluationAgent())
    [o] = runner.run("Best", pricing_channel="naver", fx_rate=FX)
    assert o.status is ListingStatus.REVIEW
    assert o.evaluation.recommendation.value == "skip"


def test_no_evaluator_is_backward_compatible():
    """evaluator 미지정 시 평가 없이 기존과 동일하게 동작."""
    [o] = [x for x in _runner().run("Best", pricing_channel="naver", fx_rate=FX)
           if x.source_id == "OK"]
    assert o.status is ListingStatus.READY and o.evaluation is None
