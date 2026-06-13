"""LLM 호출 추상화 — real/mock 자동 전환.

[원칙] LLM 호출은 반드시 이 파일을 거친다(다른 곳에서 anthropic SDK 직접 호출 금지).
[중요] ANTHROPIC_API_KEY 가 없으면 자동으로 mock 모드 → 키 없이도 전체 파이프라인이 돈다.
       real 모드에서 JSON 파싱이 실패해도 예외를 전파하지 않고 휴리스틱으로 graceful degrade.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from jikgugom.evaluation.models import MarketSignals
from jikgugom.evaluation.tools import clamp_score, heuristic_score
from jikgugom.models import SourceProduct

# 시장성 점수는 값싼 분류성 작업 → Haiku로 충분(비용 통제). 정밀 추론 필요 시 상향.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class ScoreResult:
    score: int          # 0~100 (clamp 완료)
    rationale: str
    mode: str           # "mock" | "real"
    degraded: bool      # 휴리스틱 폴백 여부


class LLM:
    """시장성 점수 산출 추상화. mode는 키 유무로 결정."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model
        self.mode = "real" if os.getenv("ANTHROPIC_API_KEY") else "mock"

    def score_market_fit(
        self, product: SourceProduct, signals: MarketSignals
    ) -> ScoreResult:
        if self.mode == "mock":
            return ScoreResult(heuristic_score(signals),
                               "mock: 신호 휴리스틱 점수", "mock", degraded=False)
        try:
            raw = self._call_anthropic(product, signals)
            score, rationale = self._parse(raw)
            return ScoreResult(clamp_score(score), rationale, "real", degraded=False)
        except Exception as e:  # 파싱/네트워크 실패 → 점수를 못 내도 파이프라인은 살린다
            return ScoreResult(heuristic_score(signals),
                               f"real 실패 → 휴리스틱 폴백 ({type(e).__name__})",
                               "real", degraded=True)

    # ── real 모드 내부 ───────────────────────────────────────
    def _call_anthropic(self, product: SourceProduct, signals: MarketSignals) -> str:
        import anthropic  # 지연 import — mock 모드에선 의존성조차 필요 없게

        client = anthropic.Anthropic()
        system = (
            "너는 한국 이커머스 소싱 분석가다. 해외 상품의 '한국 시장 판매 적합성'을 "
            "0~100 점수로 평가한다. 반드시 JSON만 출력: "
            '{"score": <int 0-100>, "rationale": "<한국어 한 문장>"}'
        )
        user = (
            f"상품: {product.title}\n카테고리: {' > '.join(product.category_path)}\n"
            f"평점: {signals.avg_rating}/5 ({signals.review_count}건)\n"
            f"감성: {signals.sentiment} 수요: {signals.demand_index} 경쟁: {signals.competition}"
        )
        msg = client.messages.create(
            model=self._model,
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text

    @staticmethod
    def _parse(raw: str) -> tuple[int, str]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)  # 본문에서 첫 JSON 블록 추출
            if not m:
                raise ValueError("no JSON object in response")
            data = json.loads(m.group(0))
        return int(data["score"]), str(data.get("rationale", ""))
