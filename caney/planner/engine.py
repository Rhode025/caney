"""
The ranking pipeline and plan assembly. §30, §8, §10, §38.

    1. candidate fishing zones for the species        (zones/registry, geography only)
    2. eliminate: craft, access, season, regulation, unsafe   ← GATES, not scores
    3. build the requested-time snapshot per candidate
    4. score with the species weights
    5. apply research evidence                        (inside the research component)
    6. confidence penalty                             (rank_key)
    7. data-freshness penalty                         (inside confidence)
    8. rank
    9. exact plan for the winner
   10. 2-3 alternatives WITH the reason they lost

Step 2 is the part that is easy to get wrong. Craft is an ELIGIBILITY GATE (§6): a zone
that cannot be waded is removed from a wade request, it does not merely score lower.
"""
import datetime as _dt
import time
from ..tz import zone as _tz

from ..domain.claim import SafetyKind
from ..domain.method import TackleMethod
from ..domain.observation import DataState
from ..domain.opportunity import FishingItinerary, SegmentType
from ..domain.plan import (FishingPlan, ScoreLine, Technique, Verdict)
from ..domain.zone import Craft
from ..species.profiles import DISPLAY, profile
from ..sources.snapshots import localize
from ..version import (PLANNER_VERSION, RESEARCH_VERSION, SPECIES_MODEL_VERSION,
                       ZONE_MODEL_VERSION)
from ..zones.registry import ZONES, zones_for_species
from ..routing.provider import build_provider as build_routing
from . import itinerary as itin_search
from . import logistics
from . import opportunity, scoring, segments, timeline, transitions, utility
from .confidence import confidence, confidence_label, rank_key
from .window import best_window

SITE_TZ = "America/Chicago"


class Request:
    """What the user asked for. §4, §5, §6 — and, since 3.0, §14.

    Two shapes, because both are things people say:

        Request(species, start, end, craft)
            "I can fish 6 to 10." The 2.1 contract, unchanged. No travel is modelled;
            the window IS the availability.

        Request(species, depart_after=…, return_by=…, origin=(lat, lon), craft=…)
            "I can leave at 5 and need to be home by 11:30." The day. Travel, rigging and
            the run to the water come out of it per candidate (§19), and `start`/`end`
            become the widest fishing bounds the day could possibly support.

    `start` and `end` still mean "the outer bounds of any fishing this request could do",
    which is what every downstream consumer already assumed they meant. The per-zone
    narrowing lives in the Envelope, not here — a single global window would be wrong the
    moment two candidates are different distances away.
    """

    def __init__(self, species, start=None, end=None, craft=Craft.ANY, tz=SITE_TZ,
                 now=None, origin=None, method=TackleMethod.EITHER,
                 depart_after=None, return_by=None, max_drive_minutes=None,
                 routing=None, preferences=None):
        self.species = species
        self.craft = craft or Craft.ANY
        self.method = TackleMethod.normalise(method)
        self.tz_name = tz
        self.tz = _tz(tz)
        self.now = now or time.time()
        self.origin = tuple(origin) if origin else None
        self.max_drive_minutes = (float(max_drive_minutes)
                                  if max_drive_minutes else None)
        self.routing = routing if routing is not None else build_routing()
        self.preferences = dict(preferences or {})

        door_to_door = depart_after is not None and return_by is not None
        if door_to_door:
            self.availability = logistics.Availability(
                depart_after=float(depart_after), return_by=float(return_by),
                fish_after=float(start) if start else None,
                fish_before=float(end) if end else None,
                window_only=False)
            self.start, self.end = self.availability.clamp(
                float(depart_after), float(return_by))
        else:
            if start is None or end is None:
                raise ValueError("a request needs either (start, end) or "
                                 "(depart_after, return_by)")
            self.start, self.end = float(start), float(end)
            self.availability = logistics.Availability(
                depart_after=self.start, return_by=self.end, window_only=True)

        if self.end <= self.start:
            raise ValueError("requested window ends before it starts")

    @property
    def door_to_door(self):
        return not self.availability.window_only and self.origin is not None

    @property
    def month(self):
        return _dt.datetime.fromtimestamp(self.start, self.tz).month

    @property
    def days_out(self):
        d0 = _dt.datetime.fromtimestamp(self.now, self.tz).date()
        d1 = _dt.datetime.fromtimestamp(self.start, self.tz).date()
        return (d1 - d0).days

    def to_json(self):
        return {"start": round(self.start), "end": round(self.end),
                "iso": _dt.datetime.fromtimestamp(self.start, self.tz).isoformat(),
                "tz": self.tz_name, "days_out": self.days_out,
                "craft": self.craft, "method": self.method,
                "species": self.species,
                "origin": list(self.origin) if self.origin else None,
                "max_drive_minutes": self.max_drive_minutes,
                "door_to_door": self.door_to_door,
                "availability": self.availability.to_json()}


class Rejected:
    def __init__(self, zone_id, name, reason):
        self.zone_id, self.name, self.reason = zone_id, name, reason

    def to_json(self):
        return {"zone_id": self.zone_id, "name": self.name, "reason": self.reason,
                "eliminated": True}


def eligible(req, snaps):
    """Step 1 + 2. Returns ([(zone, envelope)], [Rejected]).

    3.0 adds the travel gate (§19). A zone the day cannot reach is ELIMINATED here, with
    the arithmetic in the reason, rather than scored and quietly beaten later — "you
    cannot get there and back today" is a different statement from "it fishes worse", and
    a reader deserves to be told which one applies.
    """
    keep, out = [], []
    for z in zones_for_species(req.species, None):
        ref = z.species_profiles.get(req.species)
        if not z.supports_craft(req.craft):
            out.append(Rejected(z.id, z.name,
                                "no access on this water serves a %s"
                                % Craft.LABEL.get(req.craft, req.craft)))
            continue
        if ref and not ref.in_season(req.month):
            out.append(Rejected(z.id, z.name,
                                "outside the seasonal pattern for %s here"
                                % DISPLAY[req.species]["full"].lower()))
            continue
        snap = snaps.get(z.id)
        if snap is None:
            out.append(Rejected(z.id, z.name, "no snapshot could be built for this water"))
            continue
        unsafe = _unsafe(z, snap, req)
        if unsafe:
            out.append(Rejected(z.id, z.name, unsafe))
            continue
        env = logistics.envelope(z, req.availability, req.origin, req.craft, req.routing)
        if req.max_drive_minutes and env.drive_out is not None and \
                env.drive_out.minutes > req.max_drive_minutes:
            out.append(Rejected(z.id, z.name,
                                "a %d-minute drive, past the %d you allowed"
                                % (round(env.drive_out.minutes),
                                   round(req.max_drive_minutes))))
            continue
        if not env.viable:
            out.append(Rejected(z.id, z.name,
                                env.reason or "the day leaves no fishable time here"))
            continue
        keep.append((z, env))
    return keep, out


def _unsafe(zone, snap, req):
    """Hard safety elimination. Fails CLOSED — an unknown here removes the candidate.

    The wade gate is deliberately DIFFERENT on the two kinds of water, because the thing
    that hurts you is different:

      * On a TAILWATER the danger is the release, not today's level. A downstream gauge
        reading high because yesterday's generation is still passing says nothing about
        whether you can wade at the dam this morning — so the gate is the release
        schedule. No forecast at all removes the candidate; generating across the whole
        window removes it; anything else is a scoring problem, not an eligibility one.
      * On a FREE-FLOWING river the gauge IS the river, so the measured no-wade threshold
        from riverlib.WATER_MODEL applies directly.

    Getting this backwards eliminated the entire calibrated Caney trout fishery on a
    Stonewall reading taken fifteen miles below the dam.
    """
    rows = snap.weather_window(req.start, req.end)
    if rows and all(r.get("thunderstorm") for r in rows):
        return "thunderstorms forecast across the entire requested window"

    if req.craft != Craft.WADE:
        return None

    if zone.tailwater:
        fc = snap.generation_forecast
        if not fc.ok:
            return ("wade request on a tailwater with no release forecast — this plan "
                    "cannot bound the wade window, so it will not offer one")
        lead = ((snap.arrival or {}).get("first") or {}).get("earliest_h") or 0.0
        wet = 0.0
        for t, v in (fc.value or []):
            if v is None:
                continue
            on_cfs = _cfg(zone).get("gen_on")
            if on_cfs is None or v < on_cfs:
                continue
            a = t + lead * 3600.0
            wet += max(0.0, min(a + 3600.0, req.end) - max(a, req.start))
        if wet >= (req.end - req.start) * 0.95:
            return "the release runs through this entire window — the reach is not wadeable"
        return None

    if snap.flow.ok:
        import riverlib
        m = riverlib.WATER_MODEL.get(zone.hydrology_river) or {}
        no = m.get("no_wade")
        if no and snap.flow.value > no * 1.35:
            return ("flow is %s cfs, far above the measured no-wade threshold of %s for "
                    "this reach" % (scoring._n(snap.flow.value), scoring._n(no)))
    return None


def candidates(req, snaps, book, claims_by_zone):
    """Step 1-8. Each entry carries its OPPORTUNITY WINDOWS, not one averaged score.

    The 2.0 pipeline scored a zone once, over the user's whole availability, and ranked on
    that mean. §3 is the argument against it and §57 is the fixture: a candidate that peaks
    at 96 for ninety minutes must not lose to one that sits at 77 all morning. So a
    candidate is now a set of windows, each with its own quality, duration and utility, and
    the ranking is over windows rather than over averages.
    """
    pairs, rejected = eligible(req, snaps)
    scored = []
    req_date = _dt.datetime.fromtimestamp(req.start, req.tz).date()
    for z, env in pairs:
        # Localise to the DATE being planned: sun times and moon belong to that day.
        snap = localize(snaps[z.id], req_date)
        cfg = _cfg(z)
        units, gen_known = _units(snap, cfg)
        claims = claims_by_zone.get(z.id) or []
        # Compute the hourly series and the static fits ONCE per candidate; everything
        # downstream is arithmetic over them.
        series = scoring.hourly_series(req.species, z, snap, claims, req.craft, req.month,
                                       cfg, units, gen_known, req.start - 3600,
                                       req.end + 3600)
        statics = scoring.static_fits(req.species, z, snap, claims, req.craft, req.month,
                                      cfg, units, gen_known)
        hourly = hourly_scores(req.species, z, series, statics, req.craft)

        win, win_why = best_window(req, z, snap, claims, cfg, units, gen_known,
                                   series=series, statics=statics,
                                   bounds=(env.start, env.end))
        sc, lines, fits = scoring.score(req.species, z, snap, claims, win, req.craft,
                                        req.month, cfg, units, gen_known,
                                        series=series, statics=statics)
        conf, conf_rows = confidence(z, snap, claims, win, req.days_out)
        loc = z.location_confidence()
        stale = snap.flow.state == DataState.STALE or \
            snap.generation.state == DataState.STALE

        # THE ENVELOPE, NOT THE AVAILABILITY (§19). Two candidates ninety minutes apart
        # do not share a fishing window, and searching both over the raw day is how the
        # far one ends up recommended for hours nobody could be standing there.
        windows = opportunity.find_windows(
            z.id, req.species, hourly["values"], hourly["t0"], hourly["step"],
            env.start, env.end, confidence=conf, location_confidence=loc.value,
            stale=stale, conditions_summary=_conditions_summary(snap),
            reasons=[l.why for l in sorted(lines, key=lambda x: -x.earned)[:2]])

        scored.append({"zone": z, "snap": snap, "envelope": env,
                       "score": sc, "lines": lines, "fits": fits,
                       "confidence": conf, "conf_rows": conf_rows, "window": win,
                       "window_why": win_why, "claims": claims, "cfg": cfg,
                       "units": units, "gen_known": gen_known,
                       "series": series, "statics": statics, "hourly": hourly,
                       "location": loc, "windows": windows,
                       "best_utility": max((w.utility for w in windows), default=-1e9),
                       "rank": rank_key(sc, conf)})
    scored.sort(key=lambda c: -c["best_utility"])
    return scored, rejected


def hourly_scores(species, zone, series, statics, craft):
    """The zone's total weighted score at each hour of the series.

    This is the input to the window optimiser, and it is the SAME arithmetic the window
    score uses — one hour is just the shortest possible window. Emitted to the browser so
    both engines optimise over identical numbers.
    """
    from ..species.profiles import weights_for
    w = weights_for(species)
    t0, step, n = series["t0"], series["step"], series["hours"]
    static_total = 0.0
    for key, weight in w.items():
        if key in scoring.DYNAMIC:
            continue
        if key == "access":
            fit = statics.get(key)
        else:
            fit = statics.get(key)
        static_total += (fit.value if fit is not None else scoring.NEUTRAL) * weight
    values = []
    for i in range(n):
        total = static_total
        for key in w:
            if key not in scoring.DYNAMIC:
                continue
            vals = series["values"].get(key)
            total += (vals[i] if vals and i < len(vals) else scoring.NEUTRAL) * w[key]
        values.append(round(total, 4))
    return {"t0": t0, "step": step, "values": values}


def _conditions_summary(snap):
    bits = []
    if snap.flow.ok:
        bits.append("%s cfs" % scoring._n(snap.flow.value))
    if snap.generation_on.ok:
        bits.append("generation " + ("on" if snap.generation_on.value else "off"))
    if snap.water_temp.ok:
        bits.append("%d°F" % round(snap.water_temp.value))
    return " · ".join(bits)


def plan(req, snaps, book, claims_by_zone):
    """The FishingPlan for the best ITINERARY, with alternatives and losing reasons.

    §9-§14. The winner is no longer "the highest-scoring zone"; it is the highest-utility
    executable sequence of opportunity windows, which may span two or three zones joined by
    transitions the chosen craft can actually make.
    """
    scored, rejected = candidates(req, snaps, book, claims_by_zone)
    p = FishingPlan(species=req.species, craft=req.craft,
                    requested_window=req.to_json(), created_at=req.now)
    p.planner_version = PLANNER_VERSION
    p.species_model_version = SPECIES_MODEL_VERSION
    p.zone_model_version = ZONE_MODEL_VERSION
    p.research_version = RESEARCH_VERSION

    if not scored:
        p.best_window = {"start": round(req.start), "end": round(req.end),
                         "why": "nothing was eligible, so the window is the one you asked for"}
        p.verdict = Verdict.SKIP
        p.verdict_why = ("Nothing is eligible for %s on a %s in this window. "
                         % (DISPLAY[req.species]["full"].lower(),
                            Craft.LABEL.get(req.craft, req.craft).lower())) + \
                        (rejected[0].reason + "." if rejected else "")
        p.alternatives = [r.to_json() for r in rejected[:6]]
        p.limitations.append("No candidate survived the eligibility gates.")
        return p

    by_id = {c["zone"].id: c for c in scored}
    zones = {c["zone"].id: c["zone"] for c in scored}
    snaps_by_id = {c["zone"].id: c["snap"] for c in scored}
    statics_by_id = {c["zone"].id: {"units": c["units"], "gen_known": c["gen_known"]}
                     for c in scored}

    all_windows = [w for c in scored for w in c["windows"]]
    graph = transitions.build_graph(list(zones.values()), req.craft)
    winner, runners = itin_search.best_itinerary(all_windows, graph, req.species, req.craft,
                                                 req.start, req.end)

    if winner is None:
        p.verdict = Verdict.SKIP
        p.verdict_why = "No fishable window survived inside the time you gave."
        p.best_window = {"start": round(req.start), "end": round(req.end),
                         "why": "no window scored well enough to name"}
        p.alternatives = [r.to_json() for r in rejected[:6]]
        return p

    primary = by_id[winner.windows[0].zone_id]
    z, snap = primary["zone"], primary["snap"]

    segs = segments.build(winner, zones, snaps_by_id, req.species, req.craft, req.tz,
                          book, claims_by_zone, statics_by_id, req)
    itin = _itinerary(winner, segs, req, zones)
    p.itinerary = itin

    p.primary_candidate = z.id
    # §31/§65 — OPPORTUNITY is the itinerary's own quality, not a synthetic blend.
    p.score = round(winner.parts.get("quality", primary["score"]), 1)
    p.opportunity = p.score
    p.confidence = primary["confidence"]
    p.location_confidence = round(itin.location_confidence, 1)
    p.research_confidence = _research_confidence(primary["claims"], z.id)
    p.utility = round(winner.utility, 2)
    p.score_breakdown = primary["lines"]
    p.best_window = {"start": round(winner.windows[0].start),
                     "end": round(winner.windows[-1].end),
                     "why": _window_why(winner, req)}
    p.availability = {"start": round(req.start), "end": round(req.end)}
    p.verdict, p.verdict_why = _verdict(primary, req, snap, winner)
    p.why_this_won = _why_this_won(winner, scored, zones, req, graph)

    p.location = {
        "zone_id": z.id, "name": z.name, "waterbody": ", ".join(z.waterbody_names),
        "drive": z.drive, "detail_page": z.detail_page, "kind": z.kind,
        "geometry": z.geometry.to_json() if z.geometry else None,
        "habitat": z.habitat, "hazards": z.hazards, "regs": z.regs,
        "pattern": (z.species_profiles.get(req.species).pattern
                    if z.species_profiles.get(req.species) else ""),
        "holds": z.holds_phrase(req.species),
        "location_confidence": z.location_confidence().to_json(),
    }
    launch = segments.pick_access(z, req.craft)
    p.access = {
        "launch": launch,
        "takeout": _takeout(z, req.craft, launch),
        "parking": (launch or {}).get("note", ""),
        "source": (launch or {}).get("source", ""),
        "all": [a.to_json() for a in z.access],
        "verified": bool((launch or {}).get("verified")),
    }
    p.timeline = segments.to_timeline(segs, req.tz)
    p.technique = technique(req.species, z, snap, primary, req, winner.windows[0])

    # §14/§18 — the day, not just the fishing. `legs` covers every minute from leaving
    # the house to getting back, and `summary` is the five times the hero block shows.
    env = primary["envelope"]
    leg_list = logistics.legs(env, list(winner.windows), list(winner.transitions),
                              req.availability, req.craft, req.tz)
    if leg_list:
        p.logistics = {
            "legs": [l.to_json() for l in leg_list],
            "summary": logistics.summary(leg_list),
            "envelope": env.to_json(),
            "origin": list(req.origin) if req.origin else None,
            "door_to_door": req.door_to_door,
            "constants": logistics.published(),
            "routing": req.routing.describe() if hasattr(req.routing, "describe") else {},
        }
    p.backup_plan = _backup_plan(winner, scored, zones, graph, req, book)

    p.water = {"flow": snap.flow, "stage": snap.stage, "flow_trend": snap.flow_trend,
               "stage_trend": snap.stage_trend, "generation": snap.generation,
               "generation_on": snap.generation_on,
               "generation_forecast": snap.generation_forecast,
               "water_temp": snap.water_temp, "lake_elevation": snap.lake_elevation,
               "clarity": snap.clarity}
    p.weather = _weather_summary(snap, (winner.windows[0].start, winner.windows[-1].end))
    p.lunar = snap.lunar
    p.biological_context = _bio(z, profile(req.species), req, primary["claims"])
    p.evidence = [c.to_json() for c in primary["claims"][:8]]
    p.safety = [c.to_json() for c in book.for_zone(z.id)]
    for w in winner.windows[1:]:
        p.safety.extend(c.to_json() for c in book.for_zone(w.zone_id))
    p.data_freshness = primary["conf_rows"]

    p.method = req.method
    p.alternatives = _alternatives(winner, runners, scored, zones, req) + \
        [r.to_json() for r in rejected[:3]]
    p.limitations = _limitations(primary, req, snap, winner)
    return p


def _itinerary(winner, segs, req, zones):
    itin = FishingItinerary(
        species=req.species, craft=req.craft,
        requested_start=req.start, requested_end=req.end,
        segments=segs, windows=list(winner.windows),
        total_fishing_minutes=sum(w.duration_minutes for w in winner.windows),
        total_transition_minutes=sum(t.minutes for t in winner.transitions),
        utility_score=winner.utility, utility_parts=winner.parts,
        confidence=min(w.confidence for w in winner.windows),
        location_confidence=round(
            100.0 * min(w.location_confidence for w in winner.windows), 1),
        primary_zone=winner.windows[0].zone_id,
        zone_sequence=[w.zone_id for w in winner.windows])
    itin.why = [s.reason for s in segs if s.type == SegmentType.MOVE]
    return itin


def _window_why(winner, req):
    avail = (req.end - req.start) / 60.0
    fished = sum(w.duration_minutes for w in winner.windows)
    if fished >= avail - 20:
        return "the whole period you gave is worth fishing"
    if len(winner.windows) > 1:
        return ("the two strongest stretches inside your %d-hour window, with the move "
                "between them costing %d minutes"
                % (round(avail / 60), round(winner.parts.get("travelMinutes", 0))))
    return ("the strongest %d minutes of the %d you have — the rest of your window does "
            "not score well enough to be worth fishing"
            % (round(fished), round(avail)))


def _why_this_won(winner, scored, zones, req, graph):
    """§67 — a short, concrete explanation, before the deep evidence drawer."""
    out = []
    w0 = winner.windows[0]
    out.append("Best %d-minute stretch of any candidate: peaks at %.0f, floor %.0f."
               % (round(w0.duration_minutes), w0.peak_score, w0.floor_score))
    primary = next(c for c in scored if c["zone"].id == w0.zone_id)
    top = sorted(primary["lines"], key=lambda l: -(l.earned / max(1, l.possible)))[:3]
    for l in top:
        if l.earned >= l.possible * 0.75:
            out.append("%s: %s" % (l.label, l.why))
    if len(winner.windows) > 1:
        nxt = winner.windows[1]
        out.append("A %d-minute move extends the bite another %d minutes at %s."
                   % (round(winner.parts.get("travelMinutes", 0)),
                      round(nxt.duration_minutes), zones[nxt.zone_id].name))
    lc = zones[w0.zone_id].location_confidence()
    rows = lc.rows()
    out.append("Location confidence %.0f: the access is %s, the reach is %s."
               % (lc.score, rows[0]["level_label"].lower(), rows[1]["level_label"].lower()))
    return out[:6]


def _alternatives(winner, runners, scored, zones, req):
    """§38 — the runner-up ITINERARIES, and why each lost."""
    out = []
    seen = {tuple(w.zone_id for w in winner.windows)}
    for c in runners:
        key = tuple(w.zone_id for w in c.windows)
        if key in seen:
            continue
        seen.add(key)
        gap = winner.utility - c.utility
        z0 = zones[c.windows[0].zone_id]
        if len(c.windows) < len(winner.windows):
            why = ("Staying put scores %.1f against the winner's %.1f — the move is worth "
                   "more than the simplicity." % (c.utility, winner.utility))
        elif len(c.windows) > len(winner.windows):
            why = ("Adding a third zone costs %.0f minutes of travel for %.1f points less "
                   "utility." % (c.parts.get("travelMinutes", 0), gap))
        else:
            c_peak = max(w.peak_score for w in c.windows)
            w_peak = max(w.peak_score for w in winner.windows)
            c_conf = min(w.confidence for w in c.windows)
            w_conf = min(w.confidence for w in winner.windows)
            c_loc = min(w.location_confidence for w in c.windows)
            w_loc = min(w.location_confidence for w in winner.windows)
            if c_peak > w_peak and (c_conf < w_conf or c_loc < w_loc):
                # §31/§60 made visible: it fishes better on paper and still lost, so name
                # the number that beat it rather than quoting a peak it actually won on.
                bits = []
                if c_conf < w_conf - 1:
                    bits.append("forecast confidence %.0f against %.0f" % (c_conf, w_conf))
                if c_loc < w_loc - 0.01:
                    bits.append("location confidence %.0f against %.0f"
                                % (c_loc * 100, w_loc * 100))
                why = ("Peaks higher (%.0f against %.0f) and still lost by %.1f: %s."
                       % (c_peak, w_peak, gap, " and ".join(bits)))
            else:
                why = ("%.1f points behind: peak %.0f against %.0f, over %d minutes "
                       "against %d." % (gap, c_peak, w_peak,
                                        round(sum(w.duration_minutes for w in c.windows)),
                                        round(sum(w.duration_minutes for w in winner.windows))))
        out.append({
            "zone_id": z0.id,
            "name": " → ".join(zones[w.zone_id].name for w in c.windows),
            "waterbody": ", ".join(z0.waterbody_names),
            "score": round(c.parts.get("quality", 0), 1),
            "utility": round(c.utility, 1),
            "confidence": round(min(w.confidence for w in c.windows), 1),
            "location_confidence": round(
                100 * min(w.location_confidence for w in c.windows), 1),
            "window": {"start": round(c.windows[0].start), "end": round(c.windows[-1].end)},
            "drive": z0.drive, "detail_page": z0.detail_page,
            "why": why, "what_would_flip_it": why, "lost_on": [], "eliminated": False,
        })
        if len(out) >= 4:
            break
    return out


def _backup_plan(winner, scored, zones, graph, req, book):
    """§39 — what to do when the main plan falls apart."""
    primary_ids = set(w.zone_id for w in winner.windows)
    fallback = None
    for c in scored:
        if c["zone"].id in primary_ids or not c["windows"]:
            continue
        fallback = c
        break

    branches = []
    z0 = zones[winner.windows[0].zone_id]
    gen_stop = next((c for c in book.for_zone(z0.id)
                     if c.kind == SafetyKind.GENERATION_STOP), None)
    if z0.tailwater:
        if len(winner.windows) > 1:
            nxt = zones[winner.windows[1].zone_id]
            branches.append({
                "if": "generation is cancelled, or ends before you get on the water",
                "then": ("Skip %s entirely and run straight to %s — without current the "
                         "first zone is the weakest water in the plan, not the strongest."
                         % (z0.name, nxt.name))})
        elif fallback is not None:
            branches.append({
                "if": "generation is cancelled",
                "then": ("%s is current-driven — without the release it is the weakest "
                         "water in the plan. Fish %s instead."
                         % (z0.name, fallback["zone"].name))})
    if fallback is not None:
        branches.append({
            "if": "the primary zone is blown out, crowded, or simply dead after an hour",
            "then": "%s is the next-best water for this species in your window (%s)."
                    % (fallback["zone"].name, fallback["zone"].drive or "same trip")})
    branches.append({
        "if": "weather turns unsafe — lightning, or wind you cannot fish",
        "then": "Abort. Nothing in this plan is worth a thunderstorm on open water."})
    return {"branches": branches,
            "fallback_zone": fallback["zone"].id if fallback else None}


def _research_confidence(claims, zone_id):
    """§31 — research confidence as its own number, 0..100."""
    rel = [c for c in claims if (not c.location_ids or zone_id in c.location_ids)]
    if not rel:
        return 0.0
    rel = sorted(rel, key=lambda c: -c.confidence)[:4]
    return round(100.0 * sum(c.confidence for c in rel) / len(rel), 1)


#: Published to the browser as `verdictThresholds`; §8's GO / CONDITIONAL / SKIP.
VERDICT = {"go": 68, "confident": 55, "fishable": 50, "hard_component": 0.2}


def _verdict(best, req, snap, winner=None):
    sc = round(winner.parts.get("quality", best["score"]), 1) if winner else best["score"]
    conf = best["confidence"]
    hard = [c for c in best["fits"].values()
            if c.value <= VERDICT["hard_component"] and c.known]
    if sc >= VERDICT["go"] and conf >= VERDICT["confident"] and not hard:
        return Verdict.GO, "Good water, good window, and the numbers behind it are observed."
    if sc >= VERDICT["go"] and conf < VERDICT["confident"]:
        return (Verdict.CONDITIONAL,
                "The fishery reads well but too much of it is unmeasured — treat the timing "
                "as provisional and verify the release before you commit.")
    if sc >= VERDICT["fishable"]:
        return Verdict.CONDITIONAL, "Fishable, with a real limitation: " + \
               (hard[0].why if hard else "several components are only average.")
    return (Verdict.SKIP,
            "Nothing here scores well enough to be worth the drive: " +
            (hard[0].why if hard else "every component is weak in this window."))


def _alt(c, best):
    """§38 — why it lost, and what would make it win."""
    gaps = []
    bl = {l.key: l for l in best["lines"]}
    for line in sorted(c["lines"], key=lambda l: (l.earned - bl.get(l.key, l).earned)):
        b = bl.get(line.key)
        if b is None or line.earned >= b.earned:
            continue
        gaps.append({"component": line.label,
                     "lost": round(b.earned - line.earned, 1), "why": line.why})
        if len(gaps) >= 3:
            break
    flip = ""
    if c["score"] > best["score"]:
        # §31 in the open: it scored higher and still lost, so say which number did it.
        flip = ("Scored %.1f to the winner's %.1f, but on %d-point confidence against %d — "
                "too much of it is unmeasured to send you there."
                % (c["score"], best["score"], round(c["confidence"]),
                   round(best["confidence"])))
    elif gaps:
        flip = "%s would move it above the winner if it improved: %s" % (
            c["zone"].name, gaps[0]["why"])
    return {"zone_id": c["zone"].id, "name": c["zone"].name,
            "waterbody": ", ".join(c["zone"].waterbody_names),
            "score": c["score"], "confidence": c["confidence"],
            "window": {"start": round(c["window"][0]), "end": round(c["window"][1])},
            "drive": c["zone"].drive, "detail_page": c["zone"].detail_page,
            "lost_on": gaps, "what_would_flip_it": flip, "eliminated": False}


def technique(species, zone, snap, best, req, window=None):
    """§35 — what to tie on NOW, chosen from the water actually in front of you."""
    prof = profile(species)
    units, gen_known = best["units"], best["gen_known"]
    rows = snap.weather_window(*best["window"])
    light_fit = best["fits"].get("light")
    clarity_fit = best["fits"].get("clarity")
    low_light = light_fit is not None and light_fit.value >= 0.8 and \
        "low-light" in (light_fit.why or "")

    key = "default"
    why = []
    if gen_known and units and units >= 2:
        key = "heavy_current"
        why.append("%d units of push means depth and a big profile" % units)
    elif gen_known and units == 0 and prof.current.get("needs"):
        key = "slack"
        why.append("no generation — you have to go find them deep instead of on a seam")
    elif low_light:
        key = "low_light"
        why.append("low light is the window, so fish the top of the column")
    if clarity_fit is not None and "muddy" in (clarity_fit.why or ""):
        why.append("muddy water — go bigger and darker than the size below suggests")

    t = dict(prof.techniques.get(key) or prof.techniques["default"])
    wind = scoring._mean(rows, "wind_speed")
    if wind is not None and wind >= 15:
        why.append("%d mph wind — shorten the leader and accept a heavier fly" % round(wind))
    return Technique(why="; ".join(why) or "the standard read for these conditions", **t)


def _weather_summary(snap, window):
    from ..domain.observation import Observation
    rows = snap.weather_window(*window)
    if not rows:
        u = Observation.unknown("", "Open-Meteo", note="no hourly rows in this window")
        return {k: u for k in ("air_temperature", "wind_speed", "wind_gust",
                               "wind_direction", "cloud_cover",
                               "precipitation_probability", "precipitation_amount",
                               "pressure", "thunderstorm_risk")} | \
               {"sunrise": snap.sunrise, "sunset": snap.sunset}
    src, url = "Open-Meteo (hourly)", "https://open-meteo.com/"
    at = rows[0].get("_fetched_at")

    def ob(key, agg=scoring._mean, unit=""):
        v = agg(rows, key)
        return (Observation.known(round(v, 1) if isinstance(v, float) else v, unit, src, url,
                                  observed_at=at, confidence=0.8)
                if v is not None else Observation.unknown(unit, src))
    storm = any(r.get("thunderstorm") for r in rows)
    return {
        "air_temperature": ob("air_temperature", unit="°F"),
        "wind_speed": ob("wind_speed", unit="mph"),
        "wind_gust": ob("wind_gust", scoring._max, "mph"),
        "wind_direction": Observation.known(rows[len(rows) // 2].get("wind_dir_label") or "",
                                            "", src, url, observed_at=at, confidence=0.8),
        "cloud_cover": ob("cloud_cover", unit="%"),
        "precipitation_probability": ob("precipitation_probability", scoring._max, "%"),
        "precipitation_amount": ob("precipitation", sum_rows, "in"),
        "pressure": ob("pressure", unit="hPa"),
        "pressure_trend": ob("pressure_trend", unit="hPa/3h"),
        "thunderstorm_risk": Observation.known(storm, "", "Open-Meteo / NWS", url,
                                               observed_at=at, confidence=0.75),
        "sunrise": snap.sunrise, "sunset": snap.sunset,
    }


def sum_rows(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals), 2) if vals else None


def _bio(zone, prof, req, claims):
    ref = zone.species_profiles.get(req.species)
    season = prof.season_of(req.month)
    return {
        "season": season,
        "seasonal_stage": ref.pattern if ref else "",
        "forage": prof.forage,
        "forage_evidence": getattr(prof, "forage_evidence", "heuristic"),
        "forage_source": getattr(prof, "forage_source", ""),
        "habitat": ref.habitat if ref else zone.habitat,
        "thermal_refuge": (prof.thermal_refuge
                           if req.month in prof.thermal_refuge.get("months", []) else None),
        "spawning_behavior": (prof.spawn
                              if req.month in prof.spawn.get("months", []) else None),
        "hatch": prof.forage if req.species == "trout" else [],
        "heuristic": bool(ref.heuristic) if ref else True,
        "claims": [c.id for c in claims[:6]],
    }


def _limitations(best, req, snap, winner=None):
    out = []
    if winner is not None:
        # §5 — a session shorter than the species minimum is still offered, because the
        # reader asked, but it must say what it is: a short session, not a plan.
        fished = sum(w.duration_minutes for w in winner.windows)
        floor = utility.min_duration(req.species)
        if fished < floor:
            out.append(
                "You have %d minutes. The practical minimum for this species is about %d — "
                "this is a short session, not a plan, and the score is penalised "
                "accordingly." % (round(fished), floor))
        lc = min(w.location_confidence for w in winner.windows)
        if lc < 0.66:
            out.append(
                "Location confidence is %.0f/100. The species and habitat evidence supports "
                "this reach, but the exact holding water has not been field verified — "
                "read the water yourself rather than trusting a pin." % (lc * 100))
    for line in best["lines"]:
        if "(unknown" in (line.why or ""):
            out.append("%s is unknown: %s" % (line.label, line.why.split(" (unknown")[0]))
    if req.days_out >= 3:
        out.append("This request is %d days out. Beyond about 48 hours the release schedule "
                   "and the hourly weather are seasonal expectation, not forecast."
                   % req.days_out)
    if snap.model_confidence in ("reported", "unknown"):
        out.append("The routing model for this water is %s, not measured. Arrival timing is "
                   "an estimate." % snap.model_confidence)
    if snap.errors:
        out.append("Upstream problems during this build: " + "; ".join(snap.errors[:2]))
    return out


def _takeout(zone, craft, launch):
    opts = [a.to_json() for a in zone.access if a.serves(craft)]
    for a in opts:
        if not launch or a["id"] != launch["id"]:
            return a
    return None


def _cfg(zone):
    from ..sources.registry import water_for
    return water_for(zone.hydrology_river)


def _units(snap, cfg):
    """(units, gen_known). Unknown generation must never read as zero units."""
    g = snap.generation
    if not g.ok or not cfg.get("unit_cfs"):
        return None, False
    return max(0, round((g.value - cfg.get("unit_offset", 0)) / float(cfg["unit_cfs"]))), True
