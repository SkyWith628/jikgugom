"""네이버 스마트스토어 채널 어댑터 — 커머스 API 구현.

1차 판매 채널. OAuth2(client_credentials + bcrypt 서명) 토큰 → Bearer 호출.
추후 쿠팡 등은 ChannelAdapter를 구현해 나란히 붙인다.

[테스트] 모든 호출은 _api() 단일 메서드를 거친다 → 테스트는 _api를 대체해
네트워크 없이 매핑/분기 로직을 검증한다.
[비밀] client_id/secret은 Secrets Manager 주입. 토큰은 만료 전 자동 갱신(캐시).
[주의] 상품 등록 payload는 네이버 스펙이 방대하다 — 여기선 핵심 필드만 구성하고,
       정확한 필드는 공식 스펙 확인이 필요한 지점을 TODO로 표시.
"""

from __future__ import annotations

import base64
import time
from decimal import Decimal
from typing import Any

from sourcing_agent.adapters._http import AdapterError, request_json
from sourcing_agent.adapters.base import ChannelAdapter
from sourcing_agent.models import (
    ChannelCategory,
    ChannelOrder,
    ListingDraft,
    PublishResult,
    PublishStatus,
)

API_BASE = "https://api.commerce.naver.com/external"


class NaverSmartstoreAdapter(ChannelAdapter):
    name = "naver"

    def __init__(self, client_id: str, client_secret: str, *,
                 timeout: float = 15.0) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout
        self._token: str | None = None
        self._token_exp: float = 0.0

    # ── 인증 ─────────────────────────────────────────────────
    def _sign(self, timestamp_ms: int) -> str:
        """client_secret을 salt로 'client_id_timestamp'를 bcrypt 해시 → base64."""
        import bcrypt  # 지연 import (인증 경로에서만 필요)

        password = f"{self._client_id}_{timestamp_ms}".encode()
        hashed = bcrypt.hashpw(password, self._client_secret.encode())
        return base64.b64encode(hashed).decode()

    def _access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_exp - 30:   # 만료 30s 전까지 재사용
            return self._token
        ts = int(now * 1000)
        data = request_json(
            f"{API_BASE}/v1/oauth2/token",
            method="POST",
            form_body={
                "client_id": self._client_id,
                "timestamp": ts,
                "grant_type": "client_credentials",
                "client_secret_sign": self._sign(ts),
                "type": "SELF",
            },
            timeout=self._timeout,
        )
        self._token = data["access_token"]
        self._token_exp = now + int(data.get("expires_in", 3600))
        return self._token

    def _api(self, method: str, path: str, *, body: Any | None = None,
             params: dict | None = None) -> dict:
        """인증된 단일 호출 경유점. 테스트는 이 메서드를 대체한다."""
        return request_json(
            f"{API_BASE}{path}",
            method=method,
            params=params,
            json_body=body,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=self._timeout,
        )

    # ── 계약 구현 ────────────────────────────────────────────
    def map_category(self, source_category_path: list[str]) -> ChannelCategory:
        # 네이버 카테고리 검색 API로 매핑(말단 카테고리명 기준)
        leaf = source_category_path[-1] if source_category_path else ""
        data = self._api("GET", "/v1/categories", params={"name": leaf})
        cats = data.get("category") or data.get("categories") or []
        if not cats:
            raise AdapterError(f"no naver category matched: {leaf}")
        top = cats[0]
        return ChannelCategory(
            channel_category_id=str(top.get("id") or top.get("categoryId")),
            channel_category_name=top.get("name") or top.get("wholeCategoryName", leaf),
            confidence=1.0 if len(cats) == 1 else 0.5,
        )

    def publish(self, draft: ListingDraft) -> PublishResult:
        payload = self._build_product_payload(draft)
        try:
            data = self._api("POST", "/v2/products", body=payload)
        except AdapterError as e:
            return PublishResult(PublishStatus.REJECTED, None, str(e))
        no = data.get("originProductNo") or data.get("smartstoreChannelProductNo")
        if not no:
            return PublishResult(PublishStatus.PENDING, None, "no product no in response")
        return PublishResult(PublishStatus.LISTED, str(no))

    def update_price(self, channel_product_no: str, price_krw: Decimal) -> None:
        # 원상품 가격 변경 (PATCH origin-products/{no})
        self._api(
            "PATCH", f"/v2/products/origin-products/{channel_product_no}",
            body={"originProduct": {"salePrice": int(price_krw)}},
        )

    def pause(self, channel_product_no: str) -> None:
        self._set_status(channel_product_no, "SUSPENSION")

    def resume(self, channel_product_no: str) -> None:
        self._set_status(channel_product_no, "SALE")

    def fetch_orders(self, *, since: str | None = None) -> list[ChannelOrder]:
        params = {"lastChangedFrom": since} if since else None
        data = self._api("GET", "/v1/pay-order/seller/product-orders", params=params)
        contents = (data.get("data") or {}).get("contents") or data.get("contents") or []
        return [self._map_order(c) for c in contents]

    # ── 내부 ─────────────────────────────────────────────────
    def _set_status(self, no: str, status_type: str) -> None:
        # SALE(판매중) / SUSPENSION(판매중지) 전환
        self._api(
            "PATCH", f"/v2/products/origin-products/{no}",
            body={"originProduct": {"statusType": status_type}},
        )

    @staticmethod
    def _build_product_payload(draft: ListingDraft) -> dict:
        # TODO: 네이버 상품등록 스펙 전체 반영(배송/AS/원산지/옵션 등). 현재 핵심만.
        return {
            "originProduct": {
                "statusType": "SALE",
                "saleType": "NEW",
                "leafCategoryId": draft.category.channel_category_id,
                "name": draft.title_ko,
                "detailContent": draft.description_html,
                "salePrice": int(draft.price_krw),
                "stockQuantity": 999,  # 무재고 → 충분히 큰 값(품절은 모니터가 pause)
                "images": {
                    "representativeImage": {"url": draft.image_urls_cdn[0]}
                    if draft.image_urls_cdn else None,
                    "optionalImages": [{"url": u} for u in draft.image_urls_cdn[1:]],
                },
            },
        }

    @staticmethod
    def _map_order(content: dict) -> ChannelOrder:
        order = content.get("order", {}) or {}
        po = content.get("productOrder", {}) or {}
        ship = po.get("shippingAddress", {}) or {}
        return ChannelOrder(
            channel="naver",
            channel_order_no=str(order.get("orderId") or po.get("orderId", "")),
            channel_product_no=str(po.get("originProductNo") or po.get("productId", "")),
            quantity=int(po.get("quantity", 1)),
            buyer_name=order.get("ordererName", ""),
            # 개인통관고유부호(PCCC) — 저장 계층에서 암호화(개인정보보호법). 어댑터는 전달만.
            buyer_pccc_encrypted=ship.get("personalCustomsClearanceCode", ""),
            shipping_address=ship,
            ordered_at=order.get("orderDate"),
        )
