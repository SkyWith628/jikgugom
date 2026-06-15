"""Gemini 클라이언트 테스트 — 요청 구성·텍스트 추출·키 분기 (네트워크 없음).

request_json을 대체해 실제 호출 없이 body/url 구성과 응답 파싱만 검증한다.
"""

from __future__ import annotations

import pytest

from jikgugom.core import gemini


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)


def test_available_tracks_key(monkeypatch):
    assert gemini.gemini_available() is False
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert gemini.gemini_available() is True


def test_missing_key_raises():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        gemini.generate_text("sys", "user")


def test_generate_text_builds_request_and_extracts(monkeypatch):
    captured = {}

    def fake_request_json(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return {"candidates": [{"content": {"parts": [{"text": "안녕"}]}}]}

    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.setattr(gemini, "request_json", fake_request_json)

    out = gemini.generate_text("시스템", "유저", max_tokens=64, json_output=True)
    assert out == "안녕"
    # 모델·엔드포인트
    assert captured["url"].endswith("/gemini-2.5-flash:generateContent")
    kw = captured["kwargs"]
    assert kw["method"] == "POST" and kw["params"] == {"key": "secret"}
    body = kw["json_body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "시스템"
    assert body["contents"][0]["parts"][0]["text"] == "유저"
    assert body["generationConfig"]["maxOutputTokens"] == 64
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_model_override_via_env(monkeypatch):
    captured = {}
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    monkeypatch.setattr(gemini, "request_json",
                        lambda url, **kw: captured.update(url=url) or
                        {"candidates": [{"content": {"parts": [{"text": "x"}]}}]})
    gemini.generate_text("s", "u")
    assert "gemini-2.5-pro:generateContent" in captured["url"]


def test_empty_candidates_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(gemini, "request_json", lambda url, **kw: {"candidates": []})
    with pytest.raises(ValueError):
        gemini.generate_text("s", "u")
