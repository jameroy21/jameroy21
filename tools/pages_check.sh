#!/usr/bin/env bash
#
# Verify the GitHub Pages build the way Pages actually serves it.
#
# Builds for /clear-price/, drops the output into a temporary directory at the
# right subpath, serves it with a plain static file server (no rewrites, no
# API), and checks it with frontend/tests/pages.smoke.mjs.
#
# This catches the failures that only appear once a deploy is live: a missing
# icon, a root-absolute asset path, a manifest scoped to / instead of
# /clear-price/, a service worker precaching the wrong URLs.
#
#   tools/pages_check.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PAGES_CHECK_PORT:-8099}"
SUBPATH="${PAGES_SUBPATH:-clear-price}"
STAGE="$(mktemp -d)"
SERVER_PID=""

cleanup() {
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
  rm -rf "$STAGE"
}
trap cleanup EXIT

echo "==> building for /$SUBPATH/"
cd "$ROOT/frontend"
npm run build:pages >/dev/null

echo "==> staging the build at /$SUBPATH/ (as Pages will serve it)"
mkdir -p "$STAGE/$SUBPATH"
cp -r dist/. "$STAGE/$SUBPATH/"

echo "==> starting a plain static server on port $PORT"
( cd "$STAGE" && python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 ) &
SERVER_PID=$!
sleep 1

echo "==> checking the served site"
cd "$ROOT/frontend"
node tests/pages.smoke.mjs "http://127.0.0.1:$PORT/$SUBPATH/"
