"""번역 추상화 — DeepL(real) / glossary(mock) 자동 전환.

[하이브리드] 본문 번역은 DeepL(품질·비용 균형). 제목/키워드 생성은 llm.py(LLM)가 담당.
[중요] DEEPL_API_KEY 없으면 mock. real 실패 시에도 mock으로 graceful degrade.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from jikgugom.content.tools import glossary_translate

DEEPL_ENDPOINT = "https://api-free.deepl.com/v2/translate"


class Translator:
    def __init__(self) -> None:
        self._key = os.getenv("DEEPL_API_KEY")
        self.mode = "real" if self._key else "mock"

    def translate(self, text: str, target: str = "KO") -> str:
        if not text:
            return ""
        if self.mode == "mock":
            return glossary_translate(text)
        try:
            return self._deepl(text, target)
        except Exception:               # 네트워크/응답 실패 → mock 폴백(파이프라인 보호)
            return glossary_translate(text)

    def _deepl(self, text: str, target: str) -> str:
        data = urllib.parse.urlencode(
            {"auth_key": self._key, "text": text, "target_lang": target}
        ).encode()
        req = urllib.request.Request(DEEPL_ENDPOINT, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
        return payload["translations"][0]["text"]
