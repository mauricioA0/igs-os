"""Per-client rate limits for unauthenticated and paid endpoints.

In-process sliding windows: one API instance's view. Good enough for the public demo; a
multi-instance deployment adds Cloud Armor rate rules in front (docs/architecture/security.md)
and keeps this as defense in depth.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

from igs_core.deps import CurrentPrincipal
from igs_core.errors import ProblemError


class RateLimiter:
    """Sliding window per (client address, bucket). In-process: one API instance's view.

    Good enough for the public demo; a multi-instance deployment puts Cloud Armor rate rules
    in front (docs/architecture/security.md) and keeps this as defense in depth.
    """

    # Bounded so a flood of distinct client keys can't grow memory without limit.
    MAX_KEYS = 50_000

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, key: str, bucket: str, *, limit: int, window_s: float) -> None:
        now = time.monotonic()
        if len(self._hits) >= self.MAX_KEYS and (key, bucket) not in self._hits:
            self._prune(now, window_s)
        hits = self._hits[(key, bucket)]
        while hits and now - hits[0] > window_s:
            hits.popleft()
        if len(hits) >= limit:
            raise ProblemError(
                429,
                "rate-limited",
                "Too many requests. Please wait a moment and try again.",
                headers={"Retry-After": str(int(window_s))},
            )
        hits.append(now)

    def _prune(self, now: float, window_s: float) -> None:
        stale = [k for k, h in self._hits.items() if not h or now - h[-1] > window_s]
        for k in stale:
            del self._hits[k]
        if len(self._hits) >= self.MAX_KEYS:  # still full: drop the least recently used half
            by_age = sorted(self._hits, key=lambda k: self._hits[k][-1])
            for k in by_age[: len(by_age) // 2]:
                del self._hits[k]


def _limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter | None = getattr(request.app.state, "public_rate_limiter", None)
    if limiter is None:
        limiter = RateLimiter()
        request.app.state.public_rate_limiter = limiter
    return limiter


# Set by our own web proxy (apps/web): the browser's address, vouched for by a shared secret.
CLIENT_IP_HEADER = "x-igs-client-ip"
PROXY_SECRET_HEADER = "x-igs-proxy-secret"  # noqa: S105 - a header name, not a secret


def _client_key(request: Request) -> str:
    """The caller's address for rate limiting.

    Browsers reach the API through the Vercel proxy, whose egress addresses are shared by every
    visitor and rotate. When ``IGS_PROXY_SHARED_SECRET`` is set and the request carries it, the
    browser address the proxy forwards in ``x-igs-client-ip`` is used instead. Without the
    secret that header is ignored, so callers hitting the API directly can't pick their key.

    ``X-Forwarded-For`` is client-controlled: only the hops appended by our own proxies are
    trustworthy, so with ``IGS_TRUSTED_PROXY_HOPS=N`` (N proxies in front, e.g. 1 behind the
    Google load balancer) we take the N-th entry from the right. With 0 (default) the header is
    ignored and the socket peer is used — spoofing it can't dodge the limit.
    """
    proxied = _proxied_client(request)
    if proxied:
        return proxied
    hops = _trusted_proxy_hops()
    forwarded = request.headers.get("x-forwarded-for")
    if hops and forwarded:
        chain = [part.strip() for part in forwarded.split(",") if part.strip()]
        if chain:
            return chain[-min(hops, len(chain))]
    return request.client.host if request.client else "unknown"


def _proxied_client(request: Request) -> str | None:
    secret = os.environ.get("IGS_PROXY_SHARED_SECRET", "")
    presented = request.headers.get(PROXY_SECRET_HEADER, "")
    if not secret or not presented or not hmac.compare_digest(presented, secret):
        return None
    try:
        return str(ipaddress.ip_address(request.headers.get(CLIENT_IP_HEADER, "").strip()))
    except ValueError:
        return None


def _trusted_proxy_hops() -> int:
    try:
        return max(0, int(os.environ.get("IGS_TRUSTED_PROXY_HOPS", "0")))
    except ValueError:
        return 0


def rate_limit(bucket: str, *, limit: int, window_s: float) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        _limiter(request).check(_client_key(request), bucket, limit=limit, window_s=window_s)

    return dependency


def demo_rate_limit(
    bucket: str, *, limit: int, window_s: float
) -> Callable[[Request, CurrentPrincipal], None]:
    """Rate-limit the anonymous demo principal only (signed-in callers have their own quotas).

    Used on endpoints that spend model tokens, so an anonymous visitor can't burn the budget.
    """

    def dependency(request: Request, principal: CurrentPrincipal) -> None:
        if principal.kind == "demo":
            _limiter(request).check(_client_key(request), bucket, limit=limit, window_s=window_s)

    return dependency
