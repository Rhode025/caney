# Safety architecture

The rule, in one sentence:

> **Every number a person could get hurt by is minted once, deterministically, from
> instrument data — and anything generative may quote one but never restate one.**

---

## 1. What went wrong with the old guard

`riverguide/src/guard.js` used to extract every digit-bearing token from a model's reply
and check it against every number anywhere in the corpus slice, flattened. Three failures,
each of which put an unverified number in front of someone deciding whether to wade:

1. **Scope.** Numeric presence *somewhere* in the slice did not prove the number belonged
   to that river, that measurement, or that claim. A flow figure in a fly-box note licensed
   the same digits in a wade sentence about a different river.
2. **The HARMLESS set.** Small values were discarded after units were normalised away, so
   `2` and `3` passed unconditionally — including *"the water comes up in 2 hours"*.
3. **The failure mode.** On a failure it **shipped the sentence** with an italic warning
   appended. A reader who has already decided to wade does not un-decide because of a
   footnote. Unsafe prose was preserved by design.

---

## 2. What replaced it

### 2.1 Claims are minted in exactly one place

`caney/sources/snapshots.py::_mint_safety_claims` is the only function in the codebase that
creates a `SafetyClaim`. It runs on instrument data, after freshness budgets have been
applied, and produces claims of these kinds:

```
generation_start   generation_stop    flow            stage
wade_cutoff        safe_exit          release_arrival forecast_release
weather_hazard     lake_elevation
```

Each claim carries:

| field | meaning |
|---|---|
| `id` | `sc_<kind>_<sha1[:10]>`, stable across builds for the same claim |
| `zone_id` | the ONE zone it is about |
| `text` | the only wording permitted for this claim anywhere in the product |
| `numbers` | the exact digit-tokens it licenses |
| `bound` | `earliest` \| `typical` \| `latest` \| `measured` |
| `source`, `source_url`, `state`, `observed_at` | provenance and age |

`numbers` defaults to the tokens extracted from `text`, and is **overridden explicitly**
wherever the sentence carries an incidental digit. "Flow at USGS 03424860 is 1,500 cfs
(50 min ago)" licenses `1500` — not the gauge id, and not the age. A claim must not license
a number it does not assert.

### 2.2 Verification fails closed

`riverguide/src/guard.js::verify(reply, slice, claims, scope)`:

1. Splits the reply into sentences.
2. A sentence quoted **verbatim** from a claim in scope is always allowed. (Without this
   rule the guard deleted the one thing the model is explicitly told to do.)
3. Otherwise, `isSafetySensitive(sentence)` — a safety cue **and** a digit. The cues cover
   words (`generat*`, `release`, `wade`, `flow`, `cfs`, `stage`, `arrival`, `thunderstorm`,
   …) **and phrases** (`be/get/stay out`, `in/out of the water`, `comes up`, `safe exit`).
   *"Be out of the water by 1:42"* contains no cue word at all, which is how the first
   version let the single most dangerous sentence class through.
4. For a safety-sensitive sentence, **every** number must be licensed by a claim **for a
   zone in scope**. Otherwise the sentence is **removed**. Not annotated. Removed.
5. `repair()` replaces it with the claim text for the same kind of fact where one exists,
   or with an explicit "I do not have a verified figure for that", plus a pointer to the
   page and the USACE schedule.
6. Non-safety numbers (fly sizes, tippet, air temperature) keep the old gentle treatment:
   annotated, not deleted. A wrong fly size is not a drowning risk.

Verified against these, in `riverguide/test.mjs`:

| the model writes | outcome |
|---|---|
| a claim, verbatim | kept, and the grounding claim id is recorded |
| an invented generation time | **removed** |
| a rounded flow (`4100` when the claim says `3982`) | **removed** |
| a converted figure (`7.1 cubic metres per second`) | **removed** |
| a small-looking count (`2 hours before the water comes up`) | **removed** |
| an inferred exit time | **removed** |
| a claim about the *wrong* river | **removed** |
| `Fish a #18 zebra midge on 6X` | kept |

### 2.3 Conservative bounds

`riverlib.ARRIVAL_STAGES` already carried early / median / late speeds for each stage of a
release front. The planner reads all three:

```
That water reaches Middle Caney Fork no earlier than 3:24 PM
(typical 5:48 PM, later edge 6:36 PM).
Be out of the water at Middle Caney Fork by 2:54 PM.
```

* **Safety uses `earliest`.** The safe-exit claim is `earliest arrival − 30 minutes`, and
  `bound="earliest"` is asserted on every one of them by `verify.py` and by
  `test_species.py`.
* **Fishing optimisation uses `typical`.** The itinerary's "released water reaches this
  zone" step is placed at the median and displays the full spread underneath.
* A `safe_exit` claim is minted **only** where someone can actually be standing in the
  water. A power-boat-only tailrace gets the arrival claim and no exit instruction, so the
  one that matters is never lost in noise.

### 2.4 Eligibility fails closed too

`caney/planner/engine.py::_unsafe` removes a candidate rather than scoring it down:

* a **wade** request on a tailwater with **no release forecast** — the plan cannot bound
  the wade window, so it will not offer one;
* a wade request where the release runs through the entire window;
* a free-flowing river above 1.35 × its measured `no_wade` threshold;
* a window that is entirely thunderstorm.

The wade gate is deliberately **different** on the two kinds of water. On a tailwater the
danger is the release, not today's level — a downstream gauge reading high because
yesterday's generation is still passing says nothing about whether you can wade at the dam
this morning. Getting this backwards eliminated the entire calibrated Caney trout fishery
on a Stonewall reading taken fifteen miles below the dam.

---

## 3. Unknown is never zero

`Observation` exists for this. `value or 0` is how a missing Center Hill release forecast
becomes "0 cfs", becomes "minimum flow", becomes "wade all day", becomes someone in the
river during a two-unit release.

* `DataState` is `known` / `stale` / `unknown` / `error`.
* `Observation.ok` is the only gate that may precede use.
* `or_else(default)` forces the caller to name the fallback at the call site. There is no
  zero default anywhere in the API.
* `require()` raises rather than substituting.
* A **real** zero is a real reading: `Observation.known(0, "cfs")` is `ok` and its value is
  `0`. Absence and zero are different objects.
* `test_architecture.py::test_no_unknown_as_zero` greps the whole package for `or 0` and
  fails unless the line carries `# not a measurement`. It tokenises first, so it does not
  flag the docstring that explains the rule.

---

## 4. Research may never become a measurement

`ResearchClaim.__post_init__` raises `UnsourcedClaim` without a `source_url`. No source, no
claim — enforced in the constructor, not in a review.

`SAFETY_SENSITIVE_RE` flags any claim whose prose contains something shaped like a flow, a
stage, a generation time or a wade window. Those claims are kept for their language and
marked `safety_sensitive: true` in the evidence drawer — and **nothing anywhere reads a
number out of a `ResearchClaim`**. Instrument data reaches a plan only through
`caney/sources/` and `SafetyClaim`.

---

## 5. Degradation (§58)

| failure | behaviour |
|---|---|
| research unavailable | plan is unaffected; the drawer says *"research off"* |
| weather unavailable | the weather component scores neutral and is marked unknown; confidence pays for it |
| release forecast unavailable on a **wade** request | candidate **eliminated**, with the reason shown |
| release forecast unavailable otherwise | scored down explicitly (*"the wade window cannot be bounded"*), claim book says so |
| any noncritical field unknown | rendered as the word **unknown**, never as a placeholder number |
| offline | banner: *"OFFLINE — showing a cached snapshot from N hours ago. Do not treat any water number here as current."* |
