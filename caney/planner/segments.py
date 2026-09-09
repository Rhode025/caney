"""
Turning a won itinerary into instructions. §9, §15, §37, §38, §39.

This is the product. Everything upstream decides WHERE and WHEN; this decides what the
reader is actually told to do, minute by minute, and — just as importantly — WHY each
instruction exists and what would change it.

Four things it must get right:

* §15 a move is justified in terms of what changes, never "move to Zone B".
* §37 technique is per SEGMENT, not per plan, and carries its own switch trigger.
* §38 triggers are explicit and are derived from the deterministic claim book and the
  hourly weather, not written as prose by a model.
* §39 there is always a backup, because plans fall apart.
"""
import datetime as _dt

from ..domain.claim import SafetyKind
from ..domain.opportunity import FishingSegment, SegmentType
from ..domain.plan import StepKind, TimelineStep
from ..domain.method import TackleMethod
from ..species.profiles import profile
from ..species import techniques as conv
from . import features as feature_pick

#: How long before the first cast to be at the ramp.
LAUNCH_LEAD_MINUTES = 15


def _fmt(ep, tz):
    return _dt.datetime.fromtimestamp(ep, tz).strftime("%-I:%M %p")


def build(itin_candidate, zones, snaps, species, craft, tz, book, claims_by_zone,
          statics_by_zone, req):
    """[FishingSegment] for the winning candidate, in time order."""
    windows = itin_candidate.windows
    transitions = itin_candidate.transitions
    segs = []
    if not windows:
        return segs

    first = windows[0]
    zone0 = zones[first.zone_id]
    launch = pick_access(zone0, craft)
    launch_at = first.start - LAUNCH_LEAD_MINUTES * 60
    segs.append(FishingSegment(
        type=SegmentType.LAUNCH, start=launch_at, end=first.start,
        zone_id=zone0.id, zone_name=zone0.name,
        access_id=(launch or {}).get("id", ""),
        instructions="Launch at %s" % ((launch or {}).get("name") or zone0.name),
        reason=((launch or {}).get("note") or "") or
               "No verified access is recorded for this craft — check locally before you go.",
        location_confidence=zone0.location_confidence().score,
        location_evidence=(launch or {}).get("evidence", ""),
        kind="heuristic"))

    for i, w in enumerate(windows):
        zone = zones[w.zone_id]
        snap = snaps[w.zone_id]
        st = statics_by_zone.get(w.zone_id) or {}
        claims = [c for c in book.for_zone(zone.id)]
        tech = technique_for(species, zone, snap, w, st, method=req.method)
        trigs = triggers_for(zone, snap, w, claims, tz, species, st)

        instruction, read = zone.holds_parts(species)
        month = _dt.datetime.fromtimestamp(w.start, tz).month

        # §26 — name the FEATURE, and split the window when the release changes which
        # feature is right (§89). One leg is the common case; two is the case the zone
        # layer could not express at all.
        legs = feature_pick.order_for_window(zone.id, species, month, snap,
                                             w.start, w.end) or []
        if not legs:
            legs = [{"feature": None, "fit": None, "start": w.start, "end": w.end,
                     "why": ""}]

        for li, leg in enumerate(legs):
            feat = leg["feature"]
            if li > 0:
                segs.append(FishingSegment(
                    type=SegmentType.MOVE_FEATURE, start=leg["start"], end=leg["start"],
                    zone_id=zone.id, zone_name=zone.name,
                    instructions="Move to %s" % (feat.name if feat else "the next spot"),
                    reason=leg.get("why", ""),
                    feature_id=feat.id if feat else "",
                    feature_name=feat.name if feat else "",
                    kind="forecast"))
            segs.append(FishingSegment(
                type=SegmentType.FISH, start=leg["start"], end=leg["end"],
                zone_id=zone.id, zone_name=zone.name,
                access_id=(pick_access(zone, craft) or {}).get("id", ""),
                instructions=(("%s — %s" % (feat.name, feat.holds(species)))
                              if feat and feat.holds(species) else
                              (feat.name if feat else instruction)),
                reason=_join(read, window_reason(w, zone, species, snap)),
                expected_score=(round(sum(w.samples) / len(w.samples), 1)
                                if w.samples else None),
                confidence=w.confidence,
                location_confidence=zone.location_confidence().score,
                location_evidence=zone.location_confidence().tactical_level,
                technique=tech, triggers=trigs, kind="heuristic",
                feature_id=feat.id if feat else "",
                feature_name=feat.name if feat else "",
                feature_type=feat.feature_type if feat else "",
                feature_confidence=feat.confidence if feat else "",
                feature_fit=leg.get("fit"),
                feature_holding=feat.holds(species) if feat else ""))

        # A technique change INSIDE the window, where a deterministic event lands in it.
        for t in trigs:
            if t.get("at") and w.start < t["at"] < w.end and t.get("changes_technique"):
                segs.append(FishingSegment(
                    type=SegmentType.CHANGE_TECHNIQUE, start=t["at"], end=w.end,
                    zone_id=zone.id, zone_name=zone.name,
                    instructions=t["then"], reason=t["if"],
                    claim_ids=t.get("claim_ids", []), kind=t.get("kind", "forecast")))

        if i < len(windows) - 1:
            nxt = windows[i + 1]
            tr = transitions[i]
            move_start = w.end
            move_end = min(nxt.start, w.end + tr.minutes * 60)
            segs.append(FishingSegment(
                type=SegmentType.MOVE, start=move_start, end=move_end,
                zone_id=nxt.zone_id, zone_name=zones[nxt.zone_id].name,
                instructions="Move to %s" % zones[nxt.zone_id].name,
                reason=move_reason(w, nxt, tr, zones, tz),
                kind="heuristic"))
            idle = (nxt.start - move_end) / 60.0
            if idle > 5:
                segs.append(FishingSegment(
                    type=SegmentType.WAIT, start=move_end, end=nxt.start,
                    zone_id=nxt.zone_id, zone_name=zones[nxt.zone_id].name,
                    instructions="%d minutes spare — rig for the next zone" % round(idle),
                    reason=("You arrive before the next window opens. That is deliberate: "
                            "being in position early costs nothing, being late costs the "
                            "window."),
                    kind="heuristic"))

    # Safety exits, from the claim book, for every zone in the plan.
    for w in windows:
        for c in book.for_zone(w.zone_id):
            if c.kind != SafetyKind.SAFE_EXIT or c.at is None:
                continue
            if not (windows[0].start - 3600 <= c.at <= windows[-1].end + 5400):
                continue
            segs.append(FishingSegment(
                type=SegmentType.SAFETY_EXIT, start=c.at, end=c.at,
                zone_id=w.zone_id, zone_name=zones[w.zone_id].name,
                instructions=c.text,
                reason=("This uses the EARLIEST modelled arrival minus a 30-minute margin, "
                        "not the typical one."),
                claim_ids=[c.id], kind="safety"))

    last = windows[-1]
    segs.append(FishingSegment(
        type=SegmentType.END, start=last.end, end=last.end,
        zone_id=last.zone_id, zone_name=zones[last.zone_id].name,
        instructions="Primary opportunity is effectively over",
        reason=end_reason(last, zones[last.zone_id], snaps[last.zone_id], book, req),
        kind="heuristic"))

    segs.sort(key=lambda s: (s.start, 0 if s.type == SegmentType.SAFETY_EXIT else 1))
    return segs


# ── §37 · technique, per segment ────────────────────────────────────────────

def technique_for(species, zone, snap, window, statics, method=TackleMethod.EITHER):
    """The primary presentation for THIS window, plus the trigger that changes it.

    §20/§21 — method-aware since 3.0. The CONDITION KEY is chosen first and identically
    for both methods, because what the water is doing does not depend on what you are
    throwing; only the answer to it does. Both answers are carried, so the UI can offer
    the other without a second request.
    """
    prof = profile(species)
    units, gen_known = statics.get("units"), statics.get("gen_known")
    low_light = _low_light(snap, window)
    muddy = _clarity(snap) == "muddy"
    stillwater = zone.kind in _STILLWATER_KINDS

    key, why = "default", []
    if gen_known and units is not None and units >= 2:
        key = "heavy_current"
        why.append("%d units of push means depth and a big profile" % units)
    elif gen_known and units == 0 and prof.current.get("needs"):
        key = "slack"
        why.append("no generation — go find them deep instead of on a seam")
    elif stillwater and low_light:
        key = "low_light"
        why.append("still water at low light — fish the top of the column")
    elif low_light:
        key = "low_light"
        why.append("low light is the window, so fish the top of the column")
    elif stillwater:
        key = "slack"
        why.append("no current here — the cover is the structure, not the seam")
    if muddy:
        why.append("stained water — go bigger and darker than the size below suggests")

    backup_key = "slack" if key in ("heavy_current", "default") else "default"
    fly = dict(prof.techniques.get(key) or prof.techniques["default"])
    fly_b = dict(prof.techniques.get(backup_key) or prof.techniques["default"])
    conv_t = conv.for_method(species, key, TackleMethod.CONVENTIONAL)
    conv_b = conv.for_method(species, backup_key, TackleMethod.CONVENTIONAL)

    show_conv = conv.prefer_conventional(method, species, key, stillwater) and conv_t
    t = dict(conv_t) if show_conv else dict(fly)
    t["method"] = TackleMethod.CONVENTIONAL if show_conv else TackleMethod.FLY
    t["method_label"] = TackleMethod.LABEL[t["method"]]
    # §21 — target structure is a fly-table gap; the feature layer is the better source
    # for it and fills in where the table has none.
    t.setdefault("target_structure", "")
    b = dict(conv_b) if show_conv else dict(fly_b)
    t["why"] = "; ".join(why) or "the standard read for these conditions"
    t["backup_presentation"] = {
        "name": b.get("primary_fly") or b.get("primary_lure", ""),
        "fly": b.get("primary_fly", ""), "lure": b.get("primary_lure", ""),
        "size": b.get("primary_size", ""), "color": b.get("primary_color", ""),
        "line": b.get("line", ""), "presentation": b.get("presentation", ""),
        "depth": b.get("depth", ""), "retrieve": b.get("retrieve", ""),
    }
    # The other method, so the UI can offer it without another request (§20).
    other = dict(fly) if show_conv else (dict(conv_t) if conv_t else None)
    if other:
        other["method"] = TackleMethod.FLY if show_conv else TackleMethod.CONVENTIONAL
        other["method_label"] = TackleMethod.LABEL[other["method"]]
    t["alternate_method"] = other
    t["switch_trigger"] = _switch_trigger(key, prof, zone)
    t["condition_key"] = key
    return t


_STILLWATER_KINDS = ("reservoir_arm", "creek_arm", "backwater", "flat", "point",
                     "grass_bed", "riprap")


def _switch_trigger(key, prof, zone):
    if key == "heavy_current":
        return ("If the current slackens — a unit comes off, or the seam stops holding a "
                "line — drop to the backup and work it deeper and slower.")
    if key == "slack":
        return ("If they start generating, switch to the current presentation and get on "
                "the seam before the bait does.")
    if key == "low_light":
        return ("Once the sun is on the water, go subsurface: same fly family, heavier "
                "line, deeper.")
    return ("If forty minutes pass with nothing, change one variable — depth first, then "
            "size, then colour. Not all three.")


# ── §38 · explicit condition triggers ───────────────────────────────────────

def triggers_for(zone, snap, window, claims, tz, species, statics):
    """[{if, then, at, kind, claim_ids, changes_technique}] for this window."""
    out = []
    for c in claims:
        if c.at is None:
            continue
        if not (window.start - 1800 <= c.at <= window.end + 1800):
            continue
        if c.kind == SafetyKind.GENERATION_STOP:
            out.append({"if": "generation stops (%s)" % _fmt(c.at, tz), "at": c.at,
                        "then": ("The seam dies within the hour. Go deeper and slower on "
                                 "the same water, or move to the next zone."),
                        "kind": "forecast", "claim_ids": [c.id], "changes_technique": True})
        elif c.kind == SafetyKind.GENERATION_START:
            out.append({"if": "generation starts (%s)" % _fmt(c.at, tz), "at": c.at,
                        "then": ("Current arrives on the schedule above. Get on the seam. "
                                 "If you are wading, the safe-exit step is the one that "
                                 "matters, not this one."),
                        "kind": "forecast", "claim_ids": [c.id], "changes_technique": True})
        elif c.kind == SafetyKind.RELEASE_ARRIVAL:
            out.append({"if": "the released water reaches this reach", "at": c.at,
                        "then": c.text, "kind": "deterministic", "claim_ids": [c.id],
                        "changes_technique": True})

    rows = snap.weather_window(window.start, window.end)
    if rows:
        # Wind is a weather forecast value, not a water measurement, and a missing
        # hour must not lower the max below what the other hours actually say.
        wind = max((r.get("wind_speed") or 0) for r in rows)  # not a measurement
        gust = max((r.get("wind_gust") or 0) for r in rows)  # not a measurement
        if wind >= 15:
            out.append({"if": "wind holds above %d mph" % round(wind), "at": None,
                        "then": ("Shorten the leader, go heavier, and fish the bank the "
                                 "wind is pushing into rather than fighting it."),
                        "kind": "forecast", "claim_ids": [], "changes_technique": True})
        if gust >= 28:
            out.append({"if": "gusts reach %d mph on open water" % round(gust), "at": None,
                        "then": "Get off the main lake and fish the protected arms.",
                        "kind": "forecast", "claim_ids": [], "changes_technique": False})
        storm = [r for r in rows if r.get("thunderstorm")]
        if storm:
            out.append({"if": "thunderstorms reach the water", "at": storm[0].get("epoch"),
                        "then": "Terminate the plan. Get off the water and off the bank.",
                        "kind": "safety", "claim_ids": [], "changes_technique": False})
        clouds = [r.get("cloud_cover") for r in rows if r.get("cloud_cover") is not None]
        if clouds and max(clouds) - min(clouds) >= 45:
            out.append({"if": "the cloud breaks and the sun gets on the water", "at": None,
                        "then": ("Move off the flat into the shade lines and the deeper "
                                 "edge of the same structure."),
                        "kind": "forecast", "claim_ids": [], "changes_technique": True})
    return out


# ── reasons ─────────────────────────────────────────────────────────────────

def _join(*parts):
    """Join sentence fragments so the second one starts like a sentence."""
    out = []
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        if out:
            p = p[0].upper() + p[1:]
            if not out[-1].endswith((".", "!", "?")):
                out[-1] += "."
        out.append(p)
    text = " ".join(out)
    return text if not text or text.endswith((".", "!", "?")) else text + "."


def window_reason(w, zone, species, snap):
    ref = zone.species_profiles.get(species)
    bits = []
    if w.samples:
        bits.append("peaks at %.0f and never drops below %.0f across the %d minutes"
                    % (w.peak_score, w.floor_score, round(w.duration_minutes)))
    if ref and ref.pattern:
        bits.append(ref.pattern)
    return "; ".join(bits)


def move_reason(before, after, transition, zones, tz):
    """§15 — say what CHANGES, not just where to go."""
    drop = before.samples[-1] if before.samples else 0.0
    rise = after.samples[0] if after.samples else 0.0
    to_name = zones[after.zone_id].name
    if rise > drop + 4:
        core = ("%s is falling away — it is down to about %.0f by then, while %s is running "
                "%.0f and holds it for another %d minutes."
                % (zones[before.zone_id].name, drop, to_name, rise,
                   round(after.duration_minutes)))
    else:
        core = ("%s is finished by then. %s is the best remaining water inside your window "
                "and holds for another %d minutes."
                % (zones[before.zone_id].name, to_name, round(after.duration_minutes)))
    cost = ("%d minutes %s — %s"
            % (round(transition.minutes),
               {"known": "on a known route", "estimated": "estimated, no verified route",
                "unknown": "route unknown"}.get(transition.provenance, transition.provenance),
               transition.detail or transition.mode))
    return core + " The move costs " + cost


def end_reason(last, zone, snap, book, req):
    arr = next((c for c in book.for_zone(zone.id)
                if c.kind == SafetyKind.RELEASE_ARRIVAL and c.at), None)
    if arr and arr.at <= last.end + 1800:
        return "The released water is in this reach by now — the fishery you planned is gone."
    if snap.sunrise.ok and last.end > snap.sunrise.value + 10800:
        return "The low-light edge is long gone and the light is against you."
    if last.samples and last.samples[-1] < last.peak_score * 0.8:
        return ("The window has fallen to about %.0f from a peak of %.0f. Past this you are "
                "fishing memory, not conditions." % (last.samples[-1], last.peak_score))
    if last.end < req.end - 900:
        return ("You have time left, and nothing worth spending it on: no candidate scores "
                "well enough in the rest of your window to be worth the fuel.")
    return "End of the requested window."


def pick_access(zone, craft):
    opts = [a for a in zone.access if a.serves(craft)] or list(zone.access)
    if not opts:
        return None
    opts.sort(key=lambda a: (not a.verified,
                             a.river_miles_from_dam or 0))  # not a measurement (sort key)
    a = opts[0]
    return {"name": a.name, "note": a.note, "lat": a.lat, "lon": a.lon,
            "verified": a.verified, "source": a.source, "id": a.id,
            "evidence": a.evidence_level}


def _low_light(snap, window):
    if not (snap.sunrise.ok and snap.sunset.ok):
        return False
    dawn = (snap.sunrise.value - 2400, snap.sunrise.value + 5400)
    dusk = (snap.sunset.value - 5400, snap.sunset.value + 2400)
    ov = (max(0, min(dawn[1], window.end) - max(dawn[0], window.start)) +
          max(0, min(dusk[1], window.end) - max(dusk[0], window.start)))
    return ov >= 0.4 * min(window.end - window.start, 7200)


def _clarity(snap):
    if snap.clarity.ok:
        return str(snap.clarity.value)
    tr = snap.flow_trend.value if snap.flow_trend.ok else None
    if tr == "rising":
        return "stained"
    return "unknown"


def to_timeline(segments, tz):
    """A TimelineStep view of the segments, for consumers that already speak that shape."""
    kindmap = {
        SegmentType.LAUNCH: StepKind.HEURISTIC,
        SegmentType.FISH: StepKind.HEURISTIC,
        SegmentType.MOVE: StepKind.HEURISTIC,
        SegmentType.WAIT: StepKind.HEURISTIC,
        SegmentType.CHANGE_TECHNIQUE: StepKind.FORECAST,
        SegmentType.SAFETY_EXIT: StepKind.SAFETY,
        SegmentType.OPTIONAL_BACKUP: StepKind.HEURISTIC,
        SegmentType.END: StepKind.HEURISTIC,
    }
    out = []
    for s in segments:
        out.append(TimelineStep(
            at=s.start, at_label=_fmt(s.start, tz),
            until=s.end if s.end > s.start else None,
            title=s.instructions, detail=s.reason,
            kind=(StepKind.SAFETY if s.type == SegmentType.SAFETY_EXIT
                  else kindmap.get(s.type, StepKind.HEURISTIC)),
            zone_id=s.zone_id, claim_ids=s.claim_ids,
            branches=[{"if": t["if"], "then": t["then"], "claim_ids": t.get("claim_ids", [])}
                      for t in (s.triggers or [])]))
    return out
