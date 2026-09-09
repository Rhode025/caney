"""
Choosing which feature to fish, and in what order. §26, §89.

The zone layer answers "Carthage". This answers "the Caney Fork mouth first, the channel
swing after the release stops" — which is the difference between a report and a guide.

The selection is deliberately small and legible. A feature's fit for a window is:

    fit = species weight  x  hydraulic fit  x  geometry confidence prior

and nothing else. There is no learned model here and no tuning surface, because there is
no outcome data yet to tune against (§67 says explicitly not to move the scoring in 3.0).
What the three terms buy is the §89 behaviour, which is real:

    A tailrace seam and a tributary mouth in the same zone are not interchangeable, and
    which one is right depends on the DAM, not on preference. With the units turning, the
    seam exists and is the best water in the county. Forty minutes after they stop it is
    a flat pool, and the mouth — which the release has just spent three hours pushing
    bait into — is where the fish went.

So the ordering has to be a function of the generation series over the window, not a
static ranking. `order_for_window` takes the release forecast and returns the sequence.

CONFIDENCE IS A MULTIPLIER, NOT A TIEBREAK. A modelled guess about which bank does not
get to beat a surveyed feature on a 0.02 difference in species weight, and making it a
tiebreak instead of a factor would let a long tail of UNVERIFIED features quietly float to
the top of zones where we know almost nothing.
"""
from ..domain.feature import FeatureType, GeometryConfidence, HydraulicBehavior
from ..domain.observation import DataState
from ..zones.features import features_for

#: How well each hydraulic behaviour likes the water being on. 1.0 is neutral.
#: Uncalibrated priors; the ORDERING is what produces §89 and is the part worth defending.
HYDRAULIC_FIT = {
    HydraulicBehavior.NEEDS_CURRENT:          {"on": 1.30, "off": 0.30, "unknown": 0.85},
    HydraulicBehavior.IMPROVES_WITH_CURRENT:  {"on": 1.18, "off": 0.80, "unknown": 0.95},
    HydraulicBehavior.BEST_ON_FALLING:        {"on": 0.95, "off": 1.15, "unknown": 0.95},
    HydraulicBehavior.BEST_ON_RISING:         {"on": 1.15, "off": 0.85, "unknown": 0.95},
    HydraulicBehavior.CURRENT_INDIFFERENT:    {"on": 1.00, "off": 1.00, "unknown": 1.00},
    HydraulicBehavior.BLOWN_BY_CURRENT:       {"on": 0.25, "off": 1.25, "unknown": 0.85},
}

#: A feature that wants FALLING water is at its best in the window just after shutdown,
#: not indefinitely afterwards. Minutes.
FALLING_WINDOW_MINUTES = 150.0

#: Below this fit a feature is not offered at all — it is not that it scores badly, it is
#: that the thing which makes it a feature is absent.
MIN_FIT = 0.28


def generation_state(snap, start, end):
    """'on' | 'off' | 'unknown' for a window, from the RELEASE FORECAST.

    The forecast, not the current reading: a plan for tomorrow morning cannot be built on
    what the dam is doing now, and `generation_on` is a now-value. Unknown stays unknown —
    there is no `or 0` here, and a dam with no forward schedule does not read as off.
    """
    fc = getattr(snap, "generation_forecast", None)
    cfg_on = None
    if fc is None or not fc.ok or not fc.value:
        return "unknown", None
    from ..sources.registry import water_for
    cfg = water_for(getattr(snap, "river_id", "") or "")
    cfg_on = cfg.get("gen_on")
    if cfg_on is None:
        return "unknown", None
    rows = [(t, v) for t, v in fc.value if v is not None and start - 5400 <= t <= end + 5400]
    if not rows:
        return "unknown", None
    inside = [(t, v) for t, v in rows if start <= t <= end]
    if not inside:
        inside = rows
    on_frac = sum(1 for _t, v in inside if v >= cfg_on) / float(len(inside))
    # The last shutdown at or before the window, for the falling-water term.
    last_stop = None
    prev_on = None
    for t, v in rows:
        cur = v >= cfg_on
        if prev_on is True and cur is False:
            last_stop = t
        prev_on = cur
    if on_frac >= 0.6:
        return "on", last_stop
    if on_frac <= 0.2:
        return "off", last_stop
    return "mixed", last_stop


def fit(feature, species, state, window_start=None, last_stop=None):
    """0..~1.4. The multiplier a feature earns for this window."""
    base = feature.weight_for(species)
    if base <= 0:
        return 0.0
    table = HYDRAULIC_FIT.get(feature.hydraulic_behavior,
                              HYDRAULIC_FIT[HydraulicBehavior.CURRENT_INDIFFERENT])
    if state == "mixed":
        # Half the window has current. Take the average rather than picking a side —
        # a mixed window is exactly where a two-feature plan is right, and the ordering
        # step below is what exploits it.
        h = (table["on"] + table["off"]) / 2.0
    else:
        h = table.get(state, table["unknown"])

    # A falling-water feature only gets its bonus while the water is actually falling.
    if feature.hydraulic_behavior == HydraulicBehavior.BEST_ON_FALLING and \
            state == "off" and last_stop is not None and window_start is not None:
        if (window_start - last_stop) / 60.0 > FALLING_WINDOW_MINUTES:
            h = HYDRAULIC_FIT[HydraulicBehavior.CURRENT_INDIFFERENT]["off"]

    return base * h * feature.prior


def rank(zone_id, species, month, snap, start, end):
    """[(feature, fit)] for one window, best first, unfishable features dropped."""
    state, last_stop = generation_state(snap, start, end)
    out = []
    for f in features_for(zone_id, species, month):
        v = fit(f, species, state, start, last_stop)
        if v >= MIN_FIT:
            out.append((f, round(v, 4)))
    out.sort(key=lambda p: -p[1])
    return out


def order_for_window(zone_id, species, month, snap, start, end, max_features=2):
    """§89 — which feature FIRST and which SECOND, split at the generation change.

    When the release stops inside the window, the honest answer is two features and a
    time to switch, not one feature averaged over both regimes. That split is the whole
    reason the feature layer exists: the plan gains a real instruction ("move to the
    mouth at 7:45") that the zone layer could not express.
    """
    state, last_stop = generation_state(snap, start, end)
    switch = _switch_time(snap, start, end)

    def single():
        """One feature for the whole window, with the runner-up recorded, not scheduled.

        The legs this returns are SEQUENTIAL — each one is "fish here, then here". An
        earlier version returned the top two features when there was nothing to split
        on, and both carried the window's full span, so the plan told a reader at 7:12 to
        move to a spot they were already standing on for the next two and a half hours.
        A ranking is not a schedule.
        """
        picks = rank(zone_id, species, month, snap, start, end)
        if not picks:
            return []
        f, v = picks[0]
        alt = [{"id": g.id, "name": g.name, "fit": w} for g, w in picks[1:3]]
        return [{"feature": f, "fit": v, "start": start, "end": end, "why": "",
                 "alternatives": alt}]

    if switch is None or max_features < 2:
        return single()

    before = rank(zone_id, species, month, snap, start, switch)
    after = rank(zone_id, species, month, snap, switch, end)
    if not before or not after:
        return single()

    first = before[0]
    # The second leg must be a DIFFERENT feature, and it must actually be BETTER than
    # staying put. Without that second test the split happily marched people off a
    # tributary mouth fitting 0.56 onto a channel swing fitting 0.36 — a move is only
    # worth making if the water you move to is better than the water you leave, and
    # "the conditions changed" is not on its own a reason to change position.
    stay_after = next((v for f, v in after if f.id == first[0].id), 0.0)
    better = [(f, v) for f, v in after if f.id != first[0].id and v > stay_after]
    if not better:
        return single()
    second = better[0]

    stopping = _is_stop(snap, switch)
    # Say what actually changed, from the fits, rather than asserting that the release
    # "makes" one feature and "unmakes" the other. On a tributary mouth the release
    # stopping is a softening, not an ending, and prose that overstates it is prose the
    # reader will eventually catch being wrong.
    delta = second[1] - stay_after
    verb = "stops" if stopping else "starts"
    if stay_after < MIN_FIT:
        why = ("the release %s here — %s stops working, and %s is where the fish go"
               % (verb, first[0].name.lower(), second[0].name.lower()))
    else:
        why = ("the release %s here, and %s fits the new conditions better than staying "
               "put (%.2f against %.2f)"
               % (verb, second[0].name.lower(), second[1], stay_after))
    return [
        {"feature": first[0], "fit": first[1], "start": start, "end": switch, "why": ""},
        {"feature": second[0], "fit": second[1], "start": switch, "end": end,
         "why": why, "delta": round(delta, 3)},
    ]


def _switch_time(snap, start, end):
    """The first generation change strictly inside the window, or None."""
    fc = getattr(snap, "generation_forecast", None)
    if fc is None or not fc.ok or not fc.value:
        return None
    from ..sources.registry import water_for
    cfg = water_for(getattr(snap, "river_id", "") or "")
    on = cfg.get("gen_on")
    if on is None:
        return None
    prev = None
    for t, v in fc.value:
        if v is None:
            continue
        cur = v >= on
        if prev is not None and cur != prev and start < t < end:
            # Leave room for a leg on each side; a switch two minutes before the end is
            # not a plan, it is a footnote.
            if (t - start) / 60.0 >= 30 and (end - t) / 60.0 >= 30:
                return t
        prev = cur
    return None


def _is_stop(snap, at):
    fc = getattr(snap, "generation_forecast", None)
    if fc is None or not fc.ok or not fc.value:
        return True
    from ..sources.registry import water_for
    on = water_for(getattr(snap, "river_id", "") or "").get("gen_on")
    if on is None:
        return True
    before = [v for t, v in fc.value if v is not None and at - 5400 <= t < at]
    after = [v for t, v in fc.value if v is not None and at <= t <= at + 5400]
    if not before or not after:
        return True
    return (sum(before) / len(before)) > (sum(after) / len(after))


def published():
    return {"hydraulic_fit": HYDRAULIC_FIT,
            "falling_window_minutes": FALLING_WINDOW_MINUTES,
            "min_fit": MIN_FIT}
