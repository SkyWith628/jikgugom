"""관리자 인증 테스트 — 세션 JWT 라운드트립·변조·만료 + Google 검증(네트워크 없음).

세션 토큰은 우리가 만든 것만 검증하므로 서명/만료/형식만 막으면 된다.
Google 검증은 tokeninfo 호출(request_json)을 대체해 aud/email 분기를 확인한다.
"""

from __future__ import annotations

import time

import pytest

from api import auth
from api.auth import (
    AuthError,
    create_session_token,
    verify_google_id_token,
    verify_session_token,
)
from jikgugom.core.settings import Settings

SECRET = "test-secret"


# ── 세션 JWT ─────────────────────────────────────────────────
def test_session_token_roundtrip():
    tok = create_session_token("admin@x.com", SECRET)
    assert verify_session_token(tok, SECRET) == "admin@x.com"


def test_tampered_signature_rejected():
    tok = create_session_token("admin@x.com", SECRET)
    with pytest.raises(AuthError):
        verify_session_token(tok + "x", SECRET)


def test_wrong_secret_rejected():
    tok = create_session_token("admin@x.com", SECRET)
    with pytest.raises(AuthError):
        verify_session_token(tok, "other-secret")


def test_expired_token_rejected():
    tok = create_session_token("admin@x.com", SECRET, ttl=-1)
    with pytest.raises(AuthError, match="만료"):
        verify_session_token(tok, SECRET)


def test_malformed_token_rejected():
    with pytest.raises(AuthError):
        verify_session_token("not.a.valid.jwt.x", SECRET)
    with pytest.raises(AuthError):
        verify_session_token("garbage", SECRET)


# ── Google ID 토큰 검증 ──────────────────────────────────────
def test_google_verify_success(monkeypatch):
    monkeypatch.setattr(auth, "request_json", lambda url, **kw: {
        "aud": "client-123", "email": "a@x.com", "email_verified": "true"})
    assert verify_google_id_token("idtok", "client-123") == "a@x.com"


def test_google_verify_aud_mismatch(monkeypatch):
    monkeypatch.setattr(auth, "request_json", lambda url, **kw: {
        "aud": "other", "email": "a@x.com", "email_verified": "true"})
    with pytest.raises(AuthError, match="aud"):
        verify_google_id_token("idtok", "client-123")


def test_google_verify_email_not_verified(monkeypatch):
    monkeypatch.setattr(auth, "request_json", lambda url, **kw: {
        "aud": "client-123", "email": "a@x.com", "email_verified": "false"})
    with pytest.raises(AuthError, match="미인증"):
        verify_google_id_token("idtok", "client-123")


# ── auth_enabled 토글 ────────────────────────────────────────
def test_auth_disabled_without_config():
    assert Settings().auth_enabled is False


def test_auth_enabled_requires_both():
    assert Settings(google_client_id="c").auth_enabled is False          # 이메일 없음
    assert Settings(admin_allowed_emails=("a@x.com",)).auth_enabled is False  # client_id 없음
    assert Settings(google_client_id="c",
                    admin_allowed_emails=("a@x.com",)).auth_enabled is True
