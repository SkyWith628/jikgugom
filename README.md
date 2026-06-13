# 직구곰 (jikgugom) — 해외 구매대행 자동화 플랫폼

> 🐻 직구곰: 해외직구(직구)를 대신 해주는 곰. Amazon에서 곰처럼 부지런히 물어와 네이버에 풀어놓는다.

해외(Amazon 등) 인기상품을 소싱 → 통관·인증 규제 필터 → 전 비용 마진계산 →
한글 상세페이지 → **국내 멀티채널 동시 등록** → 자동/반자동 발주 → 가격·재고 모니터링까지
자동화하는 무재고(드롭십) 플랫폼.

> 돈이 직접 오가는 구간은 **결정론적 파이프라인**, 애매한 판단(시장성·CS)만 **에이전트**.

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
| ③ CS 응대 에이전트 (`cs/`) | ✅ 구현 완료 (자동응답 + 민감건 결정론 에스컬레이션) |
| 어드민 대시보드 (`api/` + `dashboard/`) | ✅ 구현 완료 (FastAPI + Next.js, 승인 버튼/발주 큐) |
| DB 영속화 / 스케줄러 / 멀티채널 / 예측 ML | 로드맵 (Phase 3) |

## 실행

### 레벨 1 — 키 없이 데모/테스트 (즉시)
```bash
pip install -r requirements.txt          # 핵심은 PyYAML만
python -m jikgugom.demo            # 샘플 카탈로그로 전체 흐름 1회 실행(mock)
python -m pytest -q                       # 94 passed
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
인메모리 저장소라 서버 재시작 시 초기화(데모). 백엔드 미실행 시 프론트가 안내 배너 표시.

### 레벨 3 — 상시 운영 (남은 갭)
DB 영속화 · Celery 스케줄러(모니터/소싱 주기 실행) ·
발주 자동화(`FulfillmentAdapter` 실구현) — Phase 3 로드맵. (대시보드는 ✅ 완료)

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
├── order/                    # 주문→발주 가드 (Phase 2): profit_at 재검증
│   ├── processor.py  fulfiller.py  models.py  CLAUDE.md
└── cs/                       # ③ CS 응대 에이전트 (자동응답 + 에스컬레이션)
    ├── agent.py  llm.py  tools.py  models.py  CLAUDE.md
config/costs.yaml             # 비용 파라미터 (환율·관세·수수료)
tests/                        # fakes.py + 계약/엔진 테스트
```

## 스택

Python · FastAPI · Celery · PostgreSQL · Redis · S3/CDN
