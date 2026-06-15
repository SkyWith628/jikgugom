"""어댑터 팩토리 테스트 — 키 유무로 real/mock을 올바르게 선택하는지.

핵심: 키 없으면 mock, 키 있으면 real 타입. 쿠팡은 실어댑터 미구현이라 항상 mock.
"""

from __future__ import annotations

from jikgugom.adapters.aliexpress import AliExpressAdapter
from jikgugom.adapters.amazon import AmazonRainforestAdapter
from jikgugom.adapters.factory import build_adapters
from jikgugom.adapters.naver import NaverSmartstoreAdapter
from jikgugom.core.settings import Settings
from jikgugom.samples import SampleChannel, SampleCoupangChannel, SampleSource


def test_no_keys_builds_all_mock():
    a = build_adapters(Settings())
    assert isinstance(a.source, SampleSource)
    assert a.modes["aliexpress"] == "mock" and a.modes["naver"] == "mock"
    naver = next(c for c in a.channels if c.name == "naver")
    assert isinstance(naver, SampleChannel)


def test_aliexpress_keys_build_real_source():
    a = build_adapters(Settings(aliexpress_app_key="ak", aliexpress_app_secret="as"))
    assert isinstance(a.source, AliExpressAdapter)
    assert a.modes["aliexpress"] == "real"


def test_aliexpress_takes_priority_over_amazon():
    a = build_adapters(Settings(aliexpress_app_key="ak", aliexpress_app_secret="as",
                                rainforest_api_key="rk"))
    assert isinstance(a.source, AliExpressAdapter)   # AliExpress가 1차


def test_rainforest_key_builds_real_source_when_no_aliexpress():
    a = build_adapters(Settings(rainforest_api_key="rk"))
    assert isinstance(a.source, AmazonRainforestAdapter)
    assert a.modes["amazon"] == "real"


def test_naver_creds_build_real_channel():
    a = build_adapters(Settings(naver_client_id="cid", naver_client_secret="cs"))
    naver = next(c for c in a.channels if c.name == "naver")
    assert isinstance(naver, NaverSmartstoreAdapter)
    assert a.modes["naver"] == "real"


def test_coupang_always_mock_even_listed():
    a = build_adapters(Settings(channels=("naver", "coupang")))
    coupang = next(c for c in a.channels if c.name == "coupang")
    assert isinstance(coupang, SampleCoupangChannel)
    assert a.modes["coupang"] == "mock"


def test_channels_subset_respected():
    a = build_adapters(Settings(channels=("naver",)))
    assert [c.name for c in a.channels] == ["naver"]
    assert "coupang" not in a.modes
