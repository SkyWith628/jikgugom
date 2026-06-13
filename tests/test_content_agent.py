"""콘텐츠 에이전트 테스트 — mock 번역/제목 결정론 + 이미지 재호스팅 + 가격 패스스루."""

from __future__ import annotations

from decimal import Decimal

import pytest

from jikgugom.content import ContentAgent, Translator
from jikgugom.content.llm import ContentLLM
from jikgugom.content.tools import (
    extract_keywords,
    glossary_translate,
    rehost_images,
    truncate_title,
)
from jikgugom.margin.models import CostBreakdown, MarginQuote
from jikgugom.models import ChannelCategory
from tests.fakes import make_source_product


def _quote(price="39000") -> MarginQuote:
    zero = Decimal("0")
    return MarginQuote(
        sale_price_krw=Decimal(price), profit_krw=Decimal("9000"),
        effective_margin_rate=Decimal("0.25"), channel="naver",
        fx_rate=Decimal("1380"), customs_type="list",
        breakdown=CostBreakdown(zero, zero, zero, zero, zero, zero, zero, zero),
    )


def _cat() -> ChannelCategory:
    return ChannelCategory("50000123", "Electronics/Headphones", 0.9)


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)


def test_mock_modes_without_keys():
    a = ContentAgent()
    assert a.mode == "translate=mock/title=mock"


def test_glossary_translate_deterministic():
    assert glossary_translate("Wireless Charger") == "무선 충전기"
    assert glossary_translate("Wireless Charger") == glossary_translate("Wireless Charger")


def test_build_produces_korean_listing():
    p = make_source_product("B0X", title="Wireless Earbuds",
                            description="Fast charging pad",
                            category_path=["Electronics", "Headphones"],
                            image_urls=["https://amazon.com/x.jpg"])
    draft = ContentAgent().build(p, _quote(), _cat())
    assert "무선" in draft.title_ko and "이어폰" in draft.title_ko
    assert "<h3>" in draft.description_html
    assert draft.product_id == "fake:B0X"


def test_price_is_passed_through_not_recomputed():
    p = make_source_product("B0X")
    draft = ContentAgent().build(p, _quote("57300"), _cat())
    assert draft.price_krw == Decimal("57300")


def test_images_are_rehosted_to_cdn():
    p = make_source_product("B0X", image_urls=["https://amazon.com/a.jpg",
                                              "https://amazon.com/b.jpg"])
    draft = ContentAgent().build(p, _quote(), _cat())
    assert all(u.startswith("https://cdn.example.com/") for u in draft.image_urls_cdn)
    assert len(draft.image_urls_cdn) == 2


def test_rehost_is_deterministic():
    urls = ["https://amazon.com/a.jpg"]
    assert rehost_images(urls) == rehost_images(urls)


def test_title_truncated_to_limit():
    long = "아주 " * 40
    assert len(truncate_title(long, 50)) <= 50


def test_keywords_dedup_and_include_category():
    kw = extract_keywords(["Electronics", "Headphones"], "무선 이어폰 무선")
    assert kw.count("무선") == 1
    assert "Headphones" in kw


def test_translator_real_falls_back_to_mock(monkeypatch):
    """real(DeepL) 호출 실패 시 glossary mock으로 graceful degrade."""
    tr = Translator.__new__(Translator)
    tr._key = "x"
    tr.mode = "real"
    monkeypatch.setattr(tr, "_deepl",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net")))
    assert tr.translate("Wireless Charger") == "무선 충전기"
