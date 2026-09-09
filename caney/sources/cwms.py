"""
USACE CWMS — dam release actuals and forecasts.

Reuses the endpoint shape riverlib.cwms_series already proved out, through the shared
cache. A thin forecast is reported as such: `state` says whether the forward series is
real, and a missing forecast becomes UNKNOWN, never zero (§3.4). This is the exact place
the "0 cfs → minimum flow → wade all day" failure would have started.
"""
import time

from ..domain.observation import Observation
from .http import cached_json

# Exactly the request riverlib.cwms_series makes, including the `unit=cfs` parameter and
# the versioned Accept header. Both are load-bearing: without them the endpoint 400s.
BASE = ("https://cwms-data.usace.army.mil/cwms-data/timeseries"
        "?office=%s&name=%s&begin=%s&end=%s&unit=cfs&page-size=500000")
ACCEPT = {"Accept": "application/json;version=2"}


def _iso(ep):
    return time.strftime("%Y-%m-%dT%H:00:00Z", time.gmtime(ep))


def series(name, office="LRN", hours_back=48, days_fwd=8, ttl=1800):
    """[(epoch, cfs)] sorted, plus error. Values may legitimately be 0.0 (dam idle)."""
    now = time.time()
    import urllib.parse
    url = BASE % (office, urllib.parse.quote(name),
                  _iso(now - hours_back * 3600), _iso(now + days_fwd * 86400))
    data, err = cached_json(url, ttl=ttl, key="cwms:" + office + ":" + name,
                            headers=ACCEPT)
    if data is None:
        return [], err
    rows = []
    try:
        for v in data.get("values") or []:
            if not v or v[0] is None or v[1] is None:
                continue
            # CWMS hourly averages are PERIOD-ENDING: a value stamped T is the mean over
            # T-1h..T. riverlib shifts by an hour to get true clock time; so does this, or
            # the planner's generation times would sit an hour later than the page's.
            ep = int(v[0] / 1000.0 // 3600) * 3600 - 3600
            rows.append((float(ep), float(v[1])))
    except Exception as e:                     # noqa: BLE001
        return [], "parse: %s" % e
    rows.sort()
    return rows, None


def release(actual_name, forecast_name, office="LRN", ttl=1800, dam=""):
    """(now_ob, forecast_ob, rows) — the release read for one dam.

    forecast_ob.value is [(epoch, cfs)] for the FUTURE only. If CWMS returns nothing
    forward, the observation is UNKNOWN with a note. It is never an empty list presented
    as a schedule, and never zero.
    """
    src = "USACE CWMS %s%s" % (office, (" — " + dam) if dam else "")
    url = "https://water.usace.army.mil/"
    act, e1 = series(actual_name, office, ttl=ttl)
    fc, e2 = series(forecast_name, office, ttl=ttl)
    now = time.time()

    past = [r for r in act if r[0] <= now + 900]
    if past:
        t, v = past[-1]
        now_ob = Observation.known(round(v), "cfs", src, url, observed_at=t, confidence=0.95)
    elif e1:
        now_ob = Observation.error("cfs", src, note=e1)
    else:
        now_ob = Observation.unknown("cfs", src, note="no CWMS actual in the window")

    fwd = [r for r in (fc or act) if r[0] > now]
    if fwd:
        fc_ob = Observation.known([[round(t), round(v)] for t, v in fwd], "cfs", src, url,
                                  observed_at=now, confidence=0.75,
                                  note="forecast release schedule")
    elif e2:
        fc_ob = Observation.error("cfs", src, note=e2)
    else:
        # THE important branch. No forward schedule is UNKNOWN. Downstream must refuse to
        # promise a wade window rather than assume the dam stays off.
        fc_ob = Observation.unknown("cfs", src,
                                    note="CWMS returned no forward release schedule")
    return now_ob, fc_ob, act
