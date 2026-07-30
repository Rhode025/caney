#!/usr/bin/env bash
# Full QA for the river tool: regenerate the site, then static + runtime checks.
# Exits non-zero if anything fails.  Usage:
#   ./test/run.sh              regenerate, then check
#   ./test/run.sh --no-build   check the current out/ without regenerating
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.bun/bin:$PATH"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"

if [ "${1:-}" != "--no-build" ]; then
  echo "▶ regenerating site…"
  ./build.sh >/dev/null 2>&1 || { echo "  ✗ build failed — run ./build.sh to see why"; exit 1; }
fi

echo "▶ static checks (verify.py)…"
python3 test/verify.py

echo "▶ runtime checks (browser.mjs)…"
( cd test && { [ -d node_modules ] || bun install >/dev/null 2>&1; }; node browser.mjs )

echo "✅ QA PASSED"
