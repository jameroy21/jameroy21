#!/usr/bin/env python3
"""Verify that every iOS launch image referenced by index.html actually exists,
and that every generated splash image is referenced.

A missing launch image means a white flash when the app opens from the home
screen — the exact thing these files exist to prevent — and it fails silently on
iOS, so it needs a test rather than a glance.

    .venv/bin/python tools/check_splash.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "frontend" / "index.html"
SPLASH_DIR = ROOT / "frontend" / "public" / "splash"


def main() -> int:
    html = HTML.read_text()
    # The href may be root-absolute ("/splash/x.png") or relative
    # ("splash/x.png"). Relative is what the GitHub Pages build needs, because
    # the site is served from the /clear-price/ subpath — matching only the
    # absolute form silently reported "0 referenced" and hid every problem.
    referenced = set(re.findall(r'href="(?:\./)?/?splash/([^"]+)"', html))
    on_disk = {path.name for path in SPLASH_DIR.glob("*.png")}

    missing = sorted(referenced - on_disk)
    unused = sorted(on_disk - referenced)

    print(f"referenced by index.html: {len(referenced)}")
    print(f"present on disk:          {len(on_disk)}")

    if missing:
        print("\nMISSING (declared but not generated):", *missing, sep="\n  ")
    if unused:
        print("\nUNUSED (generated but never referenced):", *unused, sep="\n  ")
    if missing or unused:
        return 1

    # Every referenced image must also carry a media query, or iOS ignores it.
    blocks = re.findall(r'rel="apple-touch-startup-image"\s+media="([^"]+)"\s+href="([^"]+)"', html)
    if not referenced:
        print("\nNo splash images are referenced from index.html at all — "
              "iOS will show a white flash when the installed app opens")
        return 1
    if len(blocks) != len(referenced):
        print(f"\n{len(referenced)} images declared but only {len(blocks)} have media queries")
        return 1

    for media, href in blocks:
        for part in ("device-width", "device-height", "-webkit-device-pixel-ratio"):
            if part not in media:
                print(f"\n{href} is missing '{part}' in its media query")
                return 1

    print("\nsplash images OK: all present, all referenced, all with full media queries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
