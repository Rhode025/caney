"""
Moon and solunar. §14.

Expanded from riverlib.solunar to carry phase, illumination, moonrise, moonset and both
major and minor feeding windows as EPOCHS rather than pre-formatted local strings, so the
client can label them in the reader's own clock (the repo's no-build-time-relative-time
invariant applies to the moon too).

It stays a weak signal by construction: the moon component is capped at 3 points of 100 in
every species column, and planner/scoring.py additionally refuses to let it lift a plan out
of SKIP. A 5/5 solunar day on dead water is still a dead day.

Accuracy note: this is the classic mean-synodic approximation, ±1 day on phase and roughly
±40 minutes on rise/set. That is fine for a feeding window and is labelled `approx: True`
everywhere it surfaces. It is NOT accurate enough for anything safety-shaped, and nothing
safety-shaped consumes it.
"""
import datetime as _dt
import math

SYNODIC = 29.530588853
# 2000-01-06 18:14 UTC — the new moon the approximation is anchored on.
REF = _dt.datetime(2000, 1, 6, 18, 14, tzinfo=_dt.timezone.utc).timestamp()

PHASES = [(.02, "New"), (.24, "Waxing crescent"), (.28, "First quarter"),
          (.47, "Waxing gibbous"), (.53, "Full"), (.72, "Waning gibbous"),
          (.78, "Last quarter"), (.98, "Waning crescent"), (2.0, "New")]


def moon_age(day, tz):
    tnoon = _dt.datetime(day.year, day.month, day.day, 12, 0, tzinfo=tz).timestamp()
    age = ((tnoon - REF) / 86400.0) % SYNODIC
    return age, age / SYNODIC


def lunar_day(day, sunrise_epoch, sunset_epoch, tz):
    """Full lunar read for one local date. Epochs throughout; no formatted times."""
    if sunrise_epoch is None or sunset_epoch is None:
        return {"known": False, "why": "no sun times for this date"}
    age, frac = moon_age(day, tz)
    illum = round((1 - math.cos(2 * math.pi * frac)) / 2 * 100)
    phase = next(n for f, n in PHASES if frac <= f)
    waxing = frac < 0.5

    midnight = _dt.datetime(day.year, day.month, day.day, tzinfo=tz).timestamp()
    solar_noon = (sunrise_epoch + sunset_epoch) / 2.0

    # Moon transit lags solar noon by ~48.8 min per day of age; the under-foot transit is
    # 12 h 25 m later. Both are the centres of the "major" feeding windows.
    upper = solar_noon + age * 48.8 * 60.0
    lower = upper + 12 * 3600 + 25 * 60

    def clamp_day(t):
        while t < midnight:
            t += 24 * 3600 + 50 * 60
        while t > midnight + 86400:
            t -= 24 * 3600 + 50 * 60
        return t

    upper, lower = clamp_day(upper), clamp_day(lower)
    # Rise/set sit a quarter-cycle either side of the upper transit.
    moonrise = clamp_day(upper - 6 * 3600 - 12 * 60)
    moonset = clamp_day(upper + 6 * 3600 + 12 * 60)

    d = min(frac, abs(frac - .5), abs(frac - 1.0))
    rating = max(1, min(5, round(1 + (1 - d / 0.25) * 4)))

    def win(centre, half_min):
        return {"start": round(centre - half_min * 60), "end": round(centre + half_min * 60)}

    return {
        "known": True, "approx": True,
        "phase": phase, "illumination": illum, "waxing": waxing,
        "age_days": round(age, 2),
        "moonrise": round(moonrise), "moonset": round(moonset),
        "rating": rating,
        "major_windows": [win(upper, 60), win(lower, 60)],
        "minor_windows": [win(moonrise, 30), win(moonset, 30)],
        "label": "%s · %d%% lit" % (phase, illum),
        "source": "mean-synodic solunar approximation (±1 day phase, ±40 min rise/set)",
    }


def solunar_fit(lunar, start, end):
    """0..1 — how much of [start,end] overlaps a feeding window. Weak by design."""
    if not lunar or not lunar.get("known") or end <= start:
        return 0.35, "solunar unknown"
    span = end - start
    major = sum(_overlap(w, start, end) for w in lunar.get("major_windows") or [])
    minor = sum(_overlap(w, start, end) for w in lunar.get("minor_windows") or [])
    cover = min(1.0, (major + 0.5 * minor) / max(1.0, min(span, 3 * 3600)))
    base = 0.3 + 0.45 * (lunar.get("rating", 3) - 1) / 4.0
    fit = min(1.0, 0.45 * base + 0.55 * cover)
    if cover > 0.25:
        why = "a solunar major overlaps this window"
    elif cover > 0:
        why = "a solunar minor clips this window"
    else:
        why = "no feeding window inside this slot"
    return round(fit, 3), why


def _overlap(w, start, end):
    return max(0, min(w["end"], end) - max(w["start"], start))
