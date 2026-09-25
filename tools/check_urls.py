#!/usr/bin/env python3
"""Every absolute URL in the project must name the same host.

A site move is only half a change if it is done by hand: the canonical link gets
updated and the social image does not, so link previews keep pointing at the old
host — or worse, at a relative path that WhatsApp and iMessage silently ignore.
Both of those happened while building this app.

So the host is treated as a fact to be checked, not a string to remember:

    .venv/bin/python tools/check_urls.py

Reads the canonical URL from frontend/index.html and requires every other
absolute URL (Open Graph, Twitter, JSON-LD, robots.txt, sitemap.xml, the pages
themselves) to share its origin and base path.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public"

# Hosts that are allowed to appear without matching the canonical host, because
# they are documentation examples or third-party references, not app URLs.
ALLOWED_FOREIGN = (
    "sitemaps.org",  # XML namespace in sitemap.xml, not a link to the app
    "schema.org",
    "github.com",
    "openapi.vercel.sh",
    "vercel.com",
    "render.com",
    "semver.org",
    "keepachangelog.com",
    "developer.android.com",
    "developer.apple.com",
    "storage.googleapis.com",
)

URL_RE = re.compile(r"https?://[^\s\"'<>\\)]+")


def canonical() -> tuple[str, str]:
    """(origin, base path) taken from the canonical link in index.html."""
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    if not match:
        print("FAIL: index.html has no canonical link — SEO depends on it")
        raise SystemExit(1)
    parts = urlsplit(match.group(1))
    base = parts.path if parts.path.endswith("/") else parts.path + "/"
    return f"{parts.scheme}://{parts.netloc}", base


def files_to_check() -> list[Path]:
    targets = [
        ROOT / "frontend" / "index.html",
        PUBLIC / "privacy.html",
        PUBLIC / "terms.html",
        PUBLIC / "robots.txt",
        PUBLIC / "sitemap.xml",
        PUBLIC / "manifest.webmanifest",
        PUBLIC / "sw.js",
    ]
    return [path for path in targets if path.exists()]


def main() -> int:
    origin, base = canonical()
    print(f"canonical: {origin}{base}")

    problems: list[str] = []

    for path in files_to_check():
        text = path.read_text(encoding="utf-8")
        for url in URL_RE.findall(text):
            host = urlsplit(url).netloc
            if any(foreign in host for foreign in ALLOWED_FOREIGN):
                continue
            if url.startswith(origin + base) or url.startswith(origin.rstrip("/") + base):
                continue
            if url.startswith(origin) and not url.startswith(origin + base):
                problems.append(
                    f"{path.relative_to(ROOT)}: {url}\n"
                    f"    points at the domain root, but this deployment lives at {base}"
                )
                continue
            problems.append(
                f"{path.relative_to(ROOT)}: {url}\n"
                f"    is a different host from the canonical {origin}"
            )

    if problems:
        print(f"\n{len(problems)} URL problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nFix: use the canonical host everywhere, or add a deliberate exception "
            "to ALLOWED_FOREIGN in this script."
        )
        return 1

    print(f"all absolute URLs agree with the canonical host across {len(files_to_check())} files")

    # A subpath deployment also needs no root-absolute asset references, or the
    # icons, splash screens and service worker 404 once it is live.
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    root_absolute = [
        m for m in re.findall(r'(?:href|src)="(/[^"]*)"', index) if not m.startswith("//")
    ]
    # Vite's own entry script is rewritten with the build base, so it is fine.
    root_absolute = [ref for ref in root_absolute if not ref.startswith("/src/")]
    if root_absolute:
        print(f"\nFAIL: {len(root_absolute)} root-absolute asset path(s) in index.html:")
        for ref in root_absolute:
            print(f"  - {ref}")
        print("These break on a subpath deployment such as GitHub Pages. Use relative paths.")
        return 1

    print("no root-absolute asset paths: safe to serve from a subpath")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
