"""콘텐츠 생성 에이전트 — 영문 원본 → 한글 ListingDraft.

[경계] 가격은 quote.sale_price_krw 를 받기만 한다(재계산 X). 통관/마진은 이미 결정됨.
[하이브리드] 본문=DeepL(translator), 제목=LLM(content.llm). 이미지=CDN 재호스팅.
[삽입] build()는 pipeline의 ContentBuilder 시그니처와 동일 → content_builder=agent.build.
"""

from __future__ import annotations

from jikgugom.content.llm import ContentLLM
from jikgugom.content.tools import (
    build_description_html,
    extract_keywords,
    rehost_images,
    truncate_title,
)
from jikgugom.content.translator import Translator
from jikgugom.margin.models import MarginQuote
from jikgugom.models import ChannelCategory, ListingDraft, SourceProduct


class ContentAgent:
    def __init__(self, translator: Translator | None = None,
                 llm: ContentLLM | None = None) -> None:
        self._tr = translator or Translator()
        self._llm = llm or ContentLLM()

    @property
    def mode(self) -> str:
        return f"translate={self._tr.mode}/title={self._llm.mode}"

    def build(self, product: SourceProduct, quote: MarginQuote,
              category: ChannelCategory) -> ListingDraft:
        """ContentBuilder 구현 — 영문 상품을 한글 등록 초안으로 가공."""
        title_ko = self._tr.translate(product.title)
        desc_ko = self._tr.translate(product.description)
        keywords = extract_keywords(product.category_path, title_ko)
        seo_title = truncate_title(self._llm.seo_title(title_ko, keywords, product.brand))
        images = rehost_images(product.image_urls)

        return ListingDraft(
            product_id=f"{product.source}:{product.source_id}",
            title_ko=seo_title,
            description_html=build_description_html(title_ko, desc_ko, keywords),
            image_urls_cdn=images,
            price_krw=quote.sale_price_krw,
            category=category,
            attributes=dict(product.attributes),
        )
