"""Tests for the hardening layer: headers, rate limiting, body limits, IP trust.

Run from the backend folder:
    pytest -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app  # noqa: E402
from security import (  # noqa: E402
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    SlidingWindowLimiter,
    client_ip,
)

GOOD_BODY = {"original_price": 89, "discount1_pct": 20, "discount2_pct": 70}


def fresh_client(**env) -> TestClient:
    """A client whose app was built with the given environment variables."""
    return TestClient(create_app(env))


# --------------------------------------------------------------------------- #
# Rate limiter unit behaviour
# --------------------------------------------------------------------------- #


def test_limiter_allows_up_to_the_limit_then_blocks():
    limiter = SlidingWindowLimiter(max_requests=3, window_seconds=60)
    assert [limiter.check("1.2.3.4", now=0)[0] for _ in range(3)] == [True, True, True]
    allowed, retry_after = limiter.check("1.2.3.4", now=0)
    assert allowed is False
    assert 0 < retry_after <= 60


def test_limiter_window_slides():
    limiter = SlidingWindowLimiter(max_requests=2, window_seconds=10)
    assert limiter.check("ip", now=0)[0] is True
    assert limiter.check("ip", now=1)[0] is True
    assert limiter.check("ip", now=2)[0] is False
    # The first two hits age out after the window.
    assert limiter.check("ip", now=11)[0] is True


def test_limiter_keys_are_independent():
    limiter = SlidingWindowLimiter(max_requests=1, window_seconds=60)
    assert limiter.check("a", now=0)[0] is True
    assert limiter.check("b", now=0)[0] is True
    assert limiter.check("a", now=0)[0] is False


def test_tracked_keys_are_capped_so_memory_is_bounded():
    """A flood of unique IPs cannot grow the table without limit."""
    limiter = SlidingWindowLimiter(max_requests=1, window_seconds=60)
    for i in range(30_000):
        limiter.check(f"ip-{i}", now=0)
    assert len(limiter._hits) <= limiter.MAX_KEYS
    limiter.check("late", now=1)  # still serving after the sweep


def test_quiet_windows_are_reclaimed_once_expired():
    """Real traffic arrives over time; a sweep clears windows that have expired."""
    limiter = SlidingWindowLimiter(max_requests=1, window_seconds=10)
    for i in range(limiter.SWEEP_EVERY):
        limiter.check(f"old-{i}", now=0)
    for i in range(limiter.SWEEP_EVERY):
        limiter.check(f"new-{i}", now=100)  # far past the first batch's window
    assert "old-0" not in limiter._hits
    assert len(limiter._hits) <= limiter.SWEEP_EVERY + 1


def test_xff_is_ignored_unless_proxy_is_trusted():
    scope = {
        "type": "http",
        "client": ("10.0.0.9", 1234),
        "headers": [(b"x-forwarded-for", b"1.2.3.4, 10.0.0.1")],
    }
    assert client_ip(scope, trust_proxy=False) == "10.0.0.9"
    assert client_ip(scope, trust_proxy=True) == "1.2.3.4"


def test_client_ip_survives_missing_client():
    assert client_ip({"type": "http", "headers": []}, trust_proxy=False) == "unknown"


# --------------------------------------------------------------------------- #
# Endpoint hardening
# --------------------------------------------------------------------------- #


def test_security_headers_on_every_response():
    with fresh_client() as client:
        for response in (
            client.get("/health"),
            client.get("/"),
            client.post("/calculate", json=GOOD_BODY),
        ):
            headers = response.headers
            assert headers["x-content-type-options"] == "nosniff"
            assert headers["x-frame-options"] == "DENY"
            assert headers["referrer-policy"] == "no-referrer"
            assert "camera=()" in headers["permissions-policy"]


def test_calculate_responses_are_never_cached():
    with fresh_client() as client:
        assert client.post("/calculate", json=GOOD_BODY).headers["cache-control"] == "no-store"
        # Other endpoints stay cacheable.
        assert "cache-control" not in client.get("/health").headers


def test_oversized_body_is_rejected_with_413():
    with fresh_client() as client:
        huge = {"original_price": 89, "discount1_pct": 20, "padding": "x" * 20_000}
        response = client.post("/calculate", json=huge)
        assert response.status_code == 413
        assert response.json()["detail"] == "That request was too large."


def test_lying_content_length_cannot_smuggle_a_big_body():
    """No Content-Length at all: the byte counter still stops it."""
    with fresh_client() as client:
        response = client.post(
            "/calculate",
            content=b'{"original_price": 1, "discount1_pct": 1, "pad": "' + b"x" * 20_000 + b'"}',
            headers={"Content-Type": "application/json", "Transfer-Encoding": "chunked"},
        )
        assert response.status_code == 413


def test_rate_limited_request_gets_429_and_retry_after():
    browser = {"Origin": "https://clear-price.vercel.app"}
    with fresh_client(RATE_LIMIT="3", RATE_WINDOW_SECONDS="60") as client:
        assert [
            client.post("/calculate", json=GOOD_BODY, headers=browser).status_code
            for _ in range(3)
        ] == [200] * 3
        blocked = client.post("/calculate", json=GOOD_BODY, headers=browser)
        assert blocked.status_code == 429
        assert blocked.json()["detail"].startswith("Too many requests")
        assert int(blocked.headers["retry-after"]) >= 1
        # The message must still be readable by the browser app: CORS has to
        # wrap the limiter, or the shopper sees an opaque network error.
        assert blocked.headers["access-control-allow-origin"] == "*"


def test_rate_limit_does_not_block_health_checks():
    with fresh_client(RATE_LIMIT="1", RATE_WINDOW_SECONDS="60") as client:
        client.post("/calculate", json=GOOD_BODY)
        assert client.post("/calculate", json=GOOD_BODY).status_code == 429
        for _ in range(5):
            assert client.get("/health").status_code == 200


def test_rate_limited_errors_still_carry_security_headers():
    with fresh_client(RATE_LIMIT="1", RATE_WINDOW_SECONDS="60") as client:
        client.post("/calculate", json=GOOD_BODY)
        assert client.post("/calculate", json=GOOD_BODY).headers["x-frame-options"] == "DENY"


def test_oversized_errors_still_carry_cors_and_security_headers():
    with fresh_client() as client:
        response = client.post(
            "/calculate",
            json={"original_price": 1, "discount1_pct": 1, "pad": "x" * 20_000},
            headers={"Origin": "https://clear-price.vercel.app"},
        )
        assert response.status_code == 413
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["x-content-type-options"] == "nosniff"


def test_host_allowlist_can_be_switched_on():
    with fresh_client(ALLOWED_HOSTS="clear-price-api.onrender.com") as client:
        assert client.get("/health", headers={"Host": "clear-price-api.onrender.com"}).status_code == 200
        assert client.get("/health", headers={"Host": "evil.example.com"}).status_code == 400


def test_host_allowlist_is_off_by_default():
    with fresh_client() as client:
        assert client.get("/health", headers={"Host": "anything.example.com"}).status_code == 200


def test_validation_still_works_through_the_hardening_stack():
    with fresh_client() as client:
        assert client.post("/calculate", json=GOOD_BODY).json()["final_price"] == 21.36
        assert client.post("/calculate", json={"original_price": -1, "discount1_pct": 5}).status_code == 422


def test_xff_cannot_dodge_the_rate_limit_when_proxy_is_untrusted():
    """Same socket peer, rotating X-Forwarded-For: the limit must still hold."""
    with fresh_client(RATE_LIMIT="2", RATE_WINDOW_SECONDS="60", TRUST_PROXY="0") as client:
        for i in range(2):
            assert client.post(
                "/calculate", json=GOOD_BODY, headers={"X-Forwarded-For": f"10.0.0.{i}"}
            ).status_code == 200
        spoofed = client.post(
            "/calculate", json=GOOD_BODY, headers={"X-Forwarded-For": "10.0.0.99"}
        )
        assert spoofed.status_code == 429


def test_forwarded_for_is_believed_when_proxy_is_trusted():
    """Behind a real proxy, each genuine client keeps its own budget."""
    with fresh_client(RATE_LIMIT="2", RATE_WINDOW_SECONDS="60", TRUST_PROXY="1") as client:
        for i in range(2):
            assert client.post(
                "/calculate", json=GOOD_BODY, headers={"X-Forwarded-For": f"10.0.0.{i}"}
            ).status_code == 200
        assert client.post(
            "/calculate", json=GOOD_BODY, headers={"X-Forwarded-For": "10.0.0.7"}
        ).status_code == 200


def test_calculate_price_is_untouched_by_the_hardening():
    """The maths must not depend on any of this."""
    from main import calculate_price

    assert calculate_price(89, 20, 70)["final_price"] == 21.36
