# Journal

Append-only session memory. Newest entry at the top. Each entry: what changed, why, and
what's still open. Written for a future session that has no chat history — assume it knows
nothing except this file and the code.

Keep entries short. Detail that belongs next to code goes in a code comment; detail that
belongs to a commit goes in the commit message. This file is for *state and intent*.

---

## 2026-07-30 — flow-engine backtest, then a strategy detour

**Shipped.** Built the QA harness first (`14e3207` static `verify.py` + runtime
`browser.mjs`; `1e33477` pre-commit gate), then used it to make two calibration changes to
Caney safely:

- `b2115c3` — **baseflow 375 → 205 cfs.** Backtested 90 days of the Center Hill release
  forecast against the Stonewall gauge (`analysis/backtest_flow.py`). Least-squares
  intercept came out 204; the min-flow check agrees (205 + 166 ≈ 372 = observed min). The
  old 375 had the whole river running ~170 cfs high.
- `2c2bc2c` — **leading-edge speed 3.0 → 2.5 mph.** Same backtest, 80 generation events.
  It *confirmed* the guide's miles-from-dam (Happy Hollow 6, Betty's Island 9, Stonewall
  15) but corrected his ~3 mph rule: detectable rise at Stonewall has median *and* modal
  lag 6 h (49 of 80 events), independent of release size → 15/6 = 2.5 mph. Arrivals are now
  HH ~2½ h, Betty's ~3½ h, Stonewall ~6 h. Threaded through every place that quoted the old
  number — tip text, `genHint`, footer, config trend rule — and the page JS now reads
  `DATA.mph` instead of a hardcoded `3`.

**Also on disk, uncommitted:** `PRODUCT_STRATEGY.md`, from a YC-office-hours-style session.
Verdict: *build the oracle, not the network* — the water-timing engine + 5am briefing is the
wedge; social/marketplace is Act 2 and its real job is a ground-truth data moat, not a feed.
Target customer is the angler who **resents the 4-source 6am ritual** — sharpest instance the
traveling/time-boxed angler who already pays $400/day guides. The assignment it sets: give 5
anglers the briefing for tailwaters *you don't fish*, watch them use it, then ask "would you
have paid $99 for that this morning — why or why not."

**Open threads.**
1. `PRODUCT_STRATEGY.md` is untracked — commit it or delete it, don't leave it in limbo.
2. **The backtest methodology has only been run against Caney.** The other six rivers still
   carry their original constants, unvalidated. `analysis/backtest_flow.py` is the template.
3. The strategy doc's assignment (5 anglers, unfamiliar tailwaters) is not started. It is
   explicitly gated *before* writing any consumer code.

---

## Before 2026-07-30

`a290afe` is the initial commit — 7 generators, `riverlib`, HQ, and `RIVER_SPEC.md` already
mature. History before that point was not under version control and is not recoverable; the
design rationale that survived lives in `RIVER_SPEC.md` and in the calibration comments.
