#!/usr/bin/env bash
# Regenerate the whole site into out/. Single source of the generator list and order.
# hq.py MUST run last — it aggregates every out/status/<id>.json into index.html.
#
# Used by test/run.sh (local QA) and .github/workflows/deploy.yml (scheduled build).
# No third-party Python deps; stdlib only.
set -euo pipefail
cd "$(dirname "$0")"

# duck.py emits THREE pages (duckup/duckmid/ducklow) from one run — one fetch, one engine.
GENERATORS=(briefing cumberland duck buffalo elk elktn cumbnash stones cheatham cordell)

for s in "${GENERATORS[@]}"; do
  echo "  ▸ $s"
  python3 "$s.py" || { echo "  ✗ generator crashed: $s"; exit 1; }
  sleep 2   # be gentle on the USGS / Open-Meteo / CWMS APIs
done

echo "  ▸ hq"
python3 hq.py || { echo "  ✗ hq.py crashed"; exit 1; }
