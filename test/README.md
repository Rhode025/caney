# QA suite

Codifies the checks we kept running by hand. Everything exits non-zero on failure, and
`./test/run.sh` runs the lot in cost order — the free, dependency-free checks first, so a
broken scorer fails in seconds rather than after a browser download.

- **`planner/run.py`** — the Caney 2.0 suite. Pure Python, **no network and no clock
  dependence**: every fixture is hand-built and `fixtures.T0` is pinned at 2026-09-09, so a
  failure means the code changed, never that the river did. 591 checks across the domain
  types, the published weight table, the zone registry, the §50 golden model fixtures (the
  release schedules that actually happen on this water — split generation, a 1U→2U→1U ramp,
  a missing forecast, a Smith Fork runoff event), the §51 species regressions including the
  Carthage striper case, the research layer, and the architectural invariants.
- **`verify.py`** — fast, pure Python, no browser, no network. Static checks on the built
  `out/`: token completeness, link integrity, the switcher, required components per page,
  the **fly-only content policy** (no lures/gear terms; no catfish/sauger/crappie), the
  **status contract**, and the **planner contract** (species-first homepage, no inline
  CSS/JS, safety claims declare their bound, unknown water values are `null`, arrival ships
  a distribution).
- **`planner/test_parity.mjs`** — replays `out/plan/parity.json`, Python's own score for 93
  sampled windows computed from the emitted dataset, through `web/planner/model.js`. This
  is what keeps "the browser assembles, it does not model" true.
- **`browser.mjs`** — Playwright (headless Chromium). Loads every **river page** and the
  river board (`rivers.html`) and asserts **zero JS/console errors** — this is what catches
  things like the negative-`<rect>` SVG bug — then exercises the board: species filter,
  sort, per-day weather-row alignment, day-tap detail, and card-body navigation.
- **`planner.mjs`** — the planner in a real browser, at phone width, over HTTP (it loads ES
  modules, which `file://` blocks). Walks the six §62 scenarios, checks the itinerary
  distinguishes deterministic from heuristic timing and is in time order, exercises
  on-water mode and the trip log, verifies dark mode is a real palette, and runs **axe**
  for WCAG 2 AA. Currently 0 violations.
- **`planner-smoke.mjs`** — post-deploy, against the LIVE site. A deploy can succeed and
  still serve a stale page.

`vendor-axe.js` is axe-core 4.10.2, vendored rather than installed. It keeps the
accessibility gate hermetic: `test/node_modules` is gitignored and CI installs from
`test/package.json`, so a vendored copy means the a11y check cannot silently stop running
because a dependency resolved differently.

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
