# Product strategy — office-hours diagnosis

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
