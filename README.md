# 직구곰 (jikgugom) — 해외 구매대행 자동화 플랫폼

> 🐻 직구곰: 해외직구(직구)를 대신 해주는 곰. AliExpress에서 곰처럼 부지런히 물어와 네이버에 풀어놓는다.

해외(AliExpress·Amazon 등) 인기상품을 소싱 → 통관·인증 규제 필터 → 전 비용 마진계산 →
한글 상세페이지 → **국내 멀티채널 동시 등록** → 자동/반자동 발주 → 가격·재고 모니터링까지
자동화하는 무재고(드롭십) 플랫폼.

> 돈이 직접 오가는 구간은 **결정론적 파이프라인**, 애매한 판단(시장성·CS)만 **에이전트**.

## 문서

- [`docs/DESIGN.md`](./docs/DESIGN.md) — 시스템 청사진 (재설계 확정본, 벤치마킹 반영)
- [`docs/COMPLIANCE_FILTER.md`](./docs/COMPLIANCE_FILTER.md) — 컴플라이언스 필터 상세 스펙 (우선 구현)
- [`DEPLOY.md`](./DEPLOY.md) — Docker 배포 + 관리자 로그인(Google OAuth) 가이드

## 현황

| 구성요소 | 상태 |
|---|---|
| Adapter (`adapters/`) — AliExpress(제휴 API)·Amazon(Rainforest)·Naver(커머스 API) | ✅ 본체 구현 (매핑·서명 테스트) |
| 컴플라이언스 필터 (`compliance/`) | ✅ 구현 완료 (룰 YAML + 엔진 + 테스트) |
| 마진엔진 (`margin/`) | ✅ 구현 완료 (전 비용 모델 + 통관유형 분기) |
| 모니터 워커 (`monitor/`) | ✅ 구현 완료 (폴링 → pause/reprice/resume) |
| 파이프라인 러너 (`pipeline/`) | ✅ 구현 완료 (오케스트레이션 + 승인 게이트) |
| 소싱 평가 에이전트 (`evaluation/`) | ✅ 구현 완료 (stage 2.5, mock 모드, margin/compliance 재사용) |
| 콘텐츠 에이전트 (`content/`) | ✅ 구현 완료 (ContentBuilder, DeepL+LLM 하이브리드, mock) |
| 주문→발주 가드 (`order/`) | ✅ 구현 완료 (profit_at 재검증 → 자동발주/승인큐) |
| 발주 자동화 (`order/manual.py`) | ✅ 구현 완료 (반자동 HITL — 멱등 원장 기록 → 운영자 매입 확정) |
| 발주 원장 SQL 영속화 (`api/ledger_sql.py`) | ✅ 구현 완료 (`SqlFulfillmentLedger`, idempotency_key unique → 이중결제 물리 차단) |
| 운영자 매입확정 UI (`api/` + `dashboard/`) | ✅ 구현 완료 (매입확정 모달 → PURCHASED, 주문번호·송장 기록) |
| ③ CS 응대 에이전트 (`cs/`) | ✅ 구현 완료 (자동응답 + 민감건 결정론 에스컬레이션) |
| 어드민 대시보드 (`api/` + `dashboard/`) | ✅ 구현 완료 (FastAPI + Next.js, 승인 버튼/발주 큐/매입확정) |
| 관리자 인증 (`api/auth.py`) | ✅ 구현 완료 (Google OAuth + 세션 JWT, 라우트 보호, 로그인 게이트) |
| Docker 배포 (`Dockerfile`·`docker-compose.yml`) | ✅ 구성 완료 (백+프+SQLite 볼륨 한 묶음, [DEPLOY.md](./DEPLOY.md)) |
| DB 영속화 (`api/repository.py`+`db.py`) | ✅ 구현 완료 (Repository 추상화, SQLite/PostgreSQL) |
| 스케줄러 (`api/scheduler.py`) | ✅ 구현 완료 (APScheduler, 가격·재고 주기 점검 → pause/reprice/resume) |
| 멀티채널 동시등록 (`pipeline/multichannel.py`) | ✅ 구현 완료 (`MultiChannelPublisher`, naver+coupang 팬아웃 + 채널별 발행 추적) |
| 설정·어댑터 팩토리 (`core/settings.py`+`adapters/factory.py`) | ✅ 구현 완료 (`.env`→real/mock 자동 배선, fail-fast 검증, 모드 가시화, 키 마스킹) |
| HTTP 견고성 (`adapters/_http.py`) | ✅ 구현 완료 (지수 백오프 재시도, 429 Retry-After, 키 마스킹) |
| 쿠팡 실어댑터 / 예측 ML / 멀티채널 모니터 | 로드맵 (Phase 4) |

## 실행

### 레벨 1 — 키 없이 데모/테스트 (즉시)
```bash
pip install -r requirements.txt          # 핵심은 PyYAML만
python -m jikgugom.demo            # 샘플 카탈로그로 전체 흐름 1회 실행(mock)
python -m pytest -q                       # 194 passed
```

### 레벨 2 — 실 API 키로 동작 (코드 수정 0)
**`.env`만 채우면 데모·대시보드 전체가 자동으로 real로 붙는다.** 키를 채운 레이어만
real, 빈 레이어는 mock 유지 (graceful degradation). 어댑터 선택은 `core/settings.py`
+ `adapters/factory.py`가 담당 — 더 이상 코드를 손으로 고치지 않는다.
```bash
cp .env.example .env       # 아래 키만 채우면 됨
```
```ini
ALIEXPRESS_APP_KEY=...     # 소싱 1차: AliExpress 제휴 Open Platform (무료, 둘 다 필요)
ALIEXPRESS_APP_SECRET=...  #   ALIEXPRESS_TRACKING_ID=<제휴 PID>
# RAINFOREST_API_KEY=...   # 소싱 대체: Amazon(유료). AliExpress 키 없을 때만 사용
NAVER_CLIENT_ID=...        # 네이버 커머스 API (판매자센터, 사업자등록 필요)
NAVER_CLIENT_SECRET=...    #   + pip install bcrypt   (둘 다 있어야 real)
GEMINI_API_KEY=...         # 평가/콘텐츠/CS 에이전트 real (Google Gemini, REST=추가설치 불필요)
# GEMINI_MODEL=gemini-2.5-flash   # 선택: 모델 교체
DEEPL_API_KEY=...          # 본문 번역 real (선택, deepl.com 무료 티어)
FX_RATE=1380               # USD→KRW 환율 / SALES_CHANNELS=naver,coupang
```
- **시작 시 설정 검증(fail-fast)**: 네이버 키를 한쪽만 넣는 등 잘못된 설정은 즉시 에러.
- **모드 가시화**: 대시보드 헤더와 `GET /api/config`가 레이어별 real/mock을 표시 →
  "키 넣었는데 왜 mock?"을 눈으로 확인.
- **운영 견고성**: 외부 API는 지수 백오프 재시도 + 429(Retry-After) 처리, 키는
  로그·에러에 마스킹(`api_key` 등 노출 차단).
- 쿠팡은 현재 mock 고정(실 WING 어댑터 미구현) — `ChannelAdapter` 구현체만 붙이면 real.

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
~~DB 영속화~~ ✅ · ~~스케줄러~~ ✅ · ~~발주 자동화~~ ✅ (반자동 HITL) ·
~~발주 원장 SQL 영속화~~ ✅ · ~~운영자 매입확정 UI~~ ✅ · ~~멀티채널 동시등록~~ ✅.
남은 갭: 채널별 모니터(현재 monitor는 naver primary에 키잉) · 채널별 카테고리 재매핑 · 예측 ML.

## 코드 구조

```
jikgugom/
├── models.py                # 공용 DTO (SourceProduct, ListingDraft, ...)
├── core/                     # 중앙 설정 — .env/환경변수 로딩·검증(fail-fast)·키 마스킹
│   └── settings.py
├── adapters/                # 포트-어댑터: SourceAdapter / ChannelAdapter (ABC)
│   ├── base.py  aliexpress.py  amazon.py  naver.py
│   ├── _http.py              # 공용 HTTP(재시도·백오프·429·키 마스킹)
│   └── factory.py            # build_adapters: 키 유무로 real/mock 조립(Composition Root)
├── compliance/              # 통관·인증 규제 필터 (PASS/BLOCK/REVIEW)
│   ├── engine.py  rules_loader.py  hs_classifier.py  models.py
│   └── rules/*.yaml          # 규칙 = 데이터 (배포 없이 갱신)
├── margin/                   # 전 비용 마진엔진 → 채널 판매가/예상이익
│   ├── engine.py  config.py  models.py
├── monitor/                  # 가격·재고 폴링 → auto-pause/리프라이싱/재개
│   ├── worker.py  models.py
├── pipeline/                 # 소싱→컴플→마진→[평가]→콘텐츠→등록 오케스트레이션
│   ├── runner.py             # PipelineRunner (auto_publish=False=승인 게이트)
│   └── multichannel.py       # MultiChannelPublisher (한 draft → N채널 팬아웃 발행)
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

Python · FastAPI · Celery · PostgreSQL · Redis · S3/CDN
