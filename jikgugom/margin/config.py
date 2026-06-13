"""마진 비용 설정 로더 — config/costs.yaml → MarginConfig (fail-fast 검증)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "costs.yaml"


@dataclass(frozen=True)
class ChannelFees:
    sales_fee_rate: Decimal
    payment_fee_rate: Decimal


@dataclass
class MarginConfig:
    fx_rate_krw_per_usd: Decimal
    fx_buffer: Decimal
    intl_shipping_krw: Decimal
    domestic_shipping_krw: Decimal
    return_reserve_rate: Decimal
    target_margin_rate: Decimal
    import_vat_rate: Decimal
    default_duty_rate: Decimal
    duty_rates: dict[str, Decimal]
    price_rounding_krw: Decimal
    channels: dict[str, ChannelFees] = field(default_factory=dict)

    def channel_fees(self, channel: str) -> ChannelFees:
        if channel not in self.channels:
            raise KeyError(f"unknown channel '{channel}' (config/costs.yaml channels)")
        return self.channels[channel]

    def duty_rate(self, hs_code: str | None) -> Decimal:
        if hs_code and hs_code in self.duty_rates:
            return self.duty_rates[hs_code]
        return self.default_duty_rate


def _dec(v) -> Decimal:
    return Decimal(str(v))


def load_margin_config(path: Path | None = None) -> MarginConfig:
    path = path or DEFAULT_CONFIG_PATH
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    channels = {
        name: ChannelFees(_dec(c["sales_fee_rate"]), _dec(c["payment_fee_rate"]))
        for name, c in (raw.get("channels") or {}).items()
    }
    cfg = MarginConfig(
        fx_rate_krw_per_usd=_dec(raw["fx_rate_krw_per_usd"]),
        fx_buffer=_dec(raw["fx_buffer"]),
        intl_shipping_krw=_dec(raw["intl_shipping_krw"]),
        domestic_shipping_krw=_dec(raw["domestic_shipping_krw"]),
        return_reserve_rate=_dec(raw["return_reserve_rate"]),
        target_margin_rate=_dec(raw["target_margin_rate"]),
        import_vat_rate=_dec(raw["import_vat_rate"]),
        default_duty_rate=_dec(raw["default_duty_rate"]),
        duty_rates={k: _dec(v) for k, v in (raw.get("duty_rates") or {}).items()},
        price_rounding_krw=_dec(raw["price_rounding_krw"]),
        channels=channels,
    )
    _validate(cfg)
    return cfg


def _validate(cfg: MarginConfig) -> None:
    """기동 시점 사전 검증 — 잘못된 설정으로 적자 판매가가 나오기 전에 차단."""
    if cfg.fx_rate_krw_per_usd <= 0 or cfg.fx_buffer < 1:
        raise ValueError("fx_rate must be >0 and fx_buffer >= 1")
    if not (0 <= cfg.target_margin_rate < 1):
        raise ValueError("target_margin_rate must be in [0, 1)")
    if cfg.price_rounding_krw <= 0:
        raise ValueError("price_rounding_krw must be > 0")
    for name, fees in cfg.channels.items():
        denom = 1 - cfg.target_margin_rate - fees.sales_fee_rate - fees.payment_fee_rate
        if denom <= 0:
            raise ValueError(
                f"channel '{name}': margin+fees >= 100% → 판매가 산출 불가 (denom={denom})"
            )
