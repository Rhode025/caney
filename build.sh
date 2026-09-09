#!/usr/bin/env bash
# Regenerate the whole site into out/. Single source of the generator list and order.
# hq.py aggregates every out/status/<id>.json into rivers.html, so it runs after the
# generators; planner.py runs after hq.py and writes the homepage.
#
# Used by test/run.sh (local QA) and .github/workflows/deploy.yml (scheduled build).
# No third-party Python deps; stdlib only.
set -euo pipefail
cd "$(dirname "$0")"

# duck.py emits THREE pages (duckup/duckmid/ducklow) from one run — one fetch, one engine.
GENERATORS=(briefing cumberland duck buffalo harpeth elk elktn cumbnash stones cheatham cordell)

for s in "${GENERATORS[@]}"; do
  echo "  ▸ $s"
  python3 "$s.py" || { echo "  ✗ generator crashed: $s"; exit 1; }
  sleep 2   # be gentle on the USGS / Open-Meteo / CWMS APIs
done

echo "  ▸ roadmap"
python3 roadmap.py || { echo "  ✗ roadmap.py crashed"; exit 1; }

echo "  ▸ hq (river board -> out/rivers.html)"
python3 hq.py || { echo "  ✗ hq.py crashed"; exit 1; }

# The species-first planner IS the homepage (out/index.html). It runs after the rivers
# because it reuses their calibrated hydrology through caney/sources and links to their
# pages as the drill-down layer. Set RESEARCH_ENABLED=1 + OPENAI_API_KEY to add live
# primary-source research; without them the planner is fully deterministic.
echo "  ▸ planner (species-first homepage)"
python3 planner.py || { echo "  ✗ planner.py crashed"; exit 1; }

# The 3.0 frontend. Built only when node_modules is present, because build.sh must keep
# working on a machine that has never run npm — the Python half of this repo is
# dependency-free on purpose and a missing toolchain should not stop a river page
# regenerating. CI always builds it; the deploy workflow checks the bundle budget (§73).
if [ -d web-v3/node_modules ]; then
  echo "  ▸ app (Preact/TS, -> out/app)"
  ( cd web-v3 && npm run build --silent ) || { echo "  ✗ web-v3 build failed"; exit 1; }
  rm -rf out/app && mkdir -p out/app && cp -R web-v3/dist/. out/app/
  node tools/check_bundle.mjs out/app || { echo "  ✗ bundle over budget"; exit 1; }
else
  echo "  ▸ app — skipped (web-v3/node_modules absent; run npm install there)"
fi

# Last: needs every river page AND every status card to exist.
echo "  ▸ bot corpus"
python3 bot.py || { echo "  ✗ bot.py crashed"; exit 1; }
