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
from zoneinfo import ZoneInfo

from ..domain.claim import SafetyKind
from ..domain.observation import DataState
from ..domain.plan import (FishingPlan, ScoreLine, Technique, Verdict)
from ..domain.zone import Craft
from ..species.profiles import DISPLAY, profile
from ..sources.snapshots import localize
from ..zones.registry import ZONES, zones_for_species
from . import scoring, timeline
from .confidence import confidence, confidence_label, rank_key
from .window import best_window

SITE_TZ = "America/Chicago"


class Request:
    """What the user asked for. §4, §5, §6."""

    def __init__(self, species, start, end, craft=Craft.ANY, tz=SITE_TZ, now=None):
        self.species = species
        self.start = float(start)
        self.end = float(end)
        self.craft = craft or Craft.ANY
        self.tz_name = tz
        self.tz = ZoneInfo(tz)
        self.now = now or time.time()
        if self.end <= self.start:
            raise ValueError("requested window ends before it starts")

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
                "tz": self.tz_name, "days_out": self.days_out}


class Rejected:
    def __init__(self, zone_id, name, reason):
        self.zone_id, self.name, self.reason = zone_id, name, reason

    def to_json(self):
        return {"zone_id": self.zone_id, "name": self.name, "reason": self.reason,
                "eliminated": True}


def eligible(req, snaps):
    """Step 1 + 2. Returns ([zones], [Rejected])."""
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
        keep.append(z)
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
    zones, rejected = eligible(req, snaps)
    scored = []
    req_date = _dt.datetime.fromtimestamp(req.start, req.tz).date()
    for z in zones:
        # Localise to the DATE being planned: sun times and moon belong to that day.
        snap = localize(snaps[z.id], req_date)
        cfg = _cfg(z)
        units, gen_known = _units(snap, cfg)
        claims = claims_by_zone.get(z.id) or []
        # Compute the hourly series and the static fits ONCE per candidate; the window
        # search then costs arithmetic instead of a rescore per candidate window.
        series = scoring.hourly_series(req.species, z, snap, claims, req.craft, req.month,
                                       cfg, units, gen_known, req.start - 3600,
                                       req.end + 3600)
        statics = scoring.static_fits(req.species, z, snap, claims, req.craft, req.month,
                                      cfg, units, gen_known)
        win, win_why = best_window(req, z, snap, claims, cfg, units, gen_known,
                                   series=series, statics=statics)
        sc, lines, fits = scoring.score(req.species, z, snap, claims, win, req.craft,
                                        req.month, cfg, units, gen_known,
                                        series=series, statics=statics)
        conf, conf_rows = confidence(z, snap, claims, win, req.days_out)
        scored.append({"zone": z, "snap": snap, "score": sc, "lines": lines, "fits": fits,
                       "confidence": conf, "conf_rows": conf_rows, "window": win,
                       "window_why": win_why, "claims": claims, "cfg": cfg,
                       "units": units, "gen_known": gen_known,
                       "series": series, "statics": statics,
                       "rank": rank_key(sc, conf)})
    scored.sort(key=lambda c: -c["rank"])
    return scored, rejected


def plan(req, snaps, book, claims_by_zone):
    """The FishingPlan for the winner, with alternatives and their losing reasons."""
    scored, rejected = candidates(req, snaps, book, claims_by_zone)
    p = FishingPlan(species=req.species, craft=req.craft,
                    requested_window=req.to_json(), created_at=req.now)

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

    best = scored[0]
    z, snap = best["zone"], best["snap"]
    prof = profile(req.species)
    p.primary_candidate = z.id
    p.score = best["score"]
    p.confidence = best["confidence"]
    p.score_breakdown = best["lines"]
    p.best_window = {"start": round(best["window"][0]), "end": round(best["window"][1]),
                     "why": best["window_why"]}
    p.verdict, p.verdict_why = _verdict(best, req, snap)

    p.location = {
        "zone_id": z.id, "name": z.name, "waterbody": ", ".join(z.waterbody_names),
        "drive": z.drive, "detail_page": z.detail_page,
        "geometry": z.geometry.to_json() if z.geometry else None,
        "habitat": z.habitat, "hazards": z.hazards, "regs": z.regs,
        "pattern": (z.species_profiles.get(req.species).pattern
                    if z.species_profiles.get(req.species) else ""),
        "holds": (z.species_profiles.get(req.species).holds
                  if z.species_profiles.get(req.species) else ""),
    }
    launch = timeline._pick_launch(z, req.craft)
    p.access = {
        "launch": launch,
        "takeout": _takeout(z, req.craft, launch),
        "parking": (launch or {}).get("note", ""),
        "source": (launch or {}).get("source", ""),
        "all": [a.to_json() for a in z.access],
        "verified": bool((launch or {}).get("verified")),
    }
    p.timeline = timeline.build(z, snap, prof, req.species, best["window"], req.craft,
                                req.tz, book, best["claims"], best["units"],
                                best["gen_known"])
    p.technique = technique(req.species, z, snap, best, req)

    p.water = {"flow": snap.flow, "stage": snap.stage, "flow_trend": snap.flow_trend,
               "stage_trend": snap.stage_trend, "generation": snap.generation,
               "generation_on": snap.generation_on,
               "generation_forecast": snap.generation_forecast,
               "water_temp": snap.water_temp, "lake_elevation": snap.lake_elevation,
               "clarity": snap.clarity}
    p.weather = _weather_summary(snap, best["window"])
    p.lunar = snap.lunar
    p.biological_context = _bio(z, prof, req, best["claims"])
    p.evidence = [c.to_json() for c in best["claims"][:8]]
    p.safety = [c.to_json() for c in book.for_zone(z.id)]
    p.data_freshness = best["conf_rows"]

    p.alternatives = [_alt(c, best) for c in scored[1:4]] + \
                     [r.to_json() for r in rejected[:3]]

    p.limitations = _limitations(best, req, snap)
    return p


#: Published to the browser as `verdictThresholds`; §8's GO / CONDITIONAL / SKIP.
VERDICT = {"go": 68, "confident": 55, "fishable": 50, "hard_component": 0.2}


def _verdict(best, req, snap):
    sc, conf = best["score"], best["confidence"]
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


def technique(species, zone, snap, best, req):
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


def _limitations(best, req, snap):
    out = []
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
