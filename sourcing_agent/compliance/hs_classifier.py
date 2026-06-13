"""HS코드 분류기 — 매핑 우선, 실패 시 (선택) LLM 추정, 그래도 미상이면 REVIEW.

[Why] HS코드가 관세·통관요건을 결정 → 틀리면 마진 붕괴. 돈 직결이라 LLM 단독 신뢰 금지:
      확정 못 하면 사람 검토로 넘긴다.
"""

from __future__ import annotations

from typing import Callable

from sourcing_agent.compliance.models import Verdict
from sourcing_agent.models import SourceProduct

# 카테고리 토큰 → HS코드 추정을 시도하는 외부 콜백(없으면 None). 참고용.
LlmEstimator = Callable[[SourceProduct], str | None]


class HSClassifier:
    def __init__(
        self, hs_map: dict[str, str], llm_estimator: LlmEstimator | None = None
    ) -> None:
        self._map = hs_map
        self._llm = llm_estimator

    def classify(self, product: SourceProduct) -> tuple[str | None, Verdict]:
        """(hs_code, verdict) 반환. verdict=REVIEW면 분류 불확실 → 엔진이 보류 처리."""
        if product.hs_code:                       # 원본이 이미 제공
            return product.hs_code, Verdict.PASS

        for token in product.category_path:        # 사전 매핑
            if token in self._map:
                return self._map[token], Verdict.PASS

        if self._llm is not None:                  # LLM 추정 (참고용)
            guess = self._llm(product)
            if guess:
                return guess, Verdict.REVIEW       # 추정은 확정 아님 → 검토

        return None, Verdict.REVIEW                # 미상 → 사람 검토
