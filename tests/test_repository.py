"""저장소 테스트 — InMemory와 SQL(SQLite) 구현이 같은 계약을 만족하는지.

같은 테스트를 두 구현에 돌려 'Repository 교체 가능'을 보증한다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from api.db import SqlRepository
from api.repository import InMemoryRepository
from api.store import ListingRecord, OrderRecord
from jikgugom.models import ChannelCategory, ListingDraft


@pytest.fixture(params=["memory", "sqlite"])
def repo(request):
    if request.param == "memory":
        return InMemoryRepository()
    return SqlRepository("sqlite:///:memory:")   # 프로세스 내 임시 DB


def _listing(id="B01", status="ready") -> ListingRecord:
    return ListingRecord(id=id, title="무선 이어폰", status=status, note="awaiting",
                         price_krw=82900, market_score=87, recommendation="strong")


def _draft(pid="amazon:B01") -> ListingDraft:
    return ListingDraft(product_id=pid, title_ko="무선 이어폰",
                        description_html="<p>x</p>", image_urls_cdn=["https://cdn/a.jpg"],
                        price_krw=Decimal("82900"),
                        category=ChannelCategory("50000123", "이어폰", 0.9),
                        attributes={"rating": 4.7})


def _order(id="ORD-001") -> OrderRecord:
    return OrderRecord(id=id, product_id="B01", quantity=1, buyer="홍길동",
                       status="pending_approval", guard_action="auto_order",
                       guard_reason="ok", profit_krw=20752)


def test_listing_roundtrip(repo):
    repo.save_listing(_listing(), _draft())
    got = repo.get_listing("B01")
    assert got is not None and got.title == "무선 이어폰" and got.price_krw == 82900
    assert got.market_score == 87 and got.recommendation == "strong"


def test_draft_roundtrip(repo):
    repo.save_listing(_listing(), _draft())
    d = repo.get_draft("B01")
    assert d is not None and d.price_krw == Decimal("82900")
    assert d.category.channel_category_id == "50000123"
    assert d.attributes["rating"] == 4.7


def test_is_empty_and_clear(repo):
    assert repo.is_listings_empty() is True
    repo.save_listing(_listing(), _draft())
    assert repo.is_listings_empty() is False
    repo.clear_listings()
    assert repo.is_listings_empty() is True and repo.get_draft("B01") is None


def test_update_preserves_draft(repo):
    """발행 시 draft=None으로 저장해도 기존 draft가 보존된다."""
    repo.save_listing(_listing(), _draft())
    rec = repo.get_listing("B01")
    rec.status = "published"
    rec.channel_product_no = "NV000001"
    repo.save_listing(rec, None)
    assert repo.get_listing("B01").status == "published"
    assert repo.get_draft("B01") is not None         # draft 유지


def test_order_roundtrip_and_update(repo):
    assert repo.has_orders() is False
    repo.save_order(_order())
    assert repo.has_orders() is True
    o = repo.get_order("ORD-001")
    assert o.profit_krw == 20752 and o.guard_action == "auto_order"
    o.status = "amazon_ordered"
    o.fulfillment_id = "AMZ-B01"
    repo.save_order(o)
    assert repo.get_order("ORD-001").status == "amazon_ordered"


def test_list_methods(repo):
    repo.save_listing(_listing("B01"), _draft())
    repo.save_listing(_listing("B02", status="blocked"), None)
    repo.save_order(_order("ORD-001"))
    assert {l.id for l in repo.list_listings()} == {"B01", "B02"}
    assert [o.id for o in repo.list_orders()] == ["ORD-001"]


def test_sql_persists_across_instances(tmp_path):
    """SQL: 같은 파일을 가리키는 새 인스턴스가 데이터를 읽는다(영속 증명)."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    SqlRepository(url).save_listing(_listing(), _draft())
    reopened = SqlRepository(url)                     # 새 인스턴스(=재시작 모사)
    assert reopened.get_listing("B01").price_krw == 82900
    assert reopened.get_draft("B01").category.channel_category_name == "이어폰"
