# Journal

Append-only session memory. Newest entry at the top. Each entry: what changed, why, and
what's still open. Written for a future session that has no chat history — assume it knows
nothing except this file and the code.

Keep entries short. Detail that belongs next to code goes in a code comment; detail that
belongs to a commit goes in the commit message. This file is for *state and intent*.

---

## 2026-08-01 — Day scoring reweighted, and scored per craft

Started from "why is Tue labelled Tough?" The breakdown built to answer that immediately
exposed the real problem: **the moon carried 40 of ~100 points.** Mon-Fri had identical
generation and graded Fair / Tough / Tough / Fair / Good purely on moon phase and rain.

**New weighting (each craft sums to 100):**

| | Level | Clarity | Weather | Window | Moon |
|---|---|---|---|---|---|
| Wade | 35 | 20 | 25 | 10 | 10 |
| Float | 35 | 18 | 27 | 10 | 10 |
| Powerboat | 35 | 15 | 30 | 10 | 10 |

Moon 40 -> 10. Weather is now dominated by a **thunderstorm gate** (WMO codes 95/96/99, read
over fishing hours only) that caps the term at 0.15 rather than deducting from it — lightning
is the one condition on this page that can actually kill you. Weather is weighted higher from a
boat (exposed, slower to shore), clarity higher when wading (sight-fishing).

**Scoring is now per craft, because one number cannot answer the question.** A no-generation day
is a perfect wade day and a poor powerboat day. Each day is scored three times and the outlook
toggles; the toggle shares the `craft` global with the planner, so there is one craft selection
for the page. Persisted to localStorage.

**Two inputs were wrong and are now right:**

1. **Clarity ran off the rain forecast — for TOMORROW.** Caney is a bottom-release tailwater:
   water leaving the dam is always clear, so colour comes from tributary inflow below it, which
   responds to rain that has *already fallen*. Now driven by 3-day antecedent rain
   (`past_days=2`), recency-weighted. One vocabulary page-wide; the fly box is keyed on it.

2. **"Wade dawn to the bump" was backwards.** The verdict assumed a dawn start instead of using
   the window the model had already computed. Measured at Stonewall over 14 days (USGS
   03424860, hourly medians), P(wadeable, <=600 cfs):

   ```
   00:00-09:00   0%      13:00  61%      17:00  71%
   10:00        11%      14:00  93%      18:00  46%
   11:00        21%      15:00  93%      19:00   7%
   12:00        36%      16:00  93%      20:00+  0%
   ```

   On a daily-peaking schedule the previous evening's release is still passing Stonewall at
   first light. **Dawn is the worst time to wade Caney; the window is a midday-to-afternoon
   lull.** Verdicts now name the computed window ("Wade the 12pm-3pm lull").

**Open / known limits:**

- The model's daily minimum runs ~60 cfs above the gauge (model 468-536 vs observed 399-522,
  median 442) — inside the observed spread, but it biases wade Level slightly low.
- The model's wade window runs ~1-2 h earlier than the 14-day gauge climatology suggests. Not
  chased here: the comparison is not apples-to-apples (the climatology is mostly 2U 12pm-8pm
  days, the forecast is 1U 1pm-7pm) and it is the flow model's existing timing uncertainty,
  not a scoring bug. Worth a proper backtest of window timing against matched schedules.
- Moon at 10 is a judgement, not a measurement — the only weight here with no evidence behind
  it. The trip log captures predictions; after a season it could be fitted instead of guessed.
- Grade bands moved with the model (Prime >=85 / Good >=72 / Fair >=58). Not calibrated against
  outcomes, just against the new score distribution.

**Tests:** scoring curves are probed directly in `qc_caney.py` (extracted from `briefing.py` by
regex so no network is needed) — craft direction, monotonicity, bounds, the storm gate. The
browser layer asserts the weights themselves (moon minor, level heaviest, weights differ by
craft), that a storm day never grades Prime, that the toggle moves both views, and that the
wade verdict never contradicts its own window. 207 static + full runtime.

---

## 2026-07-31 — Cumberland system: 3 tailraces, 9 rivers

Started from "where's my generation schedule for cumberland?" The answer was that there are
**two** Cumberland pages and they were very different: `cumberland` (KY / Wolf Creek) had a
generation schedule; `cumbnash` (Nashville) did not, despite being driven entirely by Old
Hickory releases. Fixed that, then added the two missing mainstem tailraces.

**Now covering all three Middle TN Cumberland tailraces:** Nashville (Old Hickory),
Cheatham, Cordell Hull. Same warmwater big-river model — navigable pool, depth stable,
**current** is the variable.

**The surprise was how little live gauge data exists.**

| Page | Release (LRN) | Gauge |
|---|---|---|
| `cumbnash` | `OHIT1-OLD_HICKORY` | USGS 03431500, healthy |
| `cheatham` | `ASHT1-CHEATHAM` | **none** — 03435000 has published nothing real-time in 30+ days |
| `cordell` | `COHT1-CORDELL_HULL` | **none** — no active gauge on the reach |

Where there is no gauge, the **release IS the hydrograph** and the footer says so. The QA gate
caught the dead gauge on the first build (`flow None`), which is exactly its job.

**Things worth not re-deriving:**
- **Location IDs are traps.** `OHHT1` = Lock and Dam, `OHIT1` = Tailwater (identical values,
  verified, but tailwater matches Center Hill's `CETT1` convention). `COHT1` carries Cordell
  Hull's *hourly* series; `CORT1` is its tailwater but publishes daily only. Always check
  `cwms-data/locations` before wiring a dam.
- **All LRN dams publish identically**: `<CODE>-<DAM>.Flow.Ave.1Hour.1Hour.man-rev` for actuals
  and `<Dam Name> Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast` for ~120 h of forecast.
- Release plumbing now lives in `riverlib` (`cwms_series`, `dam_release`, `release_at`,
  `gen_blocks`, `release_events`, `gen_days`) instead of a copy per generator.

**Deliberate restraints:** unit counts are labelled *estimates* (inferred from release steps,
never fitted to a gauge like Caney's constants), and **no arrival times** on any of the three —
these are impoundments, so a release raises current through a pool rather than sending a
wading front downstream. A countdown there would be fiction.

**⚠️ Open thread — access points.** `cheatham` and `cordell` carry exactly ONE access point
each: the USACE tailwater location, which is authoritative. Every other ramp on those reaches
is an unnamed OSM slipway with no official name, owner, or river mile, and several near Cordell
Hull sit on the **lake above the dam**. Omitted rather than guessed, per §2. USACE's own site
(`lrn.usace.army.mil`) has a TLS certificate misconfiguration and could not be fetched.
**This is the one place local knowledge beats research** — the ramps need naming from a
verified source before these two pages can tell you where to launch.

**Also:** switcher tab count and HQ card count in the QA suite now derive from the registry
instead of being hardcoded at 8 and 7, so adding a river no longer breaks the tests by design.

---

## 2026-07-30 (evening) — R1–R5 built, deployed, live

**The tool is on the internet: https://caney.pages.dev**
*(Corrected 2026-07-31: an earlier entry named `master.caney.pages.dev`. That branch alias
stopped being repointed after the first few deploys — recent wrangler runs print only a hash
URL, no `Deployment alias URL` line — while production started tracking every run. Use the
bare `caney.pages.dev`.)*
Cloudflare Pages, HTTPS, private repo, rebuilt hourly by `.github/workflows/deploy.yml`. All five tasks from the CEO review are shipped.

- **R1 — hosting.** `build.sh` is now the single source of the generator list and order
  (`hq.py` last); `test/run.sh` calls it. Deploy is gated on `verify.py`, so a build failing
  static QA is never published. `cache_dam.json` is persisted between CI runs.
- **R2 — build stamp.** Every page states how old its data is, injected via `render()` into
  `<head>` so no page can forget. Quiet / amber at 3 h / filled at 12 h, plus a distinct
  state when the device clock runs behind the build.
- **R3 — arrival strip.** "Water reaches Happy Hollow at 4:24 PM · 2h 16m from now", with a
  one-tap `.ics` + `VALARM` that hands the reminder to the phone's own calendar. Caney only.
- **R4 — the trip log now records what the tool predicted**, plus a "water arrived just now"
  stamp and the delta. This is the field backtest and the evidence engine.
- **R5 — `escUrl()`** scheme allowlist so a `javascript:` URL cannot reach an `href`.

**Two bugs found by building, both worth remembering.**

1. **The first CI deploy failed and it was the review's Finding 2.2 exactly.** Open-Meteo's
   TLS handshake timed out for duck and stones on the runner; both generators caught it,
   printed `wx warn:`, and built the page anyway with no weather, producing a `week[]` the HQ
   status contract rejects. Fixed by moving retry logic into `riverlib.get()` (2 attempts,
   2s/4s backoff, re-raise on exhaustion) and having all seven generators delegate to it
   instead of each carrying its own near-identical `get()`.
2. **`actions/cache` saves in a post-step, which is skipped when an earlier step fails** — so
   that failure discarded a good release forecast. Split into `cache/restore` + `cache/save`
   with `if: always()`.

**And one caught by writing a test:** the first cut of `arrivalPick` checked "upcoming"
before "arrived", so standing below the dam at 1pm after a 6–9am release it would announce
the 8pm arrival while you stood in rising water. Arrived wins now. Water also stays "here"
until `release_end + travel`, not merely until the front arrives.

**Testing gained real capability.** `browser.mjs` now drives `Date.now` (staleness, skew) and
exercises `window.__arrivalPick` with synthetic split-generation days — the clock-injectable
testing the review said was missing, without needing a fixture build. `test/smoke.mjs` checks
the live HTTPS site: 200, secure context, stamp present, zero JS errors, at phone viewport.
**Secure context confirmed**, which everything deferred behind GPS depends on.

**Open threads.**
1. **Fish with it and log trips.** R4's prediction-vs-actual deltas are what decide whether
   2.5 mph is right and whether any of the 13 deferred items are worth building. Nothing
   deferred should be un-deferred before that data exists.
2. ~~Runtime auto-calibration may interact with arrival math~~ — **checked, it does not.**
   `briefing.py:116-131` nudges `baseflow` against the live Stonewall gauge using only hours
   below 700 cfs (baseflow-dominated), then applies it constant along the reach. It adjusts
   flow *magnitude*; `WATER_MPH` and `travel_h` are untouched, so arrival times are unaffected.
   Working as designed, no action needed.
3. `briefing.py:265` has the same first-window-only bug class the arrival strip fixed: the
   itinerary takes the first `GW` window within 5am–9pm only.
4. `RIVER_SPEC.md` §3 matrix still lists 3 of 7 rivers; line 6 says `briefing.py → index.html`
   but it builds `caney.html`.
5. Cloudflare strips `.html`, so every internal link takes a 308 hop.

---

## 2026-07-30 (later) — CEO review of the mobile/on-water goal; scope cut

**Frame changed.** The active goal is a **robust, customizable personal tool**, not a product.
`PRODUCT_STRATEGY.md` is not the operating frame; `RIVER_SPEC.md:4` ("Personal tool, not a
product") is. Market and pricing work was dropped mid-review at the user's direction.

Ran `/plan-ceo-review` (SELECTIVE EXPANSION). Full artifact:
`~/.gstack/projects/Rhode025-caney/ceo-plans/2026-07-30-mobile-on-water-tool.md`.

**The finding that reframed everything:** most of what looked like a modeling problem is a
delivery problem, but *less* of it than first assumed. An outside-voice review established
that the flow model (`compressed_kernel`, `flow_at`, `dam_at`, `gen_windows`, `ramp_blocks`,
`unit_ct`, baseflow calibration) is **entirely build-time Python**; client JS only interpolates
a precomputed array. So a live client refetch could only ever update `relStart`, not the flow
curve, depth, itinerary, grades, or map front. Combined with two other facts — scheduled web
notifications are impossible on the web, and the riverbank is exactly where there is no signal
— the expensive live-PWA architecture was cut.

**Also found, and load-bearing for any future work:**
- `GEN[].relStart` is the **first release window of the day only** (`briefing.py:381`). Caney
  routinely runs split morning/afternoon generation, so any countdown built on it is wrong all
  afternoon. Use the *next* window relative to real now.
- `frontInfo(t)`'s `t` is `launchMin`, a day-relative planning slider, not wall clock.
- `mfd` exists **only** in Caney's `ACCESS[]`. Zero in the other six generators. `haversine`
  and `travel_h` are Python, not reusable from JS.
- Duck and Elk AL have no dam release, so leading-edge speed is undefined there. E3 is four
  tailwaters, not six rivers; those two get a `—` in the §3 matrix.
- `cache_dam.json` (the last-good release cache behind `dam_stale`) is gitignored, so a cold CI
  runner would silently build an empty forecast during a CWMS outage.
- `esc()` escapes only `& < > "` and does not neutralize a `javascript:` URL at `riverlib.py:587`.
- All four data sources (USGS, Open-Meteo, CWMS, NWPS) plus the Esri tile host send
  `Access-Control-Allow-Origin: *`, so browser-side fetching needs no server. Still true, still
  useful later.

**What to build (5 tasks, R1-R5 in the artifact):** Cloudflare Pages HTTPS hosting with
`cache_dam.json` persisted across CI runs; a build-age banner and version stamp; an arrival
strip ("water reaches Betty's at 2:47 PM, 1h 12m from now") computed from the build-time
schedule and the device clock, targeting the next window, handing off to a **native phone
alarm**; the trip log capturing the tool's own prediction; and a URL scheme allowlist.

**Why a native alarm:** it is the only mechanism that rings with no signal, a locked screen,
and the browser closed, which is all three conditions at the river.

**Open threads.**
1. R1-R5 not started. 13 items deferred with un-defer conditions listed in the artifact.
2. The trip log capturing predictions (R4) is the evidence engine: a season of it decides
   whether live refresh, GPS, and the PWA are worth building at all.
3. `RIVER_SPEC.md` §3 matrix still lists 3 rivers of 7, and line 6 wrongly says
   `briefing.py → index.html` when it builds `caney.html`.
4. `PRODUCT_STRATEGY.md` is now committed but explicitly not the operating frame.

---

## 2026-07-30 — flow-engine backtest, then a strategy detour

**Shipped.** Built the QA harness first (`14e3207` static `verify.py` + runtime
`browser.mjs`; `1e33477` pre-commit gate), then used it to make two calibration changes to
Caney safely:

- `b2115c3` — **baseflow 375 → 205 cfs.** Backtested 90 days of the Center Hill release
  forecast against the Stonewall gauge (`analysis/backtest_flow.py`). Least-squares
  intercept came out 204; the min-flow check agrees (205 + 166 ≈ 372 = observed min). The
  old 375 had the whole river running ~170 cfs high.
- `2c2bc2c` — **leading-edge speed 3.0 → 2.5 mph.** Same backtest, 80 generation events.
  It *confirmed* the guide's miles-from-dam (Happy Hollow 6, Betty's Island 9, Stonewall
  15) but corrected his ~3 mph rule: detectable rise at Stonewall has median *and* modal
  lag 6 h (49 of 80 events), independent of release size → 15/6 = 2.5 mph. Arrivals are now
  HH ~2½ h, Betty's ~3½ h, Stonewall ~6 h. Threaded through every place that quoted the old
  number — tip text, `genHint`, footer, config trend rule — and the page JS now reads
  `DATA.mph` instead of a hardcoded `3`.

**Also on disk, uncommitted:** `PRODUCT_STRATEGY.md`, from a YC-office-hours-style session.
Verdict: *build the oracle, not the network* — the water-timing engine + 5am briefing is the
wedge; social/marketplace is Act 2 and its real job is a ground-truth data moat, not a feed.
Target customer is the angler who **resents the 4-source 6am ritual** — sharpest instance the
traveling/time-boxed angler who already pays $400/day guides. The assignment it sets: give 5
anglers the briefing for tailwaters *you don't fish*, watch them use it, then ask "would you
have paid $99 for that this morning — why or why not."

**Open threads.**
1. `PRODUCT_STRATEGY.md` is untracked — commit it or delete it, don't leave it in limbo.
2. **The backtest methodology has only been run against Caney.** The other six rivers still
   carry their original constants, unvalidated. `analysis/backtest_flow.py` is the template.
3. The strategy doc's assignment (5 anglers, unfamiliar tailwaters) is not started. It is
   explicitly gated *before* writing any consumer code.

---

## Before 2026-07-30

`a290afe` is the initial commit — 7 generators, `riverlib`, HQ, and `RIVER_SPEC.md` already
mature. History before that point was not under version control and is not recoverable; the
design rationale that survived lives in `RIVER_SPEC.md` and in the calibration comments.
