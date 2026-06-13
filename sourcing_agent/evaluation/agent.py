"""소싱 평가 에이전트 — "이 상품이 한국 시장에서 팔릴까?" 자율 판단.

[경계] 돈(마진·적자·통관)은 이미 바깥의 margin/compliance가 결정론으로 거른 뒤다.
       이 에이전트는 그걸 통과한 상품에만 호출되어 '시장성 점수'만 더한다.
       MarginQuote는 참고용 입력일 뿐, 여기서 재계산하지 않는다.

[흐름] 도구로 신호 수집 → LLM(or mock)로 점수 → clamp → 추천 매핑.
       단일 에이전트 선형 흐름이라 LangGraph 없이 구성(멀티에이전트 확장 시 그래프로 승격).
"""

from __future__ import annotations

from sourcing_agent.evaluation.llm import LLM
from sourcing_agent.evaluation.models import EvaluationResult, recommend
from sourcing_agent.evaluation.tools import collect_signals
from sourcing_agent.margin.models import MarginQuote
from sourcing_agent.models import SourceProduct


class EvaluationAgent:
    def __init__(self, llm: LLM | None = None) -> None:
        self._llm = llm or LLM()

    @property
    def mode(self) -> str:
        return self._llm.mode

    def evaluate(
        self, product: SourceProduct, quote: MarginQuote | None = None
    ) -> EvaluationResult:
        """시장성 평가. quote는 맥락 참고용(선택) — 점수 산출에 돈 재계산은 없다."""
        signals = collect_signals(product)
        scored = self._llm.score_market_fit(product, signals)
        return EvaluationResult(
            market_score=scored.score,
            recommendation=recommend(scored.score),
            rationale=scored.rationale,
            signals=signals,
            mode=scored.mode,
            degraded=scored.degraded,
        )
