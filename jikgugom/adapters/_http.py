"""어댑터 공용 HTTP 헬퍼 — urllib 기반(외부 의존성 0). JSON 요청/응답 + 에러 정규화.

real 어댑터(Amazon/Naver)가 공유. 테스트는 어댑터의 transport 메서드를 주입/대체해
네트워크 없이 매핑 로직만 검증한다.

[견고성] 실 API는 일시적으로 실패한다(429/5xx/네트워크). 지수 백오프로 재시도하고,
         429는 Retry-After를 존중한다. 4xx(429 제외)는 클라이언트 오류라 재시도 안 함.
[보안] 쿼리스트링에 키가 실리는 API(예: Rainforest api_key)가 있어, 에러 메시지의 URL은
       민감 파라미터 값을 마스킹한다(키가 로그·예외에 평문 노출되는 사고 방지).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# 일시적(retryable) 상태 코드 — 재시도하면 성공할 수 있는 것만
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# 에러 메시지 URL에서 값을 가릴 민감 쿼리 파라미터
_SENSITIVE_PARAMS = {
    "api_key", "auth_key", "key", "token", "secret",
    "client_secret", "client_secret_sign", "access_token",
}
_BACKOFF_BASE = 0.5   # 초. 백오프 = base * 2**attempt (상한 8s)
_BACKOFF_CAP = 8.0


class AdapterError(RuntimeError):
    """외부 API 호출 실패(HTTP 4xx/5xx, 네트워크, 파싱)를 정규화한 예외."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _mask_url(url: str) -> str:
    """URL 쿼리의 민감 파라미터 값을 ***로 가린다(키 로그 노출 방지)."""
    base, sep, query = url.partition("?")
    if not sep:
        return url
    masked = []
    for kv in query.split("&"):
        k, eq, v = kv.partition("=")
        if k.lower() in _SENSITIVE_PARAMS and v:
            v = "***"
        masked.append(f"{k}{eq}{v}")
    return f"{base}?{'&'.join(masked)}"


def _backoff(attempt: int) -> float:
    return min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_CAP)


def _retry_after(err: urllib.error.HTTPError, attempt: int) -> float:
    """429의 Retry-After(초) 존중. 없거나 파싱 실패 시 백오프로 대체."""
    raw = err.headers.get("Retry-After") if err.headers else None
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _backoff(attempt)


def request_json(
    url: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    form_body: dict[str, Any] | None = None,
    timeout: float = 15.0,
    max_retries: int = 2,
) -> dict:
    """JSON 응답을 반환하는 단일 HTTP 호출. 실패는 AdapterError로 변환.

    params=쿼리스트링, json_body=JSON 본문, form_body=폼인코딩 본문(둘 중 하나).
    일시적 실패(429/5xx/네트워크)는 max_retries회까지 지수 백오프로 재시도한다.
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    data: bytes | None = None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if json_body is not None:
        data = json.dumps(json_body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    elif form_body is not None:
        data = urllib.parse.urlencode(form_body).encode()
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    safe_url = _mask_url(url)
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_STATUS and attempt < max_retries:
                time.sleep(_retry_after(e, attempt))
                attempt += 1
                continue
            raise AdapterError(f"{method} {safe_url} → HTTP {e.code}", status=e.code) from e
        except urllib.error.URLError as e:
            if attempt < max_retries:        # 네트워크 일시 장애 → 재시도
                time.sleep(_backoff(attempt))
                attempt += 1
                continue
            raise AdapterError(f"{method} {safe_url} → network error: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise AdapterError(f"{method} {safe_url} → invalid JSON response") from e
