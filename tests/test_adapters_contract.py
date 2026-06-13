"""Adapter 계약 테스트 — Fake 구현이 ABC 계약을 실제로 지키는지 고정.

엣지 케이스 포함: 미구현 하위 클래스는 인스턴스화 자체가 막혀야 한다(ABC의 핵심 가치).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from jikgugom.adapters.base import ChannelAdapter, SourceAdapter
from jikgugom.models import (
    AvailabilitySnapshot,
    ChannelCategory,
    ChannelOrder,
    ListingDraft,
    PublishResult,
    PublishStatus,
    SourceProduct,
)
from tests.fakes import FakeChannelAdapter, FakeSourceAdapter, make_source_product


# ── SourceAdapter 계약 ──────────────────────────────────────
def test_source_fetch_bestsellers_returns_source_products():
    src = FakeSourceAdapter()
    items = src.fetch_bestsellers("Chargers", limit=10)
    assert items and all(isinstance(p, SourceProduct) for p in items)


def test_source_get_product_roundtrip():
    p = make_source_product("B0X")
    src = FakeSourceAdapter([p])
    assert src.get_product("B0X").source_id == "B0X"


def test_source_check_availability_shape():
    src = FakeSourceAdapter([make_source_product("B0X")])
    snap = src.check_availability("B0X")
    assert isinstance(snap, AvailabilitySnapshot)
    assert snap.in_stock is True and snap.price == Decimal("19.99")


def test_source_out_of_stock_reflected():
    src = FakeSourceAdapter([make_source_product("B0X")])
    src.set_out_of_stock("B0X")
    assert src.check_availability("B0X").in_stock is False


# ── ChannelAdapter 계약 ─────────────────────────────────────
def _draft(product_id: str = "p1") -> ListingDraft:
    return ListingDraft(
        product_id=product_id,
        title_ko="무선 충전기 15W",
        description_html="<p>빠른 충전</p>",
        image_urls_cdn=["https://cdn.example.com/a.jpg"],
        price_krw=Decimal("39000"),
        category=ChannelCategory("50000123", "Electronics/Chargers", 0.9),
    )


def test_channel_publish_returns_product_no():
    ch = FakeChannelAdapter()
    res = ch.publish(_draft())
    assert isinstance(res, PublishResult)
    assert res.status is PublishStatus.LISTED and res.channel_product_no


def test_channel_publish_is_idempotent():
    ch = FakeChannelAdapter()
    a = ch.publish(_draft("p1"))
    b = ch.publish(_draft("p1"))
    assert a.channel_product_no == b.channel_product_no
    assert len(ch.published) == 1


def test_channel_update_price_and_pause():
    ch = FakeChannelAdapter()
    no = ch.publish(_draft()).channel_product_no
    ch.update_price(no, Decimal("42000"))
    ch.pause(no)
    assert ch.prices[no] == Decimal("42000")
    assert no in ch.paused


def test_channel_fetch_orders():
    order = ChannelOrder(
        channel="fake", channel_order_no="O1", channel_product_no="NV000001",
        quantity=1, buyer_name="홍길동", buyer_pccc_encrypted="enc::xxx",
        shipping_address={"zip": "06000"}, ordered_at=__import__("datetime").datetime(2026, 6, 13),
    )
    ch = FakeChannelAdapter([order])
    assert ch.fetch_orders() == [order]


# ── ABC 강제: 미구현 클래스는 인스턴스화 불가 ────────────────
def test_incomplete_source_adapter_cannot_instantiate():
    class Broken(SourceAdapter):
        pass  # 추상 메서드 미구현

    with pytest.raises(TypeError):
        Broken()  # type: ignore[abstract]


def test_incomplete_channel_adapter_cannot_instantiate():
    class Broken(ChannelAdapter):
        def map_category(self, p):  # 일부만 구현
            ...

    with pytest.raises(TypeError):
        Broken()  # type: ignore[abstract]
