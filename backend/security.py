"""Security hardening for the Clear Price API.

Dependency-free ASGI middleware, so there is nothing extra to audit or keep
patched. Three concerns:

1. `SecurityHeadersMiddleware` — response headers that stop MIME sniffing,
   framing/clickjacking and referrer leakage, and keep prices out of caches.
2. `RateLimitMiddleware` — a per-IP sliding window so one script cannot hammer
   the free-tier instance or run up bandwidth.
3. `BodySizeLimitMiddleware` — rejects oversized bodies before they are parsed,
   counting bytes even when Content-Length is absent (chunked uploads).

Why plain ASGI instead of `BaseHTTPMiddleware`: it does not buffer responses,
does not swallow disconnects, and its behaviour is easy to reason about.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque

DEFAULT_MAX_BODY_BYTES = 4096  # three numbers in JSON: plenty
DEFAULT_RATE_LIMIT = 60  # requests
DEFAULT_RATE_WINDOW = 60.0  # seconds

# Headers every API response carries. No CSP here: /docs is Swagger UI and needs
# its own CDN assets; the browser app enforces its own strict CSP.
SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"permissions-policy": b"geolocation=(), camera=(), microphone=(), payment=()",
    b"cross-origin-resource-policy": b"same-site",
}

TOO_MANY = {"detail": "Too many requests. Please wait a moment and try again."}
TOO_BIG = {"detail": "That request was too large."}


def client_ip(scope, *, trust_proxy: bool) -> str:
    """Best-effort client address for rate limiting.

    X-Forwarded-For is only believed when TRUST_PROXY is on: on most hosts
    (Render, Fly, Heroku) the platform proxy sets it, but if the header were
    trusted blindly anyone could spoof a new identity per request and dodge the
    rate limit entirely. Without the flag we use the real socket peer.
    """
    if trust_proxy:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                first = value.decode("latin-1").split(",")[0].strip()
                if first:
                    return first
    client = scope.get("client")
    return client[0] if client else "unknown"


class SlidingWindowLimiter:
    """Allow at most `max_requests` per `window_seconds`, per key."""

    #: Hard ceiling on tracked keys. A flood of unique source IPs must not be
    #: able to grow this dict without bound on a 512 MB free-tier instance.
    MAX_KEYS = 10_000
    #: Reclaim expired windows this often, so an idle table does not sit around
    #: forever. Amortised: the sweep is O(keys) but runs once per this many hits.
    SWEEP_EVERY = 512

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._since_sweep = 0
        self._lock = threading.Lock()

    def _evict(self, cutoff: float, now: float) -> None:
        """Called while holding the lock. Frees the quietest keys first."""
        for stale in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[stale]
        if len(self._hits) < self.MAX_KEYS:
            return
        # Still full of fresh keys: drop the least recently active 10%.
        oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])[
            : max(len(self._hits) // 10, 1)
        ]
        for key in oldest:
            del self._hits[key]

    def check(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic() if now is None else now
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False, max(hits[0] + self.window_seconds - now, 0.0)
            hits.append(now)
            self._since_sweep += 1
            if self._since_sweep >= self.SWEEP_EVERY or len(self._hits) > self.MAX_KEYS:
                self._since_sweep = 0
                self._evict(cutoff, now)
            return True, 0.0


class SecurityHeadersMiddleware:
    def __init__(self, app, *, no_store_paths: tuple[str, ...] = ()) -> None:
        self.app = app
        self.no_store_paths = no_store_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Any response that carries a price or a usage count is uncacheable,
        # whatever the method: shared and kiosk phones are a real scenario.
        no_store = any(path.endswith(p) for p in self.no_store_paths)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {name.lower() for name, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    if name not in present:
                        headers.append((name, value))
                if no_store:
                    headers.append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RateLimitMiddleware:
    def __init__(
        self,
        app,
        *,
        limiter: SlidingWindowLimiter,
        trust_proxy: bool,
        paths: tuple[str, ...] = ("/calculate",),
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.trust_proxy = trust_proxy
        self.paths = paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not any(
            scope.get("path", "").endswith(p) for p in self.paths
        ):
            await self.app(scope, receive, send)
            return

        allowed, retry_after = self.limiter.check(client_ip(scope, trust_proxy=self.trust_proxy))
        if allowed:
            await self.app(scope, receive, send)
            return

        body = json.dumps(TOO_MANY).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", str(int(retry_after) + 1).encode()),
                    *[(k, v) for k, v in SECURITY_HEADERS.items()],
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    """Reject oversized bodies with 413, whatever the client claims.

    The body is buffered (these requests are three numbers, a few hundred bytes)
    and replayed to the app. Buffering is what makes the limit airtight: a
    chunked request with no Content-Length, or a lying one, still cannot put more
    than `max_bytes` in front of the JSON parser.
    """

    def __init__(self, app, *, max_bytes: int, paths: tuple[str, ...] = ("/calculate",)) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.paths = paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not any(
            scope.get("path", "").endswith(p) for p in self.paths
        ):
            await self.app(scope, receive, send)
            return

        # Fast path: an honest, oversized Content-Length header.
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    if int(value) > self.max_bytes:
                        await self._reject(send)
                        return
                except ValueError:
                    pass  # let the buffering loop below decide
                break

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break  # disconnect: hand the app an empty body and let it decide
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_bytes:
                await self._reject(send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)

    async def _reject(self, send) -> None:
        body = json.dumps(TOO_BIG).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    *[(k, v) for k, v in SECURITY_HEADERS.items()],
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
