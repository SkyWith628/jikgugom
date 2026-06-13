"""파이프라인 러너 — 소싱→컴플라이언스→마진→콘텐츠→등록을 한 줄로 오케스트레이션.

[What] 한 카테고리를 소싱해 각 상품을 결정론 단계에 통과시키고, 단계별 결과를 기록.
[Why]  흩어진 엔진(컴플라이언스·마진·콘텐츠·채널)을 하나의 흐름으로 묶되, 리스크 큰
       '발행'은 기본적으로 사람 승인 게이트 뒤에 둔다(설계 결정: 등록=사람 승인).
[How]  각 상품은 독립적으로 처리되고 한 단계에서 걸러지면 사유와 함께 결과로 남는다
       (한 상품 실패가 배치 전체를 막지 않음).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Callable

from sourcing_agent.adapters.base import ChannelAdapter, SourceAdapter
from sourcing_agent.compliance import ComplianceEngine
from sourcing_agent.compliance.models import ComplianceResult, Verdict
from sourcing_agent.evaluation import EvaluationAgent, Recommendation
from sourcing_agent.evaluation.models import EvaluationResult
from sourcing_agent.margin import MarginEngine
from sourcing_agent.margin.models import MarginQuote
from sourcing_agent.models import (
    ChannelCategory,
    ListingDraft,
    PublishResult,
    PublishStatus,
    SourceProduct,
)


class ListingStatus(str, Enum):
    BLOCKED = "blocked"                  # 컴플라이언스 차단
    REVIEW = "review"                    # 사람 검토 필요
    MARGIN_REJECTED = "margin_rejected"  # 마진 부족/적자
    READY = "ready"                      # 발행 대기(사람 승인)
    PUBLISHED = "published"              # 채널 발행 완료
    PUBLISH_FAILED = "publish_failed"    # 채널 심사 거절/대기


@dataclass(frozen=True)
class PipelineOutcome:
    source_id: str
    status: ListingStatus
    note: str
    compliance: ComplianceResult | None = None
    quote: MarginQuote | None = None
    evaluation: EvaluationResult | None = None
    draft: ListingDraft | None = None
    publish: PublishResult | None = None


# 콘텐츠 빌더 계약 — 나중에 DeepL+LLM 번역기로 교체. (product, quote, category) → draft
ContentBuilder = Callable[[SourceProduct, MarginQuote, ChannelCategory], ListingDraft]


def default_content_builder(
    product: SourceProduct, quote: MarginQuote, category: ChannelCategory
) -> ListingDraft:
    """최소 콘텐츠 빌더 — 번역/CDN 재호스팅은 아직 미구현(원문 패스스루)."""
    return ListingDraft(
        product_id=f"{product.source}:{product.source_id}",
        title_ko=product.title,                  # TODO: DeepL(본문)+LLM(제목) 번역
        description_html=f"<p>{product.description}</p>",
        image_urls_cdn=list(product.image_urls),  # TODO: 자체 CDN 재호스팅
        price_krw=quote.sale_price_krw,
        category=category,
        attributes=dict(product.attributes),
    )


@dataclass
class PipelineConfig:
    min_margin_rate: Decimal = Decimal("0.10")  # 이 마진 미만이면 등록 보류


class PipelineRunner:
    def __init__(
        self,
        source: SourceAdapter,
        channel: ChannelAdapter,
        compliance: ComplianceEngine | None = None,
        margin: MarginEngine | None = None,
        evaluator: EvaluationAgent | None = None,
        content_builder: ContentBuilder = default_content_builder,
        config: PipelineConfig | None = None,
    ) -> None:
        self._src = source
        self._ch = channel
        self._compliance = compliance or ComplianceEngine()
        self._margin = margin or MarginEngine()
        self._evaluator = evaluator   # None이면 평가 단계 건너뜀(하위 호환)
        self._build_content = content_builder
        self._cfg = config or PipelineConfig()

    def run(
        self,
        category: str,
        *,
        limit: int = 50,
        auto_publish: bool = False,
        pricing_channel: str | None = None,
        fx_rate: Decimal | None = None,
    ) -> list[PipelineOutcome]:
        channel_key = pricing_channel or self._ch.name
        products = self._src.fetch_bestsellers(category, limit=limit)
        return [
            self._process(p, channel_key, auto_publish, fx_rate) for p in products
        ]

    def _process(
        self, product: SourceProduct, channel_key: str,
        auto_publish: bool, fx_rate: Decimal | None,
    ) -> PipelineOutcome:
        sid = product.source_id

        # 1) 컴플라이언스
        c = self._compliance.evaluate(product)
        if c.verdict is Verdict.BLOCK:
            return PipelineOutcome(sid, ListingStatus.BLOCKED,
                                   c.reasons[0].message, compliance=c)

        # 2) 마진 (REVIEW도 가격은 계산해 검토자에게 제공)
        quote = self._margin.quote(product, c, channel=channel_key, fx_rate=fx_rate)

        if c.verdict is Verdict.REVIEW:
            return PipelineOutcome(sid, ListingStatus.REVIEW,
                                   c.reasons[0].message, compliance=c, quote=quote)

        if quote.profit_krw <= 0 or quote.effective_margin_rate < self._cfg.min_margin_rate:
            return PipelineOutcome(sid, ListingStatus.MARGIN_REJECTED,
                                   f"margin {quote.effective_margin_rate}", compliance=c, quote=quote)

        # 2.5) 시장성 평가 (어드바이저). 돈 게이트 아님 — 단 SKIP은 사람 검토로 회부
        ev: EvaluationResult | None = None
        if self._evaluator is not None:
            ev = self._evaluator.evaluate(product, quote)
            if ev.recommendation is Recommendation.SKIP:
                return PipelineOutcome(sid, ListingStatus.REVIEW,
                                       f"low market fit ({ev.market_score})",
                                       compliance=c, quote=quote, evaluation=ev)

        # 3) 콘텐츠 → ListingDraft
        category = self._ch.map_category(product.category_path)
        draft = self._build_content(product, quote, category)

        # 4) 발행 게이트
        if not auto_publish:
            return PipelineOutcome(sid, ListingStatus.READY, "awaiting approval",
                                   compliance=c, quote=quote, evaluation=ev, draft=draft)

        res = self._ch.publish(draft)
        status = (ListingStatus.PUBLISHED if res.status is PublishStatus.LISTED
                  else ListingStatus.PUBLISH_FAILED)
        return PipelineOutcome(sid, status, res.message or res.status.value,
                               compliance=c, quote=quote, evaluation=ev, draft=draft, publish=res)
