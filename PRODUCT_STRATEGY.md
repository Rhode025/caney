# Product strategy

## The thesis (Caney 3.0)

> **Caney is a live decision engine for freshwater fishing. The user supplies the fish they
> want and the constraints of their day; Caney returns and maintains an executable trip.**

"and maintains" is the 3.0 half. 2.1 produced a very good report and then stopped. A guide
does not stop — they watch the water and change the plan when the dam does something the
forecast did not.

Still true, and still the thing that keeps this from becoming a different product:

> **Build the oracle, not the network.**

No social feed. No leaderboard. No shared catch log. The value is in answering one person's
question completely, and every feature that would be improved by more users is a feature
this product does not want.

### What "executable" rules in

A plan is executable when it answers all of these without the reader doing arithmetic:

- where to drive, and when to leave the house
- where to launch, and what the ramp costs in time
- which feature to fish first, graded by how well we know where it is
- when to move, where to, and why
- what to throw, for the tackle they actually own
- what physical condition makes the recommendation work
- what would change it
- when to get off the water — on the conservative bound, always
- when they will be home

### What it rules out

- A recommendation that does not fit inside the day. Travel is a constraint, not a note.
- A precise-sounding number the evidence does not support. A described reach is a corridor,
  never a waypoint.
- A safety claim that anything downstream is allowed to restate, round, or improve on.
- A second implementation of the model, anywhere, for any reason.

---

## Earlier strategy notes

> **Updated 2026-09-09 for Caney 2.0.** The office-hours diagnosis below is preserved
> verbatim from 2026-07-30, because its verdict — *build the oracle, not the network* — is
> exactly what this release implements. What changed is the shape of the oracle.

## Caney 2.0 — the current frame

**The product is not a collection of river dashboards. It is a species-first planner.**

> The user says what species they want to catch and when they can fish. Caney tells them
> the single best place to go, the exact time window, where to start, where to move, what
> to throw, what the water and weather will do, when conditions change, and why this is the
> best decision.

Four target species: **striped bass, smallmouth, largemouth, trout.** The core question,
and everything is subordinate to answering it:

> *"I want to fish for [SPECIES] on [DATE] from [START] to [END]. What exactly should I do?"*

### What that changed

| before | now |
|---|---|
| the homepage is a board of 13 river cards | the homepage asks **"What do you want to catch?"** |
| a species is a label on a river page | a species is a behavioural profile attached to a **fishing zone** |
| a river page owns one fishery | a **zone** can span two rivers, and one zone can be two different fisheries in different months |
| the user sorts cards to find an answer | one action — **FIND MY BEST PLAN** — returns the answer |
| "Prime / Good / Fair" | a 0–100 score from a **published weight table**, a separate confidence number, and a line-by-line breakdown |
| the AI is *told* not to invent numbers | the AI is **verified in code**, per zone, and **fails closed** |
| river pages are the product | river pages are the encyclopedia behind it |

The clearest single illustration is the Carthage case. TWRA writes: *"Striped bass are
concentrated from Cordell Hull Dam downstream to the mouth of the Caney Fork River."*
Under the old model that opportunity was unreachable, because `cordell.py`'s species line
reads "Smallmouth, white bass & panfish" and the Caney is a trout page. It is now a
first-class zone spanning both, and it is a regression test.

### Still true, still the strategy

* **Build the oracle, not the network.** No social features. The trip log exists to feed
  calibration — `prediction → outcome → calibration` — not to be a feed.
* **The wedge is collapsing the 4-source 6am ritual into one decision.** Species-first is
  that thesis taken seriously: the ritual is not "check four gauges", it is "work out where
  the fish I want are, given the water".
* **The moat is the data loop**, and it is now instrumented. Every logged plan freezes what
  Caney predicted *before* the outcome is known; the model scoreboard reports the
  water-arrival residual, the score-vs-rating correlation, the species hit rate and the
  confidence calibration — each refusing to print a figure until it has enough trips.

### The bet this release makes

That the thing worth paying for is not better numbers but **a decision you can audit**. So
every plan ships its score breakdown, the source and age of every datum, the sourced
research behind the biology, the model's own confidence in its routing, and an explicit
list of what it could not tell you. A recommendation you cannot interrogate is a horoscope.

### Deliberately not built

Social, marketplace, profiles, buddies, trip hosting. Server-pushed notifications — the
riverbank is exactly where there is no signal, and a phone alarm from an `.ics` is the thing
that actually rings. A chatbot homepage: the natural-language box is secondary, lives
*inside* a plan, and explains the deterministic recommendation rather than replacing it.

---

# Product strategy — office-hours diagnosis (2026-07-30, preserved)

*YC office-hours (startup mode) run on the "turn this into a consumer app" vision.
Pre-product, one real user (the founder). This is the verdict, not a cheerlead.*

## The one-sentence verdict

**Build the oracle, not the network.** There are two companies in the vision; only one
is a wedge you can charge for this week. Ship the morning briefing + on-water timing +
AI-guide call as a paid tool for a curated set of tailwaters, aimed at the angler who
*can't afford to guess*. The social/marketplace layer is Act 2 — and its real job is a
data moat, not a Facebook clone.

## Two companies, one wedge

| | **Company A — the oracle (BUILD)** | **Company B — the network (DEFER)** |
|---|---|---|
| What | Water-timing engine (backtested), HQ, on-water "how much water when/where at my spot," AI guide advice from live conditions | Profiles, buddies, host trips, split guides/lodging |
| Type | Tool — valuable day one, one user, zero network | Marketplace — worthless until local liquidity exists |
| Demand | "Don't waste my trip / don't get caught wading" | "Find people to fish with" (nice-to-have) |
| Risk | Niche TAM; free status quo; onX could copy | Cold-start liquidity; the founder graveyard |

Bolting B onto launch is the **platform trap** — believing the value needs the whole
thing. It doesn't. The value is the 5am briefing and the on-water call.

## The forcing questions (my answers, since the market can't yet)

- **Demand (Q1):** just the founder. Best possible seed, still n=1. Not "solution in
  search of a problem" — the problem is real and acute — but "confirmed for 1, unverified
  for many." De-risk cheaply *before* building consumer features.
- **Status quo (Q2) — founder's answer:** *all four at once* (gauge/schedule apps, ask a
  guide/buddy, Facebook groups, show-up-and-read) *"which wastes a ton of time."* This is
  stronger than "free but dumb data": the status quo is a **fragmented 6am ritual across 4
  sources**, and the pain is **quantifiable — time**. The product isn't "better numbers," it's
  *"collapse your 4-source pre-trip ritual into one decision."* Important consequence: the
  time-waste hits *everyone* who runs the ritual, including local experts — so the customer is
  broader than just travelers. **But** — the one push: "wastes time" only converts to "will
  pay" for the angler who *resents* that time. Some love the gauge-checking ritual; it's part
  of the hobby. The buyer sees the ritual as **friction between them and fishing**, not fun.
- **Who exactly (Q3):** the angler who *resents the ritual* — sharpest instance: the
  **traveling / time-boxed angler**, 4–6 trips a year, $2–5k a trip (or the dad with one
  3-hour window), who already pays guides $400/day to answer "when/where/what" and cannot
  recover a wasted morning. You're a ~$99/yr insurance policy against a blown $3k trip.
  Wallet-open. Secondary: the high-frequency local who wants the edge on marginal days.
- **Wedge (Q4):** not the app, not the network — **one artifact**: the 5am plan that says
  *here's your window, here's where, here's exactly what to throw, be off by 2pm.* Even
  narrower (no login, no setup): they text you a river + date, you send the plan back.
  **Concierge MVP** — founder's guide-brain + the engine, by hand, for 20 people.
- **Surprise to hunt (Q5):** you haven't watched anyone else use it. Bet: they won't care
  about the model's rigor — they'll want the blunt *go / no-go + what-to-throw* verdict, and
  they'll want it for rivers you haven't modeled. The market pulls toward **coverage**; your
  instinct is **depth**. Watch that tension.
- **Future-fit (Q6):** more essential in 3 years. Climate/water-management volatility erodes
  "I know my river" (raising the value of a live calibrated model), and AI guide reasoning
  keeps getting cheaper/better. Defense vs. onX/Fishbrain adding a "conditions tab":
  per-river calibration depth + guide-brain quality + a **community ground-truth flywheel**
  (users confirm/correct the model → better model → more users). *That* is why community
  eventually matters — as data, not as a social feed.

## Premise challenge (the strongest version, and where it breaks)

Strongest version: *"the angler's morning oracle — so right on unfamiliar water you'd never
fish without it."* Where it breaks: **(1) TAM** — tailwater fly is a niche within a niche;
nailing it may be a $1–5M lifestyle business unless you widen to all freshwater (which
dilutes the depth edge). **(2)** the free status quo is good enough for locals (your biggest
raw segment is your worst customer). **(3) coverage cost** — every new river needs a gauge +
calibration. **(4) safety liability** — "it's safe to wade" that's wrong is a lawsuit.

## Alternatives considered

- **A. Niche premium tool for traveling tailwater anglers** — small, real, defensible,
  chargeable now. *(recommended first)*
- **B. Broaden to all-freshwater conditions oracle** — bigger TAM, weaker moat (now fighting
  onX/Fishbrain on their turf). *(later, from strength)*
- **C. B2B: license the engine to guides / fly shops / lodges** — branded "morning briefing"
  that makes them look omniscient; they already sell when/where/what. *(fastest path to
  revenue — run in parallel with A)*
- **D. The social/marketplace vision** — cut for v1; revisit as the ground-truth flywheel.

## Recommendation & staged path

1. **Now — Concierge oracle.** Manually deliver the 5am plan to ~20 target anglers on
   rivers you *don't* fish. No signup, no app. Charge something ($5 a plan, or a $99 season).
2. **Act 1 — Productize the oracle.** Sign-up, pick your waters + boat/wade + range → the HQ
   you already built, plus on-water GPS timing + the AI guide. Subscription. Add rivers on
   demand (coverage follows paying users).
3. **Parallel — B2B pilot (C).** One lodge or guide service using a branded briefing. Faster
   cash, and it seeds ground-truth data.
4. **Act 2 — Community as data moat.** Anglers confirm/correct conditions → the flywheel.
   *Then* the social features (buddies, trips, splits) have fuel and a reason to exist.

## The assignment (do this before writing any consumer code)

Take what you already have. Pick **5 anglers who fish tailwaters you don't know**. Give each
the briefing for their next trip. Watch (don't demo), then ask one question: *"Would you have
paid $99 for that this morning — why or why not?"* Get one "yes, here's my card" or one sharp
"no, because ___." **That single data point outweighs the entire social feature set.**
