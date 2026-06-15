"""AliExpress 어댑터 테스트 — 네트워크 없이 매핑/서명/언래핑 검증.

전략: 외부 호출은 _request 단일 메서드를 거치므로 카드(canned) 응답으로 대체해
순수 매핑 로직만 테스트한다(다른 real 어댑터와 동일 패턴).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from jikgugom.adapters._http import AdapterError
from jikgugom.adapters.aliexpress import AliExpressAdapter

# productdetail.get / product.query 가 공통으로 쓰는 result.products.product 모양
PRODUCT = {
    "product_id": 1005001234567890,
    "product_title": "Wireless Earbuds Bluetooth 5.3",
    "product_main_image_url": "https://ae.com/main.jpg",
    "product_small_image_urls": {"string": ["https://ae.com/1.jpg", "https://ae.com/2.jpg"]},
    "target_sale_price": "12.34",
    "target_sale_price_currency": "USD",
    "first_level_category_name": "Consumer Electronics",
    "second_level_category_name": "Earphones",
    "evaluate_rate": "95.0%",
    "lastest_volume": 870,
}


def _adapter(result):
    a = AliExpressAdapter("ak", "as", tracking_id="pid")
    a._request = lambda method, params: result        # type: ignore[method-assign]
    return a


def _result(*products):
    return {"products": {"product": list(products)}}


def test_get_product_maps_fields():
    p = _adapter(_result(PRODUCT)).get_product("1005001234567890")
    assert p.source == "aliexpress" and p.source_id == "1005001234567890"
    assert p.title.startswith("Wireless Earbuds")
    assert p.price == Decimal("12.34") and p.currency == "USD"
    assert p.category_path == ["Consumer Electronics", "Earphones"]
    assert len(p.image_urls) == 3                      # main + small 2
    assert p.attributes["rating"] == 4.8               # 95% → 4.8
    assert p.attributes["review_count"] == 870


def test_bestsellers_uses_keyword_fallback_category():
    minimal = {**PRODUCT, "first_level_category_name": None,
               "second_level_category_name": None}
    items = _adapter(_result(minimal)).fetch_bestsellers("이어폰", limit=10)
    assert len(items) == 1
    assert items[0].category_path == ["이어폰"]         # 카테고리명 없으면 검색어로 폴백


def test_check_availability_in_stock_when_priced():
    snap = _adapter(_result(PRODUCT)).check_availability("1005001234567890")
    assert snap.in_stock is True and snap.price == Decimal("12.34")


def test_check_availability_out_of_stock_when_no_price():
    no_price = {**PRODUCT, "target_sale_price": None, "sale_price": None,
                "target_app_sale_price": None}
    snap = _adapter(_result(no_price)).check_availability("x")
    assert snap.in_stock is False and snap.price == Decimal(0)


def test_missing_product_raises():
    with pytest.raises(AdapterError):
        _adapter(_result()).get_product("nope")


def test_sign_is_stable_and_uppercase_hex():
    a = AliExpressAdapter("ak", "secret")
    params = {"app_key": "ak", "method": "m", "timestamp": "123", "b": "2", "a": "1"}
    s1 = a._sign(params)
    s2 = a._sign(params)
    assert s1 == s2 and s1 == s1.upper() and len(s1) == 64   # sha256 hex


def test_unwrap_raises_on_error_response():
    a = AliExpressAdapter("ak", "as")
    with pytest.raises(AdapterError):
        a._unwrap("aliexpress.affiliate.productdetail.get",
                  {"error_response": {"code": 15, "msg": "invalid signature"}})
