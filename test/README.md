# QA suite

Codifies the checks we kept running by hand. Two layers, both exit non-zero on failure.

- **`verify.py`** — fast, pure Python, no browser, no network. Static checks on the built
  `out/`: token completeness, link integrity, the 8-tab switcher, required components per
  page, the **fly-only content policy** (no lures/gear terms; no catfish/sauger/crappie),
  and the **HQ status contract** (per-card schema, the species set, and that the HQ
  grade-weight map covers every grade the rivers emit).
- **`browser.mjs`** — Playwright (headless Chromium). Loads every page and asserts
  **zero JS/console errors** — this is what catches things like the negative-`<rect>` SVG
  bug — then exercises the HQ: species filter, sort, per-day weather-row alignment,
  day-tap detail, and card-body navigation.

## Run

```bash
./test/run.sh              # regenerate the site, then static + runtime checks
./test/run.sh --no-build   # skip regeneration, check the current out/
python3 test/verify.py     # static only (instant, no deps)
cd test && node browser.mjs  # runtime only
```

First run installs Playwright into `test/` (`cd test && bun install`). It pins
`playwright@1.58.2` to reuse the Chromium already cached on this machine — no download.

## When to run it

After any change to a generator, `riverlib`, or `hq.py`. `verify.py` is instant and worth
running every time; `browser.mjs` on anything that touches page JS or the HQ.
