# Caney 3.0 — architecture

**This is the canonical architecture document.** `docs/ARCHITECTURE.md` describes the 2.x
static build and now points here for anything 3.0 touches (§81). Where the two disagree,
this one is right.

---

## What changed, in one paragraph

Caney 2.1 was a static site with a planner in the browser: Python computed a dataset,
shipped it, and JavaScript ran the scoring model, the window optimiser and the itinerary
search over it. That worked, and it required a four-layer parity test to keep two
implementations of one model agreeing. 3.0 has **one planner**, in Python, reachable over
an API. The browser renders what it is told.

The product change is larger than the architectural one. 2.1 answered *"which location
scores highest for the period I selected?"*. 3.0 answers *"I can leave at 5 and need to be
home by 11:30 — run my day"*, and then keeps answering it while the day happens.

---

## The shape

```
                     PRIMARY DATA
        ┌─────────────────────────────────┐
        │ USGS · USACE CWMS · Open-Meteo  │
        │ NWS · TWRA · TDEC               │
        └───────────────┬─────────────────┘
                        │  fetched concurrently, once per bundle
                        ▼
              ┌───────────────────┐
              │ caney-api         │   Cloudflare Python Worker
              │                   │
              │ caney/sources     │   adapters + SourceRuntime
              │ caney/hydrology   │   arrival, wading, striper
              │ caney/planner     │   scoring, windows, itinerary, logistics
              │ caney/domain      │   Observation, SafetyClaim, Feature, Session
              └───────┬───────────┘
                      │  service binding (not yet bound — see DEPLOYMENT.md)
                      ▼
              ┌───────────────────┐
              │ caney-research    │   Cloudflare Worker + KV
              │ search → claims   │   (D1 when the token allows)
              └───────────────────┘
                      │
                      ▼   POST /api/v3/plan → PlanEnvelope
              ┌───────────────────┐
              │ web-v3            │   Preact + TS, 16.9 KB gzipped
              │ PLAN · TRIP · REF │   renders; decides nothing
              └───────────────────┘
```

The legacy per-river generators still run on the hourly Pages build and produce
`out/rivers.html` and the river pages. They are **reference** now (§83), not a step on the
way to a plan.

---

## The five things that carry the design

### 1. Unknown is never zero

`caney/domain/observation.py`. Every value is an `Observation` with a state of
`known | stale | unknown | error`. There is no `or 0` anywhere it could be a reading;
`test_architecture.py` greps for it and fails the build.

This survives serialisation, which is where it would otherwise die: `Observation.from_json`
has no default for `state` beyond `UNKNOWN`, because a rehydrate that kept `value` and
dropped `state` would turn every stale reading back into a confident one — silently, in
exactly the place the confidence penalty reads from.

### 2. Safety is minted once and never recomputed

`caney/sources/snapshots.py::_mint_safety_claims` is the only place a `SafetyClaim` is
created. `ClaimBook.from_json` deliberately does **not** go through `add()`: `add` derives
licensed digit tokens from text, and re-deriving them downstream of the source is the one
thing about a claim that must never happen. Rehydration restores; it does not re-decide.

The hierarchy, which nothing may invert:

```
authoritative live observation  >  deterministic safety model  >  SafetyClaim
                                >  planner  >  research  >  AI explanation
```

### 3. Travel is a constraint, not a subtraction

`caney/planner/logistics.py`. Each candidate zone gets its own fishable envelope:

```
earliest fishing = depart_after + drive out + rigging + run to the water
latest fishing   = return_by - drive home (with slack) - loading - run back
```

and the opportunity search runs inside **that**, not inside the raw availability. A zone
the day cannot reach is eliminated with the arithmetic in the reason.

The asymmetry is deliberate: the outbound drive uses its nominal estimate because being
early at a ramp costs nothing; the return leg is padded by its provenance, because being
late getting home is the failure the module exists to prevent.

### 4. Geography has confidence, and it costs

Two vocabularies, mapped onto each other rather than drifting apart:
`LocationEvidence` at the zone layer, `GeometryConfidence` at the feature layer.

**§25 is enforced, not documented.** A `FeatureGeometry` with `kind="point"` at anything
below `OFFICIAL_GIS` raises `InventedWaypoint` at construction. Prose describing a reach
cannot become a six-decimal waypoint, because the constructor refuses. Every one of the 66
coordinates in `caney/zones/features.py` traces back to `caney/zones/registry.py` — a test
checks it.

### 5. The browser decides nothing

No scoring, no window optimiser, no beam search, no segment logic under `web-v3/src`. The
2.1 parity tests existed to keep two implementations agreeing; with one implementation they
are replaced by API contract tests.

---

## Request lifecycle

```
POST /api/v3/plan
  ├─ contract.parse            400 naming the field if it is wrong
  ├─ _load                     bundle from KV, or build inline
  │    └─ prefetch (two pass)  discover the URL set, fetch concurrently
  ├─ planner.engine.plan       eligibility → envelopes → windows → itinerary → segments
  ├─ PlanningSnapshot.seal     content-addressed freeze of the inputs
  └─ PlanEnvelope              graded, stored, returned
```

### The two-pass prefetch

A Worker cannot discover what to fetch by starting to plan — the first missing source is
already an error. A build-time manifest was the obvious alternative and does not survive
CWMS, whose URLs carry `begin`/`end` computed from the current hour.

So pass 1 runs the real snapshot builder against an **empty** runtime, throws the result
away, and keeps the request set it recorded. Everything is fetched concurrently. Pass 2
builds for real. §32's filtering falls out for free: only the rivers a request reaches are
ever recorded.

### Freshness

A cron writes the bundle every five minutes. It is **not trusted to be the only path** —
see DEPLOYMENT.md — so a request finding a bundle older than five minutes also triggers a
rebuild, in the background where the platform provides a `ctx` and inline where it does
not. Past an hour a bundle is refused outright.

---

## Model versions

`caney/version.py`. Bump what moved, and nothing else:

| Version | Moves when |
|---|---|
| `PLANNER_VERSION` | utility function, window search, itinerary search, logistics solver |
| `SPECIES_MODEL_VERSION` | weights, a species rule, a technique table |
| `ZONE_MODEL_VERSION` | zone registry, kinds, features, location confidence |
| `RESEARCH_VERSION` | seed corpus, tiers, decay curves |
| `HYDROLOGY_VERSION` | arrival model, wade thresholds, routing constants |
| `SCHEMA_VERSION` | the API wire format |

3.0 did **not** change the scoring formula (§67). `utility.py` and `profiles.py::WEIGHTS`
are byte-for-byte what 2.1 shipped. The *search* changed, so `PLANNER_VERSION` moved;
the corpus did not, so `RESEARCH_VERSION` stayed at 2.1.0.

---

## What is uncalibrated

Stated because a number that looks precise and is not is the most expensive kind:

- Every constant in `caney/planner/utility.py` is an uncalibrated prior.
- `caney/planner/features.py::HYDRAULIC_FIT` — the ordering is defensible, the values are not measured.
- `caney/planner/logistics.py` prep/takeout/run minutes — nothing has timed them.
- `caney/domain/session.py::Threshold` — judgements about human behaviour, not hydrology.
- `TRAILER_PENALTY` in routing — the zone drive strings were not recorded per craft.

**Fitted, not guessed:** `MINUTES_PER_STRAIGHT_MILE` and `OVERHEAD_MINUTES` in
`caney/routing/provider.py`, from all 22 zones' mapped drive times. MAE 4.8 min. Re-derive
with `python3 analysis/road_factor.py`.

Only two parameters, because two is what the data identifies. Written as a road factor
times an average speed, the first fit returned a road factor of 0.86 — roads shorter than
straight lines. Quoting two numbers where the data supports one is the manufactured
precision §17 forbids.

---

## Layout

| Path | What |
|---|---|
| `caney/api/` | contract, router, handler, storage — runtime-independent |
| `caney/domain/` | Observation, SafetyClaim, Zone, Feature, Planning, Session |
| `caney/hydrology/` | arrival, wading, striper — extracted from riverlib, canonical |
| `caney/planner/` | scoring, opportunity, itinerary, logistics, features, delta |
| `caney/routing/` | RoutingProvider chain |
| `caney/tz.py` | zoneinfo, with a US-rule fallback for runtimes with no tz database |
| `caney-api/` | the Cloudflare Python Worker — plumbing only |
| `research-worker/` | the Research Intelligence Worker |
| `web-v3/` | the Preact frontend |
| `tools/api_dev.py` | the same API, served locally |

---

## Testing

```bash
python3 test/planner/run.py     # 1005 checks, no network, fixed clock
python3 test/verify.py          # static QA
python3 tools/api_dev.py        # the API locally, for contract tests
node tools/check_bundle.mjs out/app   # §73's budget, enforced
python3 tools/api_check.py --plan     # the deployed API, end to end
python3 tools/refresh_api.py          # rebuild the snapshot shards by hand
```

`test/planner/test_v3.py` holds §87–§93's golden scenarios as fixtures.
