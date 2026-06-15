"""HTTP 헬퍼 견고성 테스트 — 재시도/백오프/429/키 마스킹 (네트워크 없음).

urlopen과 time.sleep을 대체해 실제 네트워크·대기 없이 재시도 정책만 검증한다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from jikgugom.adapters import _http
from jikgugom.adapters._http import AdapterError, _mask_url, request_json


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


def _httperror(code, headers=None):
    return urllib.error.HTTPError("http://x", code, "err", headers or {}, None)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(_http.time, "sleep", lambda s: None)   # 대기 제거


def _patch_urlopen(monkeypatch, behaviors):
    seq = iter(behaviors)

    def fake(req, timeout=None):
        b = next(seq)
        if isinstance(b, Exception):
            raise b
        return b

    monkeypatch.setattr(urllib.request, "urlopen", fake)


def test_retries_on_503_then_succeeds(monkeypatch):
    _patch_urlopen(monkeypatch, [_httperror(503), FakeResp({"ok": True})])
    assert request_json("http://x", max_retries=2) == {"ok": True}


def test_no_retry_on_400(monkeypatch):
    calls = {"n": 0}

    def fake(req, timeout=None):
        calls["n"] += 1
        raise _httperror(400)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(AdapterError) as ei:
        request_json("http://x", max_retries=3)
    assert ei.value.status == 400 and calls["n"] == 1   # 4xx는 재시도 안 함


def test_429_is_retried_honoring_retry_after(monkeypatch):
    _patch_urlopen(monkeypatch, [_httperror(429, {"Retry-After": "0"}), FakeResp({"ok": 1})])
    assert request_json("http://x", max_retries=1) == {"ok": 1}


def test_exhausts_retries_then_raises(monkeypatch):
    _patch_urlopen(monkeypatch, [_httperror(500), _httperror(500), _httperror(500)])
    with pytest.raises(AdapterError):
        request_json("http://x", max_retries=2)


def test_network_error_is_retried(monkeypatch):
    _patch_urlopen(monkeypatch, [urllib.error.URLError("down"), FakeResp({"ok": 2})])
    assert request_json("http://x", max_retries=1) == {"ok": 2}


def test_mask_url_hides_sensitive_params():
    masked = _mask_url("https://api/x?api_key=SECRET&type=product")
    assert "SECRET" not in masked
    assert "api_key=***" in masked and "type=product" in masked


def test_error_message_masks_key(monkeypatch):
    _patch_urlopen(monkeypatch, [_httperror(500), _httperror(500), _httperror(500)])
    with pytest.raises(AdapterError) as ei:
        request_json("https://api/x", params={"api_key": "SECRET"}, max_retries=2)
    assert "SECRET" not in str(ei.value)   # 키가 예외 메시지에 평문 노출되지 않음
