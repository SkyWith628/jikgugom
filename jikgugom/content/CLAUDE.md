# CLAUDE.md — 콘텐츠 생성 에이전트 (`jikgugom/content/`)

영문 원본 상품 → 한글 등록 초안(`ListingDraft`)으로 가공하는 ②번 에이전트.
파이프라인의 `ContentBuilder` 주입 지점에 꽂힌다 (`content_builder=ContentAgent().build`).

## 핵심 원칙

1. **가격 재계산 금지.** `quote.sale_price_krw` 를 받아 그대로 넣는다. 마진은 바깥에서 결정됨.
2. **하이브리드 번역.** 본문=DeepL(`translator.py`), 제목/키워드=LLM(`llm.py`). 비용·품질 균형.
3. **이미지는 CDN 재호스팅.** 원본 핫링크 금지(저작권) → `rehost_images`. 현재 mock.
4. **키 없이도 돈다.** `DEEPL_API_KEY`/`ANTHROPIC_API_KEY` 없으면 mock(glossary/템플릿).
   real 실패 시에도 mock 폴백 → 파이프라인이 끊기지 않는다.

## 파일 구조

```
content/
├── tools.py       # 순수함수: glossary 번역/키워드/이미지재호스팅/HTML조립 + GLOSSARY
├── translator.py  # 본문 번역: DeepL(real) / glossary(mock)
├── llm.py         # 제목 생성: Anthropic(real) / 템플릿(mock)
└── agent.py       # ContentAgent.build(product, quote, category) → ListingDraft
```

## 흐름

```
build(product, quote, category):
  translate(title/desc)  →  extract_keywords  →  seo_title(LLM)  →  rehost_images
       (DeepL/mock)            (tools 순수함수)      (LLM/mock)         (CDN/mock)
  →  ListingDraft(price=quote.sale_price_krw)
```

## 코드 컨벤션

- LLM 호출은 `llm.py`, 번역 호출은 `translator.py` 경유. 다른 곳에서 SDK 직접 호출 금지.
- 도구는 순수 함수(결정론) — 테스트·재현성. mock도 같은 입력 → 같은 출력.
- 제목은 `truncate_title`(기본 50자)로 길이 보정.

## TODO / 제약

- `rehost_images` mock → 실제 S3 업로드 + CDN 배포 필요(원본 다운로드 포함).
- mock 번역 glossary는 데모용 소사전 → 실서비스는 DeepL.
- 이미지 가공(배경제거/한글배너, OpenCV)은 Phase 3.

## 보안

- DeepL/Anthropic 키는 환경변수로만. 코드·깃 커밋 금지.
