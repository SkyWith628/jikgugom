"""관리자 인증 — Google OAuth(ID 토큰 검증) + 자체 세션 JWT(HS256, stdlib).

[흐름] 프론트가 Google 로그인으로 받은 ID 토큰을 백엔드에 보내면, 여기서 Google에
       검증(tokeninfo) → 이메일 화이트리스트 확인 → 우리 세션 JWT를 발급한다. 이후
       API 호출은 그 세션 토큰을 Authorization: Bearer 로 보낸다.
[왜 자체 JWT] 매 요청마다 Google에 검증하면 느리다 → 한 번 검증 후 짧은 수명의 자체
       토큰으로 무상태(stateless) 인증. Docker 단일/다중 인스턴스 모두 공유 저장소 불필요.
[의존성 0] HS256 서명은 stdlib(hmac/hashlib)로 구현. 우리가 만든 토큰만 검증하므로
       alg 협상 없음(alg는 'HS256' 고정 확인). 서명 비교는 constant-time.
[보안] 세션 시크릿(SESSION_SECRET)은 환경변수. 토큰에 민감정보 미포함(sub=email만).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from jikgugom.adapters._http import AdapterError, request_json

GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
SESSION_TTL = 12 * 3600   # 12시간


class AuthError(RuntimeError):
    """인증 실패(토큰 무효·만료·검증 실패)."""


# ── Google ID 토큰 검증 ──────────────────────────────────────
def verify_google_id_token(id_token: str, client_id: str) -> str:
    """Google ID 토큰을 검증하고 이메일을 반환. tokeninfo가 서명·만료를 확인한다."""
    try:
        data = request_json(GOOGLE_TOKENINFO, params={"id_token": id_token})
    except AdapterError as e:
        raise AuthError(f"google 검증 실패: {e}") from e
    if data.get("aud") != client_id:
        raise AuthError("aud(클라이언트 ID) 불일치")
    if str(data.get("email_verified")).lower() != "true":
        raise AuthError("이메일 미인증")
    email = data.get("email")
    if not email:
        raise AuthError("토큰에 이메일 없음")
    return str(email)


# ── 세션 JWT (HS256, stdlib) ─────────────────────────────────
def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_session_token(email: str, secret: str, *, ttl: int = SESSION_TTL) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": email, "iat": now, "exp": now + ttl}
    seg = (_b64u(json.dumps(header, separators=(",", ":")).encode()) + "."
           + _b64u(json.dumps(payload, separators=(",", ":")).encode()))
    sig = _b64u(hmac.new(secret.encode(), seg.encode(), hashlib.sha256).digest())
    return f"{seg}.{sig}"


def verify_session_token(token: str, secret: str) -> str:
    """세션 JWT 검증 → email(sub). 서명/만료/형식 오류는 AuthError."""
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("토큰 형식 오류")
    seg = f"{parts[0]}.{parts[1]}"
    expected = _b64u(hmac.new(secret.encode(), seg.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):   # constant-time
        raise AuthError("서명 불일치")
    try:
        payload = json.loads(_b64u_decode(parts[1]))
    except (ValueError, json.JSONDecodeError) as e:
        raise AuthError("페이로드 파싱 실패") from e
    if int(payload.get("exp", 0)) < time.time():
        raise AuthError("토큰 만료")
    sub = payload.get("sub")
    if not sub:
        raise AuthError("sub 없음")
    return str(sub)
