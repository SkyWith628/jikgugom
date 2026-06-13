# CLAUDE.md — 주문→발주 모듈 (`sourcing_agent/order/`)

채널 주문을 받아 '지금 매입해도 수익이 남는가'를 결정론 가드로 재검증하고,
통과 시에만 자동발주, 아니면 사람 승인 큐로 보낸다 (Phase 2).

## 핵심 원칙

1. **비가역 행동(발주=돈) 앞엔 결정론 가드.** 주문은 과거 가격에 팔렸다. 그 사이
   원본 품절·가격인상이면 자동발주 = 손실 직결. LLM 아님 — 규칙.
2. **가드 = profit_at 재계산.** 고정 판매가 + 현재 원본가로 실수익을 재계산
   (`MarginEngine.profit_at`). 적자/품절/박한마진 → `APPROVAL_REQUIRED`.
3. **순수/부수효과 분리.** `_decide()`는 순수 판정, `process()`만 발주 실행 —
   monitor와 같은 패턴. 가드 통과 주문만 `FulfillmentAdapter`에 도달한다.
4. **멱등 발주.** 같은 주문 중복발주(이중결제) 금지 — 구현체는 멱등키 사용.

## 파일 구조

```
order/
├── models.py     # OrderStatus/GuardAction, OrderContext, OrderGuardResult, OrderOutcome
├── fulfiller.py  # FulfillmentAdapter(ABC): place_order/track_shipment
└── processor.py  # OrderProcessor: evaluate_guard / process(auto_order)
```

## 흐름

```
process(order, ctx):
  check_availability(source)  →  _decide(profit_at 재계산)
     ├ 품절/적자/마진<floor → PENDING_APPROVAL (발주 안 함)
     └ AUTO_ORDER → FulfillmentAdapter.place_order → AMAZON_ORDERED
```

## TODO / 제약

- `FulfillmentAdapter` 구현체 없음: Amazon은 제3자 구매 API가 없어 발주는
  자동화(체크아웃)나 대행 매입으로 구현 → 환경 종속. 계약만 정의.
- 송장 동기화·통관추적(track_shipment 후속)·환불 흐름은 후속.
- PCCC(개인통관고유부호)는 발주 직전 복호화·발주 후 폐기 (개인정보보호법).

## 보안

- PCCC 등 민감정보는 로그 금지. 발주 어댑터 자격증명은 Secrets Manager.
