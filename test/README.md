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

## Caney deep QC

`qc_caney.py` + `qc_caney.mjs` audit the Caney page specifically, because it is the only
river with a planner that gives timed, actionable advice — and therefore the only one where
a wrong number sends you somewhere.

```bash
python3 test/qc_caney.py            # DATA payload: ~120 invariants, instant, no browser
cd test && node qc_caney.mjs        # renders + every plan it can suggest
```

`qc_caney.mjs` sweeps **216 scenarios** (craft x mode x 9 launch times x 4 days) and checks
each for internal contradiction: mileage against the distance basis the clock used, take-out
after launch, arrival inside the measured band, and never routing upstream through water the
page itself calls wadeable. It also checks the model against the LIVE gauge, which is the one
check here that can fail for real-world reasons rather than code reasons.

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

## Pre-commit hook

`test/hooks/pre-commit` is a fast, offline gate — it syntax-checks the staged Python and
runs `verify.py` against the current build, blocking the commit on failure. Git hooks
aren't cloned, so install it once (a symlink, so edits to the tracked file take effect):

```bash
ln -sf ../../test/hooks/pre-commit .git/hooks/pre-commit
```

Bypass in a pinch with `git commit --no-verify`. The hook is intentionally instant and
network-free; run the full `./test/run.sh` (regenerate + browser) before anything you care
about.
