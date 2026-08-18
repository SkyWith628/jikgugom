# 설계 — 해외 구매대행 자동화 플랫폼 (as-built 동기화본)

> **이 문서가 시스템의 청사진(blueprint)이다.** 실제 서비스(셀러오션·플레이오토·AutoDS 등)
> 벤치마킹으로 재설계한 확정본을, 이후 **as-built(실제 구현)** 상태에 맞춰 동기화했다.
> 파이프라인 7단계 + 어드민 대시보드 + 관리자 OAuth 인증 + Docker 배포까지 **구현 완료**이며,
> 남은 것은 채널별 모니터·채널 카테고리 재매핑·베스트셀러 예측 ML(§7 로드맵)뿐이다.
>
> **1차 소싱처 = AliExpress(중국발)**. 컴플라이언스 스펙 → [`COMPLIANCE_FILTER.md`](./COMPLIANCE_FILTER.md)

---

## 0. 용어 (이 문서 전반)

- **구매대행(Dropshipping/Proxy-buy)**: 재고 없이 주문이 들어오면 해외에서 대신 구매·배송하는 모델
- **무재고**: 미리 사두지 않고 주문 후 발주 → 재고 리스크 0, 대신 원본 품절·가격변동 리스크
- **Adapter 패턴(어댑터)**: 외부 시스템(소스/채널)을 공통 인터페이스로 감싸 교체 가능하게 하는 설계
  - 예) `AliExpressAdapter`를 `AmazonRainforestAdapter`로 코드 수정 없이 교체
- **HS코드(품목분류코드)**: 국제 통일 상품분류 번호. 관세율·통관요건을 결정하는 기준
- **KC인증(Korea Certification)**: 전기·생활용품 안전 인증. 없으면 통관/판매 불가 품목 존재
- **PCCC(개인통관고유부호)**: 해외직구 통관 시 개인 식별번호. 개인정보보호법 대상 → 암호화 저장

---

## 1. 사업 개요

AliExpress 등 해외 인기상품을 소싱 → 통관·인증 규제 필터 → 전 비용 마진계산 →
한글 상세페이지 생성 → **국내 멀티채널 동시 등록**(스마트스토어·쿠팡) →
주문 시 자동/반자동 발주 → 가격·재고 실시간 모니터링·CS까지 자동화.

- 배송 모델: 무재고 (주문 후 해외 발주)
- 목표: 포트폴리오 → 실거래 가능한 반자동 서비스로 단계 확장

### 확정 타깃 (1차 구현 대상)

| 축 | 1차 확정 | 추상화(교체 가능) | 근거 |
|---|---|---|---|
| **소싱 소스** | **AliExpress**(중국발) | `SourceAdapter` | 제휴(Affiliate) 공개 API로 상품·가격 수집 용이, 진입장벽 낮음. Amazon 어댑터도 대체 소스로 유지 |
| 소싱 접근 | **AliExpress Affiliate API**(app_key/secret 서명) | → Amazon Rainforest / PA-API | 키만 채우면 real, 없으면 샘플 카탈로그(mock). 소스만 교체 |
| **판매 채널** | **네이버 스마트스토어 + 쿠팡** | `ChannelAdapter` | 국내 1위 오픈마켓 + 멀티채널. 소싱 1회 비용을 N채널에 분산 |

> 1차는 **AliExpress → 네이버·쿠팡 멀티채널**. 양끝을 Adapter로 가둬 소스(Amazon)·채널(11번가 등)을
> 코드 결합 없이 붙인다. (이 "교체 가능 설계"가 면접 핵심 어필)
>
> ⚠ **소싱처 = 통관 한도 파라미터.** 중국발은 목록통관 면세 한도가 **일반국 USD 150**(미국발 한미FTA는 200).
> `compliance/rules/customs.yaml`의 `list_clearance_limit_usd`로 관리 → 소스 교체 시 이 값만 갱신(§5).

---

## 2. 벤치마킹 — 기존 설계가 놓친 5가지

| # | 기존 설계 | 실제 서비스(벤치마크) | 재설계 반영 |
|---|---|---|---|
| 1 | 단일 채널(스마트스토어) | 멀티채널 동시 등록으로 소싱비용 분산이 수익의 핵심 | **채널 Adapter (N:M)** |
| 2 | "규제 여부" 한 줄 | KC인증·통관요건·금지어·짝퉁 차단이 생사 | **컴플라이언스 필터 일급 모듈** |
| 3 | 모니터링이 로드맵 뒤 | 원본 품절/가격인상 자동 대응이 MVP 필수 | **모니터 워커 Phase 1 승격** |
| 4 | `price_usd→price_krw` 단순 | 관세·부가세·수수료·환율버퍼 전부 반영 | **마진엔진 전 비용 모델** |
| 5 | 발주 100% 수동 | 자동발주 + 임계치 가드로 스케일 | **반자동 발주(가드)** |

벤치마크 대상: 셀러오션·셀웨이·셀러봇(해외 구매대행 특화), 플레이오토·사방넷·이셀러스(멀티채널 ERP),
오너클랜·젠트레이드(실시간 재고 동기화), AutoDS·DSers·Zendrop(가격/재고 자동 모니터링·발주).

---

## 3. 전체 파이프라인

```
[1 소싱]   카테고리별 인기상품 수집 (Adapter)
   → [2 컴플라이언스]  통관·KC·금지어·브랜드 차단     ★우선 구현
   → [평가]   시장성 점수 (jikgugom, 통과분만)
   → [3 마진엔진]   전 비용 반영 + 채널별 판매가
   → [4 콘텐츠]   카테고리 템플릿 + LLM(제목/요약) + 이미지 CDN 재호스팅
   → [5 멀티채널 등록]   채널 Adapter 동시 발행 (사람 승인 게이트)
   → [6 모니터]   가격·재고·환율 폴링 → auto-pause/가격조정
   → [7 주문·발주]   주문 수집 → 가드 → 자동/반자동 발주 → 통관추적 → CS
```

**핵심 철학**: 돈이 직접 오가는 구간(소싱·필터·마진·발주)은 **결정론적 규칙**으로,
애매한 판단(시장성 평가·CS 응대)만 **에이전트**로. → 하이브리드.

---

## 4. 시스템 아키텍처

```
            ┌──────────── Admin Dashboard (Next.js) ────────────┐
            │ 승인 큐 · 발주 큐 · 매입확정 모달 · 모니터링         │
            │ (Google OAuth 로그인 게이트 · 세션 JWT · 라우트 보호)│
            └───────────────────────┬───────────────────────────┘
                                    │ REST
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI (api/) + APScheduler (인프로세스 스케줄러)                │
│                                                                   │
│ [1 소싱]→[2 컴플라이언스]→[평가]→[3 마진]→[4 콘텐츠]→[5 멀티채널] │
│                                              [6 모니터]  [7 주문·발주]│
└─────────────────────────────────────────────────────────────────┘
  ↕ Repository 추상화 → SQLite / PostgreSQL (DATABASE_URL 교체)
  ↕ core/settings.py → .env 기반 real/mock 자동 배선 · 키 마스킹
```

> **실제 스택 주석:** 청사진 초안의 Celery+Celery Beat+Redis는 포트폴리오 단계 오버엔지니어링이라
> **APScheduler 인프로세스**로 축소(별도 인프라 0). AI 제공자는 **Google Gemini(REST 직호출)**.
> 이미지 CDN 재호스팅·Secrets Manager·WebSocket은 로드맵(§7·§8).

### 결정론 vs 에이전트 배치

| 단계 | 방식 | 비고 |
|---|---|---|
| 1 소싱 | 결정론 | AliExpress(1차)→Amazon 교체 가능 (`SourceAdapter`) |
| 2 컴플라이언스 | 결정론(규칙) | ★평가보다 **앞**: 싼 필터로 비싼 LLM 평가 낭비 차단 |
| 평가 | 에이전트 | `evaluation/` (Gemini, mock 폴백), 통과분만 |
| 3 마진엔진 | 결정론 | config(YAML) 비용 파라미터 |
| 4 콘텐츠 | 하이브리드 | 템플릿 우선 + LLM(Gemini)은 제목/요약만 (토큰 통제) |
| 5 멀티채널 등록 | 결정론 | 채널 Adapter 팬아웃(naver+coupang) + 사람 승인 게이트 |
| 6 모니터 | 결정론 | APScheduler 폴링 → pause/reprice/resume |
| 7 주문·발주 | 하이브리드 | 가드(profit_at 재계산) 통과=자동, 초과=승인 큐 / CS=LLM |

---

## 5. 핵심 설계 결정 (Trade-off)

### 결정 1 — 멀티채널 우선 (채널 Adapter)
- **선택**: `ChannelAdapter` 인터페이스로 채널 추상화 (스마트스토어/쿠팡/11번가)
- **이유**: 소싱 1회 비용(평가+번역+이미지)을 N채널에 분산 → 채널 추가 한계비용 ≈ 0
- **대안**: 단일 채널 → 단순하나 마진 구조상 비현실적
- **Trade-off**: 채널별 카테고리 매핑/수수료 복잡도↑ vs 채널당 매출 선형 확장
- **면접**: "소스도 채널도 Adapter로 추상화해 N:M을 결합도 없이 확장"

### 결정 2 — 컴플라이언스 필터를 평가 **앞**에 배치
- **선택**: 규제 필터를 시장성 평가보다 먼저, 차단 사유를 DB 기록
- **이유**: 통관 불가품은 시장성 무관 0원 가치 + 등록 시 법적 리스크. 싼 규칙을 비싼 LLM 앞에
- **대안**: 등록 직전 검사 → 번역·이미지 비용 다 쓴 뒤라 낭비
- **Trade-off**: 품목분류·금지어 사전 유지보수 vs 클레임·법적 리스크 제거

### 결정 3 — 마진엔진 전 비용 모델 (AliExpress(중국발) → 멀티채널 구체값)
```
도착원가 = 상품가(USD×환율×버퍼1.05) + 미국내배송·국제배송 + 관세(HS코드별) + 부가세10%
최종원가 = 도착원가 + 국내배송 + 반품충당(예 3%)
판매가  = 최종원가 ÷ (1 - 목표마진율 - 네이버수수료 - 결제수수료)
```
**1차 타깃 파라미터 (config/costs.yaml·customs.yaml로 분리, 값은 정책 변동 시 갱신)**
- **목록통관 면세 한도**: 1차 소싱처 AliExpress(중국발)이라 **일반국 기준 USD 150** 이하면 관세·부가세 면제 →
  초과·과세대상 품목은 일반통관으로 분기(관세+부가세10% 부과). `customs_type`이 결정.
  (미국발로 교체 시 한미FTA로 200 — `customs.yaml`의 `list_clearance_limit_usd`만 갱신.)
- **네이버 수수료**: 매출연동수수료(카테고리별, 통상 수% 대) + 네이버페이 주문관리(결제)수수료.
  → 정확한 율은 카테고리별 표로 관리, 보수적으로 상한 적용.
- **환율버퍼 1.05**: 주문~발주 사이 환율 변동 흡수 (발주 시점 가드에서 재검증)

- **이유**: "팔수록 적자"의 99%는 숨은 비용 누락. 중국발 $150 한도를 넘기면 관세·부가세가 마진을 먹음
- **Trade-off**: 보수적 가격 → 경쟁력 약간↓ vs 마이너스 마진 원천 차단

### 결정 4 — 반자동 발주 (가드)
```
주문 수신 → 발주 직전 마진 재검증
   ├ 원가변동 ≤ 임계치(예 5%) & 재고 OK → 자동발주
   └ 초과/품절 → 사람 승인 큐
```
- **이유**: 정상 케이스(대부분) 무인 처리해야 스케일. 위험 케이스만 사람
- **Trade-off**: 가드 로직 복잡도 vs 처리량·안전 균형 (실서비스 표준 절충)

---

## 6. 데이터 모델 (★ = 재설계 변경점)

```sql
source_products   -- 수집 원본 (asin, raw_data JSONB, price_usd, hs_code ★)
compliance_checks -- ★신규: product_id, verdict(pass/block), reasons[], requires_kc
products          -- ★개명(listings→): 채널 독립 마스터
                  --   (title_ko, images_cdn[], cost_breakdown JSONB, status)
channel_listings  -- ★신규: product_id, channel, channel_category_id,
                  --   price_krw, channel_product_no, status
price_snapshots   -- ★개명: source_price, fx_rate, in_stock, captured_at
orders            -- channel, channel_order_no, buyer_pccc(암호화),
                  --   cost_at_order JSONB ★, profit_krw, status
order_guards      -- ★신규: order_id, check(margin/stock), passed, routed_to
```

### 상태 머신
```
products:          draft → translated → reviewed → ready
channel_listings:  pending → listed → paused(자동중지) → delisted   ★채널별 독립
orders:            received → guard_checked → [auto_ordered | pending_approval]
                   → amazon_ordered → shipped → customs → delivered
                   → (refund_requested → refunded)
```

---

## 7. 구현 로드맵 (MoSCoW)

```
Phase 1 — MVP ✅ 완료
  [Must]  소싱 Adapter(AliExpress·Amazon) / 컴플라이언스 필터 / 마진엔진 / 평가 에이전트   ✅
  [Must]  채널 등록(스마트스토어) + 사람 승인 게이트                                        ✅
  [Must]  가격·재고 모니터(APScheduler) → auto-pause/reprice                              ✅
  [Should] Admin Dashboard (승인 큐·발주 큐·매입확정)                                       ✅

Phase 2 — 멀티채널 + 반자동 발주 ✅ 완료
  [Must]  채널 Adapter 2번째(쿠팡) — N:M 팬아웃 검증                                        ✅
  [Must]  주문 → 가드(profit_at 재계산) → 멱등 원장(SQL) → 반자동 발주(HITL)               ✅
  [Should] CS 응대 에이전트 / 콘텐츠 에이전트(Gemini)                                        ✅
  [+추가]  관리자 OAuth 인증 · Docker Compose 배포 · .env real/mock 자동 배선               ✅

Phase 3 — 고도화 🔭 남은 로드맵
  [Should] 채널별 독립 모니터 (현재 monitor는 naver primary에 키잉)
  [Should] 채널별 카테고리 재매핑 (channel_listings.channel_category_id 실사용)
  [Should] 베스트셀러 예측 ML / 채널 추가(11번가·G마켓)
  [Could]  이미지 CDN 재호스팅 · OpenCV 배경제거·한글배너 · 동적 리프라이싱
  [Could]  PCCC 암호화 저장·발주 후 폐기(§8) 실제 구현
```

---

## 8. 보안 · 법무 체크리스트

```
[기존 유지]
□ 외부 API키 → Secrets Manager (코드·깃 금지)
□ PCCC → 암호화 저장, 발주 직전 복호화·발주 후 메모리 폐기 (로그 금지)
□ 네이버/채널 OAuth 토큰 자동 갱신
□ 서드파티 + 자체 API 양쪽 Rate Limiting
□ 주문 데이터 접근 RBAC (운영자/CS 권한 분리)

[★재설계 추가]
□ 사업 요건: 구매대행 사업자등록 + 통신판매업 신고 (채널 입점 전제조건)
□ 이미지 저작권: 원본 직접 핫링크 금지 → 자체 CDN 재호스팅
□ 멱등성(Idempotency): 주문→발주 멱등키로 중복발주(이중결제) 차단
□ 통관: HS코드 기반 관세·요건 매핑 / 목록통관 vs 일반통관 분기
```

---

## 9. 현재 구현 vs 로드맵

| 구성요소 | 상태 |
|---|---|
| 소싱 Adapter (AliExpress 1차·Amazon 대체·Naver 채널) | ✅ 구현 (`adapters/` + `factory.py` real/mock 배선, `_http` 백오프) |
| **컴플라이언스 필터** | ✅ 구현 (`compliance/`, 통관 한도 중국발 $150, [스펙](./COMPLIANCE_FILTER.md)) |
| **마진엔진** | ✅ 구현 (`margin/`, 전 비용 모델 + 통관유형 분기, `profit_at` 발주가드) |
| **모니터** | ✅ 구현 (`monitor/` + `api/scheduler.py` APScheduler → pause/reprice/resume) |
| **파이프라인 러너** | ✅ 구현 (`pipeline/runner.py`, 소싱→…→등록 오케스트레이션 + 승인 게이트) |
| **멀티채널 동시등록** | ✅ 구현 (`pipeline/multichannel.py`, naver+coupang 팬아웃 + 채널별 발행 추적) |
| **소싱 평가 에이전트** | ✅ 구현 (`evaluation/`, Gemini + mock 폴백, margin/compliance 재사용) |
| **콘텐츠 에이전트** | ✅ 구현 (`content/`, 번역+LLM 초안 Gemini + mock) |
| **CS 응대 에이전트** | ✅ 구현 (`cs/`, 자동응답 + 민감건 결정론 에스컬레이션) |
| **주문→발주 (가드+HITL)** | ✅ 구현 (`order/`, profit_at 재검증 → 자동/승인큐, 멱등 원장 `api/ledger_sql.py`) |
| **DB 영속화** | ✅ 구현 (`api/repository.py`+`db.py`, Repository 추상화 SQLite/PostgreSQL) |
| **어드민 대시보드 + 인증** | ✅ 구현 (FastAPI + Next.js, 승인/발주/매입확정, Google OAuth + 세션 JWT) |
| **배포** | ✅ 구성 (Docker Compose, [DEPLOY.md](../DEPLOY.md)) |
| 채널별 모니터·카테고리 재매핑·예측 ML | 🔭 로드맵 (Phase 3, §7) |
