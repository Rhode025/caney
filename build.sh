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

# Last: needs every river page AND every status card to exist.
echo "  ▸ bot corpus"
python3 bot.py || { echo "  ✗ bot.py crashed"; exit 1; }
