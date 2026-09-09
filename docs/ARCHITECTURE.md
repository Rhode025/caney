# Caney 2.0 — architecture

Caney answers one question:

> I want to fish for **[species]** on **[date]** from **[start]** to **[end]**.
> What exactly should I do?

Everything below is subordinate to answering that. The river pages that used to *be* the
product are now the encyclopedia behind it.

---

## 1. The shape of it

```
                 ┌──────────────────────────────────────────────┐
  UPSTREAM       │ USGS · USACE CWMS · NOAA/NWS · Open-Meteo     │
                 │ TWRA / TDEC documents (research, optional)    │
                 └───────────────────┬──────────────────────────┘
                                     │
  caney/sources/   one place that fetches, dedupes, caches, and turns a failure
                   into a VALUE rather than an exception
                                     │
  caney/domain/    Observation · SafetyClaim · ResearchClaim · FishingZone ·
                   RiverSnapshot · FishingPlan          (no I/O, no HTML)
                                     │
  caney/species/   declarative behaviour + the published weight table
  caney/zones/     the geographic model — zones, not web pages
  caney/research/  provider abstraction, claim extraction, TTL cache, seed corpus
                                     │
  caney/planner/   candidates → gates → score → confidence → rank → plan → timeline
                                     │
  caney/render/    the ONLY module that knows about markup
                                     │
                 ┌───────────────────┴──────────────────────────┐
                 │ out/plan/data.json   the browser's dataset   │
                 │ out/plan/featured/*  pre-built FishingPlans  │
                 │ out/index.html       a shell, ~4 KB          │
                 │ out/assets/*         shared CSS + ES modules │
                 └───────────────────┬──────────────────────────┘
                                     │
  web/planner/     assembly + rendering in the browser
  riverguide/      the Telegram bot, answering from the SAME objects
```

Nothing may import from a layer above it. `test/planner/test_architecture.py::test_layering`
fails the build if it does.

---

## 1a. What 2.1 changed

The 2.0 planner ranked **zones** by the mean of their hourly scores across the user's whole
availability. The 2.1 planner ranks **opportunity windows** by a peak-weighted utility and
then assembles the best executable **itinerary** from them. Availability became a
constraint rather than an instruction.

New modules:

| path | what |
|---|---|
| `caney/domain/opportunity.py` | `OpportunityWindow`, `FishingSegment`, `FishingItinerary` |
| `caney/domain/location.py` | `LocationEvidence`, `LocationConfidence`, `Verification` |
| `caney/planner/utility.py` | the window utility function and every constant in it |
| `caney/planner/opportunity.py` | window discovery and diverse pruning |
| `caney/planner/transitions.py` | craft-aware travel cost, with provenance |
| `caney/planner/itinerary.py` | the bounded beam search and the day objective |
| `caney/planner/segments.py` | a won itinerary → instructions, technique, triggers |
| `caney/version.py` | model versions, frozen into every plan |
| `research-worker/` | the Research Intelligence service (Cloudflare Worker + D1 + KV) |

See [PLANNER.md](PLANNER.md), [GEOGRAPHY.md](GEOGRAPHY.md), [RESEARCH.md](RESEARCH.md) and
[OUTCOMES.md](OUTCOMES.md).

## 2. The one decision everything else follows from

**Python owns every number. The browser owns assembly.**

The site is static, so an interactive "what about 6:30–10:00 instead?" cannot call Python.
The obvious fix — port the scorer to JavaScript — gives you two modelling engines and
guaranteed drift. So instead the scorer is *defined* such that

> **a window's score is the mean of its hourly scores.**

Python emits an hourly series of component fits per (zone, species); the browser averages
them over whatever window the user asks for and applies the same published weights. Both
sides compute the identical number.

In 2.1 the same principle extends to the window search and the itinerary search: the
browser runs the identical scan and the identical beam, over Python's windows, Python's
transition graph and Python's constants — which §56 permits as "selecting from precomputed
opportunities". Nothing in `web/planner/` contains a threshold.

`out/plan/parity.json` holds Python's own answers, computed **from the emitted dataset**, at
four layers — component scores, window utilities, best-subwindow sets and complete
itineraries. `test/planner/test_parity.mjs` replays every one through `web/planner/*.js`
and fails on a disagreement larger than 0.05, or on any difference in the zones or times an
itinerary picks. Currently **405 checks, all exact**.

Components split in two:

| kind | components | shipped as |
|---|---|---|
| **static** | thermal, clarity, flow, level, habitat, forage, research, seasonal, current, access, hatch | one value per zone/species/day |
| **dynamic** | light, weather, moon, generation | one value per hour |

The dynamic set is exactly the set whose window formulas were already means or coverage
fractions, so this is a refactor of the arithmetic, not a change to it.

Constants the browser would otherwise hardcode — the neutral fit, the window-search
geometry, the verdict thresholds, the confidence bands, the horizon penalty, the ranking
blend — are all published in `data.json`. `test_architecture.py::test_browser_engine_holds_no_model`
scans `model.js` for unexplained numeric literals.

---

## 3. Geography, not pages (§3.1, §3.2)

The old model was `river.species[]`. It is wrong in two directions at once:

* `cordell.py`'s species line reads *"Smallmouth, white bass & panfish"*, so a striped-bass
  request could never surface the Cordell Hull tailwater — which TWRA describes as the
  striped-bass concentration for the system: *"Striped bass are concentrated from Cordell
  Hull Dam downstream to the mouth of the Caney Fork River."*
* the same geographic water fishes as different fisheries in different months. The lower
  Caney is a trout page and a summer striper thermal refuge. Those are not one opportunity
  and must not share one score.

So a **`FishingZone`** is geography, and a **`SpeciesProfileRef`** attaches to it with its
own months, pattern, habitat, holds and evidence. A zone may span several river pages
(`carthage_confluence` spans `cordell` and `caney`); a page may hold several zones (the
Caney has three).

`hydrology_river` is the one link back to the old model, and it is one-way: it names which
calibrated generator supplies the zone's water numbers.

---

## 4. What is NOT rewritten

`riverlib.py`, `briefing.py` and the eleven other generators keep their hydrology. It is
backtested — 90 days of Center Hill release against the Stonewall gauge for the baseflow
intercept, 80 generation events for the 2.5 mph leading edge, 1,516 USGS field
measurements for the wade thresholds. The planner **imports** it:

```python
riverlib.arrival_window(mfd, "first")   # → (earliest_h, typical_h, latest_h)
riverlib.WATER_MODEL[river_id]          # measured wade/no-wade thresholds
```

`test_architecture.py` asserts that no arrival constant is redefined inside `caney/planner`.

---

## 5. Live plane vs static plane (§27)

| | rebuilt | lives in |
|---|---|---|
| **static / slow** | on commit | `caney/zones`, `caney/species`, `caney/research/corpus.py`, calibration constants |
| **live / fast** | hourly, independently refreshable | `out/plan/data.json` |

`out/plan/data.json` is a self-contained live artefact with its own per-signal ages. It can
be regenerated by `python3 planner.py` alone in under two seconds against a warm cache —
the river pages do not have to be rebuilt with it. That is the boundary a faster refresh
would slot into; nothing else has to move.

---

## 6. Where the safety boundary is

See [SAFETY.md](SAFETY.md). In one line: **every number a person could get hurt by is
minted once, in `caney/sources/snapshots.py`, as an immutable `SafetyClaim` with a stable
id and an explicit list of the digit-tokens it licenses** — and anything generative may
quote a claim but never restate one.

---

## 7. Build order

`build.sh` is the single source of it.

```
briefing cumberland duck buffalo harpeth elk elktn cumbnash stones cheatham cordell
   ↓  (each writes out/<river>.html and out/status/<id>.json)
roadmap.py            → out/roadmap.html
hq.py                 → out/rivers.html          the river board, now one level down
planner.py            → out/index.html + out/plan/* + out/assets/*
bot.py                → out/bot.json             the RiverGuide corpus
```

`planner.py` runs after `hq.py` because it links to the river pages as the drill-down
layer; it runs before `bot.py` because the bot corpus embeds the planner's claim book.

---

## 8. Files

| path | what |
|---|---|
| `caney/domain/observation.py` | `Observation`, `DataState`. Unknown ≠ zero. |
| `caney/domain/claim.py` | `SafetyClaim`, `ClaimBook`, `ResearchClaim`, `SourceTier` |
| `caney/domain/zone.py` | `FishingZone`, `AccessPoint`, `Geometry`, `Craft` |
| `caney/domain/snapshot.py` | `RiverSnapshot` — everything known about one water |
| `caney/domain/plan.py` | `FishingPlan`, `TimelineStep`, `ScoreLine`, `Technique` |
| `caney/species/profiles.py` | behaviour + **the published weight table** |
| `caney/zones/registry.py` | the 17 seeded fishing zones |
| `caney/research/` | provider, cache, claim extraction, seeded TWRA corpus |
| `caney/sources/` | `http` `usgs` `cwms` `weather` `lunar` `registry` `snapshots` |
| `caney/planner/` | `scoring` `utility` `opportunity` `transitions` `itinerary` `segments` `confidence` `window` `timeline` `engine` |
| `caney/render/` | `dataset` `pages` `icons` |
| `planner.py` | the build entry point |
| `web/assets/app.css` | the one stylesheet |
| `web/planner/*.js` | `model` `utility` `opportunity` `itin` `segments` `timeline` `ui` `app` `map` `format` `trip` |
| `research-worker/` | `worker` `claims` `search` + `schema.sql` |
| `web/sw.js`, `web/manifest.webmanifest` | the PWA |
| `riverguide/src/guard.js` | the fail-closed safety verifier |
| `test/planner/` | unit tests, golden fixtures, species regressions, parity |
| `test/planner.mjs` | the browser + accessibility suite |

---

## 9. Reading order for a new contributor

1. `caney/domain/observation.py` — the docstring explains why the whole package exists.
2. `caney/zones/registry.py`, the `carthage_confluence` entry — the product thesis in data.
3. `caney/species/profiles.py`, the `WEIGHTS` table.
4. `caney/planner/engine.py`, `plan()` — the ten-step pipeline, in order.
5. `docs/PLANNER.md` — the utility function and the itinerary objective.
6. `docs/SAFETY.md`, then `docs/GEOGRAPHY.md`.
