# CLAUDE.md — 주문→발주 모듈 (`jikgugom/order/`)

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
├── models.py     # OrderStatus/GuardAction, OrderContext, OrderGuardResult, OrderOutcome,
│                 #   FulfillmentStatus, FulfillmentRecord(원장 한 줄)
├── fulfiller.py  # FulfillmentAdapter(ABC): place_order(idempotency_key=)/track_shipment
├── ledger.py     # FulfillmentLedger(ABC) + InMemoryFulfillmentLedger (멱등 저장 포트)
├── manual.py     # ManualFulfiller: 반자동(HITL) 실구현 — 원장 기록→운영자 confirm
└── processor.py  # OrderProcessor: evaluate_guard / process(auto_order)
```

## 흐름

```
process(order, ctx):
  check_availability(source)  →  _decide(profit_at 재계산)
     ├ 품절/적자/마진<floor → PENDING_APPROVAL (발주 안 함)
     └ AUTO_ORDER → FulfillmentAdapter.place_order → AMAZON_ORDERED
```

## 발주 방식 (반자동 / HITL)

Amazon은 제3자 공개 구매 API가 없다 → 브라우저 자동결제는 ToS 위반·취약.
'돈=사람 게이트' 원칙대로 **반자동(HITL)** 으로 구현: `ManualFulfiller`.

```
place_order(idempotency_key=channel_order_no)
  ├ 원장에 키 있음 → 기존 결과 반환 (멱등: 재매입 없음)
  └ 없음 → AWAITING_PURCHASE 기록 → 운영자가 confirm_purchase로 실매입 확정
       └ confirm_purchase(amazon_order_no, tracking_no) → PURCHASED
       └ update_shipment(status) → shipped/customs/delivered
```

- **멱등키 = `channel_order_no`.** 같은 채널주문은 영원히 한 번만 매입(이중결제 금지).
  계약(`place_order`)이 `idempotency_key`를 필수로 받는다.
- 영속 원장(SqlFulfillmentLedger)은 운영 관심사라 api/에 둘 것(현재 InMemory만).

## TODO / 제약

- 운영자 confirm을 대시보드 UI/외부 구매대행 서비스 webhook과 연결(현재 메서드만).
- 환불·취소 흐름(CANCELLED)·통관추적 동기화는 후속.
- PCCC(개인통관고유부호)는 발주 직전 복호화·발주 후 폐기 (개인정보보호법).
  원장에 PCCC·결제정보 저장 금지(`FulfillmentRecord`는 source_id/qty/상태만).

## 보안

- PCCC 등 민감정보는 로그 금지. 발주 어댑터 자격증명은 Secrets Manager.
