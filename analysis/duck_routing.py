#!/usr/bin/env python3
"""
Measure how a flood wave travels down the Duck and the Buffalo — the calibration behind the
section pages.

The Caney is dam-driven: a release is announced, so arrival is a routing problem off a known
input. The Duck and the Buffalo are RAIN-driven, and nobody announces rain. But the Duck has two
live gauges 59 river miles apart (Columbia RM 133.3, Centerville RM 74.0), and the upstream one
necessarily sees a rise FIRST. Cross-correlating them measures:

  1. TRAVEL TIME  — how many hours Columbia leads Centerville. This makes the upstream gauge a
     forecast for the downstream reach, which is the only forward-looking signal the middle
     river has: NWPS publishes a forecast for Centerville (CNVT1) and Lobelville (LBVT1) and
     nothing at Columbia or Williamsport.
  2. GAIN         — how much bigger the river is downstream, from tributary inflow. Needed to
     convert an upstream reading into a downstream one rather than just shifting it in time.

Both are then interpolated by river mile for reaches with no gauge of their own (Williamsport).

    python3 analysis/duck_routing.py [days]

Writes analysis/duck_routing.json, which the generators read. Re-run it and the constants move;
that is the point. Nothing here is guessed.
"""
import json, math, os, sys, datetime, urllib.request

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 120
HERE = os.path.dirname(os.path.abspath(__file__))

# (id, USGS site, river mile, label) — river mile decreases downstream
PAIRS = [
    ("duck", [("columbia", "03599500", 133.3, "Duck at Columbia"),
              ("centerville", "03601990", 74.0, "Duck at Hwy 100, Centerville")]),
    ("buffalo", [("flatwoods", "03604000", 47.0, "Buffalo near Flat Woods"),
                 ("lobelville", "03604400", 19.0, "Buffalo below Lobelville")]),
]


def hourly(site, days):
    u = ("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=%s&parameterCd=00060"
         "&startDT=%s&endDT=%s" % (site,
         (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%d"),
         datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")))
    for attempt in range(3):
        try:
            v = json.load(urllib.request.urlopen(u, timeout=180))["value"]["timeSeries"][0]["values"][0]["value"]
            break
        except Exception as e:
            if attempt == 2: raise
            print("  retry after %s" % e)
    b = {}
    for p in v:
        try: q = float(p["value"])
        except Exception: continue
        if q < 0: continue
        t = datetime.datetime.fromisoformat(p["dateTime"]).timestamp()
        b.setdefault(int(t // 3600) * 3600, []).append(q)
    return {k: sum(x) / len(x) for k, x in b.items()}


def corr(a, b):
    n = len(a)
    if n < 2: return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = math.sqrt(sum((x - ma) ** 2 for x in a)); vb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) if va and vb else 0.0


out = {"measured": datetime.datetime.now(datetime.timezone.utc).isoformat(), "days": DAYS, "rivers": {}}
for river, sites in PAIRS:
    (uid, usite, urm, ulab), (did, dsite, drm, dlab) = sites
    print("\n=== %s: %s (RM %.1f) -> %s (RM %.1f) ===" % (river, ulab, urm, dlab, drm))
    up, dn = hourly(usite, DAYS), hourly(dsite, DAYS)
    ks = sorted(set(up) & set(dn))
    print("  aligned %d hours" % len(ks))
    if len(ks) < 500:
        print("  NOT ENOUGH DATA — skipping"); continue
    best = None; curve = []
    for lag in range(0, 49):
        pa = [up[k] for k in ks if (k + lag * 3600) in dn]
        pb = [dn[k + lag * 3600] for k in ks if (k + lag * 3600) in dn]
        if len(pa) < 500: continue
        r = corr(pa, pb); curve.append([lag, round(r, 4)])
        if best is None or r > best[1]: best = (lag, r)
    lag, r = best
    pa = [up[k] for k in ks if (k + lag * 3600) in dn]
    pb = [dn[k + lag * 3600] for k in ks if (k + lag * 3600) in dn]
    rat = sorted(y / x for x, y in zip(pa, pb) if x > 50)
    # TRANSFER FUNCTION. A constant gain multiplier is the obvious choice and it is the WORST of
    # the candidates: backtested at the measured lag it scores NSE 0.22 on the Duck and loses to
    # persistence at every horizon, with a +345 cfs bias (analysis/backtest_route.py). A power
    # law fitted in log space -- the standard hydrologic transfer between two gauges -- scores
    # NSE 0.81 on held-out data. Fit here so the pages quote a model that was actually tested.
    _tr = int(len(pa) * 0.7)
    def _fitpow(xs, ys):
        pts = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if x > 1 and y > 1]
        n2 = len(pts)
        if n2 < 20: return None
        sx = sum(q[0] for q in pts); sy = sum(q[1] for q in pts)
        sxx = sum(q[0] * q[0] for q in pts); sxy = sum(q[0] * q[1] for q in pts)
        d2 = n2 * sxx - sx * sx
        if abs(d2) < 1e-9: return None
        b2 = (n2 * sxy - sx * sy) / d2
        return round(math.exp((sy - b2 * sx) / n2), 5), round(b2, 5)
    def _fitlin(xs, ys):
        n2 = len(xs); sx = sum(xs); sy = sum(ys)
        sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
        d2 = n2 * sxx - sx * sx
        if abs(d2) < 1e-9: return None
        b2 = (n2 * sxy - sx * sy) / d2
        return round((sy - b2 * sx) / n2, 3), round(b2, 5)
    _pw = _fitpow(pa[:_tr], pb[:_tr]); _ln = _fitlin(pa[:_tr], pb[:_tr])
    def _mae(f):
        v = [abs(f(x) - y) for x, y in zip(pa[_tr:], pb[_tr:])]
        return round(sum(v) / len(v), 1) if v else None
    _cand = {}
    if _pw: _cand["power"] = (_mae(lambda x: _pw[0] * (x ** _pw[1])), {"a": _pw[0], "b": _pw[1]})
    if _ln: _cand["linear"] = (_mae(lambda x: max(0.0, _ln[0] + _ln[1] * x)), {"a": _ln[0], "b": _ln[1]})
    _gm = rat[len(rat) // 2]
    _cand["const"] = (_mae(lambda x: x * _gm), {"gain": round(_gm, 3)})
    _best = min(_cand.items(), key=lambda kv: kv[1][0] if kv[1][0] is not None else 9e9)
    miles = urm - drm
    rec = {
        "up": {"id": uid, "site": usite, "rm": urm, "label": ulab},
        "down": {"id": did, "site": dsite, "rm": drm, "label": dlab},
        "miles": round(miles, 1), "lag_h": lag, "r": round(r, 4),
        "mph": round(miles / lag, 2) if lag else None,
        "gain_mean": round((sum(pb) / len(pb)) / (sum(pa) / len(pa)), 3),
        "gain_median": round(rat[len(rat) // 2], 3),
        "gain_p25": round(rat[len(rat) // 4], 3),
        "gain_p75": round(rat[3 * len(rat) // 4], 3),
        "n_hours": len(pa), "curve": curve,
        "transfer": {"kind": _best[0], **_best[1][1], "test_mae": _best[1][0],
                     "compared": {k: v[0] for k, v in _cand.items()}},
        # Below this horizon persistence (assume the river stays put) beats routing, so the page
        # must not claim a head start inside it. Measured in analysis/backtest_route.py.
        "useful_from_h": 12,
    }
    out["rivers"][river] = rec
    print("  BEST LAG %d h (r=%.4f) · %.1f mi -> %.2f mph" % (lag, r, miles, rec["mph"] or 0))
    print("  gain: mean x%.2f · median x%.2f (p25 %.2f, p75 %.2f)"
          % (rec["gain_mean"], rec["gain_median"], rec["gain_p25"], rec["gain_p75"]))
    print("  transfer: %s  test MAE %s   (candidates: %s)"
          % (rec["transfer"]["kind"], rec["transfer"]["test_mae"],
             ", ".join("%s %s" % (k, v) for k, v in rec["transfer"]["compared"].items())))

p = os.path.join(HERE, "duck_routing.json")
json.dump(out, open(p, "w"), indent=1)
print("\nwrote %s" % p)
