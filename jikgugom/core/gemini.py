"""Gemini(Google) LLM 호출 — REST(urllib) 기반, 외부 SDK 의존 0.

[What] 에이전트(평가·콘텐츠·CS)가 공유하는 단일 LLM 호출점. system+user 프롬프트를
       Gemini generateContent에 보내고 텍스트를 돌려준다.
[Why]  제공자(Anthropic→Gemini)를 한 곳에서 갈아끼우려고 호출을 중앙화. REST를 쓰면
       새 SDK 의존성이 없고(_http 재사용), 키는 쿼리스트링(key=)으로 가되 _http의
       마스킹이 로그·에러에서 가린다.
[How]  mock/real 분기는 호출 측(각 llm.py)이 gemini_available()로 판단. 여기는 real 전용.

모델은 GEMINI_MODEL로 교체 가능(기본은 값싼 flash — 분류/카피 생성에 충분).
"""

from __future__ import annotations

import os

from jikgugom.adapters._http import request_json

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash"   # 값싼 분류·짧은 카피 → flash로 비용 통제


def gemini_available() -> bool:
    """GEMINI_API_KEY 유무 — 에이전트의 real/mock 분기 기준."""
    return bool(os.getenv("GEMINI_API_KEY"))


def gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)


def generate_text(system: str, user: str, *, model: str | None = None,
                  max_tokens: int = 256, temperature: float = 0.2,
                  json_output: bool = False) -> str:
    """Gemini로 텍스트 생성. json_output=True면 JSON만 출력하도록 강제(파싱 안정).

    GEMINI_API_KEY가 없으면 RuntimeError — 호출 측에서 mock으로 분기해야 한다.
    """
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")

    gen_config: dict = {"maxOutputTokens": max_tokens, "temperature": temperature}
    if json_output:
        gen_config["responseMimeType"] = "application/json"

    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen_config,
    }
    url = f"{API_BASE}/{model or gemini_model()}:generateContent"
    data = request_json(url, method="POST", params={"key": key}, json_body=body)
    return _extract_text(data)


def _extract_text(data: dict) -> str:
    """generateContent 응답에서 첫 후보의 텍스트를 합쳐 반환."""
    candidates = data.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini 응답에 candidates 없음")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [p["text"] for p in parts if p.get("text")]
    if not texts:
        raise ValueError("Gemini 응답에 text 파트 없음")
    return "".join(texts)
