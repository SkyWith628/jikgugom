"""컴플라이언스 엔진 — 룰 체인 + 단락 평가로 PASS/BLOCK/REVIEW 판정.

[What] SourceProduct → ComplianceResult (통관·인증 적합성).
[Why]  돈 직결 구간이라 LLM이 아닌 결정론 규칙으로 — 재현·감사 가능.
[How]  치명적 BLOCK은 단락 평가(즉시 종료), REVIEW/PASS는 사유 전체 수집.
       사기탐지·KYC 필터의 표준 패턴.
"""

from __future__ import annotations

from decimal import Decimal

from jikgugom.compliance.hs_classifier import HSClassifier
from jikgugom.compliance.models import (
    ComplianceResult,
    CustomsType,
    Reason,
    Verdict,
)
from jikgugom.compliance.rules_loader import RuleSet, load_ruleset
from jikgugom.models import SourceProduct


class ComplianceEngine:
    def __init__(self, rules: RuleSet | None = None, hs: HSClassifier | None = None) -> None:
        self._rules = rules or load_ruleset()
        self._hs = hs or HSClassifier(self._rules.hs_map)

    def evaluate(self, product: SourceProduct) -> ComplianceResult:
        text = f"{product.title or ''} {product.description or ''}"
        text_low = text.lower()
        path = product.category_path or []
        hs_code, hs_verdict = self._hs.classify(product)

        # ── 1. 통관 금지 (단락 BLOCK) ─────────────────────────
        for cat in self._rules.prohibited_categories:
            if cat in path:
                return self._block("PROHIBITED_ITEM",
                                   f"통관 금지 카테고리: {cat}", hs_code,
                                   CustomsType.PROHIBITED)
        for kw in self._rules.prohibited_keywords:
            if kw in text_low:
                return self._block("PROHIBITED_ITEM",
                                   f"통관 금지 품목 추정 키워드: {kw}", hs_code,
                                   CustomsType.PROHIBITED)

        # ── 2. 금지어 정규식 (단락 BLOCK) ─────────────────────
        for bp in self._rules.banned_patterns:
            if bp.regex.search(text):
                return self._block("BANNED_KEYWORD", bp.message, hs_code,
                                   self._customs_type(product))

        # ── 3. 짝퉁 위험 브랜드 (단락 BLOCK) ──────────────────
        brand_hay = f"{product.brand or ''} {product.title or ''}".lower()
        for brand in self._rules.counterfeit_brands:
            if brand.lower() in brand_hay:
                return self._block("COUNTERFEIT_BRAND",
                                   f"짝퉁/라이선스 위험 브랜드: {brand}", hs_code,
                                   self._customs_type(product))

        # ── 4. KC 인증 필요 ───────────────────────────────────
        reasons: list[Reason] = []
        requires_kc = False
        for kc in self._rules.kc_categories:
            if kc.match in path:
                requires_kc = True
                if kc.verdict == "block":
                    return self._block("KC_REQUIRED", kc.message, hs_code,
                                       self._customs_type(product), requires_kc=True)
                reasons.append(Reason("KC_REQUIRED", kc.message))

        # ── 5. 통관 한도 초과 (일반통관) → REVIEW ─────────────
        customs_type = self._customs_type(product)
        if customs_type is CustomsType.GENERAL:
            reasons.append(Reason(
                "PRICE_OUT_OF_RANGE",
                f"목록통관 한도(USD {self._rules.list_clearance_limit_usd}) 초과 — 일반통관 관세 확인",
            ))

        # ── 6. HS 미상 → REVIEW ──────────────────────────────
        if hs_verdict is Verdict.REVIEW:
            reasons.append(Reason("HS_UNDETERMINED", "HS코드 분류 불확실 — 관세 산정 확인 필요"))

        verdict = Verdict.REVIEW if reasons else Verdict.PASS
        return ComplianceResult(verdict, reasons, requires_kc, customs_type, hs_code)

    # ── helpers ──────────────────────────────────────────────
    def customs_type_for(self, price, currency: str) -> CustomsType:
        """가격·통화로 통관유형 산정. 모니터 워커가 변동가에 재적용할 수 있게 공개."""
        p = price if isinstance(price, Decimal) else Decimal(str(price))
        if currency == "USD" and p <= self._rules.list_clearance_limit_usd:
            return CustomsType.LIST
        return CustomsType.GENERAL

    def _customs_type(self, product: SourceProduct) -> CustomsType:
        return self.customs_type_for(product.price, product.currency)

    @staticmethod
    def _block(rule_id: str, message: str, hs_code: str | None,
               customs_type: CustomsType, *, requires_kc: bool = False) -> ComplianceResult:
        return ComplianceResult(
            verdict=Verdict.BLOCK,
            reasons=[Reason(rule_id, message)],
            requires_kc=requires_kc,
            customs_type=customs_type,
            hs_code=hs_code,
        )
