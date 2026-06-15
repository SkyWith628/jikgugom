"""중앙 설정(Settings) 테스트 — 로딩·검증(fail-fast)·마스킹.

핵심: 부분 설정(네이버 한쪽만)은 시작 시 즉시 에러로 잡고, 키는 마스킹된다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from jikgugom.core.settings import (
    ConfigError,
    Settings,
    llm_modes,
    load_settings,
    mask_secret,
)

KEYS = ["ALIEXPRESS_APP_KEY", "ALIEXPRESS_APP_SECRET", "ALIEXPRESS_TRACKING_ID",
        "RAINFOREST_API_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET",
        "GEMINI_API_KEY", "DEEPL_API_KEY", "FX_RATE", "SALES_CHANNELS",
        "SOURCING_CATEGORY", "MONITOR_INTERVAL_SECONDS",
        "GOOGLE_CLIENT_ID", "ADMIN_ALLOWED_EMAILS", "SESSION_SECRET", "CORS_ORIGINS"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # .env 자동로딩 비활성화 + 관련 환경변수 제거 → 테스트 격리
    monkeypatch.setattr("jikgugom.core.settings._DOTENV_LOADED", True)
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def test_defaults_are_all_mock():
    s = load_settings()
    assert s.rainforest_api_key is None and s.naver_client_id is None
    assert s.fx_rate == Decimal("1380")
    assert s.channels == ("naver", "coupang")
    assert s.primary_channel == "naver"
    s.validate()   # 전부 mock = 유효


def test_partial_naver_creds_fail_fast(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "cid")   # secret 누락
    s = load_settings()
    with pytest.raises(ConfigError, match="NAVER_CLIENT"):
        s.validate()


def test_both_naver_creds_ok(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "cid")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "csecret")
    load_settings().validate()   # 예외 없음


def test_fx_rate_from_env(monkeypatch):
    monkeypatch.setenv("FX_RATE", "1425.5")
    assert load_settings().fx_rate == Decimal("1425.5")


def test_invalid_fx_rate_raises(monkeypatch):
    monkeypatch.setenv("FX_RATE", "abc")
    with pytest.raises(ConfigError):
        load_settings()


def test_unknown_channel_rejected(monkeypatch):
    monkeypatch.setenv("SALES_CHANNELS", "naver,gmarket")
    with pytest.raises(ConfigError, match="알 수 없는 채널"):
        load_settings().validate()


def test_mask_secret_hides_value():
    assert mask_secret("sk-1234567890") == "sk-…****"
    assert mask_secret(None) == "(unset)"
    assert mask_secret("ab") == "****"


def test_masked_snapshot_has_no_plaintext(monkeypatch):
    monkeypatch.setenv("RAINFOREST_API_KEY", "supersecretkey123")
    snap = load_settings().masked()
    assert "supersecretkey123" not in str(snap)
    assert snap["rainforest_api_key"] == "sup…****"


def test_llm_modes_track_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    m = llm_modes(load_settings())
    assert m == {"gemini": "real", "deepl": "mock"}
