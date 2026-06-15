"""멀티채널 동시등록(MultiChannelPublisher) 테스트.

핵심: 한 draft를 여러 채널에 발행하고 채널별 결과를 모은다. 한 채널이 터져도
나머지 발행은 계속된다(부분 성공 허용 = 가용성).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from jikgugom.models import ChannelCategory, ListingDraft, PublishStatus
from jikgugom.pipeline import MultiChannelPublisher
from jikgugom.samples import SampleChannel, SampleCoupangChannel


def _draft() -> ListingDraft:
    return ListingDraft(
        product_id="amazon:B01", title_ko="무선 이어폰", description_html="<p>x</p>",
        image_urls_cdn=["https://cdn/a.jpg"], price_krw=Decimal("82900"),
        category=ChannelCategory("50000123", "이어폰", 0.9), attributes={})


class BrokenChannel:
    """발행 시 예외를 던지는 채널 — 격리 검증용."""
    name = "broken"

    def publish(self, draft):
        raise RuntimeError("channel down")


def test_publishes_to_all_channels():
    pub = MultiChannelPublisher([SampleChannel(), SampleCoupangChannel()])
    results = pub.publish(_draft())
    assert set(results) == {"naver", "coupang"}
    assert results["naver"].status is PublishStatus.LISTED
    assert results["coupang"].status is PublishStatus.LISTED
    assert results["naver"].channel_product_no.startswith("NV")
    assert results["coupang"].channel_product_no.startswith("CP")


def test_one_channel_failure_does_not_block_others():
    pub = MultiChannelPublisher([SampleChannel(), BrokenChannel()])
    results = pub.publish(_draft())
    assert results["naver"].status is PublishStatus.LISTED        # 정상 채널은 발행됨
    assert results["broken"].status is PublishStatus.PENDING      # 예외 → 격리된 실패
    assert "error" in (results["broken"].message or "")


def test_channel_names_property():
    pub = MultiChannelPublisher([SampleChannel(), SampleCoupangChannel()])
    assert pub.channel_names == ["naver", "coupang"]


def test_empty_channels_rejected():
    with pytest.raises(ValueError):
        MultiChannelPublisher([])
