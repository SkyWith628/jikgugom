"""평가 에이전트 테스트 — mock 모드 결정론 + 점수 보정 + 추천 매핑 + 폴백."""

from __future__ import annotations

from decimal import Decimal

import pytest

from sourcing_agent.evaluation import EvaluationAgent, Recommendation
from sourcing_agent.evaluation.llm import LLM, ScoreResult
from sourcing_agent.evaluation.models import MarketSignals, recommend
from sourcing_agent.evaluation.tools import clamp_score, collect_signals, heuristic_score
from tests.fakes import make_source_product


def test_mock_mode_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert EvaluationAgent().mode == "mock"


def test_evaluate_is_deterministic_in_mock(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    agent = EvaluationAgent()
    p = make_source_product(attributes={"rating": 4.6, "review_count": 800})
    a = agent.evaluate(p)
    b = agent.evaluate(p)
    assert a.market_score == b.market_score          # 같은 입력 → 같은 출력
    assert 0 <= a.market_score <= 100


def test_high_rating_scores_higher_than_low(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    agent = EvaluationAgent()
    good = make_source_product("G", attributes={"rating": 4.8, "review_count": 1000})
    bad = make_source_product("B", attributes={"rating": 2.0, "review_count": 1000})
    assert agent.evaluate(good).market_score > agent.evaluate(bad).market_score


def test_clamp_score_bounds():
    assert clamp_score(-10) == 0
    assert clamp_score(150) == 100
    assert clamp_score(73.6) == 74


def test_recommend_mapping():
    assert recommend(85) is Recommendation.STRONG
    assert recommend(55) is Recommendation.CONSIDER
    assert recommend(20) is Recommendation.SKIP


def test_no_reviews_is_neutral_sentiment():
    p = make_source_product(attributes={})
    s = collect_signals(p)
    assert s.sentiment == 0.5                          # 정보 없음 → 중립


def test_real_mode_falls_back_on_llm_failure(monkeypatch):
    """real 모드에서 LLM 호출이 터져도 휴리스틱으로 graceful degrade(예외 전파 X)."""
    llm = LLM.__new__(LLM)          # __init__ 우회
    llm._model = "x"
    llm.mode = "real"
    monkeypatch.setattr(llm, "_call_anthropic",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    signals = MarketSignals(4.0, 100, 0.7, 0.6, 0.3)
    res = llm.score_market_fit(make_source_product(), signals)
    assert isinstance(res, ScoreResult)
    assert res.degraded is True and res.mode == "real"
    assert res.score == heuristic_score(signals)
