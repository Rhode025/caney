# The planner

> **I want to catch [species] between [start] and [end]. What exactly should I do?**

Caney 2.0 answered "which zone scores highest over the period you gave?" — and answered it
with a *mean*. Caney 2.1 answers "what is the best executable day inside that period?" and
answers it with an **itinerary**.

---

## 1. Why the mean was the wrong objective

From the 2.1 brief, and it is the whole reason this phase exists:

```
Candidate A   6:30 96   7:00 95   7:30 92   8:00 63   8:30 57   9:00 55   9:30 52
Candidate B   6:30 77   7:00 77   7:30 78   8:00 76   8:30 77   9:00 76   9:30 75
```

A mean prefers B. That is wrong. The right answer is *"fish A hard from 6:30 to 7:45, then
move, switch, or stop."*

**The user's availability is a constraint, not a requirement to fish every minute of it.**
`test/planner/test_opportunity.py::test_peak_beats_average` is the mandatory fixture, and
it asserts all three orderings: A's 90-minute peak > A's whole four hours > B's flat four.

---

## 2. The window utility function

`caney/planner/utility.py`. Stated in full, because a scoring function you cannot read is a
scoring function nobody can argue with:

```
U  =  Q × D × C × L  −  transition  −  staleness

Q   quality, 0..100, peak-weighted
      Q = 0.50·peak + 0.28·cubic_mean + 0.22·floor
      peak       mean of the top third of the samples (at least one)
      cubic_mean 100·(mean((s/100)³))^(1/3) — a power mean, so a 95 counts
                 for more than a 70 in a way an arithmetic mean never does
      floor      the worst sample. THIS is the term that stops one great hour
                 being averaged with three dead ones and still winning.

D   duration, 0.72 … 1.00
      D = 0.72 + 0.28 · min(1, minutes / 150)
      × 0.35 if minutes < the species minimum practical duration
      It SATURATES. Fishing past about two and a half hours does not keep
      buying utility, which is what stops the optimiser padding a peak with
      mediocre hours to farm duration.

C   forecast confidence = 0.70 + 0.30 · confidence/100
L   location confidence = 0.75 + 0.25 · location_confidence      (0..1)

transition   minutes travelled × 0.22, plus idle × 0.15 × 0.22
staleness    4.0 flat, when the driving water reading is stale
```

Sampling is every 15 minutes, linearly interpolated from the hourly series.

**Minimum practical durations** (§5), config in `utility.MIN_DURATION`:

| species | minutes |
|---|---|
| striped bass | 60 |
| smallmouth | 75 |
| largemouth | 75 |
| trout | 60 |

A request shorter than the minimum is still answered — the reader asked — but it is
penalised and the plan says *"this is a short session, not a plan."*

### Why these constants

They are **priors**, chosen so the four mandatory scenarios (§57, §58, §59, §60) come out
as specified and so the ordering is stable under small perturbations. Nothing here is
calibrated against outcomes. The trip log and the scoreboard (`docs/OUTCOMES.md`) exist to
change that.

---

## 3. Finding the windows

`caney/planner/opportunity.py`. Candidate windows on a 15-minute grid, scored, then pruned
to a **diverse** keep-set: the best window ending in each hour, the best starting in each
hour, and the global best.

That pruning rule is load-bearing and was a real bug. Keeping only the top few by
standalone utility deletes the tight peak window that is only worth fishing as the **first
leg of a circuit** — the longer window that runs into the zone's collapse scores higher on
its own — and the itinerary search then has nothing early-ending to build on and can never
find the move.

---

## 4. Building the day

`caney/planner/itinerary.py`. A beam search over time-ordered, transition-feasible
sequences of at most **3 zones**. The objective evaluates a candidate day as **one
pseudo-window** over its concatenated samples:

```
itinerary_utility = Q(all samples) × D(total fished minutes) × C × L
                    − (travel + 0.15·idle) × 0.22
                    + breadth_bonus
                    − 1.5 × (zones − 1)

breadth_bonus = 6.0 × (segments − 1) × mean_segment_quality/100
```

Three decisions worth defending:

* **Evaluating the whole day as one window**, rather than summing per-window utilities, is
  what makes §57, §58 and §59 come out right *at once*. Summing rewards adding segments;
  averaging rewards padding; this rewards a day whose fished time is uniformly good.
* **The breadth bonus** exists because the duration factor deliberately saturates. Without
  it the optimiser could never say that ninety minutes at 95 *and* two hours at 90 beats
  either alone. It scales by mean segment quality, so stitching a good window to a bad one
  earns nothing.
* **The complexity penalty** is §14's thumb on the scale: a one-zone plan wins when it is
  clearly best, and it is always in the beam from the first iteration rather than something
  the search has to be talked back into.

### Transitions

`caney/planner/transitions.py`. Every move declares its provenance:

| provenance | meaning |
|---|---|
| `known` | a configured route between two zones on the same water |
| `estimated` | great-circle distance × a mode factor, labelled as an estimate |
| `unknown` | no route we can justify — the move is **not offered** |

Craft-aware (§12): `transition()` returns `None` when the move is impossible, which removes
it from the search rather than pricing it. A wading angler cannot run the Cumberland; a
power boat cannot be trailered across the state inside a morning; a kayak cannot cross
watersheds. Both ends must serve the craft, and a road reposition needs an access at each
end. Anything over 55 minutes is never offered — at that point it is two trips, not a move.

---

## 5. The four numbers (§31, §65)

Displayed separately, because none implies the others:

| number | what it answers |
|---|---|
| **Opportunity** | how good the fishing looks in this window |
| **Forecast confidence** | how much of that we actually measured |
| **Location confidence** | how well we know WHERE — see `docs/GEOGRAPHY.md` |
| **Research confidence** | how well sourced the biology is |

A high opportunity on unverified geography is a different thing from a high opportunity on
a mapped ramp, and collapsing them into one figure is how a planner starts lying.

---

## 6. The Python/browser split (§55, §56)

**Python owns every number. The browser selects among precomputed opportunities.**

| Python | browser |
|---|---|
| instrument readings, routing, arrival bounds | the weighted sum |
| hourly component fits and hourly totals | the window scan (argmax over Python's series) |
| every constant in the utility function | the beam search over Python's windows |
| the transition graph, per craft | segment assembly and rendering |
| eligibility gates, precomputed as flags | the eligibility lookup |

`out/plan/parity.json` holds Python's own answers, computed **from the emitted dataset**, at
four layers — component scores, window utilities, best-subwindow sets and whole itineraries
— and `test/planner/test_parity.mjs` replays every one through `web/planner/*.js`.

Currently **405 checks, all exact** including complete itinerary equality (zones, times,
utility). If a threshold, a curve or a coefficient leaks into the browser, one of the four
layers disagrees.

---

## 7. The segments

`caney/planner/segments.py`, mirrored in `web/planner/segments.js`. Types:

```
launch · fish · move · wait · change_technique · safety_exit · optional_backup · end
```

* **§15** — a `move` says what CHANGES and what it costs, never "move to Zone B".
* **§37** — technique is per **segment**, with a backup presentation and an explicit
  switch trigger.
* **§38** — triggers come from the deterministic claim book and the emitted hourly weather,
  not from prose: generation start/stop, modelled arrival, sustained wind, gusts on open
  water, thunderstorms, the cloud breaking.
* **§39** — every plan carries a backup: what to do if generation is cancelled, if the
  primary zone is dead, if the weather turns.

---

## 8. Reading order

1. `caney/planner/utility.py` — the formula, and why every constant is what it is.
2. `test/planner/test_opportunity.py` — the four mandatory scenarios, as executable prose.
3. `caney/planner/itinerary.py::evaluate` — the objective.
4. `caney/planner/segments.py` — how a won itinerary becomes instructions.
