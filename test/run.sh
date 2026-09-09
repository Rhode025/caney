#!/usr/bin/env bash
# Full QA for the river tool: regenerate the site, then every check we have.
# Exits non-zero if anything fails.  Usage:
#   ./test/run.sh              regenerate, then check
#   ./test/run.sh --no-build   check the current out/ without regenerating
#
# Order matters. The cheap, dependency-free checks run first so a broken build fails in
# seconds rather than after Playwright has started a browser.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.bun/bin:$PATH"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"

if [ "${1:-}" != "--no-build" ]; then
  echo "▶ regenerating site…"
  ./build.sh >/dev/null 2>&1 || { echo "  ✗ build failed — run ./build.sh to see why"; exit 1; }
fi

echo "▶ planner unit tests + model fixtures (no network, fixed clock)…"
python3 test/planner/run.py

echo "▶ static checks (verify.py)…"
python3 test/verify.py

echo "▶ river QC (Duck sections + Buffalo)…"
python3 test/qc_rivers.py

( cd test && { [ -d node_modules ] || bun install >/dev/null 2>&1; } )

echo "▶ Python↔browser scoring parity…"
node test/planner/test_parity.mjs

echo "▶ research worker (tiering, decay, normalisation, dedupe — no network)…"
( cd research-worker && node test.mjs )

echo "▶ RiverGuide (slicer, access policy, fail-closed guard, itinerary integration)…"
( cd riverguide && node test.mjs )

echo "▶ runtime checks — river pages (browser.mjs)…"
( cd test && node browser.mjs )

echo "▶ runtime checks — the planner + accessibility (planner.mjs)…"
( cd test && node planner.mjs )

echo "✅ QA PASSED"
