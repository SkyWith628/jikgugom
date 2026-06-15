"""CS LLM 추상화 — 의도 분류 + 응답 초안 (real=Gemini / mock 자동 전환).

[원칙] LLM 호출은 이 파일 경유. 키 없으면 mock. 파싱 실패 시 mock 폴백.
[경계] LLM은 '의도 분류'와 '문구 작성'만. 에스컬레이션 여부(돈/민감)는 agent의 결정론 규칙.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from jikgugom.core.gemini import gemini_available, generate_text
from jikgugom.cs.models import Intent

# mock 의도 분류 키워드 (민감 의도 우선 검사)
_INTENT_KEYWORDS: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.COMPLAINT, ("불량", "파손", "하자", "망가", "최악", "broken", "damaged", "defective")),
    (Intent.REFUND, ("환불", "반품", "취소", "refund", "return", "cancel")),
    (Intent.SHIPPING, ("배송", "언제", "도착", "송장", "추적", "shipping", "track", "delivery")),
    (Intent.ORDER_STATUS, ("주문", "상태", "확인", "order", "status")),
]


@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    confidence: float
    mode: str


class CSLLM:
    def __init__(self, model: str | None = None) -> None:
        self._model = model   # None이면 Gemini 기본 모델
        self.mode = "real" if gemini_available() else "mock"

    def classify(self, inquiry: str) -> IntentResult:
        if self.mode == "mock":
            return self._mock_classify(inquiry)
        try:
            intent, conf = self._real_classify(inquiry)
            return IntentResult(intent, conf, "real")
        except Exception:
            res = self._mock_classify(inquiry)
            return IntentResult(res.intent, res.confidence, "real")  # 폴백(분류는 mock)

    def draft_reply(self, intent: Intent, facts: str) -> str:
        """정보성 응답 문구 — mock은 facts를 그대로 안내. real은 다듬어 작성."""
        if self.mode == "mock":
            return facts
        try:
            return self._real_reply(intent, facts)
        except Exception:
            return facts

    # ── mock ─────────────────────────────────────────────────
    @staticmethod
    def _mock_classify(inquiry: str) -> IntentResult:
        for intent, keys in _INTENT_KEYWORDS:
            if any(k in inquiry for k in keys):
                return IntentResult(intent, 0.9, "mock")
        return IntentResult(Intent.UNKNOWN, 0.3, "mock")

    # ── real (Gemini) ────────────────────────────────────────
    def _real_classify(self, inquiry: str) -> tuple[Intent, float]:
        labels = ", ".join(i.value for i in Intent)
        system = (
            "고객 문의를 다음 의도 중 하나로 분류한다: " + labels + ". "
            'JSON만 출력: {"intent": "<label>", "confidence": <0~1>}'
        )
        raw = generate_text(system, inquiry, model=self._model,
                            max_tokens=64, json_output=True)
        data = self._parse(raw)
        return Intent(data["intent"]), float(data.get("confidence", 0.5))

    def _real_reply(self, intent: Intent, facts: str) -> str:
        system = "너는 친절한 한국어 CS 상담원이다. 주어진 사실만 근거로 1~2문장으로 답한다."
        return generate_text(system, f"의도:{intent.value}\n사실:{facts}",
                             model=self._model, max_tokens=200)

    @staticmethod
    def _parse(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                raise ValueError("no JSON in response")
            return json.loads(m.group(0))
