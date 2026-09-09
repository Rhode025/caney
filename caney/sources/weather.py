"""
Hourly weather for the user's requested window. §28.

The old pages asked for "today". A plan for 6:30–10:00 AM needs the wind, cloud, pressure
and storm risk AT 6:30–10:00 AM, so this returns an hourly series across the horizon and
RiverSnapshot.weather_window() slices it to the request.

Open-Meteo is the primary because it is the one free hourly source with no key, CORS-open,
that publishes every field the plan needs. NWS is queried for the active-alert layer only,
where it is authoritative (Tier A) and Open-Meteo has nothing equivalent.
"""
import datetime as _dt
import time

from ..domain.observation import Observation
from .http import cached_json

HOURLY = ("temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,"
          "precipitation_probability,cloud_cover,wind_speed_10m,wind_gusts_10m,"
          "wind_direction_10m,surface_pressure,weather_code,is_day")
DAILY = "sunrise,sunset,temperature_2m_max,temperature_2m_min,precipitation_probability_max"

URL = ("https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
       "&hourly=" + HOURLY + "&daily=" + DAILY +
       "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
       "&timezone=%s&forecast_days=%d")

# WMO weather codes that mean a thunderstorm is in the forecast for that hour.
STORM_CODES = {95, 96, 99}
COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def compass(deg):
    if deg is None:
        return ""
    return COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


def hourly(lat, lon, tz="America/Chicago", days=4, ttl=1800):
    """([hour dicts], daily dict, error). Missing fields stay None — never 0."""
    data, err = cached_json(URL % (lat, lon, tz.replace("/", "%2F"), days), ttl=ttl,
                            key="wx:%.3f,%.3f:%d" % (lat, lon, days))
    if data is None:
        return [], {}, err
    h = data.get("hourly") or {}
    times = h.get("time") or []
    fetched = time.time()
    out = []
    for i, t in enumerate(times):
        try:
            ep = _dt.datetime.fromisoformat(t).replace(
                tzinfo=_tz(tz)).timestamp()
        except Exception:
            continue

        def g(k):
            v = (h.get(k) or [])
            return v[i] if i < len(v) else None

        code = g("weather_code")
        out.append({
            "iso": t, "epoch": ep, "_fetched_at": fetched,
            "air_temperature": g("temperature_2m"),
            "apparent_temperature": g("apparent_temperature"),
            "humidity": g("relative_humidity_2m"),
            "precipitation": g("precipitation"),
            "precipitation_probability": g("precipitation_probability"),
            "cloud_cover": g("cloud_cover"),
            "wind_speed": g("wind_speed_10m"),
            "wind_gust": g("wind_gusts_10m"),
            "wind_direction": g("wind_direction_10m"),
            "wind_dir_label": compass(g("wind_direction_10m")),
            "pressure": g("surface_pressure"),
            "weather_code": code,
            "thunderstorm": bool(code in STORM_CODES) if code is not None else None,
            "is_day": g("is_day"),
        })
    # Pressure trend: the 3-hour change, which is the number anglers actually use.
    for i, row in enumerate(out):
        p_now, p_prev = row.get("pressure"), out[i - 3]["pressure"] if i >= 3 else None
        row["pressure_trend"] = (round(p_now - p_prev, 2)
                                 if (p_now is not None and p_prev is not None) else None)
    d = data.get("daily") or {}
    daily = {"time": d.get("time") or [], "sunrise": d.get("sunrise") or [],
             "sunset": d.get("sunset") or [],
             "hi": d.get("temperature_2m_max") or [], "lo": d.get("temperature_2m_min") or [],
             "pop": d.get("precipitation_probability_max") or []}
    return out, daily, err


_TZC = {}


def _tz(name):
    if name not in _TZC:
        from ..tz import zone as _tzf
        _TZC[name] = _tzf(name)
    return _TZC[name]


def sun_for(daily, date_iso, tz="America/Chicago"):
    """(sunrise_ob, sunset_ob) for one local date."""
    try:
        i = daily["time"].index(date_iso)
    except (ValueError, KeyError):
        return Observation.unknown("", "Open-Meteo"), Observation.unknown("", "Open-Meteo")

    def ob(key):
        try:
            iso = daily[key][i]
            ep = _dt.datetime.fromisoformat(iso).replace(tzinfo=_tz(tz)).timestamp()
            return Observation.known(ep, "epoch", "Open-Meteo (astronomical)",
                                     confidence=1.0, observed_at=ep, note=iso)
        except Exception:
            return Observation.unknown("", "Open-Meteo")
    return ob("sunrise"), ob("sunset")


def alerts(lat, lon, ttl=900):
    """NWS active alerts — Tier A, and the only authority for a weather hazard."""
    url = "https://api.weather.gov/alerts/active?point=%.4f,%.4f" % (lat, lon)
    data, err = cached_json(url, ttl=ttl)
    if data is None:
        return [], err
    out = []
    for f in (data.get("features") or [])[:6]:
        p = f.get("properties") or {}
        out.append({"event": p.get("event"), "severity": p.get("severity"),
                    "urgency": p.get("urgency"), "onset": p.get("onset"),
                    "ends": p.get("ends") or p.get("expires"),
                    "headline": (p.get("headline") or "")[:200],
                    "source": "NOAA/NWS", "source_url": "https://api.weather.gov/alerts/active"})
    return out, None
