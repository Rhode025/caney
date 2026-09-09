"""USGS instantaneous values — discharge, gage height, water temperature."""
from ..domain.observation import Observation
from .http import cached_json

BASE = "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=%s&parameterCd=%s&period=PT%dH"
PARAMS = {"flow": "00060", "stage": "00065", "temp": "00010"}
LABEL = {"flow": "cfs", "stage": "ft", "temp": "°F"}


def series(site, what="flow", hours=30, ttl=900):
    """[(epoch, value)] newest last, plus an error string. Empty list is NOT zero flow."""
    code = PARAMS.get(what)
    if not code:
        return [], "unknown parameter %r" % what
    data, err = cached_json(BASE % (site, code, hours), ttl=ttl)
    if data is None:
        return [], err
    rows = []
    try:
        for ts in data["value"]["timeSeries"]:
            for v in ts["values"][0]["value"]:
                val = float(v["value"])
                if val <= -999998:          # USGS "no data" sentinel — NOT a reading
                    continue
                import datetime as dt
                t = dt.datetime.fromisoformat(v["dateTime"]).timestamp()
                rows.append((t, val))
    except Exception as e:                  # noqa: BLE001
        return [], "parse: %s" % e
    rows.sort()
    return rows, None


def latest(site, what="flow", hours=30, ttl=900, source_label=""):
    rows, err = series(site, what, hours, ttl)
    src = source_label or ("USGS %s" % site)
    url = "https://waterdata.usgs.gov/monitoring-location/%s/" % site
    if err and not rows:
        return Observation.error(LABEL.get(what, ""), src, note=err), rows
    if not rows:
        return Observation.unknown(LABEL.get(what, ""), src,
                                   note="gauge returned no readings in the window"), rows
    t, v = rows[-1]
    if what == "temp":
        v = v * 9.0 / 5.0 + 32.0            # USGS reports Celsius
    ob = Observation.known(round(v, 2), LABEL.get(what, ""), src, url, observed_at=t,
                           confidence=0.95)
    if err:
        ob.note = (ob.note + " " + err).strip()
    return ob, rows


def trend(rows, hours=3):
    """'rising' | 'falling' | 'steady' | None. None means unknown, never 'steady'."""
    if len(rows) < 2:
        return None
    t_end = rows[-1][0]
    window = [r for r in rows if r[0] >= t_end - hours * 3600]
    if len(window) < 2:
        return None
    a, b = window[0][1], window[-1][1]
    if a == 0:
        return "rising" if b > 0 else "steady"
    ch = (b - a) / abs(a)
    if ch > 0.06:  return "rising"
    if ch < -0.06: return "falling"
    return "steady"
