"""룰 로더 — rules/*.yaml 을 검증 로드해 RuleSet으로 캐시.

[What] 흩어진 YAML 규칙을 하나의 정규화된 RuleSet으로 합친다.
[Why]  규칙을 코드가 아닌 데이터로 둬, 규제·금지어 변경에 배포가 필요 없게.
[How]  시작 시 1회 로드 + fail-fast(잘못된 YAML이면 런타임이 아니라 기동에서 터짐).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).parent / "rules"


@dataclass(frozen=True)
class BannedPattern:
    regex: re.Pattern[str]
    message: str


@dataclass(frozen=True)
class KcCategory:
    match: str
    verdict: str        # "block" | "review"
    message: str


@dataclass
class RuleSet:
    prohibited_keywords: list[str] = field(default_factory=list)
    prohibited_categories: list[str] = field(default_factory=list)
    banned_patterns: list[BannedPattern] = field(default_factory=list)
    kc_categories: list[KcCategory] = field(default_factory=list)
    counterfeit_brands: list[str] = field(default_factory=list)
    list_clearance_limit_usd: Decimal = Decimal("200")
    hs_map: dict[str, str] = field(default_factory=dict)


def _read(name: str) -> dict:
    path = RULES_DIR / name
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"rule file {name} must be a mapping, got {type(data).__name__}")
    return data


def load_ruleset(rules_dir: Path | None = None) -> RuleSet:
    """모든 룰 파일을 로드·검증해 RuleSet 반환. 잘못된 규칙은 즉시 예외(fail-fast)."""
    global RULES_DIR
    if rules_dir is not None:
        RULES_DIR = rules_dir

    prohibited = _read("prohibited.yaml")
    banned = _read("banned_keywords.yaml")
    kc = _read("kc_required.yaml")
    brands = _read("brands.yaml")
    customs = _read("customs.yaml")

    patterns: list[BannedPattern] = []
    for i, item in enumerate(banned.get("patterns", [])):
        try:
            patterns.append(
                BannedPattern(re.compile(item["pattern"]), item["message"])
            )
        except (re.error, KeyError, TypeError) as e:
            raise ValueError(f"banned_keywords.yaml[{i}] invalid: {e}") from e

    kc_categories: list[KcCategory] = []
    for i, item in enumerate(kc.get("categories", [])):
        verdict = item.get("verdict")
        if verdict not in ("block", "review"):
            raise ValueError(f"kc_required.yaml[{i}] verdict must be block/review")
        kc_categories.append(KcCategory(item["match"], verdict, item["message"]))

    return RuleSet(
        prohibited_keywords=[k.lower() for k in prohibited.get("keywords", [])],
        prohibited_categories=prohibited.get("categories", []),
        banned_patterns=patterns,
        kc_categories=kc_categories,
        counterfeit_brands=brands.get("counterfeit_risk", []),
        list_clearance_limit_usd=Decimal(str(customs.get("us_list_clearance_limit_usd", 200))),
        hs_map=customs.get("hs_map", {}),
    )
