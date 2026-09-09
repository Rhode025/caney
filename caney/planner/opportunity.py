"""
Finding the windows worth fishing. §4, §8.

Given an hourly score series for one (zone, species) and the user's availability, this
enumerates contiguous candidate windows on a 15-minute grid, scores each with the published
utility function, and returns the non-dominated best few.

Two properties matter.

1. IT DOES NOT HAVE TO USE THE WHOLE PERIOD. "You can fish 6:00–11:00" is a constraint, not
   an instruction. If the bite is 6:25–8:05 the answer is 6:25–8:05, and the UI shows both
   (§8, §68).

2. IT PRUNES TO A SMALL, HONEST SET. The itinerary search runs over these, and the browser
   receives them, so the set has to be small. `top_windows` keeps the best few
   *non-overlapping-ish* candidates per zone rather than a hundred near-duplicates that
   differ by fifteen minutes.
"""
from ..domain.opportunity import OpportunityWindow
from . import utility as U

#: Candidate grid. Starts and ends both move on this, in minutes.
GRID_MINUTES = 15

#: Longest window worth proposing. Past this, duration utility has saturated anyway.
MAX_MINUTES = 330

#: How many windows to keep per (zone, species) for the itinerary search and the dataset.
TOP_N = 6

#: Diversity bucket for the keep-set, in minutes. See `_prune`.
BUCKET_MINUTES = 60


def find_windows(zone_id, species, series_values, t0, step, avail_start, avail_end,
                 confidence, location_confidence, stale=False, conditions_summary="",
                 reasons=(), top_n=TOP_N, min_minutes=None, max_minutes=MAX_MINUTES):
    """[OpportunityWindow] — the best few fishable stretches inside the availability."""
    avail_min = (avail_end - avail_start) / 60.0
    if avail_min <= 0 or not series_values:
        return []

    floor_min = min_minutes if min_minutes is not None else U.min_duration(species)
    grid = GRID_MINUTES * 60

    # Snap the scan to the availability start so the grid is reproducible in both engines.
    cands = []
    a = avail_start
    while a < avail_end:
        b = a + floor_min * 60
        while b <= avail_end:
            minutes = (b - a) / 60.0
            if minutes > max_minutes:
                break
            samples = U.sample_series(series_values, t0, step, a, b)
            if samples:
                util, parts = U.window_utility(
                    samples, minutes, species, confidence, location_confidence,
                    transition_minutes=0.0, stale=stale)
                cands.append((util, a, b, samples, parts))
            b += grid
        a += grid

    # The availability may be shorter than the species minimum. Rather than returning
    # nothing — the user asked, and a short session is still a session — offer the whole
    # thing and let the duration penalty say what it costs.
    if not cands and avail_min > 0:
        samples = U.sample_series(series_values, t0, step, avail_start, avail_end)
        if samples:
            util, parts = U.window_utility(samples, avail_min, species, confidence,
                                           location_confidence, stale=stale)
            cands.append((util, avail_start, avail_end, samples, parts))

    kept = _prune(cands, avail_start, top_n)

    out = []
    for util, a, b, samples, parts in kept:
        out.append(OpportunityWindow(
            zone_id=zone_id, species=species, start=a, end=b, samples=samples,
            peak_score=round(max(samples), 2), mean_score=round(sum(samples) / len(samples), 2),
            floor_score=round(min(samples), 2), quality=parts["quality"],
            confidence=round(confidence, 1), location_confidence=round(location_confidence, 4),
            utility=util, parts=parts, conditions_summary=conditions_summary,
            reasons=list(reasons), stale=stale))
    return out


def _prune(cands, avail_start, top_n):
    """Keep a DIVERSE set, not just the top few by standalone utility.

    This was a real bug: pruning to the best four windows by utility threw away the tight
    peak window that is only worth fishing as the FIRST leg of a circuit, because the
    longer window that runs into the zone's collapse scored higher on its own. The
    itinerary search then had nothing early-ending to build on and could never find the
    move. So the keep-set spans the space: the best window ending in each hour, the best
    starting in each hour, and the global best — then the top few of that union.
    """
    if not cands:
        return []
    cands = sorted(cands, key=lambda c: (-c[0], c[1], -(c[2] - c[1])))
    bucket = BUCKET_MINUTES * 60

    best_by_end, best_by_start = {}, {}
    for c in cands:
        eb = int((c[2] - avail_start) // bucket)
        sb = int((c[1] - avail_start) // bucket)
        if eb not in best_by_end:
            best_by_end[eb] = c
        if sb not in best_by_start:
            best_by_start[sb] = c

    pool, seen = [], set()
    for c in [cands[0]] + list(best_by_end.values()) + list(best_by_start.values()):
        key = (round(c[1]), round(c[2]))
        if key in seen:
            continue
        seen.add(key)
        pool.append(c)
    # No overlap dedupe here. The bucket construction above IS the diversity guarantee,
    # and an overlap filter on top of it deleted precisely the windows it was meant to
    # protect: 6:00-7:45 overlaps 6:00-8:30 completely, and 6:00-7:45 is the leg that
    # makes a circuit possible.
    pool.sort(key=lambda c: (-c[0], c[1]))
    return pool[:top_n]


def describe(window, tz):
    """A one-line reason the window is what it is, for the 'why this won' block (§67)."""
    import datetime as _dt
    f = lambda t: _dt.datetime.fromtimestamp(t, tz).strftime("%-I:%M %p")
    return ("%s–%s · peak %.0f, floor %.0f over %.0f min"
            % (f(window.start), f(window.end), window.peak_score, window.floor_score,
               window.duration_minutes))
