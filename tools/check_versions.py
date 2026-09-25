#!/usr/bin/env python3
"""One version, everywhere.

A release is only trustworthy if the version stamped into the app, the API, the
manifest, the docs and the changelog are the same string. Drift happens quietly —
the package version was already bumped once while the lockfile lagged behind —
so it is checked rather than remembered.

    .venv/bin/python tools/check_versions.py              # verify
    .venv/bin/python tools/check_versions.py v1.2.0       # also check a release tag

Exits non-zero on any mismatch, so it works as a pre-release gate and in CI.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (path, description, regex with one capture group holding the version)
SOURCES: list[tuple[str, str, str]] = [
    ("frontend/package.json", "frontend package version", r'"version"\s*:\s*"([^"]+)"'),
    ("frontend/package-lock.json", "lockfile version (root)", r'"version"\s*:\s*"([^"]+)"'),
    ("backend/main.py", "API version (shown in /docs and GET /)", r'APP_VERSION\s*=\s*"([^"]+)"'),
    ("frontend/index.html", "softwareVersion in structured data", r'"softwareVersion"\s*:\s*"([^"]+)"'),
    ("frontend/src/analytics.js", "frontend fallback version", r'VITE_APP_VERSION\s*\|\|\s*"([^"]+)"'),
    ("CHANGELOG.md", "newest changelog entry", r"^##\s*\[([0-9]+\.[0-9]+\.[0-9]+)\]"),
    ("SECURITY.md", "security review version", r"\*\*Version:\*\*\s*([0-9]+\.[0-9]+\.[0-9]+)"),
    ("frontend/public/privacy.html", "privacy notice version", r"Last updated:[^<]*·\s*v([0-9]+\.[0-9]+\.[0-9]+)"),
]


def find_version(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


def collect() -> tuple[dict[str, str], list[str]]:
    """Return {description: version} plus a list of files that could not be read."""
    found: dict[str, str] = {}
    problems: list[str] = []
    for relative, description, pattern in SOURCES:
        path = ROOT / relative
        if not path.exists():
            problems.append(f"{relative}: file is missing")
            continue
        version = find_version(path.read_text(encoding="utf-8"), pattern)
        if version is None:
            problems.append(f"{relative}: could not find a version (pattern drifted?)")
            continue
        found[description] = version
    return found, problems


def current_tag() -> str | None:
    """The tag pointing at HEAD, if the commit is already tagged."""
    try:
        out = subprocess.run(
            ["git", "tag", "--points-at", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out.splitlines()[0] if out else None


def main() -> int:
    expected = sys.argv[1].lstrip("v") if len(sys.argv) > 1 else None

    found, problems = collect()

    print("version sources:")
    for description, version in found.items():
        print(f"  {version:<10} {description}")

    versions = set(found.values())
    if not versions:
        print("\nNo versions found at all — the patterns in this script need updating.")
        return 1

    if len(versions) > 1:
        print(f"\nMISMATCH: {len(versions)} different versions across the project:")
        for version in sorted(versions):
            where = [d for d, v in found.items() if v == version]
            print(f"  {version}: {', '.join(where)}")
        print("\nFix by bumping every source above to the same version.")
        return 1

    version = versions.pop()
    print(f"\nall sources agree: {version}")

    if problems:
        print("\nproblems:")
        for problem in problems:
            print(f"  {problem}")
        return 1

    if expected and expected != version:
        print(f"\nMISMATCH: the release is tagged v{expected} but the project says {version}")
        return 1

    if expected:
        print(f"release tag v{expected} matches the project version")

    # A tag on this commit must agree too, or the release points at a stale build.
    tag = current_tag()
    if tag:
        tag_version = tag.lstrip("v")
        if tag_version != version:
            print(f"\nMISMATCH: HEAD is tagged {tag} but the project says {version}")
            return 1
        print(f"HEAD tag {tag} matches")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
