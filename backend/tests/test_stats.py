"""Tests for anonymous usage counting: the numbers, the privacy, the access control.

The point of these tests is not just "does it count" but "can this ever leak a
person". Anything that stores an identity, an IP or a price should fail here.

Run from the backend folder:
    pytest -q
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app  # noqa: E402
from stats import StatsStore, utc_day  # noqa: E402

DAY = 86_400.0
NOW = 1_772_000_000.0  # fixed clock: a specific day in 2026


def store(tmp_path, **kwargs) -> StatsStore:
    return StatsStore(str(tmp_path / "stats.db"), secret="test-secret", **kwargs)


# --------------------------------------------------------------------------- #
# Counting
# --------------------------------------------------------------------------- #


def test_an_install_is_counted_once_per_device(tmp_path):
    s = store(tmp_path)
    assert s.record("device-aaaa", "install", now=NOW) is True
    # Pressing again, or reinstalling the same day, must not double count.
    assert s.record("device-aaaa", "install", now=NOW) is False
    assert s.summary(now=NOW)["installs_total"] == 1


def test_two_devices_are_two_installs(tmp_path):
    s = store(tmp_path)
    s.record("device-aaaa", "install", now=NOW)
    s.record("device-bbbb", "install", now=NOW)
    summary = s.summary(now=NOW)
    assert summary["installs_total"] == 2
    assert summary["devices_total"] == 2
    assert summary["active_today"] == 2


def test_opens_are_distinct_devices_not_traffic(tmp_path):
    """Someone opening the app 50 times is one user, not fifty."""
    s = store(tmp_path)
    for _ in range(50):
        s.record("device-aaaa", "open", now=NOW)
    s.record("device-aaaa", "open", now=NOW + DAY)  # next day
    assert s.summary(now=NOW + DAY)["active_today"] == 1
    assert s.summary(now=NOW + 2 * DAY)["active_7d"] == 1


def test_active_windows_are_correct(tmp_path):
    s = store(tmp_path)
    s.record("device-old", "open", now=NOW - 20 * DAY)  # 20 days ago
    s.record("device-recent", "open", now=NOW - 3 * DAY)
    s.record("device-today", "open", now=NOW)
    summary = s.summary(now=NOW)
    assert summary["active_today"] == 1
    assert summary["active_7d"] == 2  # today + 3 days ago
    assert summary["active_30d"] == 3  # plus the 20-day-old one


def test_returning_devices_and_retention(tmp_path):
    """The number the owner actually cares about: did they come back?"""
    s = store(tmp_path)
    s.record("device-loyal", "open", now=NOW)
    s.record("device-loyal", "open", now=NOW + DAY)
    s.record("device-once", "open", now=NOW)
    summary = s.summary(now=NOW + DAY)
    assert summary["devices_total"] == 2
    assert summary["returning_devices"] == 1
    assert summary["retention_pct"] == 50.0


def test_retention_is_zero_with_no_data(tmp_path):
    """No division-by-zero crash before the first user arrives."""
    summary = store(tmp_path).summary(now=NOW)
    assert summary == {
        "installs_total": 0,
        "devices_total": 0,
        "active_today": 0,
        "active_7d": 0,
        "active_30d": 0,
        "returning_devices": 0,
        "retention_pct": 0.0,
        "first_day": None,
        "last_day": None,
        "trend": [],
        "generated_at": utc_day(NOW),
        "note": summary["note"],
    }


def test_trend_covers_the_last_fourteen_days(tmp_path):
    s = store(tmp_path)
    s.record("device-aaaa", "install", now=NOW)
    s.record("device-aaaa", "open", now=NOW)
    s.record("device-bbbb", "open", now=NOW + DAY)
    trend = s.summary(now=NOW + DAY)["trend"]
    assert [row["day"] for row in trend] == [utc_day(NOW), utc_day(NOW + DAY)]
    assert trend[0]["installs"] == 1
    assert trend[1]["devices"] == 1


def test_unknown_event_kinds_are_refused(tmp_path):
    with pytest.raises(ValueError):
        store(tmp_path).record("device-aaaa", "email", now=NOW)


def test_old_events_are_deleted(tmp_path):
    """Retention is a promise, so it is tested, not assumed."""
    s = store(tmp_path, retention_days=30)
    s.record("device-ancient", "open", now=NOW - 90 * DAY)
    s.record("device-recent", "open", now=NOW)
    # The first write of a new day triggers the prune.
    s.record("device-newcomer", "open", now=NOW + DAY)
    with sqlite3.connect(s.path) as conn:
        devices = {row[0] for row in conn.execute("SELECT DISTINCT device FROM events")}
    assert s.device_hash("device-ancient") not in devices
    assert s.device_hash("device-newcomer") in devices


# --------------------------------------------------------------------------- #
# Privacy: what is stored, and what can never be stored
# --------------------------------------------------------------------------- #


def test_raw_device_ids_are_never_written_to_disk(tmp_path):
    s = store(tmp_path)
    s.record("device-supersecret-aaaa", "install", now=NOW)
    raw_bytes = Path(s.path).read_bytes()
    assert b"device-supersecret-aaaa" not in raw_bytes
    assert b"supersecret" not in raw_bytes  # the hash is one-way


def test_the_schema_has_nowhere_to_put_a_person(tmp_path):
    """A structural guarantee: there is no column for an IP, email or price."""
    s = store(tmp_path)
    s.record("device-aaaa", "open", now=NOW)
    with sqlite3.connect(s.path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    assert columns == {"day", "device", "kind"}


def test_changing_the_secret_breaks_linkage(tmp_path):
    """Rotating STATS_SECRET makes old rows unlinkable to new ones."""
    one = StatsStore(str(tmp_path / "a.db"), secret="secret-one")
    two = StatsStore(str(tmp_path / "b.db"), secret="secret-two")
    assert one.device_hash("device-aaaa") != two.device_hash("device-aaaa")


# --------------------------------------------------------------------------- #
# The endpoints
# --------------------------------------------------------------------------- #


def client(tmp_path, **env) -> TestClient:
    base = {
        "STATS_DB": str(tmp_path / "stats.db"),
        "STATS_SECRET": "test-secret",
        "STATS_TOKEN": "owner-token",
    }
    base.update(env)
    return TestClient(create_app(base))


def test_track_counts_an_install(tmp_path):
    with client(tmp_path) as api:
        assert api.post("/track", json={"device_id": "device-aaaa", "kind": "install"}).json() == {
            "ok": True,
            "stored": True,
        }
        summary = api.get("/stats/summary", headers={"Authorization": "Bearer owner-token"}).json()
        assert summary["installs_total"] == 1


def test_track_ignores_duplicates_and_reports_it(tmp_path):
    with client(tmp_path) as api:
        api.post("/track", json={"device_id": "device-aaaa", "kind": "install"})
        again = api.post("/track", json={"device_id": "device-aaaa", "kind": "install"})
        assert again.json() == {"ok": True, "stored": False}


def test_track_rejects_unknown_kind_and_junk_ids(tmp_path):
    with client(tmp_path) as api:
        assert api.post("/track", json={"device_id": "device-aaaa", "kind": "email"}).status_code == 422
        assert api.post("/track", json={"device_id": "short", "kind": "open"}).status_code == 422
        assert api.post("/track", json={"device_id": "x" * 200, "kind": "open"}).status_code == 422
        # No unicode, no punctuation, nothing that could carry data.
        assert api.post("/track", json={"device_id": "device aaaa@mail.com", "kind": "open"}).status_code == 422


def test_track_refuses_to_carry_extra_information(tmp_path):
    """A client cannot smuggle a price, an email or a user agent into /track."""
    with client(tmp_path) as api:
        response = api.post(
            "/track",
            json={"device_id": "device-aaaa", "kind": "open", "email": "someone@example.com"},
        )
        assert response.status_code == 422


def test_track_body_is_size_capped(tmp_path):
    with client(tmp_path) as api:
        response = api.post(
            "/track",
            json={"device_id": "device-aaaa", "kind": "open", "pad": "x" * 20_000},
        )
        assert response.status_code == 413


def test_track_is_rate_limited_in_its_own_bucket(tmp_path):
    """Spamming /track must not stop anyone from getting a price."""
    with client(tmp_path, RATE_LIMIT_TRACK="3", RATE_WINDOW_SECONDS="60") as api:
        for i in range(3):
            assert api.post("/track", json={"device_id": f"device-{i:04d}", "kind": "open"}).status_code == 200
        assert api.post("/track", json={"device_id": "device-9999", "kind": "open"}).status_code == 429

        # The calculator is unaffected.
        assert api.post(
            "/calculate", json={"original_price": 89, "discount1_pct": 20, "discount2_pct": 70}
        ).status_code == 200


def test_calculate_traffic_does_not_burn_the_track_bucket(tmp_path):
    with client(tmp_path, RATE_LIMIT="3", RATE_LIMIT_TRACK="2", RATE_WINDOW_SECONDS="60") as api:
        for _ in range(3):
            api.post("/calculate", json={"original_price": 10, "discount1_pct": 10})
        assert api.post("/track", json={"device_id": "device-aaaa", "kind": "open"}).status_code == 200


def test_track_and_stats_are_never_cached(tmp_path):
    with client(tmp_path) as api:
        assert api.post("/track", json={"device_id": "device-aaaa", "kind": "open"}).headers["cache-control"] == "no-store"
        summary = api.get("/stats/summary", headers={"Authorization": "Bearer owner-token"})
        assert summary.headers["cache-control"] == "no-store"


# --------------------------------------------------------------------------- #
# Access control on the report
# --------------------------------------------------------------------------- #


def test_summary_requires_the_owner_token(tmp_path):
    with client(tmp_path) as api:
        api.post("/track", json={"device_id": "device-aaaa", "kind": "install"})
        assert api.get("/stats/summary").status_code == 401
        assert api.get("/stats/summary", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert api.get("/stats/summary", headers={"Authorization": "owner-token"}).status_code == 401
        assert api.get("/stats/summary", headers={"Authorization": "Bearer owner-token"}).status_code == 200


def test_summary_is_invisible_when_no_token_is_configured(tmp_path):
    """A deploy that forgets STATS_TOKEN exposes no numbers at all."""
    with client(tmp_path, STATS_TOKEN="") as api:
        api.post("/track", json={"device_id": "device-aaaa", "kind": "install"})
        assert api.get("/stats/summary", headers={"Authorization": "Bearer anything"}).status_code == 404


def test_summary_reports_anonymous_numbers_only(tmp_path):
    with client(tmp_path) as api:
        api.post("/track", json={"device_id": "device-aaaa", "kind": "install"})
        api.post("/track", json={"device_id": "device-aaaa", "kind": "open"})
        summary = api.get("/stats/summary", headers={"Authorization": "Bearer owner-token"}).json()
        assert set(summary) == {
            "installs_total",
            "devices_total",
            "active_today",
            "active_7d",
            "active_30d",
            "returning_devices",
            "retention_pct",
            "first_day",
            "last_day",
            "trend",
            "generated_at",
            "note",
        }
        assert summary["installs_total"] == 1

        # Nothing in the report is an identity: no raw ids, no stored hashes.
        import json as _json

        rendered = _json.dumps(summary)
        assert "device-aaaa" not in rendered
        assert StatsStore(str(tmp_path / "other.db"), secret="test-secret").device_hash("device-aaaa") not in rendered
        # Each trend row is a count, never a list of who was there.
        assert all(set(row) == {"day", "installs", "devices"} for row in summary["trend"])


def test_counting_can_be_switched_off_entirely(tmp_path):
    """STATS_DB=off: the app still works, nothing is written, nothing to leak."""
    with client(tmp_path, STATS_DB="off") as api:
        assert api.post("/track", json={"device_id": "device-aaaa", "kind": "install"}).json() == {
            "ok": True,
            "stored": False,
            "reason": "counting disabled",
        }
        summary = api.get("/stats/summary", headers={"Authorization": "Bearer owner-token"})
        assert summary.status_code == 404
        assert not (tmp_path / "stats.db").exists()
        # The calculator is untouched by any of this.
        assert api.post(
            "/calculate", json={"original_price": 89, "discount1_pct": 20, "discount2_pct": 70}
        ).json()["final_price"] == 21.36


def test_the_calculation_is_unaffected_by_counting(tmp_path):
    with client(tmp_path) as api:
        for _ in range(5):
            api.post("/track", json={"device_id": "device-aaaa", "kind": "open"})
        assert api.post(
            "/calculate", json={"original_price": 100, "discount1_pct": 20, "discount2_pct": 10}
        ).json()["final_price"] == 72.0
