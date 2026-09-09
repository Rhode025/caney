"""
The itinerary. §9, §39, §40.

Every step declares WHERE ITS TIMING CAME FROM (StepKind), because "5:45 launch" and
"7:30 move to the creek mouth" are not the same kind of statement and must not read alike:

    DETERMINISTIC   a modelled arrival bound off an instrument feed  → cites a claim id
    ASTRONOMICAL    sunrise/sunset/moon                              → exact
    FORECAST        a forecast event, carrying its own spread
    HEURISTIC       species behaviour and guide craft                → unverified
    SAFETY          a hard exit or abort instruction                 → earliest bound only

Conditional branches (§39) are first-class rather than an afterthought: a plan that only
works if the dam keeps running is more useful when it says what to do when it stops.

No invented precision (§3.5). Where the model supports a distribution the step carries the
distribution in `uncertainty` and the SAFETY step uses the earliest edge.
"""
import datetime as _dt

from ..domain.claim import SafetyKind
from ..domain.plan import StepKind, TimelineStep


def _fmt(ep, tz):
    return _dt.datetime.fromtimestamp(ep, tz).strftime("%-I:%M %p")


def build(zone, snap, prof, species, window, craft, tz, book, claims, units, gen_known):
    """[TimelineStep] for the chosen window, in time order."""
    start, end = window
    steps = []
    ref = zone.species_profiles.get(species)
    launch = _pick_launch(zone, craft)
    my = {c.id: c for c in book.for_zone(zone.id)}

    def claim_of(kind, after=None):
        for c in my.values():
            if c.kind != kind:
                continue
            if after is not None and (c.at or 0) < after:  # not a measurement (sort key)
                continue
            return c
        return None

    # ── launch ──────────────────────────────────────────────────────────────
    launch_at = start - 900
    steps.append(TimelineStep(
        at=launch_at, at_label=_fmt(launch_at, tz),
        title="Launch at %s" % (launch["name"] if launch else zone.name),
        detail=(launch.get("note") or "") if launch else
               "No verified access recorded for this craft — check locally before you go.",
        kind=StepKind.HEURISTIC, zone_id=zone.id))

    # ── first block: where the fish are right now ───────────────────────────
    first_end = min(end, start + 2400)
    steps.append(TimelineStep(
        at=start, at_label=_fmt(start, tz), until=first_end,
        title="Fish %s" % (_holds_headline(ref, zone)),
        detail=(ref.holds if ref and ref.holds else
                "Work the primary habitat for this species on this water."),
        kind=StepKind.HEURISTIC, zone_id=zone.id))

    # ── astronomical: first light is a real event, not a guess ──────────────
    if snap.sunrise.ok and start - 3600 <= snap.sunrise.value <= end:
        steps.append(TimelineStep(
            at=snap.sunrise.value, at_label=_fmt(snap.sunrise.value, tz),
            title="Sunrise",
            detail=("The low-light edge closes over the next hour or so — take the best "
                    "water first, not last."),
            kind=StepKind.ASTRONOMICAL, zone_id=zone.id))
    if snap.sunset.ok and start <= snap.sunset.value <= end + 3600:
        steps.append(TimelineStep(
            at=snap.sunset.value, at_label=_fmt(snap.sunset.value, tz),
            title="Sunset",
            detail="Last light is the second-best window of the day for this fish.",
            kind=StepKind.ASTRONOMICAL, zone_id=zone.id))

    # ── solunar, explicitly weak ────────────────────────────────────────────
    for w in (snap.lunar or {}).get("major_windows") or []:
        if start <= w["start"] <= end:
            steps.append(TimelineStep(
                at=w["start"], at_label=_fmt(w["start"], tz), until=w["end"],
                title="Solunar major",
                detail=("A weak, secondary signal — worth being on your best water for it, "
                        "never worth choosing a worse day for. Approximate to ±40 min."),
                kind=StepKind.HEURISTIC, zone_id=zone.id))

    # ── the deterministic water events ──────────────────────────────────────
    gen_start = claim_of(SafetyKind.GENERATION_START, after=start - 7200)
    gen_stop = claim_of(SafetyKind.GENERATION_STOP, after=start - 7200)
    arrival = claim_of(SafetyKind.RELEASE_ARRIVAL, after=start - 7200)
    safe_exit = claim_of(SafetyKind.SAFE_EXIT, after=start - 7200)

    if arrival and arrival.value:
        e, m, l = arrival.value
        if start - 3600 <= e <= end + 5400:
            steps.append(TimelineStep(
                at=m, at_label=_fmt(m, tz),
                title="Released water reaches this zone",
                detail=arrival.text,
                uncertainty="earliest %s · typical %s · later edge %s"
                            % (_fmt(e, tz), _fmt(m, tz), _fmt(l, tz)),
                kind=StepKind.DETERMINISTIC, zone_id=zone.id,
                claim_ids=[arrival.id]))

    if safe_exit and safe_exit.at and start - 3600 <= safe_exit.at <= end + 5400:
        steps.append(TimelineStep(
            at=safe_exit.at, at_label=_fmt(safe_exit.at, tz),
            title="SAFE EXIT — be out of the water",
            detail=safe_exit.text + " This uses the EARLIEST modelled arrival minus a "
                                    "30-minute margin, not the typical one.",
            kind=StepKind.SAFETY, zone_id=zone.id, claim_ids=[safe_exit.id]))

    # ── the move ────────────────────────────────────────────────────────────
    move_to = (ref.move_to if ref else []) or []
    move_at = _move_time(start, end, arrival, gen_stop)
    if move_to:
        nxt = move_to[0]
        steps.append(TimelineStep(
            at=move_at, at_label=_fmt(move_at, tz),
            title="Move toward %s" % _zone_name(nxt),
            detail=("Second zone for this species when the first stops producing or the "
                    "water state changes."),
            kind=StepKind.HEURISTIC, zone_id=nxt,
            condition="when the first zone goes quiet, or on the water change below"))
    else:
        # A river with nowhere better to go still needs a move: fishing one shoal for four
        # hours is how a good window gets wasted. Rotate within the zone instead.
        habitat = [h for h in ((ref.habitat if ref else []) or zone.habitat)]
        second = habitat[1] if len(habitat) > 1 else (habitat[0] if habitat else None)
        if second:
            steps.append(TimelineStep(
                at=move_at, at_label=_fmt(move_at, tz),
                title="Rotate to the next %s" % second,
                detail=("No second zone beats this one in this window, so move WITHIN it: "
                        "leave the water you have covered and find the same structure "
                        "again downstream."),
                kind=StepKind.HEURISTIC, zone_id=zone.id))

    # ── conditional branches (§39) ──────────────────────────────────────────
    branches = []
    if gen_stop:
        branches.append({"if": "generation stops (%s)" % _fmt(gen_stop.at, tz)
                                if gen_stop.at else "generation stops",
                         "then": ("The seam dies within the hour. Move to %s and fish it "
                                  "slow and deep." % (_zone_name(move_to[0]) if move_to
                                                      else "the nearest structure")),
                         "claim_ids": [gen_stop.id]})
    if gen_start:
        branches.append({"if": "generation starts (%s)" % _fmt(gen_start.at, tz)
                                if gen_start.at else "generation starts",
                         "then": ("Current arrives on the schedule above. If you are wading, "
                                  "the SAFE EXIT step is the one that matters, not this one."),
                         "claim_ids": [gen_start.id] + ([arrival.id] if arrival else [])})
    storm = [c for c in book.for_zone(zone.id) if c.kind == SafetyKind.WEATHER_HAZARD]
    rows = snap.weather_window(start, end)
    if storm or any(r.get("thunderstorm") for r in rows):
        branches.append({"if": "thunderstorms reach the water",
                         "then": "Terminate the plan. Get off the water and off the bank.",
                         "claim_ids": [c.id for c in storm]})
    if branches:
        steps.append(TimelineStep(
            at=None, at_label="", title="If conditions change",
            detail="Branches, in the order they are most likely to fire.",
            kind=StepKind.FORECAST, zone_id=zone.id, branches=branches))

    # ── the next water change, even when it lands outside the window ────────
    # A plan that says nothing about the water because the release is two hours after you
    # planned to leave is not being careful, it is being quiet. If no deterministic step
    # landed inside the window, state the next scheduled change — or state that there is
    # none, which is itself a deterministic fact off the release feed.
    if not any(s.kind == StepKind.DETERMINISTIC for s in steps):
        nxt = None
        for c in book.for_zone(zone.id):
            if c.kind not in (SafetyKind.GENERATION_START, SafetyKind.GENERATION_STOP,
                              SafetyKind.RELEASE_ARRIVAL):
                continue
            if c.at is None or c.at <= end:
                continue
            if nxt is None or c.at < nxt.at:
                nxt = c
        if nxt is not None:
            steps.append(TimelineStep(
                at=nxt.at, at_label=_fmt(nxt.at, tz),
                title="Next water change — after your window",
                detail=nxt.text + " Nothing scheduled changes this reach inside the window "
                                  "you asked for.",
                kind=StepKind.DETERMINISTIC, zone_id=zone.id, claim_ids=[nxt.id]))
        elif snap.generation_forecast.ok:
            steps.append(TimelineStep(
                at=end, at_label=_fmt(end, tz),
                title="No water change is scheduled",
                detail=("The release feed shows no generation change for this reach inside "
                        "the planning horizon. Verify it before you get in anyway."),
                kind=StepKind.DETERMINISTIC, zone_id=zone.id))
        else:
            # A free-flowing river has no release feed at all. Its deterministic anchor is
            # the gauge, so quote the flow claim rather than leaving the plan with nothing
            # measured in it.
            flow = claim_of(SafetyKind.FLOW)
            if flow is not None:
                steps.append(TimelineStep(
                    at=start, at_label=_fmt(start, tz),
                    title="The water you are walking into",
                    detail=flow.text + " There is no dam on this water, so the gauge is the "
                                       "whole story — and it moves with the rain, not with "
                                       "a schedule.",
                    kind=StepKind.DETERMINISTIC, zone_id=zone.id, claim_ids=[flow.id]))

    # ── close ───────────────────────────────────────────────────────────────
    steps.append(TimelineStep(
        at=end, at_label=_fmt(end, tz),
        title="Primary window ends",
        detail=_close_reason(snap, start, end, arrival, gen_stop),
        kind=StepKind.HEURISTIC, zone_id=zone.id))

    steps.sort(key=lambda s: (s.at is None, s.at or 0))  # not a measurement (sort key)
    return steps


def _move_time(start, end, arrival, gen_stop):
    span = end - start
    if arrival and arrival.value and start < arrival.value[0] < end:
        return max(start + 900, arrival.value[0] - 1200)
    if gen_stop and gen_stop.at and start < gen_stop.at < end:
        return gen_stop.at
    return start + span * 0.55


def _close_reason(snap, start, end, arrival, gen_stop):
    if arrival and arrival.value and arrival.value[0] <= end:
        return "The released water is in this reach by now — the fishery you planned is gone."
    if snap.sunrise.ok and end > snap.sunrise.value + 10800:
        return "The low-light edge is long gone and the light is against you."
    if gen_stop and gen_stop.at and start <= gen_stop.at <= end:
        return "Generation ends and the current that concentrated the fish goes with it."
    return "End of the requested window."


def _pick_launch(zone, craft):
    from ..domain.zone import Craft
    opts = [a for a in zone.access if a.serves(craft)] or list(zone.access)
    if not opts:
        return None
    opts.sort(key=lambda a: (not a.verified,
                             a.river_miles_from_dam or 0))  # not a measurement (sort key)
    a = opts[0]
    return {"name": a.name, "note": a.note, "lat": a.lat, "lon": a.lon,
            "verified": a.verified, "source": a.source, "id": a.id}


def _holds_headline(ref, zone):
    if ref and ref.habitat:
        return "the " + ref.habitat[0]
    if zone.habitat:
        return "the " + zone.habitat[0]
    return zone.name


def _zone_name(zid):
    from ..zones.registry import ZONES
    z = ZONES.get(zid)
    return z.name if z else zid
