"""
Species scoring. §13, §30 step 4, §32.

The scorer computes a 0..1 FIT per component and multiplies it by the published weight
from species/profiles.py. It never contains a weight of its own, so recalibration is a
config edit. Every component returns (fit, why) and the `why` becomes the score-breakdown
line the reader sees (§32) — a component that cannot explain itself is not allowed to
contribute.

UNKNOWN IS NOT A ZERO SCORE, AND NOT A FREE PASS. A component with no data returns the
neutral fit 0.5 and records itself as unknown; the missing signal is then charged against
CONFIDENCE (confidence.py), not against the score. That separation is §31: a fishery that
looks good on paper with no live water is a high score with low confidence, and the ranker
decides between that and a merely-good fishery that is fully observed.
"""
from ..domain.observation import DataState
from ..species.profiles import COMPONENT_LABEL, profile, weights_for

NEUTRAL = 0.5


class Fit:
    __slots__ = ("value", "why", "known")

    def __init__(self, value, why, known=True):
        self.value = max(0.0, min(1.0, float(value)))
        self.why = why
        self.known = known

    @staticmethod
    def unknown(why):
        return Fit(NEUTRAL, why, known=False)


# ── individual component fits ───────────────────────────────────────────────

def fit_current(snap, prof, cfg, units, gen_known):
    """Current / generation. For stripers this is the trigger, not a modifier."""
    if not gen_known:
        return Fit.unknown("generation state unknown — no usable release reading")
    lo, hi = prof.current.get("ideal_units", [1, 3])
    heavy = prof.current.get("heavy_units", 99)
    if units == 0:
        if prof.current.get("needs"):
            return Fit(1.0 - prof.current.get("slack_penalty", 0.7),
                       "dam idle — no seam, nothing pinning bait")
        return Fit(0.85, "no generation — slack water, which suits this fish")
    if units >= heavy:
        return Fit(0.55, "very heavy water — the fish are there, boat handling is the limit")
    if lo <= units <= hi:
        return Fit(1.0, "%d unit%s turning — the seam is exactly where it should be"
                   % (units, "" if units == 1 else "s"))
    if units < lo:
        return Fit(0.7, "%d unit — current building but light" % units)
    return Fit(0.75, "%d units — more push than ideal" % units)


def fit_generation_trout(snap, prof, cfg, units, gen_known, window):
    """Trout's 30-point column: generation, flow AND whether the wade window survives."""
    if not gen_known:
        return Fit.unknown("no release reading — a tailwater plan cannot assume the dam is off")
    fc = snap.generation_forecast
    start, end = window
    if units and units > 0:
        return Fit(0.35, "%d unit%s running — this reach is not wadeable under that"
                   % (units, "" if units == 1 else "s"))
    if not fc.ok:
        # The §3.4 case, scored honestly: attractive water, no way to know when it ends.
        return Fit(0.4, "no release forecast — the wade window cannot be bounded")
    rise = _first_rise(snap, window, cfg)
    if rise is None:
        return Fit(1.0, "minimum flow through the whole window, no rise forecast")
    covered = max(0.0, min(rise, end) - start) / max(1.0, end - start)
    if covered >= 0.99:
        return Fit(1.0, "minimum flow for the whole window")
    if covered <= 0.15:
        return Fit(0.15, "the water is already up, or comes up right at the start")
    return Fit(0.35 + 0.6 * covered,
               "wadeable for about %d%% of the window before the water arrives"
               % round(covered * 100))


def _first_rise(snap, window, cfg=None):
    """Earliest epoch the release can reach this zone inside the window. Conservative.

    `gen_on` is the threshold above which the dam is GENERATING, not zero. Center Hill
    holds a 250 cfs minimum flow around the clock, so `v > 0` marks every hour of every
    day as a release and reports the wade window as permanently closed. That threshold is
    the same one briefing.py uses (registry.WATER[...]['gen_on']), copied, not re-derived.
    """
    fc = snap.generation_forecast
    if not fc.ok:
        return None
    on_cfs = (cfg or {}).get("gen_on")
    if on_cfs is None:
        return None
    arr = (snap.arrival or {}).get("first") or {}
    # A zone with no routing model gets lead 0: the water is assumed to be here the
    # instant it leaves the dam. That is the CONSERVATIVE direction, which is the only
    # direction a default is allowed to fail in here.
    lead = (arr.get("earliest_h") or 0) * 3600  # not a measurement
    start, end = window
    on = None
    for t, v in (fc.value or []):
        if v is not None and v >= on_cfs and t + lead >= start:
            on = t + lead
            break
    if on is None or on > end:
        return None
    return on


def fit_thermal(snap, prof):
    t = snap.water_temp
    if not t.ok:
        return Fit.unknown("water temperature unknown at this gauge")
    f = float(t.value)
    band = prof.temp_f
    lo, hi = band["prefer"]
    if lo <= f <= hi:
        return Fit(1.0, "%d°F sits inside the preferred %d–%d°F band" % (round(f), lo, hi))
    if f >= band["lethal_hi"]:
        return Fit(0.05, "%d°F is past what this fish tolerates" % round(f))
    if f >= band["stress_hi"]:
        return Fit(0.3, "%d°F is thermally stressful — fish will be tight to the coolest water"
                   % round(f))
    if f >= band.get("prefer_lo", lo - 10):
        span = max(1.0, lo - band.get("prefer_lo", lo - 10))
        return Fit(0.55 + 0.4 * (f - band.get("prefer_lo", lo - 10)) / span,
                   "%d°F is below the preferred band but still active" % round(f))
    if f <= band.get("slow_lo", 40):
        return Fit(0.2, "%d°F — cold and slow" % round(f))
    return Fit(0.45, "%d°F — below their best window" % round(f))


def fit_flow(snap, prof, river_id, units):
    """Flow LEVEL on a free-flowing river: low / prime / high / blown."""
    f = snap.flow
    if not f.ok:
        return Fit.unknown("no flow reading for this reach")
    import riverlib
    m = riverlib.WATER_MODEL.get(river_id) or {}
    ok, marg, no = m.get("wade_ok"), m.get("wade_marginal"), m.get("no_wade")
    v = float(f.value)
    if not (ok and marg and no):
        return Fit(0.6, "%s cfs, no calibrated level bands for this reach" % _n(v))
    if v < ok * 0.45:
        return Fit(1.0 - prof.flow.get("low_penalty", 0.5),
                   "%s cfs — low and skinny, fish are spooky" % _n(v))
    if v <= marg:
        return Fit(1.0, "%s cfs — prime level for this reach" % _n(v))
    if v <= no:
        return Fit(1.0 - prof.flow.get("high_penalty", 0.4),
                   "%s cfs — high, pushy and fishable only on the edges" % _n(v))
    return Fit(1.0 - prof.flow.get("blown_penalty", 0.9), "%s cfs — blown out" % _n(v))


def fit_level(snap, prof):
    """Water LEVEL and TREND, the largemouth column."""
    tr = snap.flow_trend
    f = snap.flow
    if not (tr.ok or f.ok):
        return Fit.unknown("no level or trend reading")
    if not tr.ok:
        return Fit(0.6, "level known, trend unknown")
    t = tr.value
    if t == "steady":
        return Fit(0.9, "stable level — what this fish wants")
    if t == "rising":
        return Fit(0.6 + prof.flow.get("rising_bonus", 0.0),
                   "rising — fish push shallow into the new water, but it colours fast")
    return Fit(1.0 - prof.flow.get("falling_penalty", 0.3),
               "falling — fish pull off the bank cover")


def fit_clarity(snap, prof):
    c = snap.clarity
    if c.ok:
        kind = str(c.value)
    else:
        kind = _clarity_proxy(snap)
        if kind is None:
            return Fit.unknown("clarity unknown — no turbidity gauge and no usable proxy")
    if kind in prof.clarity.get("prefer", []):
        return Fit(0.95, "%s water — inside the preferred range (proxy from flow and rain)"
                   % kind)
    if kind == "muddy":
        return Fit(1.0 - prof.clarity.get("muddy_penalty", 0.4),
                   "muddy — visibility is the limiting factor")
    return Fit(0.6, "%s water" % kind)


def _clarity_proxy(snap):
    """§29 allows a JUSTIFIED proxy. Rising flow colours a river; steady low water does not."""
    if not snap.flow.ok:
        return None
    tr = snap.flow_trend.value if snap.flow_trend.ok else None
    rain = snap.recent_rain_in.value if snap.recent_rain_in.ok else None
    if rain is not None and rain > 1.0:
        return "muddy"
    if tr == "rising":
        return "stained"
    if rain is not None and rain > 0.25:
        return "stained"
    if tr in ("steady", "falling"):
        return "clear"
    return None


def fit_light(snap, prof, window):
    """Time-of-day / light across the requested window, not across 'today'."""
    sr, ss = snap.sunrise, snap.sunset
    if not (sr.ok and ss.ok):
        return Fit.unknown("no sun times for this date")
    start, end = window
    dawn = (sr.value - 2400, sr.value + 5400)      # 40 min before to 90 min after
    dusk = (ss.value - 5400, ss.value + 2400)
    low = _overlap(dawn, start, end) + _overlap(dusk, start, end)
    span = max(1.0, end - start)
    night = _overlap((ss.value + 2400, sr.value + 86400 - 2400), start, end)
    cover = min(1.0, low / min(span, 7200.0))
    if cover >= 0.5:
        return Fit(prof.light.get("low_bonus", prof.light.get("low_light_bonus", 0.9)),
                   "the window sits in the low-light hour, which is when they feed")
    if night / span > 0.6 and "night" in prof.light.get("best", []):
        return Fit(0.8, "night window — this fish feeds after dark under current")
    cloud = _mean(snap.weather_window(start, end), "cloud_cover")
    if cloud is not None and cloud >= 70:
        return Fit(0.8, "%d%% cloud flattens the light all window" % round(cloud))
    mid = (start + end) / 2
    if sr.value + 10800 < mid < ss.value - 10800:
        return Fit(prof.light.get("midday_bright", 0.5),
                   "bright middle of the day — the hardest light to fish")
    return Fit(0.7, "shoulder light")


def fit_weather(snap, prof, window):
    rows = snap.weather_window(*window)
    if not rows:
        return Fit.unknown("no hourly weather for this window")
    start, end = window
    wind = _mean(rows, "wind_speed")
    gust = _max(rows, "wind_gust")
    pop = _max(rows, "precipitation_probability")
    ptr = _mean(rows, "pressure_trend")
    storm = any(r.get("thunderstorm") for r in rows)
    lo, hi = prof.weather.get("wind_ideal_mph", [3, 12])
    score, bits = 1.0, []
    if wind is not None:
        if wind > hi * 2:
            score -= 0.45; bits.append("%d mph wind is the limiting factor" % round(wind))
        elif wind > hi:
            score -= 0.2; bits.append("%d mph wind, workable but pushy" % round(wind))
        elif wind < lo:
            score -= 0.05; bits.append("almost no wind — flat and bright")
        else:
            bits.append("%d mph wind, about right" % round(wind))
    if gust is not None and gust > 25:
        score -= 0.15; bits.append("gusts to %d" % round(gust))
    if pop is not None and pop >= 70:
        score -= 0.1; bits.append("%d%% rain chance" % round(pop))
    if ptr is not None and ptr < -1.0:
        score += prof.weather.get("pressure_drop_bonus", 0.1)
        bits.append("pressure falling ahead of a front")
    if storm:
        score -= 0.5; bits.append("THUNDERSTORM in the forecast for this window")
    return Fit(score, "; ".join(bits) or "unremarkable weather")


def fit_seasonal(zone, prof, species, month):
    ref = zone.species_profiles.get(species)
    if ref is None:
        return Fit(0.0, "this zone holds no profile for the species")
    if not ref.in_season(month):
        return Fit(0.15, "out of the seasonal pattern for this zone")
    season = prof.season_of(month)
    return Fit(ref.weight, "%s pattern: %s" % (season, ref.pattern or "in season"))


def fit_habitat(zone, prof, species):
    ref = zone.species_profiles.get(species)
    want = set(prof.habitat)
    have = set(zone.habitat) | set(ref.habitat if ref else [])
    n = len(want & have)
    if not want:
        return Fit.unknown("no habitat preferences declared for this species")
    frac = min(1.0, n / max(2.0, min(4.0, len(want) * 0.5)))
    return Fit(0.25 + 0.75 * frac,
               "%d of this fish's habitat types present: %s"
               % (n, ", ".join(sorted(want & have)[:4]) or "none matched"))


def fit_forage(zone, prof, species, month, claims):
    ref = zone.species_profiles.get(species)
    hits = [c for c in claims if c.claim_type in ("forage", "recent_report")
            and (not c.location_ids or zone.id in c.location_ids)]
    base = 0.55
    why = "forage read from the species profile only"
    if hits:
        base = min(1.0, 0.6 + 0.2 * len(hits))
        why = "%d sourced forage/report claim%s for this water" % (len(hits),
                                                                   "" if len(hits) == 1 else "s")
    if ref and ref.habitat:
        overlap = set(ref.habitat) & set(prof.habitat)
        if overlap:
            base = min(1.0, base + 0.1)
    return Fit(base, why)


def fit_research(zone, claims, species, month):
    """§5 — research evidence applied AFTER the deterministic components."""
    rel = [c for c in claims if (not c.location_ids or zone.id in c.location_ids)]
    if not rel:
        return Fit(0.35, "no sourced research claim mentions this water for this species")
    rel.sort(key=lambda c: -c.confidence)
    top = rel[:4]
    strength = sum(c.confidence for c in top) / len(top)
    tiers = sorted({c.source_tier for c in top})
    return Fit(min(1.0, 0.35 + 0.9 * strength),
               "%d sourced claim%s (tier %s), best: %s"
               % (len(rel), "" if len(rel) == 1 else "s", "/".join(tiers),
                  top[0].source_title or top[0].source_domain))


def fit_moon(snap, window):
    from ..sources.lunar import solunar_fit
    fit, why = solunar_fit(snap.lunar, *window)
    return Fit(fit, why)


def fit_access(zone, craft):
    opts = zone.craft_options()
    if not opts:
        return Fit.unknown("no access points recorded for this zone")
    from ..domain.zone import Craft
    if craft != Craft.ANY and craft not in opts:
        return Fit(0.0, "no access on this water serves a %s" % Craft.LABEL.get(craft, craft))
    verified = [a for a in zone.access if a.verified]
    if verified:
        return Fit(0.95, "%d verified access point%s" % (len(verified),
                                                          "" if len(verified) == 1 else "s"))
    return Fit(0.55, "access points recorded but not verified to RIVER_SPEC §2")


def fit_hatch(zone, prof, month, claims):
    ref = zone.species_profiles.get("trout")
    on = [f for f in prof.forage]
    base = 0.6
    why = "seasonal forage from the species profile"
    if month in (4, 5, 6):
        base, why = 0.85, "sulphur and caddis season on the tailwaters"
    elif month in (12, 1, 2):
        base, why = 0.7, "midge-dominated winter — small and consistent"
    hits = [c for c in claims if c.claim_type in ("stocking", "survey")
            and (not c.location_ids or zone.id in c.location_ids)]
    if hits:
        base = min(1.0, base + 0.12)
        why += "; %d sourced stocking/survey claim" % len(hits)
    return Fit(base, why)


# ── the component table, and the hourly architecture ────────────────────────
#
# WHY HOURLY. The web app is a static site, so an interactive "what about 6:30-10:00
# instead?" cannot call Python. Rather than port the scorer to JavaScript — two engines,
# guaranteed drift — the scorer is defined so that a WINDOW SCORE IS THE MEAN OF ITS
# HOURLY SCORES. Python emits the hourly component values; the browser averages them over
# whatever window the user drags out and applies the same published weights. Both sides
# compute the identical number, and test/planner/test_hourly_parity.py pins that they do.
#
# Components split into two kinds:
#   STATIC   water temperature, clarity, flow, habitat, research … — one value for the day
#   DYNAMIC  light, weather, moon, generation/wade coverage       — one value per hour
#
# The dynamic set is exactly the set whose old window formulas were already means or
# coverage fractions, so this is a refactor of the arithmetic, not a change to it.

DYNAMIC = ("light", "weather", "moon", "generation")


def static_fits(species, zone, snap, claims, craft, month, cfg, units, gen_known):
    prof = profile(species)
    builders = {
        "thermal":  lambda: fit_thermal(snap, prof),
        "clarity":  lambda: fit_clarity(snap, prof),
        "seasonal": lambda: fit_seasonal(zone, prof, species, month),
        "habitat":  lambda: fit_habitat(zone, prof, species),
        "forage":   lambda: fit_forage(zone, prof, species, month, claims),
        "research": lambda: fit_research(zone, claims, species, month),
        "access":   lambda: fit_access(zone, craft),
        "current":  lambda: fit_current(snap, prof, cfg, units, gen_known),
        "flow":     lambda: fit_flow(snap, prof, zone.hydrology_river, units),
        "level":    lambda: fit_level(snap, prof),
        "hatch":    lambda: fit_hatch(zone, prof, month, claims),
    }
    out = {}
    for key in weights_for(species):
        if key in DYNAMIC:
            continue
        if key not in builders:
            raise KeyError("species %r weights component %r with no fit function"
                           % (species, key))
        out[key] = builders[key]()
    return out


def dynamic_fits(species, zone, snap, hour_start, cfg, units, gen_known):
    """The four time-dependent fits for the single hour beginning at `hour_start`."""
    prof = profile(species)
    w = (hour_start, hour_start + 3600)
    out = {}
    keys = weights_for(species)
    if "light" in keys:      out["light"] = fit_light(snap, prof, w)
    if "weather" in keys:    out["weather"] = fit_weather(snap, prof, w)
    if "moon" in keys:       out["moon"] = fit_moon(snap, w)
    if "generation" in keys: out["generation"] = fit_generation_trout(
        snap, prof, cfg, units, gen_known, w)
    return out


def hourly_series(species, zone, snap, claims, craft, month, cfg, units, gen_known,
                  t0, t1):
    """{'t0','step','keys','values':{key:[per-hour]},'why':{key:[per-hour]}} over [t0,t1)."""
    t0 = int(t0 // 3600) * 3600
    hours = max(1, int((t1 - t0) // 3600))
    keys = [k for k in weights_for(species) if k in DYNAMIC]
    values = {k: [] for k in keys}
    whys = {k: [] for k in keys}
    known = {k: [] for k in keys}
    for i in range(hours):
        f = dynamic_fits(species, zone, snap, t0 + i * 3600, cfg, units, gen_known)
        for k in keys:
            fit = f.get(k) or Fit.unknown("not computed")
            values[k].append(round(fit.value, 4))
            whys[k].append(fit.why)
            known[k].append(1 if fit.known else 0)
    return {"t0": t0, "step": 3600, "hours": hours, "keys": keys,
            "values": values, "why": whys, "known": known}


def aggregate(series, key, start, end):
    """The mean of a dynamic component's hourly values across [start, end).

    THIS IS THE CONTRACT the browser reimplements. Partial hours are weighted by their
    overlap, so 6:30-10:00 is not silently rounded to 6:00-10:00.
    """
    vals = series["values"].get(key)
    if not vals:
        return None, "", True
    t0, step = series["t0"], series["step"]
    num = den = 0.0
    kn = True
    for i, v in enumerate(vals):
        a, b = t0 + i * step, t0 + (i + 1) * step
        ov = max(0.0, min(b, end) - max(a, start))
        if ov <= 0:
            continue
        num += v * ov
        den += ov
        if not series["known"][key][i]:
            kn = False
    if den <= 0:
        return None, "", True
    mid = (start + end) / 2.0
    i = max(0, min(len(vals) - 1, int((mid - t0) // step)))
    return num / den, series["why"][key][i], kn


def components(species, zone, snap, claims, window, craft, month, cfg, units, gen_known,
               series=None):
    """{key: Fit} for a window. Dynamic keys come from the hourly series (§ above)."""
    out = dict(static_fits(species, zone, snap, claims, craft, month, cfg, units, gen_known))
    start, end = window
    if series is None:
        series = hourly_series(species, zone, snap, claims, craft, month, cfg, units,
                               gen_known, start, end + 3600)
    for key in weights_for(species):
        if key not in DYNAMIC:
            continue
        v, why, known = aggregate(series, key, start, end)
        out[key] = Fit(v, why, known) if v is not None else Fit.unknown(
            "no hourly value for this component in the requested window")
    return out


def score(species, zone, snap, claims, window, craft, month, cfg, units, gen_known,
          series=None, statics=None):
    """(score_0_100, [ScoreLine], {component: Fit}). No weight lives in this function."""
    from ..domain.plan import ScoreLine
    w = weights_for(species)
    if statics is not None and series is not None:
        fits = dict(statics)
        start, end = window
        for key in w:
            if key not in DYNAMIC:
                continue
            v, why, known = aggregate(series, key, start, end)
            fits[key] = (Fit(v, why, known) if v is not None
                         else Fit.unknown("no hourly value in this window"))
    else:
        fits = components(species, zone, snap, claims, window, craft, month, cfg, units,
                          gen_known, series)
    total, lines = 0.0, []
    for key, weight in sorted(w.items(), key=lambda kv: -kv[1]):
        fit = fits.get(key) or Fit.unknown("component not computed")
        earned = fit.value * weight
        total += earned
        lines.append(ScoreLine(key=key, label=COMPONENT_LABEL.get(key, key),
                               earned=round(earned, 1), possible=weight,
                               why=fit.why + ("" if fit.known else
                                              " (unknown — charged to confidence, not to score)")))
    return round(total, 1), lines, fits


# ── helpers ─────────────────────────────────────────────────────────────────

def _overlap(win, start, end):
    return max(0, min(win[1], end) - max(win[0], start))


def _mean(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def _max(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return max(vals) if vals else None


def _n(v):
    return "{:,}".format(int(round(v)))
