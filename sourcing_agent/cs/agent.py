"""CS 응대 에이전트 — 고객 문의 자동응대 + 민감 건 사람 인계.

[경계] LLM은 의도 분류·문구 작성만. **에스컬레이션 여부는 결정론 규칙**:
       환불/불만(돈·법적) + 분류 불확실은 무조건 사람. 비가역 판단을 LLM에 위임하지 않는다.
[흐름] classify(LLM) → 결정론 에스컬레이션 가드 → 정보성이면 도구로 답변 초안.
"""

from __future__ import annotations

from sourcing_agent.cs.llm import CSLLM
from sourcing_agent.cs.models import CSAction, CSContext, CSResponse, Intent
from sourcing_agent.cs.tools import label_shipment, label_status, search_refund_policy
from sourcing_agent.order.fulfiller import FulfillmentAdapter

# 항상 사람에게 넘기는 민감 의도 (돈·법적 책임)
_SENSITIVE = {Intent.REFUND, Intent.COMPLAINT}
_MIN_CONFIDENCE = 0.5


class CSAgent:
    def __init__(self, llm: CSLLM | None = None,
                 fulfiller: FulfillmentAdapter | None = None) -> None:
        self._llm = llm or CSLLM()
        self._fulfiller = fulfiller   # 있으면 실시간 배송추적

    @property
    def mode(self) -> str:
        return self._llm.mode

    def handle(self, inquiry: str, context: CSContext) -> CSResponse:
        cls = self._llm.classify(inquiry)

        # ── 결정론 에스컬레이션 가드 (LLM 아님) ──────────────
        if (cls.intent in _SENSITIVE or cls.intent is Intent.UNKNOWN
                or cls.confidence < _MIN_CONFIDENCE):
            reason = ("sensitive_intent" if cls.intent in _SENSITIVE
                      else "low_confidence")
            policy = search_refund_policy(inquiry) if cls.intent is Intent.REFUND else None
            return CSResponse(
                intent=cls.intent, action=CSAction.ESCALATE,
                reply="문의 주셔서 감사합니다. 담당자가 확인 후 빠르게 연락드리겠습니다.",
                escalated=True, mode=cls.mode,
                escalation_reason=reason, policy_snippet=policy,
            )

        # ── 정보성 → 도구로 사실 수집 후 응답 초안 ───────────
        facts = self._facts(cls.intent, context)
        reply = self._llm.draft_reply(cls.intent, facts)
        return CSResponse(intent=cls.intent, action=CSAction.AUTO_REPLY,
                          reply=reply, escalated=False, mode=cls.mode)

    def _facts(self, intent: Intent, ctx: CSContext) -> str:
        if intent is Intent.SHIPPING:
            if self._fulfiller and ctx.fulfillment_id:
                phase = label_shipment(self._fulfiller.track_shipment(ctx.fulfillment_id))
                track = f" (송장 {ctx.tracking_no})" if ctx.tracking_no else ""
                return f"주문 {ctx.order_no} 배송 상태는 '{phase}'입니다{track}."
            return f"주문 {ctx.order_no}은 현재 '{label_status(ctx.order_status)}' 단계입니다."
        # ORDER_STATUS / GENERAL
        return f"주문 {ctx.order_no}은 현재 '{label_status(ctx.order_status)}' 상태입니다."
