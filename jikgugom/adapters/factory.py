"""어댑터 팩토리 — 설정(키 유무)으로 real/mock 어댑터를 선택해 조립한다.

[What] build_adapters(settings): 소스/채널 어댑터를 real(키 있음) 또는 mock(키 없음)으로
       만들어 modes와 함께 반환. LLM 레이어가 이미 하는 '키 있으면 real' 전환을 어댑터
       레이어에도 동일하게 적용한다.
[Why]  지금까지 service/demo가 SampleSource/SampleChannel을 하드코딩해 '키를 넣어도 mock'
       이었다. 배선을 이 팩토리 하나로 모으면, 환경변수만 채우면 전체가 실 동작한다.
[How]  포트-어댑터의 조립 지점(Composition Root). 도메인은 그대로 두고 경계에서만 교체.

쿠팡은 실어댑터 미구현 → 항상 mock(SampleCoupangChannel). 추후 CoupangWingAdapter를
ChannelAdapter로 붙이면 여기서 한 줄로 real 전환된다.
"""

from __future__ import annotations

from dataclasses import dataclass

from jikgugom.adapters.aliexpress import AliExpressAdapter
from jikgugom.adapters.amazon import AmazonRainforestAdapter
from jikgugom.adapters.base import ChannelAdapter, SourceAdapter
from jikgugom.adapters.naver import NaverSmartstoreAdapter
from jikgugom.core.settings import ConfigError, Settings
from jikgugom.samples import SampleChannel, SampleCoupangChannel, SampleSource


@dataclass
class Adapters:
    source: SourceAdapter
    channels: list[ChannelAdapter]
    modes: dict[str, str]   # {"amazon": real/mock, "naver": ..., "coupang": ...}


def build_adapters(settings: Settings) -> Adapters:
    """설정에 따라 소스/채널 어댑터를 조립. 키 있으면 real, 없으면 mock."""
    modes: dict[str, str] = {}

    # ── 소스 선택: AliExpress(1차) → Amazon(대체) → mock ──────
    if settings.aliexpress_app_key and settings.aliexpress_app_secret:
        source: SourceAdapter = AliExpressAdapter(
            settings.aliexpress_app_key, settings.aliexpress_app_secret,
            tracking_id=settings.aliexpress_tracking_id)
        modes["aliexpress"] = "real"
    elif settings.rainforest_api_key:
        source = AmazonRainforestAdapter(
            settings.rainforest_api_key, domain=settings.amazon_domain)
        modes["amazon"] = "real"
    else:
        source = SampleSource()
        modes["aliexpress"] = "mock"   # 기본 소스는 AliExpress(키 없으면 샘플 카탈로그)

    # ── 채널(naver/coupang) ──────────────────────────────────
    channels: list[ChannelAdapter] = []
    for name in settings.channels:
        if name == "naver":
            if settings.naver_client_id and settings.naver_client_secret:
                channels.append(NaverSmartstoreAdapter(
                    settings.naver_client_id, settings.naver_client_secret))
                modes["naver"] = "real"
            else:
                channels.append(SampleChannel())
                modes["naver"] = "mock"
        elif name == "coupang":
            channels.append(SampleCoupangChannel())   # 실어댑터 미구현 → mock 고정
            modes["coupang"] = "mock"
        else:
            raise ConfigError(f"알 수 없는 채널: {name!r}")

    return Adapters(source=source, channels=channels, modes=modes)
