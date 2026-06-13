"""실 어댑터 테스트 — 네트워크 없이 매핑/인증/분기 검증.

전략: 모든 외부 호출은 _request(Amazon)/_api(Naver) 단일 메서드를 거치므로,
그 메서드를 카드(canned) 응답으로 대체해 순수 매핑 로직만 테스트한다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from jikgugom.adapters._http import AdapterError
from jikgugom.adapters.amazon import AmazonRainforestAdapter
from jikgugom.adapters.naver import NaverSmartstoreAdapter
from jikgugom.models import PublishStatus

# ── Rainforest 카드 응답 ────────────────────────────────────
PRODUCT = {
    "product": {
        "asin": "B07X", "title": "Wireless Earbuds", "brand": "Acme",
        "rating": 4.6, "ratings_total": 1200,
        "categories": [{"name": "Electronics"}, {"name": "Headphones"}],
        "main_image": {"link": "https://m.media-amazon.com/x.jpg"},
        "images": [{"link": "https://m.media-amazon.com/x.jpg"},
                   {"link": "https://m.media-amazon.com/y.jpg"}],
        "feature_bullets": ["Fast charging", "Noise cancel"],
        "buybox_winner": {"price": {"value": 29.99, "currency": "USD"},
                          "availability": {"raw": "In Stock."}},
    }
}
BESTSELLERS = {"bestsellers": [
    {"asin": "B01", "title": "Top Item", "image": "https://img/1.jpg",
     "price": {"value": 19.99, "currency": "USD"}},
]}


def _amazon(canned):
    a = AmazonRainforestAdapter("key")
    a._request = lambda params: canned          # type: ignore[method-assign]
    return a


def test_amazon_get_product_maps_fields():
    p = _amazon(PRODUCT).get_product("B07X")
    assert p.source == "amazon" and p.source_id == "B07X"
    assert p.title == "Wireless Earbuds" and p.brand == "Acme"
    assert p.price == Decimal("29.99") and p.currency == "USD"
    assert p.category_path == ["Electronics", "Headphones"]
    assert len(p.image_urls) == 2
    assert p.attributes["review_count"] == 1200


def test_amazon_availability_in_stock():
    snap = _amazon(PRODUCT).check_availability("B07X")
    assert snap.in_stock is True and snap.price == Decimal("29.99")


def test_amazon_availability_out_of_stock():
    oos = {"product": {**PRODUCT["product"],
                       "buybox_winner": {"price": {"value": 29.99, "currency": "USD"},
                                         "availability": {"raw": "Currently out of stock."}}}}
    assert _amazon(oos).check_availability("B07X").in_stock is False


def test_amazon_bestsellers_mapping():
    items = _amazon(BESTSELLERS).fetch_bestsellers("172282", limit=10)
    assert len(items) == 1
    assert items[0].source_id == "B01" and items[0].price == Decimal("19.99")
    assert items[0].category_path == ["172282"]


# ── Naver: _api 레코더로 대체 ───────────────────────────────
class ApiRecorder:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __call__(self, method, path, *, body=None, params=None):
        self.calls.append((method, path, body, params))
        for key, val in self.responses.items():
            if key in path:
                if isinstance(val, Exception):
                    raise val
                return val
        return {}


def _naver(responses=None):
    n = NaverSmartstoreAdapter("cid", "csecret")
    rec = ApiRecorder(responses)
    n._api = rec                                # type: ignore[method-assign]
    return n, rec


def _draft():
    from jikgugom.models import ChannelCategory, ListingDraft
    return ListingDraft(
        product_id="amazon:B07X", title_ko="무선 이어폰",
        description_html="<p>좋음</p>", image_urls_cdn=["https://cdn/a.jpg", "https://cdn/b.jpg"],
        price_krw=Decimal("39000"),
        category=ChannelCategory("50000123", "이어폰", 1.0),
    )


def test_naver_publish_success():
    n, rec = _naver({"/v2/products": {"originProductNo": 12345}})
    res = n.publish(_draft())
    assert res.status is PublishStatus.LISTED and res.channel_product_no == "12345"
    assert rec.calls[0][0] == "POST" and rec.calls[0][1] == "/v2/products"


def test_naver_publish_rejected_on_error():
    n, _ = _naver({"/v2/products": AdapterError("HTTP 400", status=400)})
    res = n.publish(_draft())
    assert res.status is PublishStatus.REJECTED


def test_naver_update_price_calls_patch():
    n, rec = _naver()
    n.update_price("999", Decimal("42000"))
    method, path, body, _ = rec.calls[0]
    assert method == "PATCH" and path.endswith("/999")
    assert body["originProduct"]["salePrice"] == 42000


def test_naver_pause_and_resume_set_status():
    n, rec = _naver()
    n.pause("999"); n.resume("999")
    assert rec.calls[0][2]["originProduct"]["statusType"] == "SUSPENSION"
    assert rec.calls[1][2]["originProduct"]["statusType"] == "SALE"


def test_naver_fetch_orders_mapping():
    orders_resp = {"data": {"contents": [
        {"order": {"orderId": "20240613A", "ordererName": "홍길동", "orderDate": "2026-06-13"},
         "productOrder": {"originProductNo": 12345, "quantity": 2,
                          "shippingAddress": {"personalCustomsClearanceCode": "P012345678901"}}},
    ]}}
    n, _ = _naver({"/pay-order": orders_resp})
    [o] = n.fetch_orders()
    assert o.channel_order_no == "20240613A" and o.quantity == 2
    assert o.channel_product_no == "12345"
    assert o.buyer_pccc_encrypted == "P012345678901"


def test_naver_map_category():
    n, _ = _naver({"/v1/categories": {"category": [{"id": 50000123, "name": "이어폰"}]}})
    cat = n.map_category(["Electronics", "Headphones"])
    assert cat.channel_category_id == "50000123" and cat.confidence == 1.0


def test_naver_sign_is_base64_and_stable():
    bcrypt = pytest.importorskip("bcrypt")
    salt = bcrypt.gensalt().decode()
    n = NaverSmartstoreAdapter("cid", salt)
    s1 = n._sign(1718000000000)
    s2 = n._sign(1718000000000)
    assert s1 == s2 and isinstance(s1, str) and len(s1) > 20
