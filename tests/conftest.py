"""테스트 전역 격리 — 개발자 로컬 .env가 테스트를 오염시키지 않게 한다.

실제 키가 .env에 있어도 테스트는 mock으로 돌아야 한다(외부 호출·과금·플레이키 방지).
모든 테스트에서 .env 로딩을 끄고 관련 환경변수를 비운다.
"""

from __future__ import annotations

import pytest

_ENV_KEYS = (
    "ALIEXPRESS_APP_KEY", "ALIEXPRESS_APP_SECRET", "ALIEXPRESS_TRACKING_ID",
    "RAINFOREST_API_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET",
    "GEMINI_API_KEY", "GEMINI_MODEL", "DEEPL_API_KEY", "FX_RATE",
    "SALES_CHANNELS", "SOURCING_CATEGORY", "MONITOR_INTERVAL_SECONDS",
    "DATABASE_URL", "AMAZON_DOMAIN",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.setattr("jikgugom.core.settings._DOTENV_LOADED", True)
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
