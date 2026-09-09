"""
Building the day. §9, §10, §13, §14.

Given the opportunity windows every eligible zone offers inside the user's availability,
and the transition graph for the chosen craft, find the sequence that maximises itinerary
utility.

THE SEARCH is deliberately small (§13). Windows are already pruned to the best few per
zone, at most `MAX_ZONES` are allowed in a plan, and the sequence must be time-ordered with
a real transition between consecutive windows — so a beam search over a few dozen windows
finishes in microseconds. Nothing here needs to be clever.

THE OBJECTIVE is the same published utility function the individual windows use, evaluated
over the CONCATENATED samples of the fished segments, minus the transitions and minus a
complexity penalty:

    itinerary_utility = Q(all samples) × D(total fished minutes) × C × L
                        − Σ transition_minutes × TRANSITION_COST_PER_MIN
                        − COMPLEXITY_PENALTY × (zones − 1)

Evaluating the plan as one pseudo-window rather than summing per-window utilities is what
makes §57, §58 and §59 come out right at once. Summing rewards adding segments; averaging
rewards padding; this rewards a day whose fished time is uniformly good, and charges for
every minute spent travelling instead of fishing.

§14 — a one-zone plan wins when it is clearly best. The complexity penalty is the thumb on
that scale, and it is small enough that a genuinely better circuit still wins.
"""
from ..domain.opportunity import FishingItinerary, OpportunityWindow
from . import utility as U

#: §13 — bound the plan. Most good plans use one or two.
MAX_ZONES = 3

#: Beam width for the sequence search.
BEAM = 24

#: Slack allowed between a window ending and the next starting, beyond travel time.
#: Some waiting is normal — on a tailwater you often run downstream and wait for the water
#: to reach you — but a lot of it means the second window is really a separate trip.
MAX_IDLE_MINUTES = 75.0


class Candidate:
    __slots__ = ("windows", "transitions", "utility", "parts")

    def __init__(self, windows, transitions, utility, parts):
        self.windows = windows
        self.transitions = transitions
        self.utility = utility
        self.parts = parts

    @property
    def zones(self):
        out = []
        for w in self.windows:
            if not out or out[-1] != w.zone_id:
                out.append(w.zone_id)
        return out


def idle_minutes(windows, transitions):
    """Minutes inside the plan spent neither fishing nor travelling."""
    total = 0.0
    for i, tr in enumerate(transitions):
        gap = (windows[i + 1].start - windows[i].end) / 60.0
        total += max(0.0, gap - tr.minutes)
    return total


def evaluate(windows, transitions, species):
    """(utility, parts) for a candidate sequence. The published formula, in one place."""
    samples = []
    minutes = 0.0
    for w in windows:
        samples.extend(w.samples)
        minutes += w.duration_minutes
    if not samples:
        return -1e9, {}

    travel = sum(t.minutes for t in transitions)
    idle = idle_minutes(windows, transitions)
    conf = min(w.confidence for w in windows)
    loc = min(w.location_confidence for w in windows)
    stale = any(w.stale for w in windows)

    util, parts = U.window_utility(
        samples, minutes, species, conf, loc,
        transition_minutes=travel + U.IDLE_COST_FACTOR * idle, stale=stale)

    n_zones = len(set(w.zone_id for w in windows))
    complexity = U.COMPLEXITY_PENALTY * max(0, n_zones - 1)
    mean_q = sum(w.quality for w in windows) / len(windows)
    breadth = U.BREADTH_BONUS * max(0, len(windows) - 1) * (mean_q / 100.0)
    util = util + breadth - complexity

    parts = dict(parts)
    parts.update({"complexity": round(complexity, 4), "breadth": round(breadth, 4),
                  "travelMinutes": round(travel, 1), "idleMinutes": round(idle, 1),
                  "fishingMinutes": round(minutes, 1), "zones": n_zones,
                  "utility": round(util, 4)})
    return round(util, 4), parts


def search(all_windows, graph, species, max_zones=MAX_ZONES, beam=BEAM):
    """Best-first over time-ordered, transition-feasible sequences. Returns [Candidate]."""
    if not all_windows:
        return []

    ordered = sorted(all_windows, key=lambda w: (w.start, -w.utility))

    # Seed with every single-window plan. §14 lives here: a one-zone plan is always in the
    # running, never something the search has to be talked back into.
    beams = []
    for w in ordered:
        u, p = evaluate([w], [], species)
        beams.append(Candidate([w], [], u, p))
    beams.sort(key=lambda c: -c.utility)
    best = list(beams[:beam])
    frontier = list(beams[:beam])

    for _ in range(max_zones - 1):
        grown = []
        for cand in frontier:
            last = cand.windows[-1]
            used = set(w.zone_id for w in cand.windows)
            for w in ordered:
                if w.zone_id in used:
                    continue
                tr = graph.get((last.zone_id, w.zone_id))
                if tr is None:
                    continue
                gap_min = (w.start - last.end) / 60.0
                if gap_min < tr.minutes - 1e-6:
                    continue                       # cannot get there in time
                if gap_min - tr.minutes > MAX_IDLE_MINUTES:
                    continue                       # that is a second trip, not a move
                seq = cand.windows + [w]
                trs = cand.transitions + [tr]
                u, p = evaluate(seq, trs, species)
                grown.append(Candidate(seq, trs, u, p))
        if not grown:
            break
        grown.sort(key=lambda c: -c.utility)
        frontier = grown[:beam]
        best.extend(frontier)

    best.sort(key=lambda c: -c.utility)

    # Deduplicate by zone sequence, keeping the strongest arrangement of each.
    seen, out = set(), []
    for c in best:
        key = tuple(c.zones) + tuple(round(w.start) for w in c.windows)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= 12:
            break
    return out


def best_itinerary(all_windows, graph, species, craft, req_start, req_end,
                   max_zones=MAX_ZONES):
    """(Candidate | None, [Candidate]) — the winner and the runners-up."""
    cands = search(all_windows, graph, species, max_zones=max_zones)
    if not cands:
        return None, []
    return cands[0], cands[1:6]


def why_move(before, after, transition, tz):
    """§15 — the sentence that justifies a move, in terms of what changes."""
    import datetime as _dt
    f = lambda t: _dt.datetime.fromtimestamp(t, tz).strftime("%-I:%M %p")
    drop = before.samples[-1] if before.samples else 0.0
    rise = after.samples[0] if after.samples else 0.0
    tail = ("The first zone is falling away — it ends around %.0f while the next one is "
            "running %.0f and holds it for another %.0f minutes."
            % (drop, rise, after.duration_minutes))
    if rise <= drop:
        tail = ("The first zone is finished by then; the next one is the best remaining "
                "water inside your window.")
    return ("Move at %s. %s %s (%s, %s: %s)"
            % (f(before.end), tail, "",
               "%.0f min" % transition.minutes, transition.provenance,
               transition.detail or transition.mode)).replace("  ", " ")
