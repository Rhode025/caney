# Schemas

Every one of these is a dataclass in `caney/domain/`, has a `to_json()`, and is what the
web UI, RiverGuide and the tests all read. Nothing scrapes generated HTML.

---

## Observation — `caney/domain/observation.py`

The type that exists to make `unknown ≠ zero` structural.

```
value          Any | None
unit           str
state          "known" | "stale" | "unknown" | "error"
observed_at    epoch — the time the reading DESCRIBES
fetched_at     epoch — the time we obtained it
source         "USACE CWMS (LRN) — Center Hill Dam"
source_url     str
confidence     0..1
note           str
```

`ok` (the only gate that may precede use) · `age_s()` · `age_label()` ("8 min ago",
"14 days old", "unknown") · `or_else(default)` (names the fallback at the call site) ·
`require()` (raises) · `with_staleness(budget)`.

Freshness budgets by kind, in `FRESHNESS_BUDGET`: flow 3 h, generation 2 h, release
forecast 6 h, water temp 12 h, weather 3 h, lake elevation 24 h, a TWRA report 21 days,
a management page 400 days.

---

## SafetyClaim / ClaimBook — `caney/domain/claim.py`

```
id             "sc_safe_720d7fbae9"   stable across builds
kind           SafetyKind.*
zone_id        the ONE zone it is about
text           the only wording permitted for this claim
numbers        ("1:45",)  — exactly the digit-tokens it licenses
value          the machine-readable value (epoch, cfs, or [early,typical,late])
unit, at, bound, source, source_url, state, observed_at, created_at
```

`bound ∈ {earliest, typical, latest, measured}`. `ClaimBook.allowed_numbers(zone_id)` is
what `riverguide/src/guard.js` verifies against. See [SAFETY.md](SAFETY.md).

---

## ResearchClaim — `caney/domain/claim.py`

```
id, species, claim_type, location_ids[], geographic_description,
season, valid_months[], claim_text,
source_url, source_title, source_domain, published_at, retrieved_at,
source_tier, source_quality, recency_score, geographic_match, seasonal_match,
confidence, safety_sensitive
```

`claim_type ∈ species_presence · seasonal_location · thermal_refuge · current_response ·
forage · time_of_day · habitat · technique · recent_report · stocking · survey · regulation`

**The constructor raises `UnsourcedClaim` without a `source_url`.** Tier is derived from
the domain, never asserted by the caller. `score(month, zone_ids)` =
`source_quality × seasonal_match × geographic_match × (0.55 + 0.45 × recency)`.

---

## FishingZone — `caney/domain/zone.py`

```
id, name
waterbody_ids[]        legacy river page ids this zone spans
waterbody_names[]
geometry               Geometry(kind=point|corridor|area, points, verified, source, note)
access[]               AccessPoint(id, name, lat, lon, kinds, craft, note, source,
                                   verified, river_miles_from_dam)
habitat[]
species_profiles{}     species -> SpeciesProfileRef(months, pattern, habitat, holds,
                                   move_to, weight, evidence, heuristic)
source_refs[], hydrology_river, mfd, dam, tailwater, drive, detail_page, regs,
hazards[], notes
```

`supports_craft()` and `supports_species(month)` are **gates**. `craft_options()` is derived
from the access points, never declared twice.

Coordinates rule: a zone stores either verified point access (USACE / TWRA / OSM-walked, as
already verified in this repo) or a **corridor between verified endpoints**. Prose that says
*"the dam downstream to the Caney Fork mouth"* becomes a corridor, never a fabricated pin.

---

## RiverSnapshot — `caney/domain/snapshot.py`

Everything known about one water at one moment. **No presentation of any kind.**

```
zone_id, river_id, taken_at
water     flow · stage · flow_trend · stage_trend · generation · generation_on ·
          generation_forecast · water_temp · lake_elevation · clarity · recent_rain_in
weather   weather_hours[]  (hourly, across the horizon) · weather_daily · sunrise · sunset
model     arrival{first,peak → earliest_h/typical_h/latest_h} · model_confidence · model_note
context   lunar · access[] · research[] · biological_context · safety_claim_ids[] · errors[]
```

`freshness()` → per-signal age rows. `weather_window(start, end)` → the user's window, not
"today". `apply_freshness_budgets()` demotes past-budget values to `stale`.
`caney/sources/snapshots.py::localize(snap, date)` returns a view with the sun times and
moon of one specific local date.

---

## OpportunityWindow — `caney/domain/opportunity.py`

One contiguous fishable stretch of one zone, for one species. The unit the 2.1 planner
ranks.

```
zone_id, species, start, end, duration_minutes
samples[]              the 15-minute score samples the utility was computed from
peak_score, mean_score, floor_score, quality
confidence             forecast confidence, 0..100
location_confidence    0..1
transition_cost_before / _after   minutes
utility, parts{}       quality · duration_factor · confidence_factor · location_factor ·
                       transition · staleness · utility
conditions_summary, reasons[], stale
```

---

## FishingSegment / FishingItinerary — `caney/domain/opportunity.py`

```
FishingSegment
  type          launch | fish | move | wait | change_technique | safety_exit |
                optional_backup | end
  start, end, zone_id, zone_name, access_id
  instructions  what to do
  reason        WHY — for a move, what changes and what it costs (§15)
  expected_score, confidence, location_confidence, location_evidence
  technique{}   primary + backup presentation + switch_trigger (§37)
  triggers[]    {if, then, at, kind, claim_ids, changes_technique}   (§38)
  claim_ids[], kind, uncertainty

FishingItinerary
  id, created_at, species, craft, requested_start, requested_end
  segments[], windows[]
  total_fishing_minutes, total_transition_minutes
  utility_score, utility_parts{}, confidence, location_confidence
  primary_zone, zone_sequence[], backup_plan{}, why[]
```

---

## LocationConfidence — `caney/domain/location.py`

```
access          LocationEvidence.*     weighted 0.40
reach           LocationEvidence.*     weighted 0.35
holding_water   LocationEvidence.*     weighted 0.25
verification    {status, verified_by, verified_at, source, notes}
value           0..1        score  0..100
tactical_level  precise | corridor | hedged        →  drives the prose (§30)
rows()          the three parts, each with its prior and an explanation (§72)
```

`LocationEvidence`: `VERIFIED_ACCESS` 0.98 · `VERIFIED_ZONE` 0.95 ·
`AGENCY_DESCRIBED_REACH` 0.85 · `MODELED_HABITAT` 0.65 · `UNVERIFIED_CANDIDATE` 0.40.
**Initial priors, not calibrated.** See [GEOGRAPHY.md](GEOGRAPHY.md).

---

## Transition — `caney/planner/transitions.py`

```
from_zone, to_zone, minutes, mode, provenance, detail, miles
provenance ∈ known | estimated | unknown
mode       ∈ boat_downstream | boat_upstream | drift_downstream |
             paddle_downstream | paddle_upstream | wade_bank | road
```

`None` rather than a Transition means the move is impossible for that craft (§12).

---

## FishingPlan — `caney/domain/plan.py`

The canonical answer object.

```
id, created_at, species, requested_window{start,end,iso,tz,days_out}, craft
verdict            GO | CONDITIONAL | SKIP        + verdict_why
score / opportunity   0..100   the itinerary's own quality
confidence            0..100   forecast confidence
location_confidence   0..100   how well we know WHERE          (§31, §65)
research_confidence   0..100   how well sourced the biology is
utility               the optimiser's objective, for audit
itinerary             FishingItinerary — THE ANSWER
availability          {start, end} — what you asked for (§68)
why_this_won[]        the concise explanation (§67)
backup_plan           {branches[], fallback_zone}  (§39)
versions              planner · species_model · zone_model · research (§53)
shadow                a candidate scorer's ranking, stored, never shown (§54)
primary_candidate  zone id
alternatives[]     scored losers with lost_on[] and what_would_flip_it,
                   plus eliminated candidates with their reason
best_window        {start, end, why}
location           {zone_id, name, waterbody, drive, detail_page, geometry, habitat,
                    hazards, regs, pattern, holds}
access             {launch, takeout, parking, source, all[], verified}
timeline[]         TimelineStep(at, at_label, until, title, detail, kind, zone_id,
                               claim_ids[], condition, branches[], uncertainty)
technique          Technique(primary_fly, primary_size, primary_color, backup_fly,
                             backup_size, line, leader, presentation, depth, retrieve, why)
water              {name: Observation}
weather            {name: Observation}   evaluated across the requested window
lunar              {phase, illumination, moonrise, moonset, major_windows, minor_windows}
biological_context {season, seasonal_stage, forage, habitat, thermal_refuge,
                    spawning_behavior, heuristic, claims[]}
evidence[]         ResearchClaim json
score_breakdown[]  ScoreLine(key, label, earned, possible, why)
safety[]           SafetyClaim json
data_freshness[]   per-signal rows
limitations[]      what this plan cannot tell you
```

`TimelineStep.kind ∈ deterministic · astronomical · forecast · heuristic · safety` — so
*"5:45 launch"* and *"7:30 move to the creek mouth"* never read alike.

---

## The browser dataset — `out/plan/data.json`

```
built, builtIso, horizon{t0,t1,hours}, tz
componentLabels, weights, moonMaxShare
rank{base,conf}, neutralFit, windowSearch, verdictThresholds, confidenceLabels,
horizonPenalty, confidenceSignals, craft[]
species{}      display, weights, techniques, forage, habitat, seasons, spawn,
               thermalRefuge, evidence, sources
zones{}        FishingZone.to_json() + water observations + generationForecast +
               arrival + modelConfidence + errors + river + unitCfs + genOn
series{}       "zone|species" -> {t0, step, hours, keys, values{}, known{}, why{}, whyTable{}}
statics{}      "zone|species" -> {static{}, accessByCraft{}, units, genKnown}
gates{}        zone -> {craft[], tailwater, noReleaseForecast, flowTooHighToWade,
                        seasons{}, storm[], wet[]}
confidence{}   "zone|species" -> {value, rows[]}
evidence{}     "zone|species" -> claim ids
claims{}       id -> ResearchClaim json
safety[]       SafetyClaim json
freshness{}    zone -> rows
weatherHours{} river -> hourly rows
lunar{}, sun{} "river|YYYY-MM-DD" -> …
research       {provider, enabled, queries, cached, refreshedAt, errors[]}
```

Times are **epochs**, always. Nothing in this file is formatted at build time; the browser
labels everything against the reader's own clock (RIVER_SPEC §0).
