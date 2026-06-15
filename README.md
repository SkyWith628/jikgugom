# 직구곰 (jikgugom) — 해외 구매대행 자동화 플랫폼

> 🐻 직구곰: 해외직구(직구)를 대신 해주는 곰. Amazon에서 곰처럼 부지런히 물어와 네이버에 풀어놓는다.

해외(Amazon 등) 인기상품을 소싱 → 통관·인증 규제 필터 → 전 비용 마진계산 →
한글 상세페이지 → **국내 멀티채널 동시 등록** → 자동/반자동 발주 → 가격·재고 모니터링까지
자동화하는 무재고(드롭십) 플랫폼.

> 돈이 직접 오가는 구간은 **결정론적 파이프라인**, 애매한 판단(시장성·CS)만 **에이전트**.

## 🔧 기술적 도전과 해결

| 문제 | 고민 | 해결 |
|---|---|---|
| **자동화 vs 안전성** — 잘못 등록하면 적자 매입·통관 불가 상품처럼 돈·법적 사고로 직결 | 어디까지 LLM에 맡길 것인가. 환각으로 마진을 잘못 계산하면 그대로 손실 | **신뢰 경계를 "돈/규제"에 긋고** 마진·통관·KC인증은 전부 결정론 코드로 확정, LLM은 시장성·콘텐츠·CS 같은 정성판단만 담당 |
| **이중 발주 위험** — 같은 주문이 두 번 발주되면 이중 매입 | 네트워크 재시도·중복 이벤트를 어떻게 막나 | 발주를 **멱등 원장(ledger)**에 기록해 중복 차단 + 발주 직전 `profit_at` 마진 재검증, 적자면 사람이 승인(HITL) |
| **벤더 종속** — Amazon·네이버 API가 언제든 바뀌거나 교체될 수 있음 | 한 벤더에 코드가 묶이면 확장·교체가 불가능 | 소스/채널/저장소를 **Adapter·Repository(ABC)로 추상화** — Rainforest→PA-API, 네이버→쿠팡, SQLite→PostgreSQL을 코드 변경 없이 교체 |

## 문서

- [`docs/DESIGN.md`](./docs/DESIGN.md) — 시스템 청사진 (재설계 확정본, 벤치마킹 반영)
- [`docs/COMPLIANCE_FILTER.md`](./docs/COMPLIANCE_FILTER.md) — 컴플라이언스 필터 상세 스펙 (우선 구현)

## 현황

| 구성요소 | 상태 |
|---|---|
| Adapter (`adapters/`) — Amazon(Rainforest)·Naver(커머스 API) | ✅ 본체 구현 (매핑·OAuth 서명 테스트) |
| 컴플라이언스 필터 (`compliance/`) | ✅ 구현 완료 (룰 YAML + 엔진 + 테스트) |
| 마진엔진 (`margin/`) | ✅ 구현 완료 (전 비용 모델 + 통관유형 분기) |
| 모니터 워커 (`monitor/`) | ✅ 구현 완료 (폴링 → pause/reprice/resume) |
| 파이프라인 러너 (`pipeline/`) | ✅ 구현 완료 (오케스트레이션 + 승인 게이트) |
| 소싱 평가 에이전트 (`evaluation/`) | ✅ 구현 완료 (stage 2.5, mock 모드, margin/compliance 재사용) |
| 콘텐츠 에이전트 (`content/`) | ✅ 구현 완료 (ContentBuilder, DeepL+LLM 하이브리드, mock) |
| 주문→발주 가드 (`order/`) | ✅ 구현 완료 (profit_at 재검증 → 자동발주/승인큐) |
| 발주 자동화 (`order/manual.py`) | ✅ 구현 완료 (반자동 HITL — 멱등 원장 기록 → 운영자 매입 확정) |
| ③ CS 응대 에이전트 (`cs/`) | ✅ 구현 완료 (자동응답 + 민감건 결정론 에스컬레이션) |
| 어드민 대시보드 (`api/` + `dashboard/`) | ✅ 구현 완료 (FastAPI + Next.js, 승인 버튼/발주 큐) |
| DB 영속화 (`api/repository.py`+`db.py`) | ✅ 구현 완료 (Repository 추상화, SQLite/PostgreSQL) |
| 스케줄러 (`api/scheduler.py`) | ✅ 구현 완료 (APScheduler, 가격·재고 주기 점검 → pause/reprice/resume) |
| 멀티채널 동시등록 / 예측 ML | 로드맵 (Phase 3) |

## 실행

### 레벨 1 — 키 없이 데모/테스트 (즉시)
```bash
pip install -r requirements.txt          # 핵심은 PyYAML만
python -m jikgugom.demo            # 샘플 카탈로그로 전체 흐름 1회 실행(mock)
python -m pytest -q                       # 123 passed
```

### 레벨 2 — 실 API 키로 동작
환경변수만 채우면 mock → real 자동 전환 (없는 키는 mock 유지).
```bash
export RAINFOREST_API_KEY=...   # Amazon 소싱 (rainforestapi.com, 유료)
export NAVER_CLIENT_ID=...      # 네이버 커머스 API (판매자센터, 사업자등록 필요)
export NAVER_CLIENT_SECRET=...  #   + pip install bcrypt
export ANTHROPIC_API_KEY=...    # 평가/콘텐츠/CS 에이전트 real (선택)
export DEEPL_API_KEY=...        # 본문 번역 real (선택, deepl.com 무료 티어)
```
실 어댑터 주입은 `demo.py`의 `SampleSource/SampleChannel`을
`AmazonRainforestAdapter(key)` / `NaverSmartstoreAdapter(id, secret)`로 교체.

### 어드민 대시보드 (웹 UI)
승인 버튼·발주 큐·시장성 점수를 눈으로 보는 대시보드 (FastAPI + Next.js).
```bash
# 1) 백엔드 API (터미널 A)
python -m uvicorn api.main:app --port 8000 --reload
# 2) 프론트 (터미널 B)
npm --prefix dashboard install      # 최초 1회
npm --prefix dashboard run dev      # http://localhost:3000
```
상태는 **SQLite 파일(`jikgugom.db`)에 영속** — 재시작해도 승인 내역이 유지된다.
저장소는 `Repository` 인터페이스로 추상화(인메모리 ↔ SQL 교체).
```bash
# 기본: SQLite 파일. PostgreSQL로 전환하려면:
export DATABASE_URL=postgresql+psycopg://user:pw@host/db
```

대시보드 헤더의 **재고·가격 점검** 버튼(또는 `MONITOR_INTERVAL_SECONDS` 주기 스케줄러)이
발행 상품의 원본가·재고를 점검해 자동으로 일시중지/가격조정/재개한다.
```bash
export MONITOR_INTERVAL_SECONDS=300   # 자동 점검 주기(기본 300초, 0=수동만)
```

### 레벨 3 — 상시 운영 (남은 갭)
~~DB 영속화~~ ✅ · ~~스케줄러~~ ✅ · ~~발주 자동화~~ ✅ (반자동 HITL).
남은 갭: 발주 원장 SQL 영속화(`SqlFulfillmentLedger`) · 운영자 매입확정 UI · 멀티채널.

## 코드 구조

```
jikgugom/
├── models.py                # 공용 DTO (SourceProduct, ListingDraft, ...)
├── adapters/                # 포트-어댑터: SourceAdapter / ChannelAdapter (ABC)
│   ├── base.py  amazon.py  naver.py
├── compliance/              # 통관·인증 규제 필터 (PASS/BLOCK/REVIEW)
│   ├── engine.py  rules_loader.py  hs_classifier.py  models.py
│   └── rules/*.yaml          # 규칙 = 데이터 (배포 없이 갱신)
├── margin/                   # 전 비용 마진엔진 → 채널 판매가/예상이익
│   ├── engine.py  config.py  models.py
├── monitor/                  # 가격·재고 폴링 → auto-pause/리프라이싱/재개
│   ├── worker.py  models.py
├── pipeline/                 # 소싱→컴플→마진→[평가]→콘텐츠→등록 오케스트레이션
│   └── runner.py             # PipelineRunner (auto_publish=False=승인 게이트)
├── evaluation/               # ① 소싱 평가 에이전트 (stage 2.5, 시장성 점수)
│   ├── agent.py  llm.py  tools.py  models.py  CLAUDE.md
├── content/                  # ② 콘텐츠 에이전트 (ContentBuilder, 한글 초안 생성)
│   ├── agent.py  translator.py  llm.py  tools.py  CLAUDE.md
├── order/                    # 주문→발주 가드 + 반자동 발주 (멱등 원장)
│   ├── processor.py  fulfiller.py  manual.py  ledger.py  models.py  CLAUDE.md
└── cs/                       # ③ CS 응대 에이전트 (자동응답 + 에스컬레이션)
    ├── agent.py  llm.py  tools.py  models.py  CLAUDE.md
config/costs.yaml             # 비용 파라미터 (환율·관세·수수료)
tests/                        # fakes.py + 계약/엔진 테스트
```

## 스택

Python · FastAPI · SQLAlchemy · APScheduler · Claude (Anthropic) · DeepL · Next.js 16 / React 19 · 네이버 커머스 API · pytest · SQLite/PostgreSQL
