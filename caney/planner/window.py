"""
Best-window selection inside the user's request. §37.

The user says "I can fish 6:30–10:00". The answer is rarely "all of it": the low-light
edge, the generation start and the storm all sit at particular clock times. This scans
30-minute offsets inside the request and returns the highest-scoring contiguous slice of
at least 90 minutes (or the whole request, when it is shorter than that).

It scores with the same species weights as everything else, so the window and the ranking
cannot disagree. That costs a handful of extra scoring passes per candidate, which is
cheap: scoring touches no network.
"""
from ..species.profiles import weights_for

# The window search geometry, published to the browser in the dataset so that
# web/planner/model.js can run the identical search without a constant of its own.
STEP = 1800.0        # scan granularity
MIN_SPAN = 5400.0    # shortest window worth calling a window
SHORT_DAY = 1.34     # a request under MIN_SPAN * this is fished whole
GAIN = 0.35          # points a shorter slice must beat the whole window by
TIE = 0.05           # inside this, the LONGER window wins


def best_window(req, zone, snap, claims, cfg, units, gen_known, series=None, statics=None,
                bounds=None):
    """((start, end), why) — the slice of the request worth fishing.

    `bounds` is the candidate's fishable envelope (§19). Since 3.0 the caller passes the
    zone's own reachable window rather than the raw request, because a zone ninety
    minutes away does not have the same day available to it as one down the road.
    """
    from . import scoring
    start, end = bounds if bounds else (req.start, req.end)
    span = end - start
    if span <= MIN_SPAN * SHORT_DAY:
        return (start, end), "the whole requested window — it is short enough to fish through"

    def sc(a, b):
        v, _lines, _fits = scoring.score(req.species, zone, snap, claims, (a, b), req.craft,
                                         req.month, cfg, units, gen_known,
                                         series=series, statics=statics)
        return v

    whole = sc(start, end)
    best, best_v = (start, end), whole
    a = start
    while a + MIN_SPAN <= end:
        b = a + MIN_SPAN
        while b <= end:
            v = sc(a, b)
            # A longer window at the same quality wins: the reader asked for the time, so
            # only give it back when the score actually pays for the loss.
            if v > best_v + GAIN or (v > best_v - TIE and (b - a) > (best[1] - best[0])):
                best, best_v = (a, b), max(v, best_v)
            b += STEP
        a += STEP

    if best == (start, end):
        why = "the whole requested window scores as well as any slice of it"
    else:
        gain = best_v - whole
        why = ("this %.1f-hour slice scores %.1f points better than fishing the whole "
               "window" % ((best[1] - best[0]) / 3600.0, gain)) if gain > 0.05 else \
              "the strongest part of the window you gave"
    return best, why
