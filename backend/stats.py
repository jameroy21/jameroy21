"""Anonymous usage counting for Clear Price.

The owner needs to know how many people installed the app and whether they come
back — **without** asking anyone to create an account, give an email or hand over
a phone number. This module does that and nothing else.

How it stays anonymous
----------------------
* No cookies. No IP addresses. No user agents. No prices, ever. Nothing that
  identifies a person is received or stored.
* The app generates a random id on the device (``crypto.randomUUID()``) and sends
  only that. The server immediately replaces it with ``HMAC-SHA256(secret, id)``
  and stores the hash. Without ``STATS_SECRET`` the stored value cannot be turned
  back into a device id, and it is useless anywhere else.
* One row per (day, device, kind). Counting is *distinct devices*, never event
  totals, so someone hammering the button does not inflate anything.
* Everything is aggregate. There is no per-person view to leak.
* Retention is enforced: events older than STATS_RETENTION_DAYS are deleted.

So the owner can answer: "how many installs, how many active today / this week /
this month, and how many came back a second day?" — and cannot answer "who".

Run/verify: tests/test_stats.py
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from datetime import date, datetime, timezone

#: Only these two events exist. "install" is sent once per device, on the first
#: launch from the home screen. "open" is sent once per device per day.
EVENT_KINDS = ("install", "open")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    day    TEXT NOT NULL,   -- YYYY-MM-DD, UTC
    device TEXT NOT NULL,   -- HMAC of the device id. Never the id itself.
    kind   TEXT NOT NULL,   -- 'install' | 'open'
    PRIMARY KEY (day, device, kind)
);
CREATE INDEX IF NOT EXISTS idx_events_kind_day ON events (kind, day);
"""


def utc_day(now: float | None = None) -> str:
    """The UTC date as YYYY-MM-DD."""
    stamp = time.time() if now is None else now
    return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d")


class StatsStore:
    """SQLite-backed aggregate counters. Stdlib only — nothing new to audit."""

    def __init__(
        self,
        path: str,
        *,
        secret: str,
        retention_days: int = 400,
    ) -> None:
        self.path = path
        self.secret = secret.encode()
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._last_prune_day: str | None = None

        if path != ":memory:":
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # -- plumbing ---------------------------------------------------------- #

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def device_hash(self, device_id: str) -> str:
        """One-way pseudonym. Rotating STATS_SECRET resets every counter."""
        return hmac.new(self.secret, device_id.encode(), hashlib.sha256).hexdigest()[:32]

    # -- writing ----------------------------------------------------------- #

    def record(self, device_id: str, kind: str, now: float | None = None) -> bool:
        """Store one event. Returns True when it was new for that day/device/kind.

        Repeats are ignored (INSERT OR IGNORE), which is what makes the numbers
        distinct devices rather than raw traffic.
        """
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind: {kind!r}")

        day = utc_day(now)
        hashed = self.device_hash(device_id)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO events (day, device, kind) VALUES (?, ?, ?)",
                (day, hashed, kind),
            )
            stored = cursor.rowcount == 1

            # Prune once a day, on the first write of a new day. ISO day strings
            # compare correctly as text, which also uses the index.
            if self._last_prune_day != day:
                self._last_prune_day = day
                cutoff = date.fromordinal(
                    date.fromisoformat(day).toordinal() - self.retention_days
                ).isoformat()
                conn.execute("DELETE FROM events WHERE day < ?", (cutoff,))
        return stored

    # -- reading ----------------------------------------------------------- #

    def summary(self, now: float | None = None) -> dict:
        """Aggregate picture for the owner. Counts, never identities."""
        today = utc_day(now)
        with self._connect() as conn:
            def scalar(sql: str, params: tuple = ()) -> int:
                return int(conn.execute(sql, params).fetchone()[0])

            installs_total = scalar("SELECT COUNT(DISTINCT device) FROM events WHERE kind = 'install'")
            devices_total = scalar("SELECT COUNT(DISTINCT device) FROM events")

            def active_within(days: int) -> int:
                return scalar(
                    "SELECT COUNT(DISTINCT device) FROM events "
                    "WHERE CAST(julianday(?) - julianday(day) AS INTEGER) < ?",
                    (today, days),
                )

            returning = scalar(
                "SELECT COUNT(*) FROM ("
                "  SELECT device FROM events GROUP BY device HAVING COUNT(DISTINCT day) > 1"
                ")"
            )

            rows = conn.execute(
                "SELECT day, "
                "  COUNT(DISTINCT CASE WHEN kind = 'install' THEN device END), "
                "  COUNT(DISTINCT device) "
                "FROM events WHERE CAST(julianday(?) - julianday(day) AS INTEGER) < 14 "
                "GROUP BY day ORDER BY day",
                (today,),
            ).fetchall()

            bounds = conn.execute("SELECT MIN(day), MAX(day) FROM events").fetchone()

        trend = [{"day": day, "installs": int(inst), "devices": int(dev)} for day, inst, dev in rows]
        retention = round((returning / devices_total) * 100, 1) if devices_total else 0.0

        return {
            "installs_total": installs_total,
            "devices_total": devices_total,
            "active_today": active_within(1),
            "active_7d": active_within(7),
            "active_30d": active_within(30),
            "returning_devices": returning,
            "retention_pct": retention,
            "first_day": bounds[0],
            "last_day": bounds[1],
            "trend": trend,
            "generated_at": utc_day(now),
            "note": (
                "Anonymous counts of distinct devices. No identities, no prices, "
                "no IP addresses are stored, by design."
            ),
        }


def resolve_secret(env: dict) -> tuple[str, bool]:
    """Pick the HMAC secret. Returns (secret, is_ephemeral).

    A random per-process secret keeps development honest, but it means counters
    reset on every restart — so production must set STATS_SECRET. The caller logs
    a warning when the secret is ephemeral.
    """
    configured = str(env.get("STATS_SECRET", "")).strip()
    if configured:
        return configured, False
    return secrets.token_hex(32), True


def compare_token(candidate: str, expected: str) -> bool:
    """Constant-time token check, so a wrong token leaks nothing by timing."""
    return hmac.compare_digest(candidate.encode(), expected.encode())
