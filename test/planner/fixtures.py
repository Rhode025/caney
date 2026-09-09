"""
Deterministic fixtures. §50, §51.

Every fixture builds a RiverSnapshot by hand, with NO network and NO clock dependence:
`T0` is a fixed epoch, so a test that passes today passes in February. That is the whole
point of a golden fixture — a suite that quietly re-derives its expectations from live
water proves nothing.
"""
import datetime as _dt
import os
import sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from caney.domain.observation import DataState, Observation      # noqa: E402
from caney.domain.snapshot import RiverSnapshot                  # noqa: E402
from caney.sources import lunar                                  # noqa: E402

CT = ZoneInfo("America/Chicago")

#: Wednesday 2026-09-09, local midnight. Every fixture time is an offset from here.
T0 = _dt.datetime(2026, 9, 9, 0, 0, tzinfo=CT).timestamp()

SUNRISE_H, SUNSET_H = 6.35, 19.0     # 2026-09-09 in Middle Tennessee


def at(hour, day=0):
    return T0 + day * 86400 + hour * 3600


def hours(day=0, temp=72, wind=6, cloud=30, pop=5, storm_hours=(), pressure=1014):
    """A day of hourly weather rows, midnight to midnight."""
    out = []
    for h in range(24):
        ep = at(h, day)
        out.append({
            "epoch": ep, "iso": _dt.datetime.fromtimestamp(ep, CT).isoformat(),
            "_fetched_at": T0 + 6 * 3600,
            "air_temperature": temp + (6 if 12 <= h <= 17 else -4 if h <= 6 else 0),
            "apparent_temperature": temp, "humidity": 70,
            "precipitation": 0.0, "precipitation_probability": pop,
            "cloud_cover": cloud, "wind_speed": wind, "wind_gust": wind * 1.8,
            "wind_direction": 200, "wind_dir_label": "SSW",
            "pressure": pressure, "pressure_trend": 0.0,
            "weather_code": 95 if h in storm_hours else 0,
            "thunderstorm": h in storm_hours,
            "is_day": 1 if 7 <= h <= 18 else 0,
        })
    return out


def snapshot(zone_id, river_id, *, flow=None, stage=None, temp_f=None, generation=None,
             forecast=None, flow_trend=None, clarity=None, arrival=None,
             model_confidence="measured", days=3, storm_hours=(), wind=6, cloud=30,
             water_state=DataState.KNOWN):
    """One snapshot with exactly the fields a test cares about; the rest stay UNKNOWN."""
    s = RiverSnapshot(zone_id=zone_id, river_id=river_id, taken_at=at(6))
    s.tz_name = "America/Chicago"

    def ob(v, unit, src):
        if v is None:
            return Observation.unknown(unit, src, note="not supplied by this fixture")
        if water_state == DataState.STALE:
            return Observation.stale(v, unit, src, observed_at=at(6) - 8 * 3600)
        return Observation.known(v, unit, src, observed_at=at(5), confidence=0.95)

    s.flow = ob(flow, "cfs", "fixture gauge")
    s.stage = ob(stage, "ft", "fixture gauge")
    s.water_temp = ob(temp_f, "°F", "fixture gauge")
    s.generation = ob(generation, "cfs", "fixture dam")
    s.clarity = (Observation.known(clarity, "", "fixture") if clarity
                 else Observation.unknown("", "fixture"))
    s.flow_trend = (Observation.known(flow_trend, "", "fixture") if flow_trend
                    else Observation.unknown("", "fixture"))
    s.stage_trend = Observation.unknown("", "fixture")

    if forecast is None:
        # THE §3.4 CASE. No forward schedule is UNKNOWN, and nothing downstream may read
        # it as "the dam stays off".
        s.generation_forecast = Observation.unknown(
            "cfs", "fixture dam", note="fixture supplies no forward release schedule")
        s.generation_on = Observation.unknown("", "fixture dam")
    elif forecast == "stale":
        s.generation_forecast = Observation.stale(
            [[round(at(h)), 250] for h in range(48)], "cfs", "fixture dam",
            observed_at=at(6) - 30 * 3600, note="last-good schedule, 30 hours old")
        s.generation_on = Observation.stale(False, "", "fixture dam",
                                            observed_at=at(6) - 30 * 3600)
    else:
        s.generation_forecast = Observation.known(
            [[round(t), round(v)] for t, v in forecast], "cfs", "fixture dam",
            observed_at=at(5), confidence=0.75)
        s.generation_on = Observation.known(
            bool(generation and generation > 800), "", "fixture dam", observed_at=at(5))

    s.weather_hours = []
    for d in range(days):
        s.weather_hours += hours(d, storm_hours=storm_hours if d == 0 else (),
                                 wind=wind, cloud=cloud)
    s.weather_daily = {
        "time": [(_dt.datetime.fromtimestamp(T0, CT) + _dt.timedelta(days=d)).date().isoformat()
                 for d in range(days)],
        "sunrise": [_dt.datetime.fromtimestamp(at(SUNRISE_H, d), CT).strftime("%Y-%m-%dT%H:%M")
                    for d in range(days)],
        "sunset": [_dt.datetime.fromtimestamp(at(SUNSET_H, d), CT).strftime("%Y-%m-%dT%H:%M")
                   for d in range(days)],
        "hi": [88] * days, "lo": [66] * days, "pop": [10] * days,
    }
    s.sunrise = Observation.known(at(SUNRISE_H), "epoch", "fixture", confidence=1.0)
    s.sunset = Observation.known(at(SUNSET_H), "epoch", "fixture", confidence=1.0)
    s.lunar = lunar.lunar_day(_dt.datetime.fromtimestamp(T0, CT).date(),
                              at(SUNRISE_H), at(SUNSET_H), CT)
    s.arrival = arrival or {}
    s.model_confidence = model_confidence
    return s


def with_arrival(s, mfd, dam="Center Hill Dam"):
    """Attach the real routing distribution for a zone `mfd` miles below the dam."""
    import riverlib
    e, m, l = riverlib.arrival_window(mfd, "first")
    pe, pm, pl = riverlib.arrival_window(mfd, "peak")
    s.arrival = {"mfd": mfd, "dam": dam,
                 "first": {"earliest_h": e, "typical_h": m, "latest_h": l},
                 "peak": {"earliest_h": pe, "typical_h": pm, "latest_h": pl},
                 "source": "riverlib.ARRIVAL_STAGES"}
    return s


# ── §50 golden release schedules ───────────────────────────────────────────

def _flat(cfs, h1=48):
    return [(at(h), cfs) for h in range(h1)]


def _blocks(spec, base=250, h1=48):
    """spec: [(start_h, end_h, cfs), …] on top of a minimum-flow baseline."""
    out = []
    for h in range(h1):
        v = base
        for a, b, c in spec:
            if a <= h < b:
                v = c
        out.append((at(h), v))
    return out


GOLDEN_RELEASES = {
    "no_generation":          _flat(250),
    "single_afternoon":       _blocks([(13, 18, 7300)]),
    "ramp_1u_2u_1u":          _blocks([(9, 11, 3900), (11, 15, 7300), (15, 18, 3900)]),
    "two_separate_releases":  _blocks([(6, 9, 3900), (15, 20, 7300)]),
    "overnight_into_morning": _blocks([(21, 30, 7300)]),
    "all_day":                _flat(7300),
}

#: The ones that are NOT schedules at all — these must never look like "no generation".
GOLDEN_ABSENCES = {"missing_forecast": None, "stale_forecast": "stale"}

#: §50 warmwater flow bands, expressed against the reach's OWN measured wade thresholds
#: rather than as arbitrary multiples — a fixed multiplier landed "very low" inside the
#: prime band on the Duck and the assertion passed for the wrong reason.
WARMWATER_BANDS = ("very_low", "prime", "rising_stained", "high", "blown")


def warmwater_flow(model, band):
    ok, marg, no = model["wade_ok"], model["wade_marginal"], model["no_wade"]
    return {
        "very_low":       ok * 0.30,
        "prime":          ok * 1.00,
        "rising_stained": (ok + marg) / 2.0,
        "high":           (marg + no) / 2.0,
        "blown":          no * 1.8,
    }[band]


def smith_fork_runoff(base_forecast, add_cfs=1800, from_h=8, to_h=20):
    """A tributary runoff event on top of a release: the Smith Fork case (§50).

    Modelled as extra water in the reach that the DAM SCHEDULE does not explain — which is
    the whole difficulty: the release says minimum flow and the river is not at minimum."""
    out = []
    for t, v in base_forecast:
        h = (t - T0) / 3600.0
        out.append((t, v + (add_cfs if from_h <= h < to_h else 0)))
    return out
