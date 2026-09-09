"""
Release arrival timing. §27.

MOVED VERBATIM FROM riverlib.py. Not rewritten, not re-derived, not "modernised" — §27 is
explicit that validated hydrological science is not to be rewritten to tidy the code, and
these speeds are backtested against real releases. The provenance comment below came with
them and is the reason anybody should believe the numbers.

riverlib.py now imports these back from here (§28): the modern model is canonical and the
legacy page generators consume it, rather than the planner reaching down into a 2,100-line
generator module. That inversion is what lets the planner run inside a Cloudflare Worker,
where riverlib's urllib fetches and matplotlib-shaped helpers cannot go.

Equivalence with the pre-extraction implementation is proved over a sweep in
test/planner/test_hydrology.py, not asserted here.
"""
# ── ARRIVAL STAGES (measured, not assumed) ───────────────────────────────────
# analysis/onset_lag.py replays 144 real Center Hill releases against the Stonewall
# gauge and measures how long each STAGE of the response takes. A tailwater has two
# different lags and conflating them is what put two disagreeing clocks on the page:
#
#   the gauge starts MOVING at wave celerity (fast — the river is a connected body,
#   so stage downstream responds before the released water gets there), and the WATER
#   arrives later. The wading decision belongs to the first; "when is it good boat
#   water" belongs to the later stages.
#
# Measured at Stonewall, 15 mi below Center Hill (median, p25-p75 in hours):
#     first rise (+5% of the eventual rise)   6.0 h   [3-7]    2.50 mph
#     quarter risen (+25%)                    7.0 h   [6-8]    2.14 mph
#     half risen (+50%)                       8.0 h   [7-12]   1.88 mph
#     near peak (+90%)                       10.0 h   [8-16]   1.50 mph
#
# The spread is the point. Reporting "the water arrives at 2:47" implies a precision
# the river does not have: a quarter of releases reach Stonewall in 3 h, not 6. For a
# safety call ("be off the flats") the honest number is the EARLY end, not the median.
ARRIVAL_STAGES = {
    "first":   {"mph": 2.50, "mph_early": 5.00, "mph_late": 2.14, "label": "starts rising"},
    "quarter": {"mph": 2.14, "mph_early": 2.50, "mph_late": 1.88, "label": "coming up"},
    "half":    {"mph": 1.88, "mph_early": 2.14, "mph_late": 1.25, "label": "half up"},
    "peak":    {"mph": 1.50, "mph_early": 1.88, "mph_late": 0.94, "label": "near peak"},
}

def arrival_window(mfd, stage="first"):
    """(earliest_h, median_h, latest_h) for the release to reach mfd at this stage.

    Use `earliest` for anything safety-shaped. The median is what to display; the
    spread is what stops the display from lying about its own precision.
    """
    s = ARRIVAL_STAGES.get(stage) or ARRIVAL_STAGES["first"]
    if not mfd or mfd <= 0: return (0.0, 0.0, 0.0)
    return (round(mfd / s["mph_early"], 2), round(mfd / s["mph"], 2), round(mfd / s["mph_late"], 2))
