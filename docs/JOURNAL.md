# Journal

Append-only session memory. Newest entry at the top. Each entry: what changed, why, and
what's still open. Written for a future session that has no chat history — assume it knows
nothing except this file and the code.

Keep entries short. Detail that belongs next to code goes in a code comment; detail that
belongs to a commit goes in the commit message. This file is for *state and intent*.

---

## 2026-08-13 — Harpeth River added (13 rivers)

Hwy 100 down to the Cumberland confluence — a Tennessee State Scenic River, no dam anywhere on
it, canoe/kayak water through Harpeth River State Park. Built on the same routing engine as the
Duck and Buffalo.

**Channel and accesses.** 55.2 river miles traced as the shortest path along the OSM river graph
from the Hwy 100 access to the Harpeth River Bridge at the mouth (135 points). TWRA maps **no**
Harpeth accesses at all, so the access list is the Harpeth River State Park units placed off that
centreline: Hwy 100 · Harpeth River Park · Newsom Station · Hidden Lake · Kingston Springs ·
Gossett Tract · **Narrows of the Harpeth** · Harpeth River Bridge.

**Routing measured** (`analysis/duck_routing.py`, 180 days, 4,303 aligned hours): Bellevue
(03433500, 409 mi²) → Kingston Springs (03434500, 683 mi²), **5 h lag, r = 0.878, gain ×1.48**,
27.1 river miles → 5.4 mph. Bellevue sits at the top of the reach, so it is the earliest reading
on the river.

**Two honest limits, both surfaced rather than hidden:**

1. **NWPS publishes no forecast anywhere on the Harpeth** — none of its seven gauges has a
   forecast point. The page runs on USGS observations and says "observed, not forecast".
2. **The 5 h lag is inside the horizon where persistence wins** (routing only beats "assume the
   river stays put" beyond ~12 h). So the routed forecast is *suppressed entirely* on this river.
   The guard was already there; this is the first river to exercise it.

Its transfer function also only beats a constant gain by **3%** (against the Duck's 43%), so the
QC check that demanded a 20% margin became a warning — that margin was a Duck/Buffalo
observation, not a law, and 3% is the honest finding that the model choice barely matters here.

**The new page immediately exposed a bug in an existing one.** A check that no page may mention
another river's place names caught the **Buffalo** shipping Duck ramps — Chickasaw, Williamsport,
Leatherwood, Littlelot — in its flow timer, because that list had never been re-derived when the
Buffalo was cloned from the Duck. Both rivers also defaulted to **jet boat** while their own
`WATER_MODEL` says "too skinny for a jet". Fixed both, and there are now checks for foreign place
names, for claiming an NWPS forecast that does not exist, and that the default craft is one the
river's water model actually allows.

**A QC check that was wrong.** `qc_caney.mjs` asserted the wade/boat call rises monotonically
with flow **across different accesses at one hour**. That is not an invariant: `condp` uses a
per-access reference depth, so Stonewall (15 mi down, wide) at 522 cfs genuinely can be too deep
to wade while Betty's Island (9 mi) at 596 cfs is fine. Rewritten as the true invariant — per
place, more water must never read as more wadeable.

QC: 256 river + 411 Caney.

---

## 2026-08-12 — Clarity is the Smith Fork's doing, not the sky's

A guide's account of a bad day supplied a better clarity model than the one shipped:

> "None of the river was brown until the confluence with Smith Fork Creek. That's typically the
> way it is. Most of the creeks and tributaries above that area are not large enough to change
> the colour of the entire river. Sometimes the Smith Fork flows with more force than the Caney
> Fork! When that happens the fishing is going to be tough."

The page was inferring clarity from **rainfall**. Smith Fork has its own live USGS gauge
(03424730), so this is measurable rather than inferred. Two facts make it work.

**WHERE.** The confluence is an exact shared node in the OSM channel geometry at
36.13968,-85.86988 → **mfd 11.08**, between Betty's Island (9.0) and Stonewall (15.0). Seven of
the ten accesses and *every* trout hole sit above it and stay clear whatever the creek does.

**HOW MUCH.** 365 days of gauge record: p10 24.5 · p50 65.9 · p75 163 · p90 318 · p95 543 ·
p99 1550 · max 5910. The guide's clear-water figure was "24 cfs" and his chocolate-milk day was
"over 1300" — **the p10 baseline and a p95–p99 event.** Those two anchor the curve.

Two conditions must both hold, which is the part rainfall could never capture:

```
sed  = log-scaled load between 50 cfs (clear) and 1200 cfs (chocolate milk)
frac = smith / (smith + caney_at_confluence)        <- the release DILUTES it
mud  = sed * clamp(frac / 0.5)
```

Backtested over the year: **63.4% clear · 16.9% some colour · 9.0% stained · 10.7% chocolate
milk** — brown about one day in nine, which fits a guide being caught out by it. And the dilution
term reproduces his insight directly: 26 Feb at 1,630 cfs reads chocolate milk at minimum flow
but only *stained* under two units.

Surfaced as a banner that shows in **every** state, because "the creek is fine" is worth knowing
before you drive. Access popups say which side of the confluence each ramp is on. Day scoring
uses the live creek for today and falls back to rainfall for later days — there is no Smith Fork
forecast, and the breakdown says so rather than implying a measurement.

**A test caught me overstating it.** The banner claimed the confluence split leaves "the whole
wade reach" clear. It does not: **Stonewall is a wade access and it is below the confluence.** The
copy now names the clear water precisely (Long Branch → Betty's Island, and every trout hole) and
explicitly includes the wading at Stonewall in the coloured reach. There is now a check that the
page never makes the broader claim again.

---

## 2026-08-10 (5) — TWRA site detail on the access pins

Extended `analysis/twra_access.json` from coordinates to the **full published record** per site:
ramp surface and lane count, hull-size limit, parking and trailer-space bands, road/parking
surface, restroom, courtesy dock, fishing pier, accessible parking, lighting, camping, gas, bait,
fee, sunrise-to-sunset restriction, owner/manager, and TWRA's own driving directions. The source
uses Access-style booleans (`-1` true / `0` false); those are decoded to real booleans on the way
in so nothing downstream has to know that.

`riverlib.twra_for(lat, lon, water_key)` attaches the record and `accessPopup` renders it under a
green **TWRA** rule, visually separate from our own notes — these are the state's record for the
site, not our read of it. Wired into every generator. **11 of 49 accesses** now carry one; the
rest are county, private or informal sites TWRA does not map.

**The matching radius was the sharp edge.** At 400 m the I-40 Welcome Center sat 218 m from the
Betty's Island ramp and claimed its record — one site's ramp and parking shown under another's
name. Every genuine match is within 61 m, so the radius is now 150 m. Williamsport is still
claimed by two *pages*, which is correct: it is the shared boundary between the Upper and Middle
Duck. QC asserts a site is never claimed twice on one page.

**Three inconsistencies the data exposed:**

1. Our Riverside note said "canoe/kayak; Maury Co. lists it technically closed" while TWRA lists a
   **concrete ramp for 26 ft boats**. Two different places: the Riverside Dam canoe slide and
   TWRA's Riverside Access Area just below it. The note now distinguishes them and the access
   carries `ramp`.
2. Popups printed **"river mile 19"** for Happy Hollow — the retired `rm` basis — while the
   planner calls the same spot 6.0 mi below the dam. Popups now prefer `mfd`.
3. `owner` is frequently the literal string "TWRA", which rendered as "TWRA · TWRA"; and TWRA
   stores parking spaces and trailer spaces as separate fields that often carry the same bucket,
   which read as two facts. Both collapsed.

Records with nothing but a name are dropped rather than rendering an empty section — TWRA carries
several canoe accesses (LINDEN) with no ramp, parking or facility data at all.

QC is now **159 checks**.

---

## 2026-08-10 (4) — Cross-referenced every access against the TWRA access map

Pulled the official TWRA Boating & Fishing Access layer (`tnmap.tn.gov/arcgis/rest/services/
ENVIRONMENTAL/TWRA/MapServer/1`) — **982 georeferenced sites statewide**, 57 on the waters this
tool covers. Saved to `analysis/twra_access.json` so it is reviewable and testable offline.

**Where TWRA lists a site, our pins were wrong — and the Caney was the worst.**

Measured along the channel from Long Branch against each access's own `mfd`:

```
our pins        Happy Hollow  +1.2 mi     Betty's Island  +2.2 mi     (disagree by 1.0)
TWRA's          Happy Hollow  -0.8 mi     Betty's Island  -0.8 mi     (agree exactly)
```

A **constant** −0.8 offset is just the polyline's datum; a *drifting* +1.2/+2.2 is error. TWRA's
coordinates land precisely on the model's mfd of 6.0 and 9.0. Our hand-placed pins were sitting
1–2 miles downstream of the actual ramps. `mfd` itself is unchanged, so the flow model is
untouched — this was a navigation bug, not a model bug.

Corrected from TWRA: Caney Happy Hollow + Betty's Island; Duck Riverside (1.8 km off),
Williamsport (3.0 km), Centerville ramp (1.4 km); Buffalo Linden (0.8 km). Chickasaw Trace
already agreed to 11 m, as did Old Dam Ford (10 m), Veto Access (40 m), Cleece's Ferry (61 m) and
the Percy Priest tailwater (5 m) — where names match, TWRA and our data agree tightly.

**Not in TWRA's layer, correctly left alone:** Littlelot, Stonewall, Lancaster, Buffalo Valley,
the I-40 Welcome Center, Leatherwood (private). These are county, private or informal accesses;
absence from the state layer is not evidence of a bad coordinate.

**The Duck channel had to be retraced.** Its polyline was hand-drawn THROUGH our own access
coordinates, so once TWRA's positions replaced them the drawn channel no longer passed the
ramps (Williamsport ended up 3 km off its own river). Rebuilt as the shortest path along the
OSM river graph from the Riverside ramp to the Centerville ramp — 111 points, 56.8 mi against a
59.8-river-mile reach — and the three section slices re-cut from it.

**QC** is now 126 checks. The TWRA-matched pins are guarded individually: if any of the six
corrected coordinates drifts more than 250 m from TWRA's published position again, it fails.

---

## 2026-08-10 (later still) — Map pins audited; HQ and the river pages made to agree

**1. Access-point coordinates.** Audited all 50 pins against the real OSM river centrelines
(1,173 river ways, 113k segments). The Caney pins are excellent (0–70 m). **The Buffalo ones I
shipped were town centres** — Lobelville 1,236 m and Topsy Bridge 1,099 m from the water, so the
Google Maps link dropped you in the middle of town rather than at the launch.

Fixed by intersecting OSM highway geometry with the OSM Buffalo centreline: 19 road bridges
cross the river, and the named accesses match them exactly (Topsy Road, US 412/SR 100, SR 13).
All Buffalo pins are now ≤ 99 m from the channel. The mapped channel itself was redrawn the same
way — it had been a line through those town centres — by chaining the two OSM `waterway=river`
ways end-to-end: 48.7 mi, terminating exactly at the mouth.

Topsy Bridge was dropped: OSM does not name the river above it, so it cannot be placed on the
channel, and the Buffalo above Flat Woods only floats Nov–Aug anyway. The reach now starts at
Flat Woods, where the gauge is.

**A correction to the audit criterion itself.** My first pass flagged any pin >120 m from the
centreline. That is wrong for navigation: **a Google Maps pin should land on the ramp you drive
to, not mid-river.** Parking legitimately sits off the water. Snapping everything to the
centreline would have made the links worse — pins in the river are not drivable. Only the
town-centroid errors were genuinely broken, and the QC threshold is now 800 m, which catches
those without false-flagging bank parking.

**2. HQ vs the river pages — they disagreed, systematically.**

- HQ showed **all three Duck sections at 1,580 cfs** while their pages read 0.48 / 0.89 / 1.30
  kcfs. The HQ day-state used the Centerville gauge for every section — the exact bug the split
  existed to fix, leaking into the board. Now scaled per reach.
- HQ's week **persisted today's grade for seven days** even on rivers with a real multi-day flow
  forecast. `build_week()` already accepted a per-day list; the Duck, Buffalo, Cumberland and
  Caney were all passing a scalar. Now they pass their own outlook.
- **The moon term was one-sided**: `+0.5 / +0.2 / +0.0`, never negative. Its expected value is
  strictly positive, so HQ read a full grade above the pages on **24 of 24** day-grades. Grade
  bands are 0.8 wide and Fair (1.3) + 0.5 = 1.8 lands in Good, so the moon alone promoted a day.
  Now zero-mean and bounded to ±0.3.
- Even then HQ contradicted Caney, because it re-applied a weather penalty on top of a page grade
  that **already scores weather at 25 of 100 points** — double-counting. The rule is now
  coherent: a per-day list is the river's own verdict and is shown verbatim; the weather/moon
  blend applies only to the scalar case, where the river has no forecast and the nudge is the
  only forward information there is.

**Result: 0 of 30 day-grades differ**, down from 24 of 30.

**QC.** `qc_rivers.py` grew to 114 checks: HQ must agree with every river page's own outlook,
the moon term must stay zero-mean (a regression guard — the offset returns the moment it goes
one-sided again), and no access pin may sit more than 800 m from its river.

Also fixed while in there: `build_week()` raised `IndexError` on a per-day base shorter than 7
days (NWPS publishes 6), which took the whole generator down; the last forecast day now persists.

---

## 2026-08-10 (later) — Backtested the routing engine. The model I shipped was the worst one.

Built `analysis/backtest_route.py`: fit on the first 70% of the record, score only on the last
30%, and compare every candidate against **persistence** (assume the river stays where it is).
Beating persistence is the whole bar — if a forecast cannot, it is decoration.

**A. TEMPORAL — Duck, Columbia → Centerville, 14 h ahead, held-out:**

```
model                     MAE    RMSE    bias      NSE
lag + power law         477.0   861.0  -151.7   0.8121   BEATS persistence
lag + linear fit        535.5  1003.7   -50.5   0.7446   BEATS persistence
lag + FIR kernel (30h)  692.1  1161.8  -104.8   0.6653   BEATS persistence
persistence             561.7  1206.8    -2.3   0.6308
lag + CONST GAIN        835.0  1754.0  +345.3   0.2201   loses to persistence
```

**The constant gain is what I shipped**, and it is the worst of five candidates — NSE 0.22, a
+345 cfs bias, and it loses to doing nothing at every horizon. Replaced with the fitted transfer,
read from `duck_routing.json` rather than hardcoded:

| River | transfer | held-out MAE | vs const gain |
|---|---|---|---|
| Duck | power law | 475 cfs | 836 → **43% better** |
| Buffalo | linear | 169 cfs | 355 → **52% better** |

**Persistence wins below ~12 h.** At h=6 nothing beats it (NSE 0.915). So the routed forecast is
only offered at the measured lag and the page says outright that it is not a short-range
forecast. `useful_from_h: 12` is now a published constant.

**B. SPATIAL — held-out test of the ungauged-reach interpolation.** The middle Duck has no gauge,
so its level is interpolated. Normally untestable — but **Columbia itself sits between two
gauges** (Milltown RM 179, Centerville RM 74), so it can be hidden and predicted:

```
method                      MAE   RMSE    bias      NSE
linear in river mile      333.2  510.2  +210.2   0.7850   <- deployed
linear in drainage area   193.5  477.7   -13.2   0.8115
log blend, lag-aware      217.2  459.5  -148.3   0.8256
```

Distance-based interpolation ran **+210 cfs biased**. Area-based is essentially unbiased.

**A negative result worth recording.** My first instinct was to deploy area-fraction and claim a
42% win. It would have been a **no-op**: only two gauges bracket Columbia→Centerville, so the
area curve there is a straight line by construction and area-fraction *equals* distance-fraction.
The measured improvement came from the wider Milltown→Centerville span where accrual genuinely
changes (6.4 vs 14.2 mi²/mi). Checked before shipping instead of after.

The fix came from finding **four USGS mainstem points with published drainage areas inside the
reach** (RM 120.3 = 1,429 mi², 104.9 = 1,696, 101.7 = 1,700, 98.8 = 1,707). Accrual runs 17.0,
17.3, **1.8**, 13.8 mi²/mi — genuinely non-uniform, so area-fraction ≠ distance-fraction after
all. Channel positions are now derived from that profile; the real correction is Williamsport,
0.345 → 0.396. Those sites publish no flow, so this is physically grounded but not directly
validated in-reach — stated as such in the code.

**QC.** `test/qc_rivers.py` is new — 101 checks. The four new pages shipped with none. It asserts
the routing constants are sane, that the deployed transfer is the backtested winner (a check that
fails if anyone reverts to a constant gain), that the winner really has the lowest held-out
error, that the three Duck sections report *different* water increasing downstream, and that the
ungauged reach admits it has no gauge. Wired into `test/run.sh`.

---

## 2026-08-10 — Duck split into three sections; Buffalo River added

**Twelve river pages now, up from nine.** `duck` is retired and replaced by `duckup` / `duckmid`
/ `ducklow`; `buffalo` is new. `duck.py` emits all three Duck pages from ONE run (one fetch, one
engine) so a fix cannot land on one section and miss the others.

**Why split.** The single Duck page quoted the Centerville gauge for 59 miles of river. Measured
today, that reach is not one river:

```
Riverside  0.40 kcfs   Chickasaw 0.44   Williamsport 0.72
Leatherwood 1.14       Littlelot 1.25   Centerville  1.60
```

Quoting Centerville on the upper river overstated it by ~4x. Upper now grades Fair (skinny)
while Lower grades Good — on the same day, from the same data.

**The routing engine (`analysis/duck_routing.py`) — measured, not assumed.** Cross-correlating
the two gauges over 120 days:

| River | Reach | Lag | r | Gain | n |
|---|---|---|---|---|---|
| Duck | Columbia RM133.3 → Centerville RM74.0, 59.3 mi | **14 h** | 0.899 | x2.33 median | 2,868 h |
| Buffalo | Flat Woods → Lobelville, 28 mi | **22 h** | 0.973 | x1.46 median | 2,869 h |

This matters because **NWPS forecasts Centerville (CNVT1) and nothing upstream**. So the Columbia
gauge is a 14-hour head start on the lower river, and the only forward signal the upper and
middle reaches have. Each page says which of the three it is living on:

- **Upper** — Columbia gauge IS this water, and runs 14 h ahead of everything below it
- **Middle** — no gauge at all; interpolated, and says so
- **Lower** — the only reach with a published NWPS forecast

**Sections split at JET-BOAT ramps**, not paddler accesses — you cannot end a jet trip at a
canoe slide. Boundaries: Riverside 133.5 → Williamsport 113.9 → Leatherwood 95.0 → Centerville
73.7 (19.6 / 18.9 / 21.3 mi). The user asked for ~18/15/7; the real motorized ramps fall where
they fall, and the ramps won.

**Buffalo River** is the same engine on a free-flowing State Scenic River — no dam anywhere, so
nothing buffers rain. Flat Woods (03604000) is the only gauge on either river carrying water
temperature.

**Access data** came from the TWRA/paddler access table (43 points, RM 265.4→11.7, with owner
and motorized/canoe type per site) — extracted from a PDF, not guessed.

**Known soft spots, all flagged in code:**

- The Buffalo's wade thresholds are NOT a field-measurement fit — no USGS wading measurements
  were available for 03604000. Scaled from the Duck's curve; `WATER_MODEL["buffalo"]["src"]`
  says so outright.
- Buffalo river miles are approximate; TWRA publishes none for that river.
- The Middle Duck has no gauge. Everything on it is interpolated and the page says so.

**A test that claimed to be derived was hardcoded.** `test/browser.mjs` carried
`const RIVERS = [...]` with the comment "derived, never hardcoded" on the very next line. It
broke the moment the registry changed — exactly as `verify.py`'s `RIVER_FILES` did once before.
It now reads the registry out of `riverlib.py`. Two more Caney checks were data-fragile rather
than wrong (a float that only crosses midnight at low flow; a craft check keyed on "no release
scheduled" when the water was still 900 cfs from yesterday's) and now assert the rule instead of
the day.

---

## 2026-08-05 — Backtested the timing. The model was right; I was wrong.

I had recorded a "~1–2 h early bias at Stonewall" as the next thing worth backtesting. Backtested
it over 120 days. **There is no early bias.**

```
window: 120 days · 2,702 aligned hourly points · gauge mean 1,848 cfs

A. MAGNITUDE   bias +29  MAE 252  RMSE 345  r 0.978  NSE 0.956
               gauge peak 7,725 vs model peak 7,567  (98% of observed)
B. TIMING      model -> gauge  best lag 0 h (r=0.978)      <- timing is correct
               release -> gauge best lag 7 h  [centroid 7.8 h]
C. PER-EVENT   111 events · rise lag median 6 h (range 0-13)  [2.5-mph rule says 6 h]
               peak lag median 10 h  [kernel centroid 7.8 h]
D. KERNEL      empirical vs deployed, near-identical; implied baseflow 214 (model 205)
               steady-state gain 1.01 (model 1.00) · centroid 7.97 (model 7.76)
```

Cross-correlation of model against gauge peaks at **zero lag**. `WATER_MPH=2.5` is confirmed
independently a second time: 111 events, median rise lag 6 h, and 15 mi / 2.5 mph = 6 h.

**Where my wrong conclusion came from.** Two things, neither of them a model defect:

1. The 886-cfs live discrepancy was a **stale-data artifact**. CWMS was 500ing, so the build
   fell back to a release schedule cached four days earlier. Rebuilt against live CWMS the same
   hour: gauge 723 vs model 626, a 97-cfs gap.
2. The diurnal comparison behind the "1–2 h early" claim was not apples-to-apples — the 14-day
   climatology was mostly 2U 12pm–8pm days against a 1U 1pm–7pm forecast.

The one real residual: **modelled peaks land ~2 h before observed peaks** (peak lag median 10 h
vs centroid 7.8 h) while the leading edge is exactly right. Not worth chasing — the page's
user-facing timing is arrival, not peak, and shifting the kernel to fix the peak would break the
edge. Per-event rise lag spreads 0–13 h, which is why `ARRIVAL_STAGES` publishes bands.

**Conclusion: change nothing in the model.** Recorded so the next session does not re-litigate it.

**Three bugs found doing it:**

1. `backtest_flow.py` carried a hand-copied "verbatim from briefing.py" constants block that had
   gone stale: `WATER_MPH = 3.0` after `2c2bc2c` overrode it to 2.5, and `375` baseflow labels
   after `b2115c3` moved it to 205. **The backtest was grading a model that is not deployed.**
   It now READS the constants out of `briefing.py` by regex; the logic stays an independent
   reimplementation (briefing.py is still never imported) but the numbers are authoritative.
2. **CWMS 500s on a history-only window** for `CETT1-CENTER_HILL...man-rev` — `begin=-90d,
   end=now` fails at every chunk size, `begin=-120d, end=+1d` returns 2,774 hours. Production
   never hit this because it always asks for the forecast too. Ask past the present.
3. The cached-schedule warning said only "⚠ cached schedule (USACE API down)" — a 2-hour-old
   cache and a 4-day-old one read identically. It now states the age, and the timed plan carries
   its own banner, because every clock time in it is computed FROM that schedule.

---

## 2026-08-01 (later still) — The plan now solves for the launch time

"Why is every daily recommendation essentially *launch at first light at Stonewall and run up*?"
Because it was one hardcoded sentence. It never looked at the release. With a noon release it
was telling you to sit at the top of the river for six hours.

**The powerboat plan now solves the intercept.** The edge leaves the dam at T and walks down at
`WATER_MPH`; a boat leaves `frm` and runs up at `UP_MPH`. To be at spot s when the edge arrives:

```
launch_by(s) = T + mfd(s)/WATER_MPH - (mfd(frm) - mfd(s))/UP_MPH
```

For a noon release that is **10:55am at Stonewall**, not 5:53am — and 11:55am for a 1pm release,
so it moves with the schedule. The plan also names the saving from putting in higher (Betty's
Island buys an hour), and the first-light step now reports the real morning split (upper reach
~509 cfs while Stonewall still carries last night's 1,145) instead of calling 1,912 cfs "low".

**The float plan searches put-in times** so the rise catches you in the middle of the reach
rather than at the take-out — 11:30am today, 10:30am Monday. `float_meet()` steps the boat at
its local drift speed while the edge walks down, and returns where they meet.

**Two constants moved out of the page JS into Python** (`UP_MPH`, `DRIFT_C`), which the
no-hardcoded-calibrated-numbers invariant already required and which Python needed anyway — it
could not simulate a boat at all without them.

**`DATA.itinerary` was dead payload.** Never referenced by the page. Worse, both QC harnesses
"checked" it: `qc_caney.py` asserted `len(itinerary)==7`, which passed only because the old
fixed plan happened to emit seven steps, and `qc_caney.mjs` indexed the STEP LIST by day and
read `.short`/`.long` off it, so that field was always `''`. Two checks, neither testing
anything. Removed; replaced with per-craft plan checks that assert the intercept arithmetic
actually holds and that the launch time varies when the release schedule does.

**Open:** ~~the live warn `model 886 cfs off the live gauge` is a ~1–2 h early bias~~ — **wrong,
see the 2026-08-05 entry above.** Backtested over 120 days: timing is correct at zero lag. That
warn was a stale-cache artifact, not a model defect.

---

## 2026-08-01 (later) — Timed plan rebuilt per craft; wade scoring corrected

**Correction to the entry below.** That entry claims "dawn is the worst time to wade Caney".
That is true **at Stonewall** and false for the rest of the river, and the wade window I shipped
with it was wrong. `_sc_window` measured wadeability at Stonewall alone (mfd 15) and reported it
as the day's window. Modelled hour by hour, per access:

```
                 mfd   6a  7a  8a  9a 10a 11a 12p  1p  2p  3p  4p  5p
Long Branch      0.0    w   w   w   w   w   w   w   .   .   .   .   .
Lancaster        2.5    w   w   w   w   w   w   w   ~   .   .   .   .
Happy Hollow     6.0    w   w   w   w   w   w   w   w   ~   .   .   .
Betty's Island   9.0    w   w   w   w   w   w   w   w   w   ~   .   .
Stonewall       15.0    .   .   .   ~   ~   ~   ~   w   w   w   ~   .
```

The upper bars wade from first light; Stonewall only opens as the previous evening's release
finally clears it. Wadeability is a property of a **place**, not of the river. Wade Level and
Window now read the whole reach (`WADE_SPOTS`, `wade_open()`), and the window names where as
well as when. The 14-day gauge climatology in the entry below is still correct — it is a
Stonewall gauge, so it only ever described Stonewall.

**The timed plan was one narrative that assumed a powerboat and then told you to wade.** Every
day opened "launch at Stonewall and run up" (powerboat), continued "wade the bars" (on foot),
and closed "hold on the rise on the oars" (drift boat) — three craft in one plan, none of them
the one selected. It is now written per craft off one organising fact, that the bump walks
downstream at ~2.5 mph:

- **wade** — retreat downstream ahead of the rise; each spot closing means *move down*, not go home
- **power** — run up and meet the rise, then ride it back down
- **float** — put in above it and let it catch you

Also added: a thunderstorm step that sorts ahead of fishing advice in its hour and a matching
"storms should be through" step; the falling limb (when the tail passes and the river drops out);
all release blocks in a day rather than only the first; `DRIFT_SWEET` as one named constant
instead of "1,500–3,000" retyped into prose.

**Two bugs found on the way, both pre-existing:**

1. `gen_windows()` closed a still-open run *at its own start timestamp*, so whenever the last
   forecast sample was generating it emitted a zero-length release window. The timed plan would
   have generated arrival steps for a release with no duration. Now closes an hour later (each
   sample stands for the hour it opens) and degenerate windows are dropped.
2. `verify.py` divided all three Cumberland tailraces by 6,500 cfs/unit. Old Hickory is 6,500,
   Cheatham 9,000, Cordell Hull 8,000 — so Cordell's perfectly consistent "2 units / 16,330 cfs"
   (16,330/8,000 = 2.04) failed. Now reads each river's own published `relUnit`.

**A test encoded the wrong conclusion.** "wade verdict does not promise dawn on a generating day"
was written from the Stonewall-only finding and started failing once the reach-aware model
correctly said dawn. Replaced with the weaker, true invariant: the verdict must agree with the
computed window, whichever way it falls. Worth remembering that a test written in the same
breath as a conclusion inherits its errors.

**Open:** `DRIFT_SWEET` (1,500–3,000 cfs) is guide practice with no measurement behind it —
flagged in the code, unlike `WATER_MPH` and `CALIB_BASEFLOW` which are backtested.

---

## 2026-08-01 — Day scoring reweighted, and scored per craft

Started from "why is Tue labelled Tough?" The breakdown built to answer that immediately
exposed the real problem: **the moon carried 40 of ~100 points.** Mon-Fri had identical
generation and graded Fair / Tough / Tough / Fair / Good purely on moon phase and rain.

**New weighting (each craft sums to 100):**

| | Level | Clarity | Weather | Window | Moon |
|---|---|---|---|---|---|
| Wade | 35 | 20 | 25 | 10 | 10 |
| Float | 35 | 18 | 27 | 10 | 10 |
| Powerboat | 35 | 15 | 30 | 10 | 10 |

Moon 40 -> 10. Weather is now dominated by a **thunderstorm gate** (WMO codes 95/96/99, read
over fishing hours only) that caps the term at 0.15 rather than deducting from it — lightning
is the one condition on this page that can actually kill you. Weather is weighted higher from a
boat (exposed, slower to shore), clarity higher when wading (sight-fishing).

**Scoring is now per craft, because one number cannot answer the question.** A no-generation day
is a perfect wade day and a poor powerboat day. Each day is scored three times and the outlook
toggles; the toggle shares the `craft` global with the planner, so there is one craft selection
for the page. Persisted to localStorage.

**Two inputs were wrong and are now right:**

1. **Clarity ran off the rain forecast — for TOMORROW.** Caney is a bottom-release tailwater:
   water leaving the dam is always clear, so colour comes from tributary inflow below it, which
   responds to rain that has *already fallen*. Now driven by 3-day antecedent rain
   (`past_days=2`), recency-weighted. One vocabulary page-wide; the fly box is keyed on it.

2. **"Wade dawn to the bump" was backwards.** The verdict assumed a dawn start instead of using
   the window the model had already computed. Measured at Stonewall over 14 days (USGS
   03424860, hourly medians), P(wadeable, <=600 cfs):

   ```
   00:00-09:00   0%      13:00  61%      17:00  71%
   10:00        11%      14:00  93%      18:00  46%
   11:00        21%      15:00  93%      19:00   7%
   12:00        36%      16:00  93%      20:00+  0%
   ```

   On a daily-peaking schedule the previous evening's release is still passing Stonewall at
   first light. **Dawn is the worst time to wade Caney; the window is a midday-to-afternoon
   lull.** Verdicts now name the computed window ("Wade the 12pm-3pm lull").

**Open / known limits:**

- The model's daily minimum runs ~60 cfs above the gauge (model 468-536 vs observed 399-522,
  median 442) — inside the observed spread, but it biases wade Level slightly low.
- The model's wade window runs ~1-2 h earlier than the 14-day gauge climatology suggests. Not
  chased here: the comparison is not apples-to-apples (the climatology is mostly 2U 12pm-8pm
  days, the forecast is 1U 1pm-7pm) and it is the flow model's existing timing uncertainty,
  not a scoring bug. Worth a proper backtest of window timing against matched schedules.
- Moon at 10 is a judgement, not a measurement — the only weight here with no evidence behind
  it. The trip log captures predictions; after a season it could be fitted instead of guessed.
- Grade bands moved with the model (Prime >=85 / Good >=72 / Fair >=58). Not calibrated against
  outcomes, just against the new score distribution.

**Tests:** scoring curves are probed directly in `qc_caney.py` (extracted from `briefing.py` by
regex so no network is needed) — craft direction, monotonicity, bounds, the storm gate. The
browser layer asserts the weights themselves (moon minor, level heaviest, weights differ by
craft), that a storm day never grades Prime, that the toggle moves both views, and that the
wade verdict never contradicts its own window. 207 static + full runtime.

---

## 2026-07-31 — Cumberland system: 3 tailraces, 9 rivers

Started from "where's my generation schedule for cumberland?" The answer was that there are
**two** Cumberland pages and they were very different: `cumberland` (KY / Wolf Creek) had a
generation schedule; `cumbnash` (Nashville) did not, despite being driven entirely by Old
Hickory releases. Fixed that, then added the two missing mainstem tailraces.

**Now covering all three Middle TN Cumberland tailraces:** Nashville (Old Hickory),
Cheatham, Cordell Hull. Same warmwater big-river model — navigable pool, depth stable,
**current** is the variable.

**The surprise was how little live gauge data exists.**

| Page | Release (LRN) | Gauge |
|---|---|---|
| `cumbnash` | `OHIT1-OLD_HICKORY` | USGS 03431500, healthy |
| `cheatham` | `ASHT1-CHEATHAM` | **none** — 03435000 has published nothing real-time in 30+ days |
| `cordell` | `COHT1-CORDELL_HULL` | **none** — no active gauge on the reach |

Where there is no gauge, the **release IS the hydrograph** and the footer says so. The QA gate
caught the dead gauge on the first build (`flow None`), which is exactly its job.

**Things worth not re-deriving:**
- **Location IDs are traps.** `OHHT1` = Lock and Dam, `OHIT1` = Tailwater (identical values,
  verified, but tailwater matches Center Hill's `CETT1` convention). `COHT1` carries Cordell
  Hull's *hourly* series; `CORT1` is its tailwater but publishes daily only. Always check
  `cwms-data/locations` before wiring a dam.
- **All LRN dams publish identically**: `<CODE>-<DAM>.Flow.Ave.1Hour.1Hour.man-rev` for actuals
  and `<Dam Name> Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast` for ~120 h of forecast.
- Release plumbing now lives in `riverlib` (`cwms_series`, `dam_release`, `release_at`,
  `gen_blocks`, `release_events`, `gen_days`) instead of a copy per generator.

**Deliberate restraints:** unit counts are labelled *estimates* (inferred from release steps,
never fitted to a gauge like Caney's constants), and **no arrival times** on any of the three —
these are impoundments, so a release raises current through a pool rather than sending a
wading front downstream. A countdown there would be fiction.

**⚠️ Open thread — access points.** `cheatham` and `cordell` carry exactly ONE access point
each: the USACE tailwater location, which is authoritative. Every other ramp on those reaches
is an unnamed OSM slipway with no official name, owner, or river mile, and several near Cordell
Hull sit on the **lake above the dam**. Omitted rather than guessed, per §2. USACE's own site
(`lrn.usace.army.mil`) has a TLS certificate misconfiguration and could not be fetched.
**This is the one place local knowledge beats research** — the ramps need naming from a
verified source before these two pages can tell you where to launch.

**Also:** switcher tab count and HQ card count in the QA suite now derive from the registry
instead of being hardcoded at 8 and 7, so adding a river no longer breaks the tests by design.

---

## 2026-07-30 (evening) — R1–R5 built, deployed, live

**The tool is on the internet: https://caney.pages.dev**
*(Corrected 2026-07-31: an earlier entry named `master.caney.pages.dev`. That branch alias
stopped being repointed after the first few deploys — recent wrangler runs print only a hash
URL, no `Deployment alias URL` line — while production started tracking every run. Use the
bare `caney.pages.dev`.)*
Cloudflare Pages, HTTPS, private repo, rebuilt hourly by `.github/workflows/deploy.yml`. All five tasks from the CEO review are shipped.

- **R1 — hosting.** `build.sh` is now the single source of the generator list and order
  (`hq.py` last); `test/run.sh` calls it. Deploy is gated on `verify.py`, so a build failing
  static QA is never published. `cache_dam.json` is persisted between CI runs.
- **R2 — build stamp.** Every page states how old its data is, injected via `render()` into
  `<head>` so no page can forget. Quiet / amber at 3 h / filled at 12 h, plus a distinct
  state when the device clock runs behind the build.
- **R3 — arrival strip.** "Water reaches Happy Hollow at 4:24 PM · 2h 16m from now", with a
  one-tap `.ics` + `VALARM` that hands the reminder to the phone's own calendar. Caney only.
- **R4 — the trip log now records what the tool predicted**, plus a "water arrived just now"
  stamp and the delta. This is the field backtest and the evidence engine.
- **R5 — `escUrl()`** scheme allowlist so a `javascript:` URL cannot reach an `href`.

**Two bugs found by building, both worth remembering.**

1. **The first CI deploy failed and it was the review's Finding 2.2 exactly.** Open-Meteo's
   TLS handshake timed out for duck and stones on the runner; both generators caught it,
   printed `wx warn:`, and built the page anyway with no weather, producing a `week[]` the HQ
   status contract rejects. Fixed by moving retry logic into `riverlib.get()` (2 attempts,
   2s/4s backoff, re-raise on exhaustion) and having all seven generators delegate to it
   instead of each carrying its own near-identical `get()`.
2. **`actions/cache` saves in a post-step, which is skipped when an earlier step fails** — so
   that failure discarded a good release forecast. Split into `cache/restore` + `cache/save`
   with `if: always()`.

**And one caught by writing a test:** the first cut of `arrivalPick` checked "upcoming"
before "arrived", so standing below the dam at 1pm after a 6–9am release it would announce
the 8pm arrival while you stood in rising water. Arrived wins now. Water also stays "here"
until `release_end + travel`, not merely until the front arrives.

**Testing gained real capability.** `browser.mjs` now drives `Date.now` (staleness, skew) and
exercises `window.__arrivalPick` with synthetic split-generation days — the clock-injectable
testing the review said was missing, without needing a fixture build. `test/smoke.mjs` checks
the live HTTPS site: 200, secure context, stamp present, zero JS errors, at phone viewport.
**Secure context confirmed**, which everything deferred behind GPS depends on.

**Open threads.**
1. **Fish with it and log trips.** R4's prediction-vs-actual deltas are what decide whether
   2.5 mph is right and whether any of the 13 deferred items are worth building. Nothing
   deferred should be un-deferred before that data exists.
2. ~~Runtime auto-calibration may interact with arrival math~~ — **checked, it does not.**
   `briefing.py:116-131` nudges `baseflow` against the live Stonewall gauge using only hours
   below 700 cfs (baseflow-dominated), then applies it constant along the reach. It adjusts
   flow *magnitude*; `WATER_MPH` and `travel_h` are untouched, so arrival times are unaffected.
   Working as designed, no action needed.
3. `briefing.py:265` has the same first-window-only bug class the arrival strip fixed: the
   itinerary takes the first `GW` window within 5am–9pm only.
4. `RIVER_SPEC.md` §3 matrix still lists 3 of 7 rivers; line 6 says `briefing.py → index.html`
   but it builds `caney.html`.
5. Cloudflare strips `.html`, so every internal link takes a 308 hop.

---

## 2026-07-30 (later) — CEO review of the mobile/on-water goal; scope cut

**Frame changed.** The active goal is a **robust, customizable personal tool**, not a product.
`PRODUCT_STRATEGY.md` is not the operating frame; `RIVER_SPEC.md:4` ("Personal tool, not a
product") is. Market and pricing work was dropped mid-review at the user's direction.

Ran `/plan-ceo-review` (SELECTIVE EXPANSION). Full artifact:
`~/.gstack/projects/Rhode025-caney/ceo-plans/2026-07-30-mobile-on-water-tool.md`.

**The finding that reframed everything:** most of what looked like a modeling problem is a
delivery problem, but *less* of it than first assumed. An outside-voice review established
that the flow model (`compressed_kernel`, `flow_at`, `dam_at`, `gen_windows`, `ramp_blocks`,
`unit_ct`, baseflow calibration) is **entirely build-time Python**; client JS only interpolates
a precomputed array. So a live client refetch could only ever update `relStart`, not the flow
curve, depth, itinerary, grades, or map front. Combined with two other facts — scheduled web
notifications are impossible on the web, and the riverbank is exactly where there is no signal
— the expensive live-PWA architecture was cut.

**Also found, and load-bearing for any future work:**
- `GEN[].relStart` is the **first release window of the day only** (`briefing.py:381`). Caney
  routinely runs split morning/afternoon generation, so any countdown built on it is wrong all
  afternoon. Use the *next* window relative to real now.
- `frontInfo(t)`'s `t` is `launchMin`, a day-relative planning slider, not wall clock.
- `mfd` exists **only** in Caney's `ACCESS[]`. Zero in the other six generators. `haversine`
  and `travel_h` are Python, not reusable from JS.
- Duck and Elk AL have no dam release, so leading-edge speed is undefined there. E3 is four
  tailwaters, not six rivers; those two get a `—` in the §3 matrix.
- `cache_dam.json` (the last-good release cache behind `dam_stale`) is gitignored, so a cold CI
  runner would silently build an empty forecast during a CWMS outage.
- `esc()` escapes only `& < > "` and does not neutralize a `javascript:` URL at `riverlib.py:587`.
- All four data sources (USGS, Open-Meteo, CWMS, NWPS) plus the Esri tile host send
  `Access-Control-Allow-Origin: *`, so browser-side fetching needs no server. Still true, still
  useful later.

**What to build (5 tasks, R1-R5 in the artifact):** Cloudflare Pages HTTPS hosting with
`cache_dam.json` persisted across CI runs; a build-age banner and version stamp; an arrival
strip ("water reaches Betty's at 2:47 PM, 1h 12m from now") computed from the build-time
schedule and the device clock, targeting the next window, handing off to a **native phone
alarm**; the trip log capturing the tool's own prediction; and a URL scheme allowlist.

**Why a native alarm:** it is the only mechanism that rings with no signal, a locked screen,
and the browser closed, which is all three conditions at the river.

**Open threads.**
1. R1-R5 not started. 13 items deferred with un-defer conditions listed in the artifact.
2. The trip log capturing predictions (R4) is the evidence engine: a season of it decides
   whether live refresh, GPS, and the PWA are worth building at all.
3. `RIVER_SPEC.md` §3 matrix still lists 3 rivers of 7, and line 6 wrongly says
   `briefing.py → index.html` when it builds `caney.html`.
4. `PRODUCT_STRATEGY.md` is now committed but explicitly not the operating frame.

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
