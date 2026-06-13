# CLAUDE.md — CS 응대 에이전트 (`sourcing_agent/cs/`)

고객 문의를 받아 정보성은 자동응답, 환불·불만 등 민감 건은 사람에게 인계하는 ③번 에이전트.
주문/발주 모듈 위에서 동작한다(주문 사실을 CSContext로 받음).

## 핵심 원칙

1. **에스컬레이션은 결정론 규칙, LLM 아님.** LLM은 의도 분류·문구 작성만.
   환불/불만(돈·법적) + 분류 불확실은 **무조건 사람**. 비가역 판단을 LLM에 위임 금지.
2. **도구는 정보 제공만.** 환불 승인·취소 같은 실행 도구는 없다(사람이 실행).
3. **키 없이도 돈다.** `ANTHROPIC_API_KEY` 없으면 mock(키워드 분류). real 실패 시 폴백.

## 파일 구조

```
cs/
├── models.py   # Intent, CSAction, CSContext, CSResponse
├── tools.py    # 순수함수: 주문상태/배송단계 라벨, 환불정책 검색(간이 KB)
├── llm.py      # 의도 분류 + 응답 초안 (Anthropic/mock)
└── agent.py    # CSAgent.handle(inquiry, context) → CSResponse
```

## 흐름

```
handle(inquiry, ctx):
  classify(LLM/mock)  →  결정론 에스컬레이션 가드
     ├ REFUND/COMPLAINT/UNKNOWN/저신뢰 → ESCALATE (정책 첨부, 사람 인계)
     └ ORDER_STATUS/SHIPPING/GENERAL → 도구로 사실 수집 → AUTO_REPLY
```

## TODO / 제약

- 환불정책은 간이 KB(dict) → 실서비스는 문서 검색/RAG.
- 배송추적은 `FulfillmentAdapter.track_shipment` 주입 시 실시간, 없으면 주문상태.
- 멀티턴 대화·티켓 시스템 연동은 후속(LangGraph 승격 후보).

## 보안

- 응답에 PCCC·결제정보 등 민감정보 노출 금지. API 키는 환경변수.
