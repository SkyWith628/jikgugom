"""CS 도구 — 주문상태 포맷/배송단계/환불정책 검색 (순수 함수).

돈 실행 도구는 없다(환불 승인은 사람). 도구는 '정보 제공'만.
"""

from __future__ import annotations

from jikgugom.order.models import OrderStatus

# 주문 상태 → 한국어 라벨
STATUS_LABEL: dict[OrderStatus, str] = {
    OrderStatus.RECEIVED: "주문 접수",
    OrderStatus.PENDING_APPROVAL: "주문 확인 중",
    OrderStatus.AMAZON_ORDERED: "해외 발주 완료",
    OrderStatus.SHIPPED: "배송 중",
    OrderStatus.CUSTOMS: "통관 중",
    OrderStatus.DELIVERED: "배송 완료",
    OrderStatus.REFUND_REQUESTED: "환불 접수",
    OrderStatus.REFUNDED: "환불 완료",
}

# 배송 원시 단계(track_shipment) → 한국어
SHIPMENT_LABEL: dict[str, str] = {
    "ordered": "발주 완료", "shipped": "배송 중",
    "customs": "통관 중", "delivered": "배송 완료",
}

# 환불 정책 간이 지식베이스 (실서비스: 문서 검색/RAG)
REFUND_POLICY = [
    {"keys": ["단순", "변심", "취소"],
     "text": "단순 변심 반품은 수령 후 7일 이내 가능하며 왕복 배송비는 고객 부담입니다(해외배송 특성상 반품비가 큽니다)."},
    {"keys": ["불량", "파손", "하자", "오배송"],
     "text": "상품 불량/파손/오배송은 사진 확인 후 전액 환불 또는 재발송하며 배송비는 当사 부담입니다."},
    {"keys": ["통관", "관세"],
     "text": "통관 진행 후에는 반품 시 이미 부과된 관세·부가세 환급이 어려울 수 있습니다."},
]


def label_status(status: OrderStatus) -> str:
    return STATUS_LABEL.get(status, "확인 중")


def label_shipment(raw_phase: str) -> str:
    return SHIPMENT_LABEL.get(raw_phase, raw_phase)


def search_refund_policy(query: str) -> str:
    """질문과 가장 많이 겹치는 정책 항목 반환 (없으면 기본 안내)."""
    best, best_hits = None, 0
    for item in REFUND_POLICY:
        hits = sum(1 for k in item["keys"] if k in query)
        if hits > best_hits:
            best, best_hits = item, hits
    if best is None:
        return "반품/환불은 상품 상태와 통관 단계에 따라 정책이 다릅니다. 담당자가 확인해 드립니다."
    return best["text"]
