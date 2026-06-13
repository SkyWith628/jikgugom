# sourcing-agent — 해외 구매대행 자동화 플랫폼

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
| Adapter 계약 (`adapters/base.py`) + Amazon/Naver 골격 | ✅ 인터페이스 확정 + 계약 테스트 |
| 컴플라이언스 필터 (`compliance/`) | ✅ 구현 완료 (룰 YAML + 엔진 + 테스트) |
| 마진엔진 (`margin/`) | ✅ 구현 완료 (전 비용 모델 + 통관유형 분기) |
| 모니터 워커 (`monitor/`) | ✅ 구현 완료 (폴링 → pause/reprice/resume) |
| 파이프라인 러너 (`pipeline/`) | ✅ 구현 완료 (오케스트레이션 + 승인 게이트) |
| 소싱 평가 에이전트 (`evaluation/`) | ✅ 구현 완료 (stage 2.5, mock 모드, margin/compliance 재사용) |
| 콘텐츠 에이전트 (`content/`) | ✅ 구현 완료 (ContentBuilder, DeepL+LLM 하이브리드, mock) |
| CS 에이전트 | 로드맵 (Phase 2) |
| 멀티채널 등록 / 발주 가드 | 로드맵 (Phase 2) |

## 실행

```bash
pip install -r requirements.txt          # 핵심은 PyYAML만; anthropic/DeepL은 real 모드에서만
python -m pytest -q   # 68 passed
# ANTHROPIC_API_KEY / DEEPL_API_KEY 없으면 에이전트는 자동 mock 모드 (키 없이 전체 동작)
```

## 코드 구조

```
sourcing_agent/
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
└── content/                  # ② 콘텐츠 에이전트 (ContentBuilder, 한글 초안 생성)
    ├── agent.py  translator.py  llm.py  tools.py  CLAUDE.md
config/costs.yaml             # 비용 파라미터 (환율·관세·수수료)
tests/                        # fakes.py + 계약/엔진 테스트
```

## 스택

Python · FastAPI · Celery · PostgreSQL · Redis · S3/CDN
