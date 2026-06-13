"""컴플라이언스 판정 결과 모델 — 엔진의 출력 계약.

입력은 공용 SourceProduct(jikgugom.models)를 그대로 재사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    PASS = "pass"        # 통과 → 평가 단계로
    BLOCK = "block"      # 차단 → 폐기 (사유 기록)
    REVIEW = "review"    # 보류 → 사람 검토 큐


class CustomsType(str, Enum):
    LIST = "list"            # 목록통관 (간이·면세 한도 이하)
    GENERAL = "general"      # 일반통관 (관세·요건 확인)
    PROHIBITED = "prohibited"  # 통관 금지


@dataclass(frozen=True)
class Reason:
    """차단/보류 사유 1건. rule_id로 어느 룰이 잡았는지 추적 가능(감사 로그)."""

    rule_id: str
    message: str


@dataclass
class RuleOutcome:
    """개별 룰 1건의 판정. verdict=PASS면 '이 룰은 통과'."""

    verdict: Verdict
    reason: Reason | None = None
    requires_kc: bool = False


@dataclass
class ComplianceResult:
    """엔진 최종 출력. BLOCK/REVIEW면 reasons가 비어선 안 된다(엔진 불변식)."""

    verdict: Verdict
    reasons: list[Reason] = field(default_factory=list)
    requires_kc: bool = False
    customs_type: CustomsType = CustomsType.GENERAL
    hs_code: str | None = None

    def __post_init__(self) -> None:
        if self.verdict in (Verdict.BLOCK, Verdict.REVIEW) and not self.reasons:
            raise ValueError("BLOCK/REVIEW verdict must carry at least one reason")
