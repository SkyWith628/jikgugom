"""AliExpress 소스 어댑터 — 제휴(Affiliate) Open Platform API.

드롭십(무재고) 소싱의 표준 소스. 아마존(Rainforest)을 대체하는 1차 소스로,
SourceAdapter 계약만 지키면 파이프라인은 무변경으로 갈아끼워진다.

[테스트] 모든 외부 호출은 _request() 단일 메서드를 거친다 → 테스트는 _request를
         카드(canned) 응답으로 대체해 네트워크 없이 매핑 로직(_map_*)만 검증한다.
[서명] app_secret은 요청에 실리지 않고 sign 계산에만 쓰인다(HMAC-SHA256, stdlib).
[비밀] app_key/secret은 Secrets Manager 주입. 코드·깃 커밋 금지.
[주의] AliExpress 게이트웨이는 지역(SG/Global) 변형이 있어, 정확한 endpoint·서명은
       발급받은 앱 콘솔 문서로 확인 권장. 매핑 로직은 테스트로 고정돼 있다.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from jikgugom.adapters._http import AdapterError, request_json
from jikgugom.adapters.base import SourceAdapter
from jikgugom.models import AvailabilitySnapshot, SourceProduct

GATEWAY = "https://api-sg.aliexpress.com/sync"


class AliExpressAdapter(SourceAdapter):
    name = "aliexpress"

    def __init__(self, app_key: str, app_secret: str, *, tracking_id: str = "default",
                 currency: str = "USD", language: str = "EN", ship_to: str = "KR",
                 timeout: float = 15.0) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._tracking_id = tracking_id      # 제휴 추적 ID(PID) — 제휴 API 필수
        self._currency = currency            # 가격 통화(target_currency)
        self._language = language
        self._ship_to = ship_to              # 한국 배송가 기준
        self._timeout = timeout

    # ── 단일 네트워크 경유점 (테스트는 이걸 대체) ────────────
    def _request(self, method: str, params: dict[str, Any]) -> dict:
        common = {
            "app_key": self._app_key,
            "method": method,
            "timestamp": str(int(time.time() * 1000)),  # epoch ms
            "sign_method": "sha256",
            "format": "json",
            "v": "2.0",
            **{k: str(v) for k, v in params.items()},
        }
        common["sign"] = self._sign(common)
        data = request_json(GATEWAY, params=common, timeout=self._timeout)
        return self._unwrap(method, data)

    def _sign(self, params: dict[str, str]) -> str:
        """HMAC-SHA256(secret, 정렬된 key+value 연결) 대문자 hex. (TOP/IOP 표준)"""
        base = "".join(f"{k}{params[k]}" for k in sorted(params) if k != "sign")
        return hmac.new(self._app_secret.encode(), base.encode(),
                        hashlib.sha256).hexdigest().upper()

    @staticmethod
    def _unwrap(method: str, data: dict) -> dict:
        """게이트웨이 응답 래퍼를 벗겨 resp_result.result를 돌려준다(에러는 변환)."""
        if "error_response" in data:
            err = data["error_response"]
            raise AdapterError(f"aliexpress error: {err.get('msg') or err}",
                               status=err.get("code"))
        root = data.get(method.replace(".", "_") + "_response", data)
        rr = root.get("resp_result", root)
        if rr.get("resp_code") not in (None, 200, "200"):
            raise AdapterError(f"aliexpress resp_code {rr.get('resp_code')}: {rr.get('resp_msg')}")
        return rr.get("result") or {}

    @staticmethod
    def _products(result: dict) -> list[dict]:
        return (result.get("products") or {}).get("product") or []

    # ── 계약 구현 ────────────────────────────────────────────
    def fetch_bestsellers(self, category: str, *, limit: int = 50) -> list[SourceProduct]:
        # category 문자열을 검색 키워드로 사용(실운영: SOURCING_CATEGORY=키워드 권장)
        result = self._request("aliexpress.affiliate.product.query", {
            "keywords": category, "page_size": min(limit, 50), "page_no": 1,
            **self._target_params(),
        })
        return [self._map(p, [category]) for p in self._products(result)[:limit]]

    def get_product(self, source_id: str) -> SourceProduct:
        return self._map(self._detail(source_id))

    def check_availability(self, source_id: str) -> AvailabilitySnapshot:
        p = self._detail(source_id)
        price, currency = self._price(p)
        return AvailabilitySnapshot(
            source_id=source_id, price=price, currency=currency,
            in_stock=price > 0,            # 제휴 API엔 명시적 재고 플래그 없음 → 가격 유무로 근사
            captured_at=datetime.now(timezone.utc))

    # ── 내부 ─────────────────────────────────────────────────
    def _detail(self, source_id: str) -> dict:
        result = self._request("aliexpress.affiliate.productdetail.get", {
            "product_ids": source_id, **self._target_params()})
        products = self._products(result)
        if not products:
            raise AdapterError(f"aliexpress: no product for {source_id}")
        return products[0]

    def _target_params(self) -> dict[str, str]:
        return {"target_currency": self._currency, "target_language": self._language,
                "ship_to_country": self._ship_to, "tracking_id": self._tracking_id}

    # ── 매핑 (순수, 테스트 대상) ─────────────────────────────
    @classmethod
    def _map(cls, p: dict, category_fallback: list[str] | None = None) -> SourceProduct:
        price, currency = cls._price(p)
        cats = [p.get("first_level_category_name"), p.get("second_level_category_name")]
        category_path = [c for c in cats if c] or (category_fallback or [])
        return SourceProduct(
            source="aliexpress",
            source_id=str(p.get("product_id", "")),
            title=p.get("product_title", ""),
            description=p.get("product_title", ""),   # 제휴 API엔 상세 본문이 없음 → 제목 패스스루
            category_path=category_path,
            price=price,
            currency=currency,
            image_urls=cls._images(p),
            brand=None,                               # 제휴 응답에 브랜드 없음
            hs_code=None,
            attributes={
                "rating": cls._rating(p.get("evaluate_rate")),
                "review_count": int(p.get("lastest_volume") or p.get("volume") or 0),
            },
            raw_data=p,
        )

    @staticmethod
    def _price(p: dict) -> tuple[Decimal, str]:
        value = p.get("target_sale_price") or p.get("sale_price") or p.get("target_app_sale_price")
        currency = p.get("target_sale_price_currency") or "USD"
        return (Decimal(str(value)) if value else Decimal(0), currency)

    @staticmethod
    def _images(p: dict) -> list[str]:
        imgs: list[str] = []
        if p.get("product_main_image_url"):
            imgs.append(p["product_main_image_url"])
        imgs += (p.get("product_small_image_urls") or {}).get("string", [])
        return imgs

    @staticmethod
    def _rating(evaluate_rate: str | None) -> float:
        """'95.0%' → 4.8 (0~5 환산). 평가율이 없으면 0."""
        if not evaluate_rate:
            return 0.0
        try:
            pct = float(str(evaluate_rate).rstrip("%"))
        except ValueError:
            return 0.0
        return round(pct / 20, 1)
