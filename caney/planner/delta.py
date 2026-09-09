"""
Comparing two planning snapshots. §10, §11, §56.

The question is not "did anything change" — gauges move constantly, and a product that
says PLAN CHANGED every five minutes teaches people to ignore the banner exactly when it
matters. The question is "did anything change that should change what you DO".

Everything here compares INPUTS and then the resulting itinerary, in that order, because
the two answer different things. An input change explains WHY; an itinerary change is the
what. A refresh that finds the generation forecast moved forty minutes but the plan
unchanged should say so calmly, and one that finds the plan moved should lead with the
move and offer the cause underneath.

THE SERVER DECIDES MATERIALITY, NOT THE CLIENT (§11). The thresholds live in
`caney/domain/session.py::Threshold` and are published in every delta payload, so a client
can EXPLAIN a verdict but never reach a different one.
"""
import datetime as _dt

from ..domain.session import (DeltaChange, Materiality, PlanDelta, Threshold)


def _fmt(ep, tz):
    return _dt.datetime.fromtimestamp(ep, tz).strftime("%-I:%M %p") if ep else "—"


def _events(series, gen_on):
    """[(epoch, 'start'|'stop')] from a release series. Empty is not 'no generation'."""
    if not series or gen_on is None:
        return []
    out, prev = [], None
    for row in series:
        try:
            t, v = row[0], row[1]
        except (TypeError, IndexError):
            continue
        if v is None:
            continue
        cur = v >= gen_on
        if prev is not None and cur != prev:
            out.append((float(t), "start" if cur else "stop"))
        prev = cur
    return out


def _nearest(events, kind, to):
    cands = [t for t, k in events if k == kind]
    if not cands:
        return None
    return min(cands, key=lambda t: abs(t - to))


def compare_release(zone_id, zone_name, old_series, new_series, gen_on, tz,
                    window_start=None):
    """Generation start/stop times moving. The single most consequential input."""
    changes = []
    old_ev = _events(old_series, gen_on)
    new_ev = _events(new_series, gen_on)
    anchor = window_start or (old_ev[0][0] if old_ev else None)
    if anchor is None:
        return changes

    for kind, label in (("stop", "Generation stop"), ("start", "Generation start")):
        o = _nearest(old_ev, kind, anchor)
        n = _nearest(new_ev, kind, anchor)
        if o is None and n is None:
            continue
        if o is None or n is None:
            # An event appearing or vanishing is always material: the shape of the day
            # changed, not just its timing.
            changes.append(DeltaChange(
                field_name="generation_" + kind, label=label,
                was=o, now=n, was_label=_fmt(o, tz), now_label=_fmt(n, tz),
                materiality=Materiality.MATERIAL, zone_id=zone_id,
                why=("The %s that was forecast at %s is no longer in the schedule."
                     % (label.lower(), _fmt(o, tz))) if n is None else
                    ("A %s has appeared in the forecast at %s."
                     % (label.lower(), _fmt(n, tz)))))
            continue
        shift = (n - o) / 60.0
        if abs(shift) < Threshold.GENERATION_SHIFT_MINUTES:
            if abs(shift) >= 5:
                changes.append(DeltaChange(
                    field_name="generation_" + kind, label=label, was=o, now=n,
                    was_label=_fmt(o, tz), now_label=_fmt(n, tz),
                    materiality=Materiality.INFORMATIONAL, zone_id=zone_id,
                    why="%s moved %d minutes." % (label, round(abs(shift)))))
            continue
        changes.append(DeltaChange(
            field_name="generation_" + kind, label=label, was=o, now=n,
            was_label=_fmt(o, tz), now_label=_fmt(n, tz),
            materiality=Materiality.MATERIAL, zone_id=zone_id,
            why="%s %s %d minutes %s, at %s."
                % (label, "moved", round(abs(shift)),
                   "later" if shift > 0 else "earlier", _fmt(n, tz))))
    return changes


def compare_observation(zone_id, label, field, old_ob, new_ob, tz):
    """Flow and stage. Proportional for discharge, absolute for depth."""
    changes = []
    o = (old_ob or {}).get("value")
    n = (new_ob or {}).get("value")
    o_state = (old_ob or {}).get("state")
    n_state = (new_ob or {}).get("state")

    # §91 — a source going stale or erroring is itself a change, and never silent.
    if o_state != n_state and n_state in ("stale", "unknown", "error"):
        changes.append(DeltaChange(
            field_name=field, label=label, was=o_state, now=n_state,
            was_label=str(o_state), now_label=str(n_state),
            materiality=Materiality.NOTABLE, zone_id=zone_id,
            why="%s is now %s. Confidence in this plan has dropped."
                % (label, {"stale": "stale", "unknown": "unavailable",
                           "error": "failing"}.get(n_state, n_state))))
        return changes

    if o is None or n is None or not isinstance(o, (int, float)) or \
            not isinstance(n, (int, float)):
        return changes

    if field == "flow":
        if o <= 0:
            return changes
        frac = abs(n - o) / float(o)
        if frac >= Threshold.FLOW_CHANGE_FRACTION:
            changes.append(DeltaChange(
                field_name=field, label=label, was=o, now=n,
                was_label="%s cfs" % round(o), now_label="%s cfs" % round(n),
                materiality=Materiality.MATERIAL, zone_id=zone_id,
                why="Flow %s from %s to %s cfs."
                    % ("rose" if n > o else "dropped", round(o), round(n))))
    elif field == "stage":
        if abs(n - o) >= Threshold.STAGE_CHANGE_FEET:
            changes.append(DeltaChange(
                field_name=field, label=label, was=o, now=n,
                was_label="%.1f ft" % o, now_label="%.1f ft" % n,
                materiality=Materiality.MATERIAL, zone_id=zone_id,
                why="Stage %s %.1f ft, now %.1f."
                    % ("rose" if n > o else "fell", abs(n - o), n)))
    return changes


def compare_safety(old_claims, new_claims, tz):
    """Safe-exit times. THE ASYMMETRY IS THE POINT.

    Later is good news and merely notable. Earlier is material every time, at five
    minutes, because the person is standing in the river acting on the old number and the
    cost of a missed alert here is not a worse morning.
    """
    changes = []
    old_by = {c.get("kind"): c for c in (old_claims or []) if c.get("kind")}
    for c in (new_claims or []):
        kind = c.get("kind")
        if kind not in ("safe_exit", "generation_start", "arrival"):
            continue
        o = old_by.get(kind)
        if not o:
            continue
        ot, nt = o.get("at"), c.get("at")
        if not ot or not nt:
            continue
        shift = (nt - ot) / 60.0
        if shift <= -Threshold.SAFE_EXIT_EARLIER_MINUTES:
            changes.append(DeltaChange(
                field_name="safety_" + kind, label="Safe exit", was=ot, now=nt,
                was_label=_fmt(ot, tz), now_label=_fmt(nt, tz),
                materiality=Materiality.MATERIAL, zone_id=c.get("zone_id", ""),
                why="Get off the water %d minutes earlier than planned — %s, not %s."
                    % (round(abs(shift)), _fmt(nt, tz), _fmt(ot, tz))))
        elif shift >= Threshold.SAFE_EXIT_LATER_MINUTES:
            changes.append(DeltaChange(
                field_name="safety_" + kind, label="Safe exit", was=ot, now=nt,
                was_label=_fmt(ot, tz), now_label=_fmt(nt, tz),
                materiality=Materiality.NOTABLE, zone_id=c.get("zone_id", ""),
                why="You have %d more minutes than planned — safe until %s."
                    % (round(shift), _fmt(nt, tz))))
    return changes


def compare_itinerary(old_plan, new_plan, tz):
    """The plan itself: the sequence, the move times, and the opportunity."""
    changes = []
    o_it = (old_plan or {}).get("itinerary") or {}
    n_it = (new_plan or {}).get("itinerary") or {}
    o_seq = o_it.get("zone_sequence") or []
    n_seq = n_it.get("zone_sequence") or []

    if o_seq and n_seq and o_seq != n_seq:
        changes.append(DeltaChange(
            field_name="zone_sequence", label="Where to fish",
            was=o_seq, now=n_seq,
            was_label=" → ".join(o_seq), now_label=" → ".join(n_seq),
            materiality=Materiality.MATERIAL,
            why="The plan now goes %s instead of %s."
                % (" then ".join(n_seq), " then ".join(o_seq))))

    o_w = o_it.get("windows") or []
    n_w = n_it.get("windows") or []
    for i in range(min(len(o_w), len(n_w))):
        os_, ns_ = o_w[i].get("start"), n_w[i].get("start")
        if not os_ or not ns_:
            continue
        shift = (ns_ - os_) / 60.0
        if abs(shift) >= Threshold.MOVE_SHIFT_MINUTES:
            changes.append(DeltaChange(
                field_name="window_%d_start" % i, label="Fishing window",
                was=os_, now=ns_, was_label=_fmt(os_, tz), now_label=_fmt(ns_, tz),
                materiality=Materiality.MATERIAL,
                zone_id=n_w[i].get("zone", ""),
                why="Start at %s instead of %s." % (_fmt(ns_, tz), _fmt(os_, tz))))

    o_op = (old_plan or {}).get("opportunity")
    n_op = (new_plan or {}).get("opportunity")
    if isinstance(o_op, (int, float)) and isinstance(n_op, (int, float)):
        d = n_op - o_op
        if abs(d) >= Threshold.OPPORTUNITY_POINTS:
            changes.append(DeltaChange(
                field_name="opportunity", label="Opportunity",
                was=o_op, now=n_op, was_label="%.0f" % o_op, now_label="%.0f" % n_op,
                materiality=Materiality.NOTABLE,
                why="Opportunity %s from %.0f to %.0f."
                    % ("improved" if d > 0 else "dropped", o_op, n_op)))
    return changes


def compute(old_snapshot, new_snapshot, old_plan=None, new_plan=None, tz=None,
            gen_on_by_river=None):
    """The PlanDelta between two snapshots and the plans they produced. §10, §11."""
    from ..tz import zone as tzf
    tz = tz or tzf("America/Chicago")
    d = PlanDelta(from_snapshot=(old_snapshot or {}).get("id", ""),
                  to_snapshot=(new_snapshot or {}).get("id", ""))

    old_zones = (old_snapshot or {}).get("zones") or {}
    new_zones = (new_snapshot or {}).get("zones") or {}
    # Only zones the PLAN uses. A gauge moving on water nobody is going to is not news.
    used = list(((new_plan or {}).get("itinerary") or {}).get("zone_sequence") or []) or \
        list(new_zones)

    gen_on_by_river = gen_on_by_river or {}
    win = None
    nw = ((new_plan or {}).get("itinerary") or {}).get("windows") or []
    if nw:
        win = nw[0].get("start")

    for zid in used:
        o, n = old_zones.get(zid) or {}, new_zones.get(zid) or {}
        if not o or not n:
            continue
        name = zid
        river = n.get("river_id") or o.get("river_id") or ""
        gen_on = gen_on_by_river.get(river)
        if gen_on is None:
            from ..sources.registry import water_for
            gen_on = water_for(river).get("gen_on")
        d.changes.extend(compare_release(
            zid, name,
            ((o.get("generation_forecast") or {}).get("value")),
            ((n.get("generation_forecast") or {}).get("value")),
            gen_on, tz, window_start=win))
        d.changes.extend(compare_observation(zid, "Flow", "flow",
                                             o.get("flow"), n.get("flow"), tz))
        d.changes.extend(compare_observation(zid, "Stage", "stage",
                                             o.get("stage"), n.get("stage"), tz))

    d.changes.extend(compare_safety((old_plan or {}).get("safety"),
                                    (new_plan or {}).get("safety"), tz))
    d.changes.extend(compare_itinerary(old_plan, new_plan, tz))

    # SAFETY LEADS. Where several things moved, the headline must be the one that can
    # hurt somebody, not the one that happens to sort first.
    d.changes.sort(key=lambda c: (
        -Materiality.rank(c.materiality),
        0 if c.field_name.startswith("safety_") else 1))

    d.was_itinerary = (old_plan or {}).get("itinerary")
    d.now_itinerary = (new_plan or {}).get("itinerary")
    d.new_plan_id = (new_plan or {}).get("id", "")
    return d.finalise()
