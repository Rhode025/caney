"""
The planner dataset the browser runs on. §24, §27.

THE DATA/ENGINE BOUNDARY, stated once so it cannot be argued about later:

    PYTHON owns every NUMBER — instrument readings, routing, arrival bounds, the hourly
    component fits, the confidence signals, the safety claims, the technique tables and
    the published weights. None of it is recomputed anywhere else.

    THE BROWSER owns ASSEMBLY ONLY — the weighted sum (arithmetic over Python's values
    and Python's weights), the window search (argmax over Python's hourly series), the
    ranking blend (Python's published rank formula, shipped as two constants), the
    eligibility gates (Python's precomputed flags) and the rendering.

This split is what makes an interactive planner possible on a static host without a
second modelling engine to keep in sync, and test/planner/test_parity.mjs pins that the
browser reproduces Python's own scores for a set of sampled windows to within 0.05.

The dataset is the LIVE plane (§27): it is regenerated on every build, carries its own
per-signal ages, and can be refreshed independently of the river pages that surround it.
"""
import json
import time

from ..domain.location import LocationEvidence as _LE
from ..domain.observation import DataState
from ..domain.zone import Craft, ZoneKind as _ZK
from ..planner import itinerary as itin_search
from ..planner import opportunity, scoring, transitions, utility, window
from ..planner.engine import VERDICT, hourly_scores
from ..sources.snapshots import localize
from ..version import versions
from ..planner.confidence import SIGNALS, confidence, rank_key
from ..species.profiles import (COMPONENT_LABEL, DISPLAY, MOON_MAX_SHARE, SPECIES,
                                SPECIES_PROFILES, WEIGHTS)
from ..zones.registry import all_zones

HORIZON_H = 96   # local midnight today + 4 days, so "this morning" is always inside it


def _ob(o):
    return {"value": o.value, "unit": o.unit, "state": o.state, "source": o.source,
            "url": o.source_url, "age": o.age_label(), "at": o.observed_at,
            "note": o.note}


def build(snaps, book, claims_by_zone_species, now=None, research_meta=None,
          horizon_h=HORIZON_H):
    now = now or time.time()
    # The horizon starts at LOCAL MIDNIGHT TODAY, not at `now`. A request for "this
    # morning" made at 08:16 still has to score 06:00-08:00, and a series that began at
    # 08:00 would silently drop those hours — which is exactly the parity failure that
    # made this comment necessary.
    import datetime as _d
    from ..tz import zone as _Z
    _tz = _Z("America/Chicago")
    _today = _d.datetime.fromtimestamp(now, _tz).date()
    t0 = int(_d.datetime(_today.year, _today.month, _today.day, tzinfo=_tz).timestamp())
    t1 = t0 + horizon_h * 3600

    data = {
        "built": round(now), "builtIso": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                       time.gmtime(now)),
        "horizon": {"t0": t0, "t1": t1, "hours": horizon_h},
        "tz": "America/Chicago",
        "componentLabels": COMPONENT_LABEL,
        "weights": WEIGHTS,
        "moonMaxShare": MOON_MAX_SHARE,
        "rank": {"base": 0.65, "conf": 0.35},
        # Everything the browser engine would otherwise have to hardcode. §47: a constant
        # in model.js is a second model; a constant here is the same model, shipped.
        "neutralFit": scoring.NEUTRAL,
        "windowSearch": {"step": window.STEP, "min": window.MIN_SPAN,
                         "shortDay": window.SHORT_DAY, "gain": window.GAIN,
                         "tie": window.TIE},
        "verdictThresholds": {"go": VERDICT["go"], "confident": VERDICT["confident"],
                              "fishable": VERDICT["fishable"],
                              "hardComponent": VERDICT["hard_component"]},
        # §6, §7 — the window utility function's constants, published so the browser
        # computes the identical number rather than carrying a model of its own.
        "utility": utility.constants(),
        "opportunity": {"gridMinutes": opportunity.GRID_MINUTES,
                        "maxMinutes": opportunity.MAX_MINUTES,
                        "topN": opportunity.TOP_N,
                        "bucketMinutes": opportunity.BUCKET_MINUTES},
        "itinerary": {"maxZones": itin_search.MAX_ZONES, "beam": itin_search.BEAM,
                      "maxIdleMinutes": itin_search.MAX_IDLE_MINUTES},
        "locationEvidence": {
            "order": list(_LE.ORDER), "prior": dict(_LE.PRIOR), "label": dict(_LE.LABEL),
            "explain": dict(_LE.EXPLAIN), "style": dict(_LE.STYLE),
        },
        "zoneKinds": dict(_ZK.LABEL),
        "versions": versions(),
        "confidenceLabels": [[78, "HIGH CONFIDENCE"], [55, "MODERATE CONFIDENCE"],
                             [32, "LOW CONFIDENCE"], [0, "VERY LOW CONFIDENCE"]],
        "horizonPenalty": {"fromDays": 3, "perDay": 12, "max": 45},
        "confidenceSignals": [{"key": k, "weight": w, "label": l} for k, w, l in SIGNALS],
        "species": {}, "zones": {}, "series": {}, "statics": {}, "gates": {},
        "hourly": {}, "transitions": {},
        "safety": book.to_json(), "claims": {}, "evidence": {}, "freshness": {},
        "confidence": {}, "weatherHours": {}, "lunar": {}, "sun": {},
        "research": research_meta or {"provider": "disabled", "enabled": False},
        "craft": [{"key": c, "label": Craft.LABEL[c]} for c in Craft.ALL],
    }

    for sp in SPECIES:
        p = SPECIES_PROFILES[sp]
        data["species"][sp] = {
            "key": sp, "display": DISPLAY[sp], "weights": WEIGHTS[sp],
            "techniques": p.techniques, "forage": p.forage,
            "habitat": p.habitat, "seasons": p.seasons,
            "spawn": p.spawn, "thermalRefuge": p.thermal_refuge,
            "evidence": {a: getattr(p, a + "_evidence", "heuristic")
                         for a in ("temp", "current", "clarity", "light", "weather")},
            "sources": {a: getattr(p, a + "_source", "")
                        for a in ("temp", "current", "clarity", "light", "forage", "spawn")},
        }

    by_river_weather = {}
    for z in all_zones():
        snap = snaps.get(z.id)
        if snap is None:
            continue
        cfg = _cfg(z)
        zj = z.to_json()
        zj["tailwater"] = z.tailwater
        zj["water"] = {k: _ob(getattr(snap, k)) for k in
                       ("flow", "stage", "flow_trend", "stage_trend", "generation",
                        "generation_on", "water_temp", "lake_elevation", "clarity")}
        zj["generationForecast"] = {"state": snap.generation_forecast.state,
                                    "source": snap.generation_forecast.source,
                                    "url": snap.generation_forecast.source_url,
                                    "age": snap.generation_forecast.age_label(),
                                    "note": snap.generation_forecast.note,
                                    "rows": (snap.generation_forecast.value
                                             if snap.generation_forecast.ok else None)}
        zj["arrival"] = snap.arrival
        zj["modelConfidence"] = snap.model_confidence
        zj["modelNote"] = snap.model_note
        zj["errors"] = snap.errors
        zj["unitCfs"] = cfg.get("unit_cfs")
        zj["genOn"] = cfg.get("gen_on")
        zj["river"] = z.hydrology_river
        data["zones"][z.id] = zj
        data["freshness"][z.id] = snap.freshness()

        if z.hydrology_river not in by_river_weather:
            by_river_weather[z.hydrology_river] = [
                {k: h.get(k) for k in
                 ("epoch", "air_temperature", "wind_speed", "wind_gust", "wind_dir_label",
                  "cloud_cover", "precipitation_probability", "precipitation",
                  "pressure", "pressure_trend", "thunderstorm", "is_day")}
                for h in snap.weather_hours if t0 - 3600 <= h.get("epoch", 0) <= t1 + 3600]
        data["weatherHours"][z.hydrology_river] = by_river_weather[z.hydrology_river]

        # per-date sun and moon across the horizon (§14, and the day-identity invariant:
        # epochs only, labelled client-side from the reader's own clock)
        import datetime as _dt
        from ..tz import zone as _tzf
        tz = _tzf(snap.tz_name)
        for d in range(0, horizon_h // 24 + 2):
            date = (_dt.datetime.fromtimestamp(t0, tz) + _dt.timedelta(days=d)).date()
            v = localize(snap, date)
            key = z.hydrology_river + "|" + date.isoformat()
            if key not in data["lunar"]:
                data["lunar"][key] = v.lunar
                data["sun"][key] = {"sunrise": v.sunrise.value if v.sunrise.ok else None,
                                    "sunset": v.sunset.value if v.sunset.ok else None}

        # ── the gates, precomputed so the browser never re-derives a safety rule ──
        import riverlib
        m = riverlib.WATER_MODEL.get(z.hydrology_river) or {}
        no = m.get("no_wade")
        gates = {
            "craft": z.craft_options(),
            "tailwater": z.tailwater,
            "noReleaseForecast": not snap.generation_forecast.ok,
            "flowTooHighToWade": bool(no and snap.flow.ok and snap.flow.value > no * 1.35),
            "flowTooHighDetail": ("flow is %s cfs, far above the measured no-wade threshold "
                                  "of %s for this reach"
                                  % (scoring._n(snap.flow.value), scoring._n(no))
                                  if (no and snap.flow.ok and snap.flow.value > no * 1.35)
                                  else ""),
            "seasons": {sp: ref.months for sp, ref in z.species_profiles.items()},
            "storm": _storm_hours(snap, t0, t1),
            "wet": _wet_hours(z, snap, cfg, t0, t1),
        }
        data["gates"][z.id] = gates

        for sp in z.species_profiles:
            claims = (claims_by_zone_species.get((z.id, sp)) or [])
            units, gen_known = _units(snap, cfg)
            key = z.id + "|" + sp
            ser = scoring.hourly_series(sp, z, localize(snap, _dt.datetime.fromtimestamp(t0, tz).date()), claims, Craft.ANY,
                _dt.datetime.fromtimestamp(t0, tz).month, cfg, units, gen_known, t0, t1)
            # Light and moon move with the DATE, so the series is stitched per local day
            # rather than computed once against today's sunrise.
            _stitch_by_day(ser, sp, z, snap, claims, cfg, units, gen_known, t0, t1, tz)
            data["series"][key] = _compact(ser)

            st = {}
            for ck, fit in scoring.static_fits(sp, z, snap, claims, Craft.ANY,
                                               _dt.datetime.fromtimestamp(t0, tz).month,
                                               cfg, units, gen_known).items():
                st[ck] = {"v": round(fit.value, 4), "why": fit.why,
                          "known": bool(fit.known)}
            # access is craft-dependent, so ship one value per craft option
            st_by_craft = {}
            for c in Craft.ALL:
                f = scoring.fit_access(z, c)
                st_by_craft[c] = {"v": round(f.value, 4), "why": f.why, "known": f.known}
            data["statics"][key] = {"static": st, "accessByCraft": st_by_craft,
                                    "units": units, "genKnown": gen_known}

            # §4/§55 — the total weighted score at each hour. The window optimiser runs
            # on exactly this array in both engines, so there is one canonical number per
            # hour rather than two derivations of it.
            data["hourly"][key] = hourly_scores(sp, z, ser, scoring.static_fits(
                sp, z, snap, claims, Craft.ANY,
                _dt.datetime.fromtimestamp(t0, tz).month, cfg, units, gen_known),
                Craft.ANY)

            conf, rows = confidence(z, snap, claims, (t0 + 6 * 3600, t0 + 10 * 3600), 0)
            data["confidence"][key] = {"value": conf, "rows": rows}
            # The SCORED confidence is per (zone, species) — the same TWRA claim is worth
            # more at the water it names than at the water it does not. Keying only by
            # claim id meant the last zone written silently overwrote every earlier
            # zone's score, which is how a 66 became a 20 in the header.
            data["evidence"][key] = [{"id": c.id, "confidence": round(c.confidence, 4),
                                      "geographic_match": c.geographic_match,
                                      "seasonal_match": c.seasonal_match}
                                     for c in claims[:8]]
            for c in claims[:8]:
                j = c.to_json()
                j.pop("confidence", None)      # lives in `evidence`, per zone
                data["claims"].setdefault(c.id, j)

    # §11/§12 — the transition graph, per craft. Computed once here so the browser never
    # has to reason about whether a boat can get from one reach to another; it looks the
    # move up and reads the minutes, the mode and the provenance.
    zone_objs = [z for z in all_zones() if z.id in data["zones"]]
    for c in Craft.ALL:
        g = transitions.build_graph(zone_objs, c)
        data["transitions"][c] = {"%s|%s" % k: v.to_json() for k, v in g.items()}

    return data


def _stitch_by_day(ser, sp, z, snap, claims, cfg, units, gen_known, t0, t1, tz):
    """Recompute each hour against ITS OWN local date's sun and moon."""
    import datetime as _dt
    cur_date, view = None, None
    for i in range(ser["hours"]):
        t = ser["t0"] + i * 3600
        d = _dt.datetime.fromtimestamp(t, tz).date()
        if d != cur_date:
            cur_date, view = d, localize(snap, d)
        f = scoring.dynamic_fits(sp, z, view, t, cfg, units, gen_known)
        for k in ser["keys"]:
            fit = f.get(k)
            if fit is None:
                continue
            ser["values"][k][i] = round(fit.value, 4)
            ser["why"][k][i] = fit.why
            ser["known"][k][i] = 1 if fit.known else 0


def _compact(ser):
    """Dedupe the `why` strings — 72 hours of identical prose is most of the payload."""
    out = {"t0": ser["t0"], "step": ser["step"], "hours": ser["hours"],
           "keys": ser["keys"], "values": ser["values"], "known": ser["known"],
           "whyTable": {}, "why": {}}
    for k in ser["keys"]:
        table, idx = [], []
        seen = {}
        for w in ser["why"][k]:
            if w not in seen:
                seen[w] = len(table)
                table.append(w)
            idx.append(seen[w])
        out["whyTable"][k] = table
        out["why"][k] = idx
    return out


def _storm_hours(snap, t0, t1):
    out = []
    for i in range((t1 - t0) // 3600):
        h = snap.weather_at(t0 + i * 3600)
        out.append(1 if (h and h.get("thunderstorm")) else 0)
    return out


def _wet_hours(zone, snap, cfg, t0, t1):
    """1 where released water is expected to be in this reach. Unknown → all zeros + flag."""
    n = (t1 - t0) // 3600
    out = [0] * n
    fc = snap.generation_forecast
    if not fc.ok or not zone.tailwater:
        return out
    on_cfs = cfg.get("gen_on")
    lead = ((snap.arrival or {}).get("first") or {}).get("earliest_h") or 0.0
    for t, v in (fc.value or []):
        if v is None or on_cfs is None or v < on_cfs:
            continue
        a = t + lead * 3600.0
        i0 = int((a - t0) // 3600)
        for i in range(max(0, i0), min(n, i0 + 2)):
            out[i] = 1
    return out


def _cfg(zone):
    from ..sources.registry import water_for
    return water_for(zone.hydrology_river)


def _units(snap, cfg):
    g = snap.generation
    if not g.ok or not cfg.get("unit_cfs"):
        return None, False
    return max(0, round((g.value - cfg.get("unit_offset", 0)) / float(cfg["unit_cfs"]))), True


# ── rehydration: read the EMITTED dataset back into scorer inputs ────────────
# The parity fixture scores through these, so the test compares Python and JavaScript over
# byte-identical arrays rather than over two independently built ones.

def expand_series(compact):
    """The inverse of _compact()."""
    return {"t0": compact["t0"], "step": compact["step"], "hours": compact["hours"],
            "keys": compact["keys"], "values": compact["values"],
            "known": compact["known"],
            "why": {k: [compact["whyTable"][k][i] for i in compact["why"][k]]
                    for k in compact["keys"]}}


def rehydrate(data, zone_id, species, craft="any"):
    """(series, {key: Fit}) exactly as the browser sees them."""
    from ..planner.scoring import Fit
    key = zone_id + "|" + species
    ser = expand_series(data["series"][key])
    st = data["statics"][key]
    fits = {k: Fit(v["v"], v["why"], v["known"]) for k, v in st["static"].items()}
    a = st["accessByCraft"].get(craft) or st["accessByCraft"]["any"]
    if "access" in data["weights"][species]:
        fits["access"] = Fit(a["v"], a["why"], a["known"])
    return ser, fits
