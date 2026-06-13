# 컴플라이언스 필터 — 모듈 상세 스펙 (우선 구현)

> 상위 설계: [`DESIGN.md`](./DESIGN.md) · 단계 [2 컴플라이언스]
>
> **한 문장 요구사항**: "수집한 해외 상품이 한국으로 합법 통관·판매 가능한지 결정론적으로
> 판정하고, 불가하면 사유와 함께 차단해 이후 비싼 단계(평가·번역·등록)로 흘러가지 않게 한다."

---

## 0. 왜 이 모듈이 먼저인가

- 통관 불가 상품은 **시장성이 아무리 좋아도 0원**이고, 등록 시 **법적 리스크**(전기용품안전관리법·
  식품위생법·관세법 위반)까지 안는다.
- **싼 규칙 필터를 비싼 LLM 평가 앞에** 두는 게 비용상으로도 정답: 차단될 상품에 번역·이미지·
  평가 토큰을 쓰지 않는다.
- 실서비스(셀러오션·셀러봇)에서 "금지어·인증 필터"가 곧 운영 안정성. 여기가 뚫리면 주문받고
  발송 못 하는 클레임이 직격탄.

---

## 1. 입력 / 출력 스펙 (Spec)

```python
# 입력: 소싱 단계가 넘긴 원본 상품
@dataclass
class SourceProduct:
    asin: str
    title_en: str
    description_en: str
    category_path: list[str]      # ["Electronics", "Chargers"]
    price_usd: float
    brand: str | None
    hs_code: str | None           # 없으면 분류기가 추정
    attributes: dict              # 배터리 포함 여부, 용량 등 raw

# 출력: 판정 결과 (DB의 compliance_checks 한 행)
class Verdict(str, Enum):
    PASS = "pass"          # 통과 → 평가 단계로
    BLOCK = "block"        # 차단 → 폐기 (사유 기록)
    REVIEW = "review"      # 보류 → 사람 검토 큐 (애매한 회색지대)

@dataclass
class ComplianceResult:
    verdict: Verdict
    reasons: list[Reason]         # 차단/보류 사유 (룰 id + 메시지)
    requires_kc: bool             # KC인증 필요 품목 여부
    customs_type: Literal["list", "general", "prohibited"]  # 목록/일반/금지
    hs_code: str | None           # 분류 결과
```

> **출력 범위 검증(필수)**: `verdict`는 enum 3종만, `reasons`는 BLOCK/REVIEW일 때 비어있으면 안 됨
> (룰 엔진 버그 가드).

---

## 2. 설계 결정 + Trade-off

### 결정 A — 룰 엔진 = "순차 룰 체인 + 단락 평가(short-circuit)"
- **선택**: 차단 룰들을 우선순위 순으로 평가, 첫 BLOCK에서 즉시 종료
  (단락 평가: 결과가 확정되면 나머지 룰 건너뜀 — 비용·시간 절약)
- **대안**: 모든 룰을 다 돌려 사유 전부 수집 → 사유는 풍부하나 느림
- **Trade-off**: 진단 정보량 vs 속도. → **BLOCK은 단락, REVIEW/PASS는 전체 수집**으로 절충
- **실무**: 안티스팸·KYC 필터의 표준 패턴
- **면접**: "치명적 차단은 단락 평가로 빠르게, 회색지대는 전체 평가로 정확하게 — 비용·정확도 분리"

### 결정 B — 룰은 코드가 아니라 **데이터(YAML)** 로 관리
- **선택**: 금지어 사전·KC품목·금지브랜드를 `rules/*.yaml`에 분리, 엔진은 로더+평가만
- **이유**: 규제·금지어는 **자주 바뀐다**. 룰 추가에 배포가 필요하면 운영이 막힘
- **대안**: 하드코딩 → 빠르지만 변경마다 코드수정·배포
- **Trade-off**: 로딩/검증 오버헤드 vs 운영 민첩성. → 룰 파일은 시작 시 1회 로드 + 캐시
- **실무**: 룰을 데이터로 빼는 건 결제 사기탐지·콘텐츠 모더레이션의 정석

### 결정 C — HS코드 분류는 "사전 매핑 → 실패 시 LLM 추정 → REVIEW"
- **선택**: 카테고리→HS코드 매핑 테이블 우선, 미스 시 LLM 1회 추정, 그래도 애매하면 REVIEW
- **이유**: HS코드가 관세·통관요건을 결정하는데 원본에 없는 경우가 많음. 틀리면 관세 오산 → 마진 붕괴
- **Trade-off**: LLM 호출 비용 vs 분류 정확도. 매핑 캐시로 호출 최소화
- **주의**: LLM 추정은 **참고용**, 확정 불가 시 사람 검토로 — 돈 직결 구간은 LLM 단독 신뢰 금지

---

## 3. 룰 카테고리 (차단/보류 기준)

| 룰 ID | 종류 | 판정 | 예시 |
|---|---|---|---|
| `PROHIBITED_ITEM` | 통관 금지 품목 | BLOCK | 의약품, 무기류, 모의총포, CITES(멸종위기종) 가죽 |
| `KC_REQUIRED` | KC인증 필요 (전기·생활) | BLOCK 또는 REVIEW | 충전기·보조배터리·전기장판·LED |
| `BATTERY_RESTRICTED` | 리튬배터리 항공운송 제한 | REVIEW | 보조배터리 단독, 드론 |
| `FOOD_HEALTH` | 식품·건강기능식품·화장품 | BLOCK | 식약처 신고/검역 대상 |
| `BANNED_KEYWORD` | 금지어 (의료효능·과장) | BLOCK | "치료", "FDA approved", "정품보장" |
| `COUNTERFEIT_BRAND` | 짝퉁 위험 브랜드 | BLOCK | 명품·캐릭터 라이선스 |
| `PRICE_OUT_OF_RANGE` | 마진/통관면세 한계 초과 | REVIEW | 미국발 목록통관 한도(USD 200, 한미FTA) 초과 등 |

> **목록통관 vs 일반통관**: 일정 금액(미국발 USD 200 등) 이하 비과세 간이통관(목록통관) 가능,
> 초과 또는 특정품목은 일반통관(관세·요건 확인) → `customs_type`으로 분기.

룰 데이터 예시:
```yaml
# rules/banned_keywords.yaml
banned_keywords:
  - pattern: "(?i)\\b(FDA|치료|의료용|질병)\\b"
    reason: "의료/효능 표현 — 의약품·의료기기 오인 소지"
    rule_id: BANNED_KEYWORD
# rules/kc_required.yaml
kc_required_categories:
  - match: ["Electronics", "Chargers"]
    requires_kc: true
    verdict: block        # 인증 없으면 판매 불가
    reason: "전기용품 — KC 안전인증 필요"
```

---

## 4. 파일 구조

```
sourcing_agent/compliance/        # (또는 src/compliance/)
├── __init__.py
├── engine.py            # 룰 체인 평가 엔진 (단락 평가 + 사유 수집)
├── rules_loader.py      # rules/*.yaml 로드·검증·캐시
├── hs_classifier.py     # 카테고리→HS 매핑 → 실패 시 LLM 추정 → REVIEW
├── models.py            # SourceProduct / ComplianceResult / Verdict / Reason
├── rules/
│   ├── prohibited.yaml
│   ├── kc_required.yaml
│   ├── banned_keywords.yaml
│   ├── brands.yaml
│   └── hs_map.yaml
└── tests/
    └── test_engine.py   # 엣지 케이스 단위 테스트
```

각 파일 한 줄 역할:
- `engine.py` — 룰들을 우선순위로 돌려 `ComplianceResult` 반환 (핵심 로직)
- `rules_loader.py` — YAML을 Pydantic으로 검증 로드(잘못된 룰은 기동 실패 → fail-fast)
- `hs_classifier.py` — HS코드 확정/추정/보류 판단
- `models.py` — 입출력 데이터클래스 + enum (입출력 스펙의 단일 소스)

---

## 5. 핵심 인터페이스 (스켈레톤)

```python
# engine.py
class ComplianceEngine:
    """
    룰 체인 기반 통관·인증 적합성 판정 엔진.

    [What] 원본 상품 → PASS/BLOCK/REVIEW 판정
    [Why]  돈 직결 구간이라 LLM이 아닌 결정론 규칙으로 — 재현·감사 가능
    [How]  사기탐지·KYC에서 쓰는 룰체인+단락평가 패턴
    """
    def __init__(self, rules: RuleSet, hs: HSClassifier) -> None:
        self._rules = rules
        self._hs = hs

    def evaluate(self, product: SourceProduct) -> ComplianceResult:
        reasons: list[Reason] = []
        hs_code, hs_verdict = self._hs.classify(product)

        for rule in self._rules.ordered():       # 우선순위 순
            outcome = rule.check(product, hs_code)
            if outcome.verdict is Verdict.BLOCK:
                return ComplianceResult(           # 단락: 치명적 차단 즉시 종료
                    verdict=Verdict.BLOCK,
                    reasons=[outcome.reason],
                    requires_kc=outcome.requires_kc,
                    customs_type=outcome.customs_type,
                    hs_code=hs_code,
                )
            if outcome.verdict is Verdict.REVIEW:
                reasons.append(outcome.reason)     # 보류 사유는 모아둠

        verdict = Verdict.REVIEW if (reasons or hs_verdict is Verdict.REVIEW) else Verdict.PASS
        return ComplianceResult(verdict, reasons, ..., hs_code=hs_code)
```

---

## 6. 테스트 포인트 (엣지 케이스)

```
□ 정상 통과: 일반 잡화 → PASS, reasons=[]
□ 금지품: "prescription medicine" → BLOCK / reason=PROHIBITED_ITEM (단락 — 뒤 룰 미실행 확인)
□ KC 품목: USB 충전기 → BLOCK / requires_kc=True
□ 금지어: 설명에 "FDA approved" → BLOCK / BANNED_KEYWORD (대소문자 무관 정규식)
□ 회색지대: 보조배터리(배터리 제한) → REVIEW / 사람 큐로
□ HS 미상: hs_code=None & 매핑 미스 → LLM 추정 호출 → 실패 시 REVIEW
□ 빈 입력/None: title_en="" , brand=None → 크래시 없이 처리 (입력 검증)
□ 룰 파일 오류: 잘못된 YAML → 기동 시 fail-fast (런타임 X)
□ 출력 검증: BLOCK/REVIEW인데 reasons 비면 assert 실패 (엔진 버그 가드)
```

---

## 7. 개선 방향

- **룰 우선순위 메타데이터화**: 현재 코드 순서 의존 → YAML에 `priority` 필드로 분리
- **사유 다국어/사용자노출**: 내부 reason과 운영자 표시 메시지 분리(i18n 여지)
- **HS 분류 캐시 영속화**: (category_path → hs_code) Redis 캐시로 LLM 호출 절감
- **감사 로그(audit)**: 모든 BLOCK을 `compliance_checks`에 적재 → 규제 변경 시 소급 재평가 가능
- **Phase 2 확장**: 채널별 추가 규제(쿠팡 로켓직구 vs 스마트스토어 요건 차이) 룰셋 분리
