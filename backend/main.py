"""Clear Price — backend API.

One job: given a price and one or two discounts, tell the shopper what they
actually pay.

The detail that matters (and that most people get wrong):

    Stacked discounts are SEQUENTIAL, not additive.
    The second discount applies to the price that is ALREADY discounted.

        $89 with 20% off, then 70% off
        step 1: 89.00 x (1 - 0.20) = 71.20
        step 2: 71.20 x (1 - 0.70) = 21.36      <-- not 89 x 0.10 = 8.90
        saved : 89.00 - 21.36      = 67.64

Run locally:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Deploy (Render):
    uvicorn main:app --host 0.0.0.0 --port $PORT

Configuration (all optional — see SECURITY.md):
    ALLOWED_ORIGINS     comma separated frontend origins; default "*"
    ALLOWED_HOSTS       comma separated Host allowlist; default off
    TRUST_PROXY         1 to believe X-Forwarded-For (default: on for Render)
    RATE_LIMIT          requests per window per IP on /calculate; default 60
    RATE_WINDOW_SECONDS window length in seconds; default 60
    MAX_BODY_BYTES      largest accepted request body; default 4096
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from security import (
    DEFAULT_MAX_BODY_BYTES,
    DEFAULT_RATE_LIMIT,
    DEFAULT_RATE_WINDOW,
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    SlidingWindowLimiter,
)

# --------------------------------------------------------------------------- #
# Core calculation
# --------------------------------------------------------------------------- #


def calculate_price(
    original_price: float,
    discount1_pct: float,
    discount2_pct: float = 0,
) -> dict:
    """Apply up to two discounts one after the other (never added together).

    Args:
        original_price: the price on the tag, before any discount. Must be > 0.
        discount1_pct: first discount, in percent (0-100).
        discount2_pct: second discount, in percent (0-100), applied to the
            already-discounted price. Defaults to 0 (no second discount).

    Returns:
        dict with original_price, final_price, amount_saved (all in currency
        units, rounded to the cent) and total_discount_pct (the real, combined
        percentage off, rounded to one decimal).

    Example:
        >>> calculate_price(89, 20, 70)
        {'original_price': 89, 'final_price': 21.36, 'amount_saved': 67.64, 'total_discount_pct': 76.0}
    """
    price_after_first = original_price * (1 - discount1_pct / 100)
    final_price = (
        price_after_first * (1 - discount2_pct / 100)
        if discount2_pct
        else price_after_first
    )
    saved = original_price - final_price
    return {
        "original_price": round(original_price, 2),
        "final_price": round(final_price, 2),
        "amount_saved": round(saved, 2),
        "total_discount_pct": round((saved / original_price) * 100, 1),
    }


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #


class CalculateRequest(BaseModel):
    """Body of POST /calculate."""

    # allow_inf_nan=False keeps NaN / Infinity / "-Infinity" out. extra="forbid"
    # rejects unexpected keys, so a request cannot smuggle anything past the
    # size and shape checks.
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"original_price": 89, "discount1_pct": 20, "discount2_pct": 70}
            ]
        },
    )

    original_price: float = Field(
        ..., gt=0, description="Price on the tag, before any discount."
    )
    discount1_pct: float = Field(
        ..., ge=0, le=100, description="First discount in percent (0-100)."
    )
    discount2_pct: float | None = Field(
        default=0,
        ge=0,
        le=100,
        description="Second discount in percent, applied to the already-discounted "
        "price. Optional: leave out (or send 0) when there is only one discount.",
    )


class CalculateResponse(BaseModel):
    original_price: float
    final_price: float
    amount_saved: float
    total_discount_pct: float


# --------------------------------------------------------------------------- #
# Configuration helpers (pure functions of the environment, so they are testable)
# --------------------------------------------------------------------------- #


def _get(env: Mapping[str, str], name: str, default: str = "") -> str:
    return str(env.get(name, default)).strip()


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(_get(env, name) or default)
    except ValueError:
        return default


def _env_float(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(_get(env, name) or default)
    except ValueError:
        return default


def _env_flag(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = _get(env, name).lower()
    return default if not raw else raw in {"1", "true", "yes", "on"}


def allowed_origins(env: Mapping[str, str] | None = None) -> list[str]:
    """Frontend origins allowed by CORS.

    Set ALLOWED_ORIGINS on the host (comma separated), e.g.
        ALLOWED_ORIGINS=https://clear-price.vercel.app,http://localhost:5173
    Defaults to "*" so local development, previews and Vercel deploys just work.
    The API holds no user data, sets no cookies and needs no credentials, so an
    open origin policy gives an attacker nothing to read.
    """
    raw = _get(env if env is not None else os.environ, "ALLOWED_ORIGINS", "*")
    if not raw or raw == "*":
        return ["*"]
    return [origin.rstrip("/") for origin in (part.strip() for part in raw.split(",")) if origin]


def allowed_hosts(env: Mapping[str, str] | None = None) -> list[str] | None:
    """Optional Host-header allowlist (DNS-rebinding / host spoofing defence).

    Set ALLOWED_HOSTS="clear-price-api.onrender.com,127.0.0.1" to switch it on.
    Off by default because the platform hostname is not known until deploy time
    and a wrong value would take the API down.
    """
    raw = _get(env if env is not None else os.environ, "ALLOWED_HOSTS")
    if not raw or raw == "*":
        return None
    return [host.strip() for host in raw.split(",") if host.strip()]


def trust_proxy_default(env: Mapping[str, str]) -> bool:
    """Believe X-Forwarded-For?

    Behind a platform proxy (Render sets RENDER=true) the socket peer is always
    the proxy, so the real client IP only exists in X-Forwarded-For. Anywhere
    else the header is attacker-controlled and must be ignored — otherwise every
    request could claim a new IP and walk straight past the rate limit.
    """
    return _env_flag(env, "TRUST_PROXY", default="RENDER" in env)


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #


def create_app(env: Mapping[str, str] | None = None) -> FastAPI:
    """Build the app. `env` defaults to the process environment."""
    env = os.environ if env is None else env

    app = FastAPI(
        title="Clear Price API",
        version="1.1.0",
        summary="Work out the real price after one or two stacked discounts.",
        description=(
            "Discounts are applied one after the other, so a 20% discount followed by "
            "a 70% discount is **not** 90% off. The second discount lands on the "
            "already reduced price."
        ),
        # Do not hand out schema URLs or server banners a probe could use.
        docs_url="/docs",
        redoc_url=None,
    )

    # Middleware order matters. Starlette wraps in reverse order of registration,
    # so the LAST one added is the OUTERMOST:
    #
    #   SecurityHeaders  <- every response, including errors, gets hard headers
    #     CORS           <- so 429/413 replies still carry Access-Control-Allow-Origin
    #       RateLimit    <- cheap rejection before parsing anything
    #         BodySize   <- cap the body before Pydantic sees it
    #           app
    #
    hosts = allowed_hosts(env)
    if hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=_env_int(env, "MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES),
        paths=("/calculate",),
    )
    app.add_middleware(
        RateLimitMiddleware,
        limiter=SlidingWindowLimiter(
            max_requests=_env_int(env, "RATE_LIMIT", DEFAULT_RATE_LIMIT),
            window_seconds=_env_float(env, "RATE_WINDOW_SECONDS", DEFAULT_RATE_WINDOW),
        ),
        trust_proxy=trust_proxy_default(env),
        paths=("/calculate",),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(env),
        # No cookies or auth are involved, so credentials stay off (and "*" stays valid).
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware, no_store_paths=("/calculate",))

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        """Tiny welcome payload — handy when checking that a deploy is alive."""
        return {
            "service": "Clear Price API",
            "endpoint": "POST /calculate",
            "example": {
                "request": {"original_price": 89, "discount1_pct": 20, "discount2_pct": 70},
                "response": {
                    "original_price": 89.0,
                    "final_price": 21.36,
                    "amount_saved": 67.64,
                    "total_discount_pct": 76.0,
                },
            },
            "docs": "/docs",
        }

    @app.get("/health", include_in_schema=False)
    def health() -> dict:
        """For Render health checks and uptime pings."""
        return {"status": "ok"}

    @app.post("/calculate", response_model=CalculateResponse)
    def calculate(payload: CalculateRequest) -> CalculateResponse:
        """Return the final price after stacking the given discounts."""
        result = calculate_price(
            original_price=payload.original_price,
            discount1_pct=payload.discount1_pct,
            discount2_pct=payload.discount2_pct or 0,
        )
        return CalculateResponse(**result)

    return app


app = create_app()
