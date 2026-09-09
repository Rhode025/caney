# The evidence loop

```
prediction  →  outcome  →  calibration
```

Every number in the scoring model is a **prior**. The only way any of them improves is
outcomes, and outcomes are only useful if the prediction was frozen before the outcome was
known. That ordering is the whole design.

---

## 1. What is frozen, and when (§50)

`web/planner/trip.js::snapshotPrediction`, called when the reader logs a plan — **before
they fish it**. It is never overwritten; a later recheck writes a delta *alongside*.

```
builtAt, plannedAt, requested window, species, craft
versions        planner · species_model · zone_model · research      (§53)
weights         the species weight column this plan was scored with
utilityConstants  every constant in the utility function
verdict, opportunity, confidence, locationConfidence, researchConfidence
utility, utilityParts    quality × duration × confidence × location − travel …
zone, zoneSequence, zoneKind, window
segments[]      the itinerary as executed-intent, each with its expected score
hourly{}        the opportunity curve for every ranked candidate
ranking[]       what the alternatives scored, and why they lost
predictedArrival {earliest, typical, latest}, predictedSafeExit
predictedFlow / Generation / WaterTemp, modelConfidence, conditions
research[]      the claims used, with tier and per-zone confidence
breakdown[]     the component score lines
```

Freezing the *weights and the model versions* is what makes a result from today still
interpretable after the weights move. A calibration figure computed across a weight change
means nothing, so the scoreboard groups by version.

---

## 2. Collecting the outcome (§48, §49)

Friction here is the only thing between the model and the data it needs. So the first
screen is **four taps and no typing**:

```
Did you fish the plan?          Yes / Partly / No
Target species caught?          Yes / No
How was the fishing?            1 2 3 4 5
Did Caney put you in the right place?   Yes / Partly / No
```

Detail is behind a disclosure: counts, largest, actual arrival time, clarity, temperature,
the fly that actually worked, where the fish actually were, notes.

**Per-segment outcomes** (§49) sit behind a second disclosure, one form per fishing
stretch: fished it, fish caught, largest, where they actually were, what actually worked.
A segment outcome calibrates the *itinerary* — the expected score for that stretch against
what it produced — which one trip-wide rating cannot.

Everything is optional. Everything is on the device.

---

## 3. The scoreboard (§44, §51)

`web/planner/trip.js::scoreboard`. Every measure reports its own sample size and **refuses
to print a figure until it has enough data**. That refusal is the feature: a model whose
validation is one trip should say so rather than print a number somebody will act on.

| question | how it is answered |
|---|---|
| Is the water-arrival model right? | median residual (predicted typical vs actual), mean absolute error, fraction inside the earliest→latest bounds, and **how many trips saw water before the earliest bound** — that last one is the safety number |
| Does a 90 outperform an 80? | mean rating bucketed by opportunity band, plus the correlation |
| Does confidence mean accuracy? | mean rating by confidence band, checked for monotonicity |
| Does location confidence predict the right place? | "did Caney put you in the right place" by location-confidence band |
| Which species model performs best? | mean rating and target-species hit rate per species |
| Which zones are poorly calibrated? | per zone, predicted opportunity (rescaled to 1–5) minus the rating given |
| Does the itinerary optimiser beat a single zone? | mean rating, multi-zone plans vs single-zone |
| Does research improve results? | mean rating with ≥2 sourced claims vs fewer |
| Do segment expectations hold? | correlation between a stretch's expected score and fish caught |

---

## 4. Recheck and the delta (§40, §41)

In on-water mode, **RECHECK PLAN** re-fetches the dataset, re-runs the planner against the
*same request*, and diffs against the plan that was actually started:

```
PLAN CHANGED

Generation           was 8:30 stop        now 7:47 stop
Primary zone         was Cordell Hull     now Caney Confluence
Fly                  was large Deceiver   now smaller Clouser

Move to Caney Confluence now — the water you planned for is no longer the
best of what is left.
```

Only material changes are shown: a zone change, a window move over 15 minutes, a
generation/arrival claim moving over 15 minutes, or the fly changing.

**The original plan is preserved.** `ctx.originalPlan` and `ctx.frozenClaims` survive the
recheck untouched, because the trip log needs what we predicted, not what we would have
predicted with hindsight.

---

## 5. Model versioning and shadow scoring (§53, §54)

`caney/version.py`:

```
PLANNER_VERSION        the utility function, the window search, the itinerary search
SPECIES_MODEL_VERSION  the weight table or a species profile rule
ZONE_MODEL_VERSION     the zone registry, zone kinds, location confidence
RESEARCH_VERSION       the seed corpus, the tiers, the decay curves
```

Every plan and every frozen prediction carries all four. The scoreboard groups by
`planner`, so a calibration result never silently spans a model change.

**Shadow scoring** is architected but not active: `FishingPlan.shadow` and the frozen
prediction's `shadow` field hold a candidate scorer's ranking, stored and never displayed.
To run an experiment, compute a second ranking in `plan()`, write it to `p.shadow`, and
compare against outcomes later. Nothing else has to move.

---

## 6. Calibration data model (§52)

The shape the frozen records support is:

```
species × zone × season × conditions  →  outcome
```

Deliberately **no ML yet**. First gather clean evidence; simple statistics — band means,
monotonicity checks, correlations, residuals — answer every question in §51 and are
interpretable when they disagree with intuition, which is when it matters.

Export with **Export log** (a JSON file). Import merges by trip id.

---

## 7. What to do first

1. **Fish it and log trips.** Twenty logged plans with outcomes, across at least three
   species, is the threshold at which the scoreboard starts printing figures instead of
   "not enough trips to say".
2. Watch the **arrival residual** first. It is the only measure with a safety consequence:
   if trips start seeing water before the earliest bound, that bound moves before anything
   else does.
3. Then the **opportunity bands**. If a 90 does not outperform an 80, the weights are wrong
   and `docs/SCORING.md` §Recalibrating is the procedure.
