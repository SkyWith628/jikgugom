"""제목/키워드 생성 LLM 추상화 — Anthropic(real) / 템플릿(mock) 자동 전환.

[원칙] LLM 호출은 이 파일 경유. 키 없으면 mock. real 파싱 실패 시 mock 폴백.
[역할] SEO 친화 한국어 상품명 생성(제목은 검색 노출의 핵심).
"""

from __future__ import annotations

import json
import os
import re

from sourcing_agent.content.tools import truncate_title

DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # 짧은 카피 생성 → Haiku로 비용 통제


class ContentLLM:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model
        self.mode = "real" if os.getenv("ANTHROPIC_API_KEY") else "mock"

    def seo_title(self, translated_title: str, keywords: list[str],
                  brand: str | None) -> str:
        if self.mode == "mock":
            return self._template_title(translated_title, keywords, brand)
        try:
            return truncate_title(self._call_anthropic(translated_title, keywords, brand))
        except Exception:
            return self._template_title(translated_title, keywords, brand)

    # ── mock ─────────────────────────────────────────────────
    @staticmethod
    def _template_title(translated_title: str, keywords: list[str],
                        brand: str | None) -> str:
        parts = [translated_title]
        for k in keywords:                       # 제목에 없는 키워드 1개 보강
            if k not in translated_title:
                parts.append(k)
                break
        if brand:
            parts.append(brand)
        return truncate_title(" ".join(parts))

    # ── real ─────────────────────────────────────────────────
    def _call_anthropic(self, translated_title: str, keywords: list[str],
                        brand: str | None) -> str:
        import anthropic

        client = anthropic.Anthropic()
        system = (
            "너는 네이버 스마트스토어 상품명 카피라이터다. 검색 노출에 유리한 한국어 "
            f"상품명을 {0}자 이내로 만든다. JSON만 출력: ".format(50)
            + '{"title": "<상품명>"}'
        )
        user = f"번역 제목: {translated_title}\n키워드: {', '.join(keywords)}\n브랜드: {brand or '없음'}"
        msg = client.messages.create(
            model=self._model, max_tokens=128, system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = msg.content[0].text
        try:
            return str(json.loads(raw)["title"])
        except (json.JSONDecodeError, KeyError):
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                raise ValueError("no JSON in response")
            return str(json.loads(m.group(0))["title"])
