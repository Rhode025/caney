"""
Build a RiverSnapshot for every fishing zone. §23, §24, §29.

This is where instrument data becomes domain objects, and the ONLY place SafetyClaims are
minted (§3.3). Three properties matter more than anything else here:

1. UNKNOWN NEVER BECOMES ZERO (§3.4). A dam with no forward CWMS schedule produces
   `generation_forecast = Observation.unknown(...)`, and every downstream consumer — the
   wade window, the safe-exit claim, the timeline — refuses to promise anything rather
   than assuming the dam stays off. There is not one `or 0` in this file.

2. UNCERTAINTY IS FIRST CLASS (§3.5). Arrival is never a single time. riverlib's own
   ARRIVAL_STAGES already carries early/median/late speeds; this reads all three and
   emits earliest / typical / latest. SAFETY USES THE EARLIEST BOUND. Fishing
   optimisation uses the typical one.

3. FETCHES ARE SHARED. Zones are grouped by hydrology_river before anything is
   requested, so eight zones on four dams make four CWMS calls, not eight (§26, §56).
"""
import datetime as _dt
import time
from zoneinfo import ZoneInfo

from ..domain.claim import ClaimBook, SafetyKind
from ..domain.observation import DataState, Observation
from ..domain.snapshot import RiverSnapshot
from ..zones.registry import all_zones
from . import cwms, lunar, usgs, weather
from .registry import water_for

# riverlib is the calibrated hydrology. Imported, never reimplemented (CLAUDE.md).
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import riverlib  # noqa: E402


def _units(cfs, cfg):
    """Turbine units turning, using the SAME arithmetic as the river page."""
    if cfs is None:
        return None
    u = cfg.get("unit_cfs")
    if not u:
        return None
    return max(0, round((cfs - cfg.get("unit_offset", 0)) / float(u)))


def _gen_on(cfs, cfg):
    if cfs is None:
        return None
    on = cfg.get("gen_on")
    return None if on is None else bool(cfs >= on)


def _fmt(ep, tz):
    return _dt.datetime.fromtimestamp(ep, tz).strftime("%-I:%M %p")


def _release_events(rows, cfg, now, horizon):
    """[(epoch, 'start'|'stop', cfs)] for the forward schedule. Empty ≠ 'no generation'."""
    on_cfs = cfg.get("gen_on")
    if not rows or on_cfs is None:
        return []
    ev, prev = [], None
    for t, v in rows:
        if t < now - 7200 or t > horizon:
            continue
        cur = v >= on_cfs
        if prev is None:
            prev = cur
            continue
        if cur and not prev:
            ev.append((t, "start", v))
        elif prev and not cur:
            ev.append((t, "stop", v))
        prev = cur
    return ev


def build_all(now=None, horizon_days=3, tz_name="America/Chicago", book=None):
    """{zone_id: RiverSnapshot}, plus the ClaimBook every safety sentence must cite."""
    now = now or time.time()
    tz = ZoneInfo(tz_name)
    book = book if book is not None else ClaimBook()
    horizon = now + horizon_days * 86400

    zones = all_zones()
    by_river = {}
    for z in zones:
        by_river.setdefault(z.hydrology_river, []).append(z)

    # §56: the rivers are independent fetch sets, so load them concurrently — but only
    # AFTER deduping by hydrology river, because parallelising duplicated work is how a
    # build gets slower and ruder to USGS at the same time. Modest pool: these are four
    # public agencies, not a CDN.
    river_data = {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {rid: pool.submit(_load_river, rid, now, horizon) for rid in by_river}
        for rid, fut in futures.items():
            try:
                river_data[rid] = fut.result()
            except Exception as e:                       # noqa: BLE001
                river_data[rid] = {"cfg": water_for(rid),
                                   "errors": ["load failed: %s: %s" % (type(e).__name__, e)]}

    snaps = {}
    for z in zones:
        snaps[z.id] = _zone_snapshot(z, river_data.get(z.hydrology_river) or {},
                                     now, horizon, tz, book)
    return snaps, book


def _load_river(rid, now, horizon):
    """One fetch set per hydrology river, shared by every zone on it."""
    cfg = water_for(rid)
    out = {"cfg": cfg, "errors": []}

    if cfg.get("cwms_actual"):
        now_ob, fc_ob, rows = cwms.release(cfg["cwms_actual"], cfg.get("cwms_forecast"),
                                           cfg.get("office", "LRN"), dam=cfg.get("dam") or "")
        out["release_now"] = now_ob
        out["release_forecast"] = fc_ob
        out["release_rows"] = rows
        for ob in (now_ob, fc_ob):
            if ob.state == DataState.ERROR:
                out["errors"].append("%s: %s" % (ob.source, ob.note))
    else:
        out["release_now"] = Observation.unknown("cfs", cfg.get("dam") or rid,
                                                 note="no dam release feed for this water")
        out["release_forecast"] = Observation.unknown(
            "cfs", cfg.get("dam") or rid, note="no dam release forecast for this water")
        out["release_rows"] = []

    if cfg.get("usgs"):
        scale = cfg.get("usgs_scale", 1.0)
        flow, frows = usgs.latest(cfg["usgs"], "flow", source_label=cfg.get("usgs_label", ""))
        if flow.ok and scale != 1.0:
            flow = Observation.known(round(flow.value * scale), "cfs",
                                     flow.source, flow.source_url, flow.observed_at,
                                     confidence=0.6,
                                     note="interpolated from the upstream gauge (x%.2f)" % scale)
        stage, srows = usgs.latest(cfg["usgs"], "stage", source_label=cfg.get("usgs_label", ""))
        temp, _ = usgs.latest(cfg["usgs"], "temp", source_label=cfg.get("usgs_label", ""))
        out.update(flow=flow, stage=stage, water_temp=temp,
                   flow_trend=usgs.trend(frows), stage_trend=usgs.trend(srows))
    else:
        note = cfg.get("note") or "no gauge on this reach"
        out.update(flow=Observation.unknown("cfs", cfg.get("name", rid), note=note),
                   stage=Observation.unknown("ft", cfg.get("name", rid), note=note),
                   water_temp=Observation.unknown("°F", cfg.get("name", rid), note=note),
                   flow_trend=None, stage_trend=None)

    if cfg.get("lat") is not None:
        hrs, daily, werr = weather.hourly(cfg["lat"], cfg["lon"], cfg.get("tz", "America/Chicago"))
        out["weather_hours"] = hrs
        out["weather_daily"] = daily
        if werr:
            out["errors"].append("weather: %s" % werr)
        al, _ = weather.alerts(cfg["lat"], cfg["lon"])
        out["alerts"] = al
    else:
        out["weather_hours"], out["weather_daily"], out["alerts"] = [], {}, []
    return out


def _zone_snapshot(z, rd, now, horizon, tz, book):
    cfg = rd.get("cfg") or {}
    s = RiverSnapshot(zone_id=z.id, river_id=z.hydrology_river, taken_at=now)
    s.errors = list(rd.get("errors") or [])

    s.flow = rd.get("flow") or Observation.unknown("cfs")
    s.stage = rd.get("stage") or Observation.unknown("ft")
    s.water_temp = rd.get("water_temp") or Observation.unknown("°F")
    for name, key in (("flow_trend", "flow_trend"), ("stage_trend", "stage_trend")):
        t = rd.get(key)
        setattr(s, name, Observation.known(t, "", s.flow.source, confidence=0.7)
                if t else Observation.unknown("", s.flow.source,
                                              note="not enough readings to call a trend"))

    rel_now = rd.get("release_now") or Observation.unknown("cfs")
    rel_fc = rd.get("release_forecast") or Observation.unknown("cfs")
    s.generation = rel_now
    s.generation_forecast = rel_fc

    on = _gen_on(rel_now.value, cfg) if rel_now.ok else None
    s.generation_on = (Observation.known(on, "", rel_now.source, rel_now.source_url,
                                         rel_now.observed_at, confidence=rel_now.confidence)
                       if on is not None
                       else Observation.unknown("", rel_now.source or (cfg.get("dam") or ""),
                                                note="generation state unknown — "
                                                     "no usable release reading"))

    s.weather_hours = rd.get("weather_hours") or []
    daily = rd.get("weather_daily") or {}
    s.weather_daily = daily
    s.tz_name = cfg.get("tz", "America/Chicago")
    today_iso = _dt.datetime.fromtimestamp(now, tz).date().isoformat()
    s.sunrise, s.sunset = weather.sun_for(daily, today_iso, cfg.get("tz", "America/Chicago"))
    s.lunar = lunar.lunar_day(_dt.datetime.fromtimestamp(now, tz).date(),
                              s.sunrise.value if s.sunrise.ok else None,
                              s.sunset.value if s.sunset.ok else None, tz)

    s.access = [a.to_json() for a in z.access]
    s.biological_context = {
        "habitat": z.habitat,
        "species": {k: v.to_json() for k, v in z.species_profiles.items()},
    }

    # ── model predictions with their uncertainty (§3.5) ─────────────────────
    if z.tailwater and z.mfd is not None:
        e, m, l = riverlib.arrival_window(z.mfd, "first")
        pe, pm, pl = riverlib.arrival_window(z.mfd, "peak")
        s.arrival = {"mfd": z.mfd, "dam": z.dam,
                     "first": {"earliest_h": e, "typical_h": m, "latest_h": l},
                     "peak": {"earliest_h": pe, "typical_h": pm, "latest_h": pl},
                     "source": "riverlib.ARRIVAL_STAGES — 80-event Center Hill backtest",
                     "note": ("Safety uses the EARLIEST bound. The typical figure is for "
                              "planning where you fish, never for when you get out.")}
        s.model_confidence = "measured" if z.hydrology_river == "caney" else "reported"
        s.model_note = cfg.get("note") or ""
    else:
        s.arrival = {}
        s.model_confidence = "structural" if not z.tailwater else "unknown"

    s.apply_freshness_budgets(now)
    _mint_safety_claims(z, s, rd, cfg, now, horizon, tz, book)
    return s


def _mint_safety_claims(z, s, rd, cfg, now, horizon, tz, book):
    """The ONLY place a safety number enters the product. §3.3, §20."""
    ids = []

    def add(kind, text, **kw):
        c = book.add(kind, z.id, text, **kw)
        ids.append(c.id)
        return c

    if s.flow.ok:
        add(SafetyKind.FLOW,
            "Flow at %s is %s cfs (%s)." % (cfg.get("usgs_label") or z.name,
                                            _num(s.flow.value), s.flow.age_label(now)),
            value=s.flow.value, unit="cfs", at=s.flow.observed_at, bound="measured",
            source=s.flow.source, source_url=s.flow.source_url, state=s.flow.state,
            observed_at=s.flow.observed_at,
            numbers=(str(int(round(s.flow.value))),))
    if s.stage.ok:
        add(SafetyKind.STAGE,
            "Stage at %s is %.2f ft (%s)." % (cfg.get("usgs_label") or z.name,
                                              s.stage.value, s.stage.age_label(now)),
            value=s.stage.value, unit="ft", at=s.stage.observed_at, bound="measured",
            source=s.stage.source, source_url=s.stage.source_url, state=s.stage.state,
            observed_at=s.stage.observed_at,
            numbers=("%.2f" % s.stage.value,))

    if s.generation.ok and cfg.get("dam"):
        u = _units(s.generation.value, cfg)
        add(SafetyKind.FORECAST_RELEASE,
            "%s is releasing %s cfs right now%s." % (
                cfg["dam"], _num(s.generation.value),
                (" — about %d unit%s turning" % (u, "" if u == 1 else "s")) if u else ", dam idle"),
            value=s.generation.value, unit="cfs", at=s.generation.observed_at,
            bound="measured", source=s.generation.source, source_url=s.generation.source_url,
            state=s.generation.state, observed_at=s.generation.observed_at,
            numbers=tuple(x for x in (str(int(round(s.generation.value))),
                                      (str(u) if u else None)) if x))

    rows = rd.get("release_rows") or []
    fc = s.generation_forecast
    if fc.ok:
        rows_fwd = [(t, v) for t, v in (fc.value or [])]
        events = _release_events(rows_fwd, cfg, now, horizon)
        for t, kind, v in events[:6]:
            if kind == "start":
                c = add(SafetyKind.GENERATION_START,
                        "%s is forecast to start generating at %s." % (cfg["dam"], _fmt(t, tz)),
                        value=t, unit="epoch", at=t, bound="typical", source=fc.source,
                        source_url=fc.source_url, state=fc.state, observed_at=fc.observed_at)
                # THE safety number on a tailwater: the earliest the water can reach you.
                if z.tailwater and z.mfd:
                    e, m, l = riverlib.arrival_window(z.mfd, "first")
                    add(SafetyKind.RELEASE_ARRIVAL,
                        ("That water reaches %s no earlier than %s (typical %s, later edge "
                         "%s)." % (z.name, _fmt(t + e * 3600, tz), _fmt(t + m * 3600, tz),
                                   _fmt(t + l * 3600, tz))),
                        value=[round(t + e * 3600), round(t + m * 3600), round(t + l * 3600)],
                        unit="epoch", at=t + e * 3600, bound="earliest", source=fc.source,
                        source_url=fc.source_url, state=fc.state, observed_at=fc.observed_at)
                    # Safe exit = earliest arrival minus a 30-minute walking margin.
                    # Only where someone can actually be standing in the water: a
                    # power-boat-only tailrace gets the arrival claim but not an exit
                    # instruction, so the one that matters is never lost in noise.
                    exit_t = t + e * 3600 - 1800
                    if _wadeable(z):
                        add(SafetyKind.SAFE_EXIT,
                            "Be out of the water at %s by %s." % (z.name, _fmt(exit_t, tz)),
                            value=round(exit_t), unit="epoch", at=exit_t, bound="earliest",
                            source=fc.source, source_url=fc.source_url, state=fc.state,
                            observed_at=fc.observed_at)
            else:
                add(SafetyKind.GENERATION_STOP,
                    "%s is forecast to stop generating at %s." % (cfg["dam"], _fmt(t, tz)),
                    value=t, unit="epoch", at=t, bound="typical", source=fc.source,
                    source_url=fc.source_url, state=fc.state, observed_at=fc.observed_at)
        if not events and z.tailwater:
            add(SafetyKind.WADE_CUTOFF,
                "No generation change is forecast for %s inside the planning horizon. "
                "Verify the release schedule before you get in." % (cfg.get("dam") or z.name),
                bound="typical", source=fc.source, source_url=fc.source_url, state=fc.state)
    elif z.tailwater and _wadeable(z):
        # §3.4 / §58: a wadeable tailwater with no release forecast FAILS SAFE, loudly.
        add(SafetyKind.WADE_CUTOFF,
            ("No release forecast is available for %s. This plan cannot tell you when the "
             "water will come up — do not wade this reach on it." % (cfg.get("dam") or z.name)),
            bound="earliest", source=fc.source or (cfg.get("dam") or ""),
            state=fc.state)

    for a in (rd.get("alerts") or []):
        if a.get("event"):
            add(SafetyKind.WEATHER_HAZARD,
                "NWS active alert: %s (%s)." % (a["event"], a.get("severity") or "unknown"),
                source="NOAA/NWS", source_url=a.get("source_url", ""), bound="measured")

    s.safety_claim_ids = ids


def localize(snap, date):
    """A view of `snap` with the sun times and moon of ONE local date. §28, §14.

    Sunrise on the day you are planning is not sunrise today. Scoring the light component
    against today's sunrise for a tomorrow-morning request silently threw away the
    low-light bonus that is the whole reason to fish at 6:30 — so the date is explicit,
    and everything time-of-day reads through this.

    Lives here rather than on RiverSnapshot because the domain layer is not allowed to
    import the sources layer (§25).
    """
    import copy as _copy
    v = _copy.copy(snap)
    tz = ZoneInfo(snap.tz_name)
    v.sunrise, v.sunset = weather.sun_for(snap.weather_daily or {}, date.isoformat(),
                                          snap.tz_name)
    v.lunar = lunar.lunar_day(date,
                              v.sunrise.value if v.sunrise.ok else None,
                              v.sunset.value if v.sunset.ok else None, tz)
    return v


def _wadeable(z):
    from ..domain.zone import Craft
    return Craft.WADE in z.craft_options()


def _num(v):
    try:
        return "{:,}".format(int(round(float(v))))
    except Exception:
        return str(v)
