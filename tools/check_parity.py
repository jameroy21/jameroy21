#!/usr/bin/env python3
"""Parity check: the on-device maths must match the server's, exactly.

The app falls back to src/calculate.js when there is no signal. If the two
implementations ever disagreed, the same tag would show two different prices
depending on signal — the one thing this app cannot do.

    .venv/bin/python tools/check_parity.py

Fuzzes prices, discounts and rounding edge cases (half-cent boundaries) through
both implementations and reports any mismatch. Needs node on PATH.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from main import calculate_price  # noqa: E402

# Written next to the module so the relative import resolves, and deleted after.
NODE_SCRIPT = """import { readFileSync } from 'node:fs';
import { calculatePriceLocally } from './src/calculate.js';

const cases = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const out = cases.map(([price, d1, d2]) => calculatePriceLocally(price, d1, d2));
process.stdout.write(JSON.stringify(out));
"""


def cases() -> list[tuple[float, float, float]]:
    rng = random.Random(20240925)
    out: list[tuple[float, float, float]] = [
        (89, 20, 70),  # the spec example
        (100, 20, 10),  # sequential, not additive
        (50, 30, 0),  # single discount
        (0.01, 0, 0),  # smallest sensible price
        (9.99, 33, 10),  # penny rounding
        (1.005, 0, 0),  # exact half-cent boundary
        (0.135, 10, 0),
        (89.99, 100, 100),  # everything free
        (1234.56, 12.5, 7.25),  # fractional percents
    ]
    for _ in range(4000):
        price = round(rng.uniform(0.01, 5000), rng.choice([2, 2, 2, 1, 0]))
        d1 = rng.choice([0, 5, 10, 15, 20, 25, 30, 33, 40, 50, 60, 70, 75, 80, 90, 100])
        d2 = rng.choice([0, 0, 10, 20, 25, 30, 50, 70, 75, 90, 100])
        out.append((price, float(d1), float(d2)))
    # Half-cent boundaries: the only place two languages can disagree, and the
    # discounts shoppers actually see on a clearance rack. 70% off a price
    # ending in .x5, or 75% off one ending in .x2, lands exactly on a half cent.
    for cents in range(1, 500):
        price = cents / 100
        for d1, d2 in ((70.0, 0.0), (75.0, 0.0), (25.0, 0.0), (30.0, 0.0),
                       (20.0, 70.0), (50.0, 0.0), (33.0, 10.0), (10.0, 0.0)):
            out.append((price, d1, d2))
    return out


def run_in_node(all_cases: list[tuple[float, float, float]]) -> list[dict]:
    """Evaluate the browser module in node and return its answers."""
    frontend = ROOT / "frontend"
    runner = frontend / "__parity_runner.mjs"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(all_cases, handle)
        cases_file = handle.name
    try:
        runner.write_text(NODE_SCRIPT)
        completed = subprocess.run(
            ["node", str(runner), cases_file],
            cwd=frontend,
            capture_output=True,
            text=True,
        )
    finally:
        runner.unlink(missing_ok=True)
        Path(cases_file).unlink(missing_ok=True)

    if completed.returncode != 0:
        print("node failed to evaluate the browser maths:", file=sys.stderr)
        print(completed.stderr.strip()[:2000], file=sys.stderr)
        raise SystemExit(2)
    return json.loads(completed.stdout)


def main() -> int:
    all_cases = cases()
    js_results = run_in_node(all_cases)

    mismatches = []
    for (price, d1, d2), js_result in zip(all_cases, js_results):
        py_result = calculate_price(price, d1, d2)
        for key in ("final_price", "amount_saved", "total_discount_pct"):
            if abs(py_result[key] - js_result[key]) > 1e-9:
                mismatches.append((price, d1, d2, key, py_result[key], js_result[key]))

    print(f"compared {len(all_cases)} cases across Python and JavaScript")
    if mismatches:
        print(f"{len(mismatches)} MISMATCHES:")
        for price, d1, d2, key, py_value, js_value in mismatches[:20]:
            print(f"  price={price} d1={d1} d2={d2} {key}: python={py_value} js={js_value}")
        return 1
    print("parity OK: the offline maths matches the server exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
