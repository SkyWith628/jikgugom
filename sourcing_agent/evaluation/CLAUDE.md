# CLAUDE.md — 소싱 평가 에이전트 (`sourcing_agent/evaluation/`)

이 디렉토리는 결정론 파이프라인의 **stage 2.5** 에 삽입되는 평가 에이전트다.
"이 상품이 한국 시장에서 팔릴까?"를 0~100 점수로 자율 판단해 어드민의
**승인 우선순위**를 돕는다 (어드바이저). 발주·등록은 사람이 최종 승인한다.

## 핵심 원칙 (절대 위반 금지)

1. **돈은 여기서 판단하지 않는다.** 마진·적자·통관·KC는 이미 바깥의
   `margin/`·`compliance/` 가 결정론으로 거른 뒤다. 이 에이전트는 그걸 통과한
   상품에만 호출된다. → `MarginQuote` 는 참고 입력일 뿐, **재계산 금지**.
2. **재구현 금지, 재사용.** 마진/가드레일을 여기서 다시 만들지 말 것.
   필요하면 `from sourcing_agent.margin import ...` / `compliance` 를 import.
3. **점수는 게이트가 아니다.** 점수는 정보. 단 `SKIP` 추천은 자동발행을 막고
   사람 검토(`REVIEW`)로 회부한다 — 파이프라인 러너가 처리.
4. **키 없이도 돈다.** `ANTHROPIC_API_KEY` 가 없으면 `llm.py` 가 자동 mock 모드.
   이 동작을 깨지 말 것 (테스트·CI·재현성).

## 파일 구조

```
evaluation/
├── models.py   # MarketSignals, EvaluationResult, Recommendation, recommend()
├── tools.py    # 시장신호 도구(순수함수): 감성/수요/경쟁 + clamp_score/heuristic_score
├── llm.py      # LLM 추상화(real/mock 자동전환 + 파싱실패 graceful degrade)
└── agent.py    # EvaluationAgent: 신호수집 → 점수 → 추천 매핑
```
> 단일 에이전트 선형 흐름이라 LangGraph 미사용. 멀티에이전트(②콘텐츠/③CS)로
> 확장할 때 그래프로 승격 고려.

## 흐름

```
evaluate(product, quote?):
  collect_signals(product)  →  llm.score_market_fit()  →  clamp  →  recommend()
       (tools.py 순수함수)        (mock=휴리스틱 / real=Anthropic)
```

## 코드 컨벤션

- **LLM 호출은 반드시 `llm.py` 경유.** 다른 파일에서 anthropic SDK 직접 호출 금지.
- **도구는 순수 함수** (같은 입력 → 같은 출력). 현재 수요/경쟁은 mock.
- LLM 점수는 `clamp_score` 로 0~100 보정 후 사용.
- real 모드 JSON 파싱 실패 → 예외 전파 말고 `heuristic_score` 폴백 + `degraded=True`.
- 새 신호 추가 시: `tools.py` 함수 → `MarketSignals` 필드 → `heuristic_score` 가중치.

## TODO / 제약

- `estimate_demand`·`assess_competition` 은 mock → 네이버 데이터랩/쇼핑 API 연동 필요.
- 리뷰 감성은 평점·표본수 휴리스틱 → 실서비스는 리뷰 텍스트 감성분석 모델.
- 경쟁사 조회를 실 API로 바꿀 땐 **Adapter 패턴**으로 추상화(소스/채널과 일관).

## 보안

- API 키는 환경변수로만. 코드·깃 커밋 금지.
