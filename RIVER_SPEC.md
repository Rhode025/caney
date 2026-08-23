# River page — standard spec & template

The canonical feature spec every river page targets, plus the shared-code rules so a
change made once lands on every river. Personal tool, not a product.

Pages today (9 rivers + the HQ). `hq.py` builds `index.html`; every river builds its own file:
**Caney Fork** (`briefing.py` → `caney.html`), **Duck River** (`duck.py`), **Cumberland KY /
Wolf Creek** (`cumberland.py`), **Elk River / AL–Wheeler** (`elk.py`), **Elk / Tims Ford**
(`elktn.py`), **Stones River** (`stones.py`), and the three Cumberland tailraces —
**Nashville** (`cumbnash.py`), **Cheatham** (`cheatham.py`), **Cordell Hull** (`cordell.py`).
Shared code: **`riverlib.py`**. Build order lives in `build.sh`, `hq.py` last.

*Elk River (added from the Elk River Field Atlas) is the proof the template works: a Duck-style
smallmouth flow page (USGS 03584600 at Prospect, atlas flow bands, falling-beats-rising) plus a
Plan A/B "which way to turn" decision and four backwater→river zones. It reuses every shared
component — switcher, popups+GMaps, map, solunar, hatch, chatter — and adding it to `RIVERS`
auto-updated all switchers. It also surfaced the mobile-switcher overflow at 4 rivers, fixed once
in `SWITCH_CSS`.*

---

## 0. THE PARITY RULE (read this first)

**Every user-facing feature is shared and lives on every river, unless it is physically N/A for
that river's hydrology.** A feature that ships on one river MUST be a `riverlib` component wired
into all of them in the same change. "I'll add it to the others later" is how the spec rots —
don't. If a feature can't apply to a river (e.g. dam-generation UI on a free-flowing river),
say so explicitly in the feature matrix (§3) with a `—` and a one-line reason.

When you finish a feature, before you stop: confirm it renders on **all four** pages (or is
justified `—`), and update the §3 matrix. Historical violations that prompted this rule: the
trip **log** and the **flow-timer river diagram** were built on Caney only.

**Directions must be SHOWN, not just named.** If a page tells the user to fish "Zone C", "the
shoals", "the leading edge", or a named spot, that thing must be visible on the map (a colored
channel segment, a pin, a marker) — text guidance and the map must agree. Example: Elk colors the
channel by zone (`buildRiverMap(D,color,zoneSegs)`), draws today's target zones bold, adds a
legend, and the Plan card points at them ("→ the bold amber & red water on the map — Zones C & D").

**No build-time relative time. Python emits absolute instants; the client renders relative
time.** Nothing baked at build time may say *Today / Tomorrow / Yesterday / tonight*. Every day
row carries `iso: "YYYY-MM-DD"`; every page carries `todayIso`. `riverlib.DAYLABEL_JS` stamps
`label` / `date` / `isToday` / `dayDelta` from the **reader's** clock (in the river's timezone),
and `render()` wraps each page's DATA in `window.__rlRelabel(…)` so the walk runs synchronously
at `const DATA=…`, ahead of every render call. Any row carrying an `iso` — including ones added
later — is corrected for free; that is the parity rule holding by construction.

Two corollaries, both of which were real bugs:
- **Never use an array index to mean "today"** (`di===0`, `week[0]`, `label==='Today'`). Select
  by `isToday`. On a stale build, row 0 is a day that has already happened.
- **Relative words in prose are unreachable** by the relabeler — a sentence is not a day row. Use
  weekday names in anything Python formats into a string (see `WEEK_SYNTH` in `briefing.py`).

*Why this is a rule:* on 2026-08-23 GitHub Actions stopped running (billing), the site froze for
55 h, and every page went on calling Friday's data "Today" — showing a 2-unit generation day when
TVA said 1. The unit maths was right; the label was wrong, and the day rows carried no date
identity, so the page could not self-correct even in principle. `test/verify.py` now gates all of
the above.

## 1. How we avoid repeating ourselves

Each generator builds one big `TEMPLATE` string and does
`TEMPLATE.replace("__DATA__", json.dumps(DATA))`. Anything common to all rivers is a
**token** filled by `riverlib.render(html, river_id)` — so it's written once in
`riverlib.py` and referenced once per page.

**The mechanism**
```python
import riverlib
html = riverlib.render(TEMPLATE, "duck").replace("__DATA__", json.dumps(DATA))
```

**Shared tokens** (drop into any TEMPLATE; unused ones stay blank-safe):

| Token | Fills with | Where it goes |
|---|---|---|
| `__SWITCH_CSS__` | switcher CSS | inside `<style>` |
| `__SWITCHER__` | the river-nav for THIS river | top of `<body>` |
| `__CREDIT__` | shared data-source credit line | footer |
| `__POPUP_JS__` | `accessPopup()`/`gmapsUrl()`/`wireHover()` — access popups w/ Google Maps links | `<script>` |
| `__MAP_JS__` | `buildRiverMap(D,color)` — satellite map + pins + popups (simple maps) | `<script>` |
| `__SOLUNAR_CSS__` / `__SOLUNAR_JS__` | moon/feeding panel styles + `renderSolunar(elId,s,tie)` | `<style>` / `<script>` |
| `__HATCH_CSS__` / `__HATCH_JS__` | seasonal hatch-calendar styles + `renderHatch(elId,H,month)` | `<style>` / `<script>` |
| `__CHATTER_CSS__` / `__CHATTER_JS__` | "River chatter" Reddit-intel styles + `renderChatter(elId,data,wrapId)` | `<style>` / `<script>` |
| `__LOG_CSS__` / `__LOG_JS__` | trip-log styles + `buildLog(containerId,storageKey,spots[],sumElId?,legacyKey?)` | `<style>` / `<script>` |
| `__MOONCAL_CSS__` / `__MOONCAL_JS__` | monthly moon/feeding calendar + `buildMoonCal(containerId,lat,lon)` (client-side solunar, any month) | `<style>` / `<script>` |
| `__FLOWTIMER_CSS__` / `__FLOWTIMER_JS__` | flow-timer river diagram + `buildFlowTimer(containerId,timeline)` (scrub time; front for tailwaters) | `<style>` / `<script>` |
| `__FLYMATRIX_CSS__` / `__FLYMATRIX_JS__` | clarity×light fly matrix + `buildFlyMatrix(containerId,F)` (grid + box inventory + rig + sources) | `<style>` / `<script>` |
| `__GENSCHED_CSS__` / `__GENSCHED_JS__` | generation schedule (dam tailwaters) + `buildGenSchedule(id,days,hint,legend,opts)` — day windows-chips + bars + now-marker + arrival line | `<style>` / `<script>` |
| `__ARRIVAL_CSS__` / `__ARRIVAL_JS__` | on-water arrival strip + `buildArrival(id,cfg)` — "water reaches X at 2:47 PM", live countdown, and a one-tap `.ics` phone alarm | `<style>` / `<script>` |

**Arrival strip — availability per river (parity rule §0 justification).** Currently **Caney
only**. Two independent gates, both of which must be satisfied before a river gets it:

1. **Backtested constants.** The strip states a time you may wade on, so it ships only where
   the leading-edge speed has been validated against a downstream gauge (`analysis/backtest_flow.py`).
   Caney is the only river that has been. `cfg.validated=false` renders nothing at all rather
   than a confident number on unproven math.
2. **`mfd` data.** Arrival needs miles-from-dam per access. Only Caney's `ACCESS[]` carries
   `mfd`; the other six generators have none, and §2 forbids guessing river distances.

`—` for **Duck** and **Elk (AL/Wheeler)** is permanent, not pending: Duck is free-flowing and
Elk is Wheeler-lake-fed, so neither has a dam release and a leading-edge speed is undefined.
`—` for **Cumberland, Elk TN, Stones, Cumberland-Nashville** is *pending* both gates above.

*(The §3 matrix still has columns for only 3 of 7 rivers and does not yet carry this row —
tracked as owed documentation debt.)*

**Selecting the release event.** `buildArrival` consumes `gen_windows()` (`GW`) — maximal runs
above 800 cfs, which is the actual release *event*. It must **never** consume `GEN[].relStart`,
which derives from `ramp_blocks`: that splits on unit-count change (a 1U→2U→1U day is three
blocks but one front) and only ever reports the first block of a day, so a countdown built on
it is silently wrong for an afternoon release. `arrivalPick()` is pure and exposed as
`window.__arrivalPick` so `browser.mjs` can drive split-generation days directly.

**Shared helpers (Python):** `riverlib.get()`, `haversine()`, `shuttle_miles()`,
`solunar(day, sunrise_hm, sunset_hm, tz)`, `light_now(hour, cloud, wind)` → dawn/low/bright/wind.

**Access popups (feature):** every access marker binds `accessPopup(p)` — icons by type
(🥾🛶🚤), a description (from `p.info`, or falls back to `p.note` + river-mile), and a
**📍 Open in Google Maps** link to the exact coords. `wireHover(mk)` opens it on hover.
Give each access a `types` list and an `info` string (Caney reuses its `note`/`rm`).

**Auto-injected (no token needed).** `render()` also injects two things into `<head>` for
every page: `BASE_HEAD` (the font link) and the **build stamp** — a banner that states how
old the page's data is, escalating from quiet to amber at 3 h and to a filled bar at 12 h,
and calling out a device clock that runs behind the build. It is injected rather than
tokenised so no page can forget to display its own age. Every number on these pages is
baked at generation time, so the page's age *is* the data's age. Covered by `browser.mjs`,
which drives the device clock through all four states.

**The registry** — `riverlib.RIVERS` is the single source of truth for which rivers
exist. Add one entry and every page's switcher updates on the next run.

**The config** — `riverlib.RIVER_CONFIG` is the canonical *declarative* per-river config
(gauge, bands, zones, launch, access, hazards, flies, regs, species, vessel, base, lat/lon).
The **Atlas Generator reads it** (no inline copy), and **all four pages now consume their
`gauge` from it** (no hardcoded gauge IDs remain in the fetches — Duck NWPS CNVT1, Caney USGS
Stonewall, Cumberland USGS Burkesville, Elk USGS Prospect; Elk also reads its `zones`). Put a
fact here once; both the pages and the atlas use it, so they can't drift. (Deeply-embedded model
logic — band functions, routing kernels, full access coords — still lives per-page; migrate
opportunistically. NB: Cumberland's page *model* runs on the CWMS Wolf Creek **release**, while
its config `gauge` is the downstream USGS Burkesville reference — these legitimately differ.)

### Adding a NEW river
1. Add a row to `riverlib.RIVERS` (`id, name, emoji, file, on_bg, on_fg, species`) and a config to `riverlib.RIVER_CONFIG`.
2. Copy the closest existing generator (tailwater trout → `elktn.py`; warmwater big-river → `cumbnash.py`; peaking tailwater → `stones.py`; smallmouth float → `duck.py`; generation drift → `cumberland.py`). Every river is fly-only.
3. In its TEMPLATE use `__SWITCH_CSS__` + `__SWITCHER__`, and call `riverlib.render(TEMPLATE, "<id>")`.
4. Walk the **§3 feature checklist** below; wire the shared components; add the river-specific model.
5. **Emit the HQ status card** (required): end the generator with `riverlib.emit_status(id, now, wx, base_score, tz, species, kind, drive)` — writes `out/status/<id>.json` so the homepage board picks it up. `wx` must be a 7-day Open-Meteo fetch with daily `temperature_2m_max/min, precipitation_probability_max, sunrise, sunset` (build_week needs them). `now`={grade,cond,col,note,detail,asof}; `base_score` is a 0–3 current-water score; `species` is a list of standardized tags (for the HQ filter).
6. Run `hq.py` last (it aggregates every status card into `index.html`). Then run all generators — confirm no leftover `__…__` tokens and the switcher (🏠 HQ + every river) shows the new river everywhere.

### River Monitor HQ (homepage)
`index.html` is the aggregator (built by `hq.py`), not a river. Each river writes `out/status/<id>.json`; the HQ embeds them and renders a filter-by-species / sort-by-(best week | now | drive | name) board with a 7-day conditions strip per river. The week projection (`riverlib.build_week`) blends current water + weather + moon feeding — an honest planning lean, NOT a flow forecast (only Duck has a true multi-day flow forecast). Justified N/A per river (flow-timer, float planner, generation schedule) is fine — mark it and say why.

### Adding a NEW shared feature (the "apply to all" rule)
When a feature proves out on one river and belongs on all:
1. Move the logic into `riverlib.py` (a new token in `render()`, or a shared helper/JS constant).
2. Add the token/call to **each** page's TEMPLATE once.
3. Note it in §3 so the matrix stays honest.
4. Re-run all generators and spot-check each page.

---

### Cumberland system — three tailraces, three different data situations

Added 2026-07-31. All three run the same warmwater big-river model (navigable pool, so depth
is stable and **current** is the variable), driven by USACE LRN generation. They differ in
what live data exists, which is worth recording because it is not obvious:

| Page | Release series (LRN) | Live gauge |
|---|---|---|
| `cumbnash` — Nashville | `OHIT1-OLD_HICKORY` (Old Hickory) | USGS 03431500, healthy |
| `cheatham` — Cheatham Dam → Clarksville | `ASHT1-CHEATHAM` | **none** — 03435000 has published no real-time value in 30+ days |
| `cordell` — Cordell Hull → Old Hickory Lake | `COHT1-CORDELL_HULL` | **none** — no active gauge on the reach |

Where there is no gauge, **the release IS the hydrograph**: the plotted flow is the USACE
hourly actual plus forecast, and the footer says so. Do not point a page at a dead gauge.

**Location IDs matter.** `OHHT1` is the *Lock and Dam*, `OHIT1` is the *Tailwater* (they
return identical values — verified — but tailwater is the convention, as with Center Hill's
`CETT1`). `COHT1` is Cordell Hull's Lock and Dam and carries the hourly series; `CORT1` is
its tailwater but only publishes daily. Check `cwms-data/locations` before wiring a new dam.

**Unit counts on these three are estimates, not backtested constants.** `OH_UNIT_CFS` is
inferred from observed release steps, never fitted to a downstream gauge the way Caney's were
(`analysis/backtest_flow.py`). The legend on each page says so. Do not let them drift into
sounding authoritative.

**No arrival times on any of the three.** These are impoundments: a release raises current
through a pool rather than sending a wading-hazard front down a shallow tailwater, so a
Caney-style "water reaches you at 2:47" would be a confident fiction. The arrival strip stays
Caney-only until another river earns it (see §1).

**⚠️ Access points are incomplete on `cheatham` and `cordell`.** Each currently carries exactly
ONE access point: the USACE tailwater location, which is authoritative (official name and
coordinates from `cwms-data/locations`). Every other ramp on those reaches appears in OSM as an
*unnamed* slipway with no official name, owner, or river mile — below the bar §2 sets — and
several near Cordell Hull sit on the **lake above the dam**, not the tailwater. They are
deliberately omitted rather than guessed. Fill them in from a verified source before relying
on these pages for where to launch.

## 2. Data sources (public only)

| Source | Used for |
|---|---|
| USACE CWMS (`cwms-data.usace.army.mil`, office LRN/LRL) | dam release + forecast (Center Hill, Wolf Creek). Period-ending — subtract 3600s. |
| USGS Water Services (`waterservices.usgs.gov/nwis/iv`) | real-time discharge (00060) + gage height (00065) |
| NOAA NWPS (`api.water.noaa.gov/nwps/v1`) | river stage/flow forecast (Duck @ CNVT1) |
| Open-Meteo | weather, sunrise/sunset (no key) |
| OpenStreetMap / Overpass | river channel geometry for the map |
| Esri World Imagery (Leaflet) | satellite map tiles |

Solunar/moon are computed locally (moon age + sun times). No paid APIs, no scraping that
needs auth.

**Access points must be REAL.** Never invent ramp names or guess coordinates. Verify each
against an authority — TWRA access tables, the higherpursuits Duck access-point table (has
river miles), OSM `leisure=slipway` nodes, or a state boating-access list — and record the
official name, owner, river mile, and whether it takes **motorized boats** vs canoe/kayak.
Place the pin on the real ramp (or on the channel at its river mile) so the Google Maps link
lands right. Note nearby hazards (low-head dams, which bank is above/below them).

---

## 3. Standard feature checklist

✅ present · ◻ planned · — n/a for this river type

| # | Feature | Caney | Duck | Cumb | Shared? |
|---|---|:--:|:--:|:--:|---|
| 1 | River switcher (registry-driven) | ✅ | ✅ | ✅ | **riverlib** ✔ |
| 2 | Eyebrow + H1 + caption (date + gauge source) | ✅ | ✅ | ✅ | per-page |
| 3 | "Now" conditions card (level, trend, grade, note, clarity, water-temp, as-of) | ✅ | ✅ | ✅ | per-page (candidate) |
| 4 | Primary model chart | ✅ routing | ✅ flow forecast | ✅ release sched | per-page |
| 5 | Live satellite map + accesses on OSM channel | ✅ bespoke | ✅ | ✅ | **`buildRiverMap`** (Duck/Cumb/Elk) ✔ · Elk adds zone-colored channel via `zoneSegs` |
| 6 | Multi-day outlook (grade + level + weather) | ✅ | ✅ | ✅ | per-page (candidate) |
| 7 | Weather panel (dawn/midday/dusk, hi/lo, sun) | ✅ | ✅ | ✅ | per-page (candidate) |
| 8 | Solunar / moon feeding windows | ✅ own | ✅ | ✅ | **`riverlib.solunar` + `renderSolunar`** ✔ |
| 9 | Fly selection · clarity×light matrix (grid + box inv + sources) | ✅ | ✅ | ✅ | **`buildFlyMatrix`** ✔ (Elk ✅; replaced the old mined fly boxes) |
| 10 | Guide's-take tips | ✅ | ✅ | ✅ | per-page (candidate) |
| 11 | Footer data-source credit | ✅ | ✅ | ✅ | `__CREDIT__` available |
| 12 | Auto-calibration to live gauge | ✅ | — | ◻ | tailwater models |
| 13 | Trip / catch log (localStorage) | ✅ | ✅ | ✅ | **`buildLog`** ✔ (Elk ✅ too; Caney keeps its `caneyLog` key) |
| 14 | Access popups + Google Maps links (hover) | ✅ | ✅ | ✅ | **`accessPopup`** ✔ |
| 15 | Seasonal hatch/forage calendar (month-highlighted) | ✅ | ✅ | ✅ | **`renderHatch`** ✔ (per-river `HATCH` data) |
| 16 | River chatter — recent Reddit intel (self-hiding) | ✅ | ✅ | ✅ | **`renderChatter`** + `load_intel` ✔ (feed by `reddit_intel.py`) |
| 17 | Monthly moon & feeding calendar (nav + hover) | ✅ | ✅ | ✅ | **`buildMoonCal`** ✔ (client-side solunar; Elk ✅ too) |
| 18 | Flow-timer river diagram (slider + play) | ✅ bespoke | ✅ | ✅ | **`buildFlowTimer`** (Duck/Cumb/Elk) ✔ · Caney = its richer satellite planner |

**Flow-timer per river type:** `buildFlowTimer(D, timeline)` takes `timeline.points[]` each with a
per-frame `series[]`. **Tailwaters** (Cumberland) pass each access's series LAGGED by its travel time
below the dam + `front:true` — dots light up downstream in sequence and a front descends the strip
as you play (the release traveling down). **Flow rivers** (Duck, Elk) pass ~uniform series (Duck
scales by its Columbia→Centerville gradient) — the whole reach changes color together as you scrub
the obs/forecast hydrograph. Caney keeps its bespoke satellite planner (gliding front on the real
channel, drift planner) — a justified superset, same as the map row.

**River chatter data flow:** `reddit_intel.py` (official Reddit API, OAuth, read-only) writes
`out/intel/reddit.json`; each generator calls `riverlib.load_intel("<id>")` → `DATA.chatter`;
`renderChatter` shows recent posts (with 🆕 flags + thread links) or hides the whole section
when there's nothing. Needs a free Reddit app credential — see `reddit_intel.py` header. No
Facebook: the Groups API is dead and account-automation/scraping violates ToS (won't build).

**Live shop reports — investigated, not built (v25).** Auto-scraping fly-shop reports is
unreliable: the best-structured source (Caney Fork Outdoors' Shopify atom feed) stopped
publishing fishing reports in Feb 2026 and pivoted to gear blogs, so "latest report" would
surface 5-month-old data as current. Robust answer = the seasonal hatch calendar (#15, always
accurate) + the linked shop sources in each fly box (click through to whatever's current). A
freshness-gated version (only show a report if < ~21 days old, else hide) is possible if a
river ever has a reliably-updated feed — deferred until one does.

**Model-type modules** (mutually exclusive core):

- **Tailwater / generation-driven** (Caney, Cumberland): dam release + forecast → routing
  or wade-window logic; craft/drift controls; honest note when downstream routing is weak.
- **Free-flowing / forecast float river** (Duck): flow forecast → fishability bands; **float
  planner** (14) below.

**Float planner** (float rivers) — Duck reference impl:
- Best-float pick: best forecast day × a reach that floats at that level × fits daylight.
- Section table between accesses: local flow (interpolated along the flow gradient),
  floatability, on-water hours, **road-shuttle miles** (`riverlib.shuttle_miles`).
- **Craft toggle** (jet vs kayak/canoe) — live floatability thresholds (`DATA.craft`).
- **Safety**: real, sourced hazards (low-head dams, strainers) — never guessed; global
  safety banner + per-section notes; dam warnings styled red.

---

## 3b. Atlas Generator (LLM-powered PDF)

`atlas_generator.py` (engine) + `atlas_server.py` (web UI) turn a **river + date range** into a
downloadable **field-atlas PDF** in the Elk-atlas format. Flow: per-river `ATLAS` config + live
gauge + per-date weather/solunar → a brief → the **`claude` CLI** writes the conditions-specific
prose → styled multi-sheet HTML → headless-Chrome `--print-to-pdf`.

- **No API key** — uses the local `claude` CLI (existing auth); template fallback if absent.
- **Nested-claude gotcha:** call with `--output-format json --disallowed-tools … --append-system-prompt …`
  and **cwd outside the project**, else it loads CLAUDE.md and acts like an agent. Parse `result` → inner JSON.
- Run: `python3 atlas_server.py` → http://127.0.0.1:8899 · or CLI `--river <id> --start <d> --end <d>`.
- New rivers: add an `ATLAS[<id>]` entry (gauge, bands, zones, launch, access, hazards, flies, regs).

## 4. Design system (shared visual language)

Tokens: `--ink #16202b · --muted #66788a · --faint #93a3b3 · --line #e6ecf2 · --card #fff`.

**Contrast override (this is what actually renders).** `riverlib.SWITCH_CSS` re-declares two
of those tokens app-wide because the originals failed WCAG AA on the page and card
backgrounds: `--faint #93a3b3` measured 2.6:1 and `--muted #66788a` 3.7:1, against a 4.5:1
requirement. The values in force everywhere are:

    --faint: #616e7b     --muted: #566270     --blue: #0068d6

Build against the token NAMES, never the hex above — a component that hardcodes `#93a3b3`
silently opts out of the contrast fix. Anything measuring computed colour in a test should
expect `rgb(97,110,123)` for faint, not `rgb(147,163,179)`.
Grades: Prime `#28c76f` · Good/High `#f2a832` · Low/Skinny `#20b2aa` · Blown/Tough `#8b6cef`.
Cards `border-radius:18px` soft shadow; section labels `.sec`; `max-width:900px` app;
`-apple-system` font. Mobile breakpoint `680px`. Keep new rivers on these tokens.

---

## 5. Migration backlog (shared-code debt)

Extracting these into `riverlib` (as tokens or JS constants) would remove the last of the
per-page duplication — do it the next time one of them changes:

- [x] Solunar compute + panel → `riverlib.solunar` + `renderSolunar` (unlocked #8 on Duck & Cumberland)
- [x] Satellite-map builder JS → `riverlib.buildRiverMap` (Duck & Cumberland; Caney stays bespoke — draggable pins, gliding front marker, diagram toggle)
- [x] Access popups + Google Maps links → `riverlib.accessPopup`/`gmapsUrl`/`wireHover` (all three)
- [ ] Design-system CSS (`:root`, `.card`, `.sec`, `.wx`, `.tips`, `.foot`) → `riverlib.BASE_CSS` (identical across pages; risky to merge — do carefully)
- [ ] Weather panel render JS → shared constant (markup is identical on all three)
- [ ] Outlook row render JS → shared constant (Duck/Cumberland identical; Caney's is richer)
- [ ] Fly box render JS → shared constant
- [ ] Guide-tips render JS → shared constant (trivial — identical on all three)
- [ ] Migrate Caney's solunar panel onto `renderSolunar` (Caney still uses its own richer feed render)
- [x] **Audit Caney & Cumberland access points against real ramps** (v24 — Caney names verified real & coords snapped/on-channel + draggable; Cumberland reordered to real KY F&W/USACE ramps with Helm's Landing fixed to ~4.5 mi below the dam)
- [ ] Adopt `__CREDIT__` in all three footers (token exists; pages still hand-roll model-specific footers)
