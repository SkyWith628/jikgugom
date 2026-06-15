"""중앙 설정 — 모든 운영 파라미터(키·환율·채널)를 한 곳에서 로딩·검증한다.

[What] Settings: 환경변수(+선택적 .env)를 읽어 타입을 맞춘 설정 객체. 팩토리·서비스는
       흩어진 os.getenv 대신 이 객체만 본다.
[Why]  키·환율이 코드 곳곳에 박히면 '지금 real인가 mock인가'를 알 수 없고, 부분 설정
       (id만 있고 secret 없음)이 런타임에 조용히 mock으로 떨어진다. 한 곳에 모아 시작 시
       검증(fail-fast)하면 '키 넣었는데 왜 mock?' 류 사고를 차단한다.
[How]  12-factor 설정 원칙(설정=환경변수). .env는 로컬 편의용이며 실제 환경변수가 우선한다.

[보안] 키는 절대 평문 로그 금지 — 노출이 필요하면 mask_secret()로 가린다.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

SUPPORTED_CHANNELS = ("naver", "coupang")
DEFAULT_CORS = ("http://localhost:3000", "http://127.0.0.1:3000",
                "http://localhost:3100", "http://127.0.0.1:3100")


class ConfigError(RuntimeError):
    """설정이 일관되지 않을 때(부분 설정·잘못된 값) 시작 시점에 던지는 예외."""


def mask_secret(value: str | None) -> str:
    """키를 로그/응답에 안전하게 노출 — 앞 3글자만 남기고 마스킹."""
    if not value:
        return "(unset)"
    if len(value) <= 4:
        return "****"
    return f"{value[:3]}…****"


_DOTENV_LOADED = False


def _load_dotenv(path: str = ".env") -> None:
    """.env가 있으면 KEY=VALUE를 환경변수로 주입(한 번만). 실제 환경변수가 우선."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if val[:1] in ('"', "'"):           # 따옴표 값은 그대로(내부 # 보존)
            val = val.strip('"').strip("'")
        else:                                # 따옴표 없으면 # 이후는 인라인 주석
            val = val.split("#", 1)[0].strip()
        os.environ.setdefault(key, val)


@dataclass(frozen=True)
class Settings:
    # ── 외부 API 키 (없으면 해당 레이어는 자동 mock) ──────────
    aliexpress_app_key: str | None = None     # AliExpress 소싱(1차)
    aliexpress_app_secret: str | None = None
    aliexpress_tracking_id: str = "default"   # 제휴 추적 ID(PID)
    rainforest_api_key: str | None = None     # Amazon 소싱(대체)
    naver_client_id: str | None = None        # 네이버 커머스 API
    naver_client_secret: str | None = None
    gemini_api_key: str | None = None         # 평가/콘텐츠/CS LLM (Google Gemini)
    deepl_api_key: str | None = None          # 본문 번역
    # ── 운영 파라미터 ────────────────────────────────────────
    fx_rate: Decimal = Decimal("1380")        # USD→KRW (실시간 연동은 후속)
    sourcing_category: str = "Best"
    channels: tuple[str, ...] = ("naver", "coupang")
    amazon_domain: str = "amazon.com"
    database_url: str = "sqlite:///./jikgugom.db"
    monitor_interval_seconds: int = 300
    # ── 인증(관리자 로그인, Google OAuth) ────────────────────
    google_client_id: str | None = None       # 없으면 인증 비활성(로컬 개발 편의)
    admin_allowed_emails: tuple[str, ...] = ()  # 로그인 허용 이메일 화이트리스트(소문자)
    session_secret: str = field(default_factory=lambda: secrets.token_hex(32))
    cors_origins: tuple[str, ...] = DEFAULT_CORS

    # ── 파생 ─────────────────────────────────────────────────
    @property
    def primary_channel(self) -> str:
        """가격기준·모니터 키잉의 기준 채널. naver 우선, 없으면 첫 채널."""
        return "naver" if "naver" in self.channels else self.channels[0]

    @property
    def auth_enabled(self) -> bool:
        """관리자 인증 활성 여부 — client_id와 허용 이메일이 모두 있어야 켜짐."""
        return bool(self.google_client_id and self.admin_allowed_emails)

    def validate(self) -> None:
        """일관성 검증 — 부분 설정/잘못된 값이면 즉시 ConfigError(fail-fast)."""
        if bool(self.aliexpress_app_key) != bool(self.aliexpress_app_secret):
            raise ConfigError(
                "AliExpress는 ALIEXPRESS_APP_KEY와 ALIEXPRESS_APP_SECRET을 함께 설정해야 "
                "합니다 (현재 하나만 설정됨 → real 전환 불가).")
        if bool(self.naver_client_id) != bool(self.naver_client_secret):
            raise ConfigError(
                "네이버는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 함께 설정해야 합니다 "
                "(현재 하나만 설정됨 → real 전환 불가).")
        if self.fx_rate <= 0:
            raise ConfigError(f"FX_RATE는 양수여야 합니다: {self.fx_rate}")
        if not self.channels:
            raise ConfigError("최소 한 개의 판매 채널이 필요합니다 (SALES_CHANNELS).")
        for c in self.channels:
            if c not in SUPPORTED_CHANNELS:
                raise ConfigError(
                    f"알 수 없는 채널: {c!r} (지원: {', '.join(SUPPORTED_CHANNELS)})")

    def masked(self) -> dict:
        """로그/디버그용 — 키를 가린 설정 스냅샷."""
        return {
            "aliexpress_app_key": mask_secret(self.aliexpress_app_key),
            "aliexpress_app_secret": mask_secret(self.aliexpress_app_secret),
            "rainforest_api_key": mask_secret(self.rainforest_api_key),
            "naver_client_id": mask_secret(self.naver_client_id),
            "naver_client_secret": mask_secret(self.naver_client_secret),
            "gemini_api_key": mask_secret(self.gemini_api_key),
            "deepl_api_key": mask_secret(self.deepl_api_key),
            "fx_rate": str(self.fx_rate),
            "channels": list(self.channels),
            "sourcing_category": self.sourcing_category,
        }


def load_settings() -> Settings:
    """.env(있으면) → 환경변수 순으로 설정을 읽어 Settings를 만든다."""
    _load_dotenv()

    def g(key: str) -> str | None:
        v = os.getenv(key)
        return v if v else None

    fx_raw = os.getenv("FX_RATE")
    try:
        fx_rate = Decimal(fx_raw) if fx_raw else Decimal("1380")
    except InvalidOperation as e:
        raise ConfigError(f"FX_RATE를 숫자로 해석할 수 없습니다: {fx_raw!r}") from e

    channels_raw = os.getenv("SALES_CHANNELS", "naver,coupang")
    channels = tuple(c.strip() for c in channels_raw.split(",") if c.strip())

    emails_raw = os.getenv("ADMIN_ALLOWED_EMAILS", "")
    emails = tuple(e.strip().lower() for e in emails_raw.split(",") if e.strip())
    cors_raw = os.getenv("CORS_ORIGINS", "")
    cors = tuple(o.strip() for o in cors_raw.split(",") if o.strip()) or DEFAULT_CORS

    try:
        interval = int(os.getenv("MONITOR_INTERVAL_SECONDS", "300"))
    except ValueError as e:
        raise ConfigError("MONITOR_INTERVAL_SECONDS는 정수여야 합니다") from e

    return Settings(
        aliexpress_app_key=g("ALIEXPRESS_APP_KEY"),
        aliexpress_app_secret=g("ALIEXPRESS_APP_SECRET"),
        aliexpress_tracking_id=os.getenv("ALIEXPRESS_TRACKING_ID", "default"),
        rainforest_api_key=g("RAINFOREST_API_KEY"),
        naver_client_id=g("NAVER_CLIENT_ID"),
        naver_client_secret=g("NAVER_CLIENT_SECRET"),
        gemini_api_key=g("GEMINI_API_KEY"),
        deepl_api_key=g("DEEPL_API_KEY"),
        fx_rate=fx_rate,
        sourcing_category=os.getenv("SOURCING_CATEGORY", "Best"),
        channels=channels,
        amazon_domain=os.getenv("AMAZON_DOMAIN", "amazon.com"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./jikgugom.db"),
        monitor_interval_seconds=interval,
        google_client_id=g("GOOGLE_CLIENT_ID"),
        admin_allowed_emails=emails,
        session_secret=os.getenv("SESSION_SECRET") or secrets.token_hex(32),
        cors_origins=cors,
    )


def llm_modes(settings: Settings) -> dict[str, str]:
    """LLM/번역 레이어의 real/mock 상태(가시화용). 키 유무로 결정."""
    return {
        "gemini": "real" if settings.gemini_api_key else "mock",
        "deepl": "real" if settings.deepl_api_key else "mock",
    }
