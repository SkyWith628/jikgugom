"""평가 에이전트 도구 — 시장 신호 수집 (순수 함수, 재현 가능).

[원칙] 도구는 같은 입력 → 같은 출력. 현재 일부는 mock(실서비스는 API 연동).
       돈 계산 도구는 여기에 없다 — 마진은 에이전트 바깥의 margin 엔진이 이미 처리.
"""

from __future__ import annotations

from jikgugom.evaluation.models import MarketSignals
from jikgugom.models import SourceProduct


def clamp_score(value: float) -> int:
    """LLM/휴리스틱 점수를 0~100 정수로 보정 (출력 범위 검증)."""
    return max(0, min(100, int(round(value))))


def analyze_review_sentiment(product: SourceProduct) -> float:
    """리뷰 감성 0~1. attributes의 rating/review_count 기반(없으면 중립).

    실서비스: 리뷰 텍스트 감성분석 모델. 여기선 평점·표본수 휴리스틱.
    """
    rating = float(product.attributes.get("rating", 0) or 0)       # 0~5
    count = int(product.attributes.get("review_count", 0) or 0)
    if count == 0:
        return 0.5                                                  # 정보 없음 → 중립
    confidence = min(1.0, count / 200)                              # 표본 적으면 보수적
    base = rating / 5.0
    return round(0.5 + (base - 0.5) * confidence, 4)


def estimate_demand(product: SourceProduct) -> float:
    """수요 지수 0~1 (mock). 리뷰 수를 인기 프록시로 사용.

    실서비스: 네이버 데이터랩/트렌드 API.
    """
    count = int(product.attributes.get("review_count", 0) or 0)
    # 0건→0.0, 1000건 이상→1.0 사이 로그형 근사
    import math
    return round(min(1.0, math.log10(count + 1) / 3.0), 4)


def assess_competition(product: SourceProduct) -> float:
    """경쟁 포화도 0~1 (mock, 결정론적). source_id 해시로 안정적 의사난수.

    실서비스: 네이버 쇼핑 검색결과 수/가격분포.
    """
    seed = sum(ord(c) for c in product.source_id)
    return round((seed % 100) / 100.0, 4)


def collect_signals(product: SourceProduct) -> MarketSignals:
    """모든 도구를 호출해 MarketSignals로 합친다."""
    return MarketSignals(
        avg_rating=float(product.attributes.get("rating", 0) or 0),
        review_count=int(product.attributes.get("review_count", 0) or 0),
        sentiment=analyze_review_sentiment(product),
        demand_index=estimate_demand(product),
        competition=assess_competition(product),
    )


def heuristic_score(signals: MarketSignals) -> int:
    """LLM 없이(또는 LLM 실패 시) 신호로 점수 산출. mock 모드의 기본 + real 폴백.

    감성·수요는 가점, 경쟁은 감점. 가중합 후 0~100 보정.
    """
    raw = (
        signals.sentiment * 45
        + signals.demand_index * 40
        + (1 - signals.competition) * 15
    )
    return clamp_score(raw)
