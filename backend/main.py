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
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

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

    # allow_inf_nan=False keeps NaN / Infinity / "-Infinity" out.
    model_config = ConfigDict(
        allow_inf_nan=False,
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
# App
# --------------------------------------------------------------------------- #


def allowed_origins() -> list[str]:
    """Frontend origins allowed by CORS.

    Set ALLOWED_ORIGINS on the host (comma separated), e.g.
        ALLOWED_ORIGINS=https://clear-price.vercel.app,http://localhost:5173
    Defaults to "*" so local development and preview deployments just work.
    """
    raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="Clear Price API",
    version="1.0.0",
    summary="Work out the real price after one or two stacked discounts.",
    description=(
        "Discounts are applied one after the other, so a 20% discount followed by a "
        "70% discount is **not** 90% off. The second discount lands on the already "
        "reduced price."
    ),
)

_origins = allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # No cookies or auth are involved, so credentials stay off (and "*" stays valid).
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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
