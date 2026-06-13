"""어댑터 공용 HTTP 헬퍼 — urllib 기반(외부 의존성 0). JSON 요청/응답 + 에러 정규화.

real 어댑터(Amazon/Naver)가 공유. 테스트는 어댑터의 transport 메서드를 주입/대체해
네트워크 없이 매핑 로직만 검증한다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class AdapterError(RuntimeError):
    """외부 API 호출 실패(HTTP 4xx/5xx, 네트워크, 파싱)를 정규화한 예외."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def request_json(
    url: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    form_body: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict:
    """JSON 응답을 반환하는 단일 HTTP 호출. 실패는 AdapterError로 변환.

    params=쿼리스트링, json_body=JSON 본문, form_body=폼인코딩 본문(둘 중 하나).
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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise AdapterError(f"{method} {url} → HTTP {e.code}", status=e.code) from e
    except urllib.error.URLError as e:
        raise AdapterError(f"{method} {url} → network error: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise AdapterError(f"{method} {url} → invalid JSON response") from e
