"""멀티채널 동시등록 — 한 ListingDraft를 여러 판매 채널에 팬아웃 발행.

[What] MultiChannelPublisher: 가공 완료된 ListingDraft를 등록 대상 채널들에 동시 발행하고
       채널별 발행 결과(PublishResult)를 모아 돌려준다.
[Why]  무재고(드롭십) 플랫폼의 핵심 레버리지는 '한 번 가공 → 여러 채널 노출'이다. 단,
       채널 하나의 장애가 나머지 발행을 막으면 안 된다(부분 성공 허용 = 가용성↑).
[How]  포트-어댑터 재사용 — 각 채널은 ChannelAdapter 계약만 만족하면 된다(naver/coupang…).
       채널별 try/except로 격리: 예외는 실패 결과로 변환해 수집(한 채널 실패≠배치 실패).

채널별 카테고리 매핑 차이는 draft에 단일 카테고리만 담는 현 구조상 1차로는 단순화한다
(채널별 카테고리 재매핑은 후속). 여기서는 '동시 발행 + 채널별 결과 추적'에 집중한다.
"""

from __future__ import annotations

from jikgugom.adapters.base import ChannelAdapter
from jikgugom.models import ListingDraft, PublishResult, PublishStatus


class MultiChannelPublisher:
    def __init__(self, channels: list[ChannelAdapter]) -> None:
        if not channels:
            raise ValueError("at least one channel is required")
        self._channels = list(channels)

    @property
    def channel_names(self) -> list[str]:
        return [c.name for c in self._channels]

    def publish(self, draft: ListingDraft) -> dict[str, PublishResult]:
        """모든 채널에 발행 → {채널명: PublishResult}. 채널 예외는 PENDING 결과로 격리."""
        results: dict[str, PublishResult] = {}
        for ch in self._channels:
            try:
                results[ch.name] = ch.publish(draft)
            except Exception as e:   # 한 채널 장애가 다른 채널 발행을 막지 않게 격리
                results[ch.name] = PublishResult(PublishStatus.PENDING, None, f"error: {e}")
        return results
