"""Security guards from docs/reviews/security-2026-10.md."""

import base64
import os

import pytest
from pydantic import SecretStr, ValidationError
from starlette.requests import Request

from igs_core import ratelimit as public_chat  # limiter lives in igs_core.ratelimit
from igs_core.config import Settings
from igs_core.errors import ProblemError

SECRET = "test-proxy-secret"  # noqa: S105
KEY = SecretStr(base64.b64encode(os.urandom(32)).decode())


def test_demo_mode_is_off_by_default_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IGS_DB_APP_ROLE", "igs_app")
    assert Settings(environment="local").demo_mode is True
    assert Settings(environment="production", temporal_codec_key=KEY).demo_mode is False
    explicit = Settings(environment="production", temporal_codec_key=KEY, demo_mode=True)
    assert explicit.demo_mode is True


def test_production_requires_rls_role_and_codec_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IGS_DB_APP_ROLE", raising=False)
    with pytest.raises(ValidationError, match="IGS_DB_APP_ROLE"):
        Settings(environment="production", temporal_codec_key=KEY)
    monkeypatch.setenv("IGS_DB_APP_ROLE", "igs_app")
    with pytest.raises(ValidationError, match="CODEC_KEY"):
        Settings(environment="production")


def _request(peer: str, forwarded: str | None, extra: dict[str, str] | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    headers += [(k.encode(), v.encode()) for k, v in (extra or {}).items()]
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def test_forwarded_for_is_ignored_without_trusted_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IGS_TRUSTED_PROXY_HOPS", raising=False)
    assert public_chat._client_key(_request("10.0.0.9", "1.2.3.4")) == "10.0.0.9"


def test_forwarded_for_uses_the_hop_our_proxy_appended(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IGS_TRUSTED_PROXY_HOPS", "1")
    # The client prepends a fake address; the load balancer appends the real one.
    spoofed = _request("10.0.0.9", "6.6.6.6, 203.0.113.7")
    assert public_chat._client_key(spoofed) == "203.0.113.7"


def test_web_proxy_client_ip_needs_the_shared_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    # Readiness B-02: behind Vercel every visitor shares a few egress IPs.
    monkeypatch.setenv("IGS_TRUSTED_PROXY_HOPS", "1")
    monkeypatch.setenv("IGS_PROXY_SHARED_SECRET", SECRET)
    vercel = "54.80.27.93"
    proxied = _request(
        "10.0.0.9", vercel, {"x-igs-client-ip": "198.51.100.4", "x-igs-proxy-secret": SECRET}
    )
    assert public_chat._client_key(proxied) == "198.51.100.4"
    forged = _request(
        "10.0.0.9", "203.0.113.7", {"x-igs-client-ip": "6.6.6.6", "x-igs-proxy-secret": "wrong"}
    )
    assert public_chat._client_key(forged) == "203.0.113.7"
    garbage = _request(
        "10.0.0.9", vercel, {"x-igs-client-ip": "not-an-ip", "x-igs-proxy-secret": SECRET}
    )
    assert public_chat._client_key(garbage) == vercel
    monkeypatch.delenv("IGS_PROXY_SHARED_SECRET")
    assert public_chat._client_key(proxied) == vercel


def test_rate_limiter_memory_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(public_chat.RateLimiter, "MAX_KEYS", 100)
    limiter = public_chat.RateLimiter()
    for i in range(1_000):
        limiter.check(f"client-{i}", "chat", limit=5, window_s=60)
    assert len(limiter._hits) <= 100
    # The limit still holds for a client that keeps hammering.
    for _ in range(5):
        limiter.check("hammer", "chat", limit=5, window_s=60)
    with pytest.raises(ProblemError) as exc:
        limiter.check("hammer", "chat", limit=5, window_s=60)
    assert exc.value.status == 429
