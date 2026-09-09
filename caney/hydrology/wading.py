"""
Wade and float thresholds. §27.

MOVED VERBATIM FROM riverlib.py. Every threshold here is either MEASURED or SOURCED and
carries which — see the per-reach `src` strings, which are USGS field-measurement counts,
not estimates. Do not adjust one without the evidence that moved it and without rewriting
its `src` (CLAUDE.md).

`craft` is user-stated ground truth and OUTRANKS every flow number: no threshold should
ever suggest wading a river you cannot wade. The planner reads this through
`caney/planner/engine.py::_unsafe`, where it is an eligibility GATE and not a score.

riverlib.py imports it back from here (§28).
"""
# ── WADE / FLOAT MODEL ───────────────────────────────────────────────────────
# Every threshold here is either MEASURED or SOURCED, and each carries which.
#
# Two independent evidence streams, combined:
#
# 1. USGS field measurements (analysis/channel_geom.py) — 1,516 physically measured
#    cross-sections across 7 rivers. Each gauging records channel width, area, and
#    HOW the crew worked: wading, or from a boat/bridge/cableway. The flow at which
#    P(wading) crosses 50% is a behavioural wade threshold measured over decades.
# 2. Angler/guide reports, used where stream 1 is confounded or absent.
#
# WHAT THIS MODEL DELIBERATELY DOES NOT DO: state an absolute depth at your ramp.
# Mean depth at a gauge is area/width at a bridge or cableway section, which includes
# the thalweg and is not the water you stand in. Caney measures 3.0 ft mean at 500 cfs
# while USGS crews waded it 75% of the time at 398 cfs, and the Stones gauge reads
# 4.1 ft at 100 cfs because it sits in Cheatham backwater. Absolute depth at the gauge
# does not transfer to the reach. Flow thresholds do.
#
# depth_exp is the measured Leopold-Maddock exponent f in (mean depth ∝ Q^f). It is a
# channel-shape property and DOES transfer: it says how fast the river deepens when
# flow doubles (2^f), which is what "is it coming up fast" actually means.

# "craft" is the set of vessels that actually work on each reach. It is USER-STATED
# ground truth (2026-08-01) and OUTRANKS everything below it: no flow number should ever
# suggest wading a river you cannot wade, or a power boat on water you only kayak. The
# flow thresholds decide WHICH available craft fits today, never whether one exists.
WATER_MODEL = {
    # --- Duck, by section ---------------------------------------------------------------
    # Wade thresholds come from USGS field measurements at 03599500 (Columbia), so they describe
    # the UPPER reach directly. The Duck's flow roughly doubles between Columbia and Centerville
    # (measured median gain x2.33, analysis/duck_routing.py), so the same wadeability downstream
    # takes correspondingly more water. Each section carries the thresholds for its own reach.
    "duckup": {"craft": ["boat", "wade"],
        "craft_why": "jet boat, and genuinely wadeable at summer level up top",
        "wade_ok": 560, "wade_marginal": 915, "no_wade": 1200,
        "depth_exp": 0.633, "fit_r2": 0.87, "n_meas": 255, "substrate": "gravel & ledge",
        "src": "USGS field measurements at 03599500 (Columbia, in this reach): waded 95% at 128 cfs, 100% at 209, 96% at 342, 74% at 559, 16% at 915, 0% at 1,495. P(wade) crosses 50% at ~915.",
        "note": "The skinniest of the three reaches — the gauge here is the river, not an estimate."},
    "duckmid": {"craft": ["boat"],
        "craft_why": "boat only — no gauge on this reach and the shoals are unforgiving",
        "wade_ok": 900, "wade_marginal": 1500, "no_wade": 2000,
        "depth_exp": 0.633, "fit_r2": 0.87, "n_meas": 255, "substrate": "gravel & ledge",
        "src": "Scaled from the Columbia measurements (03599500) by the measured Columbia→Centerville gain (x2.33 median, analysis/duck_routing.py); this reach sits about halfway between the two gauges.",
        "note": "No gauge sits on this water. Everything here is interpolated between Columbia and Centerville — treat it as an estimate, not a reading."},
    "ducklow": {"craft": ["boat"],
        "craft_why": "boat only — the biggest, deepest water of the three",
        "wade_ok": 1300, "wade_marginal": 2100, "no_wade": 2800,
        "depth_exp": 0.633, "fit_r2": 0.87, "n_meas": 255, "substrate": "gravel & ledge",
        "src": "Scaled from the Columbia measurements (03599500) by the measured Columbia→Centerville gain (x2.33 median, analysis/duck_routing.py). Gauged directly at 03601990 / NWPS CNVT1.",
        "note": "The only Duck reach with a published forward forecast (NWPS CNVT1)."},
    "harpeth": {"craft": ["paddle", "wade"],
        "craft_why": "canoe/kayak and wadeable shoals — a State Scenic River, too skinny for a jet",
        "wade_ok": 300, "wade_marginal": 550, "no_wade": 850,
        "depth_exp": 0.60, "fit_r2": None, "n_meas": 0, "substrate": "gravel & limestone ledge",
        "src": "NOT a field-measurement fit — no USGS wading measurements were available for 03434500 at build time. Scaled from the Duck's measured curve by drainage area (683 sq mi at Kingston Springs vs the Duck's 1,208 at Columbia) and sanity-checked against the gauge's own record (p50 ~250 cfs).",
        "note": "Free-flowing State Scenic River with no dam anywhere on it. Low gradient: it comes up fast after rain and drops slowly. Unverified thresholds — treat the craft call as provisional."},
    "buffalo": {"craft": ["paddle", "wade"],
        "craft_why": "canoe/kayak water with wadeable shoals — too skinny for a jet most of the year",
        "wade_ok": 350, "wade_marginal": 600, "no_wade": 900,
        "depth_exp": 0.60, "fit_r2": None, "n_meas": 0, "substrate": "gravel & bedrock",
        "src": "NOT a field-measurement fit — no USGS wading measurements were available for 03604000 at build time. Thresholds are scaled from the Duck's measured curve by drainage size and confirmed only against the qualitative record (TWRA/State Scenic River: floatable Nov–Aug above Flat Woods, year-round below Linden).",
        "note": "Free-flowing State Scenic River — no dam anywhere on it, so it rises and drops fast. Unverified thresholds: treat the craft call as provisional."},

 "caney": {
   "craft": ["wade","float","boat"], "craft_why": "wade, drift/float, or power boat depending on release",
   "wade_ok": 400, "wade_marginal": 600, "no_wade": 1000,
   "depth_exp": 0.514, "fit_r2": 0.76, "n_meas": 110, "substrate": "gravel",
   "src": "USGS field measurements at 03424860: waded 80% at 272 cfs, 75% at 398, "
          "20% at 582, 0% above 1,824 (P(wade) crosses 50% at ~582). Corroborated by "
          "Middle TN Fly Fishers / Trout Zone: base flow 200-400 cfs wades well, one "
          "unit (~1,200-2,000 cfs) is drift-boat water, not wadeable.",
   "note": "Any generation ends wading regardless of the number — the bump arrives before the gauge shows it.",
 },
 "elktn": {
   "craft": ["kayak","wade"], "craft_why": "kayak or wade only — no power boat on this reach",
   "wade_ok": 300, "wade_marginal": 400, "no_wade": 500,
   "depth_exp": 0.603, "fit_r2": 0.75, "n_meas": 665, "substrate": "unspecified",
   "src": "Angler reports (thefuntimesguide / Tennessee Fly Fishers): zero generation "
          "with the ~245 cfs sluice is 'a great wading schedule', 240-400 cfs is the "
          "best window, and 'anything over around 400 cfs makes it pretty much "
          "non-wadeable'. USGS measurement_type is NOT usable here: this is a cableway "
          "site, so crews rarely wade (9% even at 143 cfs) regardless of the water.",
   "note": "TVA warns: do not wade during, or within 4 hours after, generation.",
 },
 "elk": {
   "craft": ["boat"], "craft_why": "boat only — the 60/40 jet (StealthCraft 1654)",
   "wade_ok": 250, "wade_marginal": 400, "no_wade": 550,
   "depth_exp": 0.455, "fit_r2": 0.68, "n_meas": 200, "substrate": "unspecified",
   "src": "USGS field measurements at 03584600: waded 78% at 153 cfs, 29% at 246, "
          "17% at 395, 0% at 634 (crossover ~246). Consistent with the general "
          "wading-safety guidance that above ~550 cfs current is unsafe to wade.",
   "note": "",
 },
 "cumberland": {
   "craft": ["boat","wade"], "craft_why": "boat or wade, gated on generation",
   "wade_ok": None, "wade_marginal": None, "no_wade": 1500,
   "depth_exp": 0.367, "fit_r2": 0.97, "n_meas": 57, "substrate": "cobbles",
   "src": "KY Fish & Wildlife / guide consensus: 'if no turbines are running you can "
          "wade; if one is running you can float'. USGS has no wading measurements at "
          "03414100 (lowest measured flow 2,540 cfs), so generation state is the "
          "threshold, not a flow number. The existing WADE=1500 anchor matches.",
   "note": "Wadeable only with the dam off, at the dam and Kendall shoals.",
 },
 "stones": {
   "craft": ["boat"], "craft_why": "boat only",
   "wade_ok": None, "wade_marginal": None, "no_wade": None,
   "depth_exp": 0.245, "fit_r2": 0.67, "n_meas": 130, "substrate": "cobbles",
   "src": "NO USABLE THRESHOLD. The gauge (03430200, US-70 near Donelson) sits in "
          "Cheatham backwater: it measures 4.1 ft mean depth at 100 cfs, so its "
          "geometry describes an impounded pool, not the fishable reach. Percy Priest "
          "releases drive the upper river and are not in this gauge.",
   "note": "Treated as unknown rather than guessed.",
 },
 # The three Cumberland mainstem pools are never wadeable at any release: navigable
 # impoundments maintained for barge traffic. That is a fact about the river, not a
 # missing measurement, so it is stated rather than modelled.
 "cumbnash":  {
   "craft": ["boat"], "craft_why": "boat only — navigable pool","wade_ok": None, "wade_marginal": None, "no_wade": 0,
               "depth_exp": 0.163, "fit_r2": 0.77, "n_meas": 99, "substrate": "silt/mud",
               "src": "Navigable impoundment (Cheatham pool). USGS measured mean depth "
                      "9.6 ft at 100 cfs; never waded in 99 measurements.", "note": ""},
 "cheatham":  {
   "craft": ["boat"], "craft_why": "boat only — navigable pool","wade_ok": None, "wade_marginal": None, "no_wade": 0,
               "depth_exp": None, "fit_r2": None, "n_meas": 0, "substrate": "silt/mud",
               "src": "Navigable impoundment below Cheatham Dam. No working gauge on the "
                      "reach (03435000 stopped reporting), so no fit exists.", "note": ""},
 "cordell":   {
   "craft": ["boat"], "craft_why": "boat only — navigable pool","wade_ok": None, "wade_marginal": None, "no_wade": 0,
               "depth_exp": None, "fit_r2": None, "n_meas": 0, "substrate": "unspecified",
               "src": "Navigable impoundment into Old Hickory Lake. No gauge on the reach.",
               "note": ""},
}

# A 60/40 jet drafts under a foot, but on GRAVEL and COBBLE the impeller eats what it
# sucks up, so the practical floor is higher than the draft. Jet guidance converges on
# staying in 1.5-2 ft over rock; a prop needs ~12 in where a jet needs 4-6 in of pure
# draft. Rather than convert that to an absolute depth the gauge cannot give us, tie it
# to the same measured anchor: water too shallow for a boat is water you could wade.
