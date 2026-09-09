# Species scoring, ranking and confidence

## 1. Weights are config, not logic

`caney/species/profiles.py::WEIGHTS` is a plain dict per species, summing to 100. The
scorer multiplies a 0–1 component **fit** by the weight and sums. Recalibrating means
editing a number in that table — never touching `caney/planner/scoring.py`.

`test/planner/test_domain.py::test_weights` pins the published table value by value, so a
silent drift fails the build rather than quietly changing every recommendation.

### Striped bass
| component | weight |
|---|---|
| current / generation | 25 |
| water temperature / thermal fit | 20 |
| seasonal geographic pattern | 15 |
| recent primary research | 15 |
| forage / habitat | 10 |
| time of day / light | 7 |
| weather | 5 |
| moon / solunar | 3 |

### Smallmouth
| component | weight |
|---|---|
| flow level / trend | 20 |
| water temperature / season | 15 |
| clarity | 15 |
| habitat | 15 |
| weather / cloud / wind | 10 |
| recent research | 10 |
| current | 7 |
| access / craft | 5 |
| moon / solunar | 3 |

### Largemouth
| component | weight |
|---|---|
| water temperature / season | 20 |
| habitat / cover | 20 |
| water level / trend | 15 |
| weather / cloud / wind | 15 |
| forage / recent reports | 15 |
| time of day / light | 7 |
| current | 5 |
| moon / solunar | 3 |

### Trout
| component | weight |
|---|---|
| generation / flow / wade timing | 30 |
| water temperature / dissolved O₂ | 20 |
| hatch / forage | 15 |
| clarity | 10 |
| weather / light | 8 |
| recent research | 7 |
| access / craft | 7 |
| moon / solunar | 3 |

A species scores **exactly** the components it publishes weights for. Adding a weight key
with no fit function raises `KeyError` rather than silently scoring zero — the first
version computed every fit for every species and asked the striped-bass profile for a
free-flowing `flow` rule it has no reason to declare.

## 2. Craft is a gate, not a weight

`access` appears in two weight columns, but craft **eligibility** is never a score.
`FishingZone.supports_craft()` removes a zone from a wade request; it does not rank it
lower. A reach you cannot wade must never appear in a wade plan at any score.

## 3. The moon is capped structurally

Three points of 100, in every column, plus `validate()` refusing a value above 3 and
`test_weights` asserting `moon < (100 − moon) × 0.05`. A perfect solunar window cannot
rescue bad water, bad temperature, no generation or a thunderstorm. It is displayed clearly
in the conditions strip — with its own accuracy caveat, `±40 min`, because the model is the
classic mean-synodic approximation — and it moves the number by at most three points.

## 4. Unknown scores neutral and is charged to confidence

A component with no data returns fit `0.5` and marks itself `known: false`. The missing
signal is charged against **confidence**, not against the score, and the breakdown line
says so: *"(unknown — charged to confidence, not to score)"*. The bar renders hatched.

This is what makes §31 possible: a fishery that looks good on paper with no live water is a
high score with low confidence, and the ranker — not the scorer — decides what to do about
that.

## 5. Confidence

`caney/planner/confidence.py`. Weighted credit across nine signals:

| signal | weight |
|---|---|
| flow | 0.16 |
| release forecast | 0.16 |
| dam release now | 0.14 |
| hourly weather in the requested window | 0.14 |
| water temperature | 0.12 |
| sourced research | 0.10 |
| routing model confidence | 0.08 |
| stage | 0.06 |
| sun times | 0.04 |

`known` scores full credit, `stale` scores 0.45, `unknown` and `error` score nothing. A
river with no dam is not penalised for having no release forecast — that signal leaves the
denominator entirely rather than counting as a miss.

Beyond about 48 hours the request becomes a **seasonal expectation**, not a forecast:
12 points of confidence per day past day 2, capped at 45, and the plan says so in its
limitations.

## 6. Ranking

Score and confidence are separate numbers. They are blended **once**, explicitly, in
`rank_key`:

```
rank = score × (0.65 + 0.35 × confidence/100)
```

Confidence can cost a candidate up to 35% of its score. §31's worked example falls straight
out:

```
89 × (0.65 + 0.35 × 0.42) = 71.0     attractive fishery, no live water
84 × (0.65 + 0.35 × 0.93) = 81.9     slightly worse fishery, fully observed   ← wins
```

`0.65` and `0.35` are published to the browser as `data.rank`, so both engines use the
same blend.

## 7. Verdict

| verdict | rule |
|---|---|
| **GO** | score ≥ 68 **and** confidence ≥ 55 **and** no component below 20% of its weight that is actually known |
| **CONDITIONAL** | score ≥ 68 with confidence < 55 (*"too much of it is unmeasured"*), or score ≥ 50 |
| **SKIP** | anything else |

Published as `data.verdictThresholds`; asserted in both engines by
`test_architecture.py::test_browser_engine_holds_no_model`.

## 8. The window search

`caney/planner/window.py`. Scans 30-minute offsets inside the request, minimum span 90
minutes, and returns the highest-scoring contiguous slice. A longer window wins ties: the
reader asked for the time, so only give it back when the score actually pays for the loss
(a slice must beat the whole window by 0.35 points).

The search uses the same weights as everything else, so the window and the ranking cannot
disagree. Geometry is published as `data.windowSearch`.

## 9. Provenance for biology

Every behavioural rule in a species profile is classified `Evidence.SOURCED` — naming the
agency document behind it — or `Evidence.HEURISTIC` — angling convention, useful and
unvalidated. Nothing is allowed to be neither; `validate()` fails a profile with an
unclassified rule. This is the repo's calibration-provenance invariant (CLAUDE.md), applied
to fish behaviour.

## 10. Recalibrating

1. Change a number in `WEIGHTS`.
2. Update the pinned table in `test/planner/test_domain.py::test_weights`.
3. Update the table above.
4. Run `python3 test/planner/run.py` — the species regression fixtures will tell you what
   the change did to each of the §51 scenarios.
5. Rebuild; `test_parity.mjs` confirms the browser picked up the new table.

The evidence for a recalibration is `docs/` plus the trip log: the model scoreboard
(§44, `web/planner/trip.js::scoreboard`) reports the water-arrival residual, score-vs-rating
correlation, species hit rate and confidence calibration, each with its sample size and
each refusing to print a figure until there is enough data.
