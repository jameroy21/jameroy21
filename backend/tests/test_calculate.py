"""Tests for the sequential-discount maths and the /calculate endpoint.

Run from the backend folder:
    pytest -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import allowed_origins, app, calculate_price  # noqa: E402

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Core maths
# --------------------------------------------------------------------------- #


def test_spec_example_89_with_20_and_70_off():
    """The worked example from the spec."""
    assert calculate_price(89, 20, 70) == {
        "original_price": 89.0,
        "final_price": 21.36,
        "amount_saved": 67.64,
        "total_discount_pct": 76.0,
    }


def test_discounts_stack_sequentially_not_additively():
    """20% then 10% is 28% off, not 30% off."""
    result = calculate_price(100, 20, 10)
    assert result["final_price"] == 72.00
    assert result["amount_saved"] == 28.00
    assert result["total_discount_pct"] == 28.0


def test_single_discount_unchanged_by_second_argument():
    assert calculate_price(50, 30) == calculate_price(50, 30, 0)
    assert calculate_price(50, 30)["final_price"] == 35.00


def test_zero_percent_discounts_leave_price_alone():
    result = calculate_price(19.99, 0, 0)
    assert result["final_price"] == 19.99
    assert result["amount_saved"] == 0.0
    assert result["total_discount_pct"] == 0.0


def test_full_100_percent_discount_makes_it_free():
    result = calculate_price(80, 100, 0)
    assert result["final_price"] == 0.0
    assert result["amount_saved"] == 80.0
    assert result["total_discount_pct"] == 100.0


def test_penny_prices_round_to_cents():
    result = calculate_price(9.99, 33, 10)
    assert result["final_price"] == 6.02
    assert result["amount_saved"] == 3.97
    assert result["original_price"] == 9.99


def test_amounts_are_never_more_than_two_decimals():
    result = calculate_price(89.95, 17, 23)
    for key in ("original_price", "final_price", "amount_saved"):
        assert round(result[key], 2) == result[key]


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #


def test_post_calculate_two_discounts():
    response = client.post(
        "/calculate",
        json={"original_price": 89, "discount1_pct": 20, "discount2_pct": 70},
    )
    assert response.status_code == 200
    assert response.json() == {
        "original_price": 89.0,
        "final_price": 21.36,
        "amount_saved": 67.64,
        "total_discount_pct": 76.0,
    }


def test_post_calculate_second_discount_is_optional():
    response = client.post("/calculate", json={"original_price": 40, "discount1_pct": 25})
    assert response.status_code == 200
    assert response.json()["final_price"] == 30.0

    explicit_null = client.post(
        "/calculate",
        json={"original_price": 40, "discount1_pct": 25, "discount2_pct": None},
    )
    assert explicit_null.status_code == 200
    assert explicit_null.json()["final_price"] == 30.0


@pytest.mark.parametrize(
    "payload",
    [
        {"original_price": 0, "discount1_pct": 20},  # price must be positive
        {"original_price": -89, "discount1_pct": 20},
        {"original_price": 89, "discount1_pct": -1},  # discounts are 0-100
        {"original_price": 89, "discount1_pct": 101},
        {"original_price": 89, "discount1_pct": 20, "discount2_pct": 150},
        {"original_price": 89},  # discount1_pct is required
        {"discount1_pct": 20},  # original_price is required
        {"original_price": "free", "discount1_pct": 20},  # not a number
    ],
)
def test_bad_input_is_rejected_with_422(payload):
    assert client.post("/calculate", json=payload).status_code == 422


def test_healthcheck():
    assert client.get("/health").json() == {"status": "ok"}


def test_cors_headers_are_present_for_the_frontend():
    response = client.post(
        "/calculate",
        json={"original_price": 10, "discount1_pct": 10},
        headers={"Origin": "https://clear-price.vercel.app"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_cors_preflight_from_the_browser_is_allowed():
    """This is the OPTIONS request a browser sends before POSTing JSON."""
    response = client.options(
        "/calculate",
        headers={
            "Origin": "https://clear-price.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_allowed_origins_can_be_locked_down_with_an_env_var(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS", "https://clear-price.vercel.app, http://localhost:5173/"
    )
    assert allowed_origins() == [
        "https://clear-price.vercel.app",
        "http://localhost:5173",
    ]
