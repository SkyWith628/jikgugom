"""평가 에이전트 입출력 모델 — 시장성 신호와 결과.

이 에이전트는 '돈'을 판단하지 않는다(그건 margin/compliance가 이미 결정론으로 처리).
오직 "한국 시장에서 팔릴까?"라는 정성 점수만 낸다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Recommendation(str, Enum):
    STRONG = "strong"      # 적극 등록 추천
    CONSIDER = "consider"  # 검토 후 등록
    SKIP = "skip"          # 시장성 낮음 → 보류(사람 검토)


@dataclass(frozen=True)
class MarketSignals:
    """도구들이 수집한 시장 신호 (순수 함수 산출 → 재현 가능)."""

    avg_rating: float        # 0~5
    review_count: int
    sentiment: float         # 0~1 (리뷰 감성)
    demand_index: float      # 0~1 (수요/트렌드 추정)
    competition: float       # 0~1 (경쟁 포화도, 높을수록 레드오션)


@dataclass(frozen=True)
class EvaluationResult:
    """평가 결과 — 어드민의 '승인 우선순위'를 돕는 어드바이저 출력."""

    market_score: int            # 0~100 (clamp 보정 완료)
    recommendation: Recommendation
    rationale: str
    signals: MarketSignals
    mode: str                    # "mock" | "real"
    degraded: bool = False       # LLM 실패로 휴리스틱 폴백했는지


def recommend(score: int) -> Recommendation:
    """점수 → 추천 매핑 (결정론적). 돈 게이트가 아니라 우선순위 신호."""
    if score >= 70:
        return Recommendation.STRONG
    if score >= 45:
        return Recommendation.CONSIDER
    return Recommendation.SKIP
