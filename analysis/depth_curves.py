#!/usr/bin/env python3
"""
Fit a depth-rise curve for every river whose gauge reports BOTH discharge (00060) and
gage height (00065). Emits, per river, median stage per flow bin referenced to the
min-flow stage — i.e. "how many feet does the river come up at this flow".

This is the MEASURED half of the wade/float model. It says nothing about whether a
given depth floats a given boat; that anchor has to come from somewhere else and is
recorded separately with its source.

    python3 analysis/depth_curves.py            # all rivers
    python3 analysis/depth_curves.py caney      # one
"""
import json, urllib.request, datetime, statistics, math, sys, os

UA = {"User-Agent": "caney-depth/0.2"}
START, END = "2018-01-01", "2026-08-01"
GAUGES = {                       # river id -> (usgs site, human label)
    "caney":      ("03424860", "Caney Fork at Stonewall"),
    "cumberland": ("03414100", "Cumberland at Burkesville"),
    "cumbnash":   ("03431500", "Cumberland at Nashville"),
    "stones":     ("03430200", "Stones River at US-70"),
    "elktn":      ("03582000", "Elk River above Fayetteville"),
    "elk":        ("03584600", "Elk River at Prospect"),
    "duck":       ("03599500", "Duck River (USGS)"),
}

def hk(e): return int(e // 3600) * 3600

def pairs_for(site):
    u = ("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=%s"
         "&startDT=%s&endDT=%s&parameterCd=00060,00065" % (site, START, END))
    d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=600))
    ser = {}
    for ts in d["value"]["timeSeries"]:
        code = ts["variable"]["variableCode"][0]["value"]; b = {}
        for p in ts["values"][0]["value"]:
            try: v = float(p["value"])
            except Exception: continue
            if v <= -999: continue
            b.setdefault(hk(datetime.datetime.fromisoformat(p["dateTime"]).timestamp()), []).append(v)
        ser[code] = {k: statistics.mean(x) for k, x in b.items()}
    Q, S = ser.get("00060", {}), ser.get("00065", {})
    return [(Q[k], S[k]) for k in sorted(set(Q) & set(S)) if Q[k] > 0]

def curve(pairs, nbins=11):
    """Log-spaced flow bins -> median stage rise over the min-flow bin."""
    qs = sorted(p[0] for p in pairs)
    lo = qs[int(len(qs) * 0.01)]; hi = qs[int(len(qs) * 0.995)]
    edges = [lo * (hi / lo) ** (i / nbins) for i in range(nbins + 1)]
    out, base = [], None
    for a, b in zip(edges, edges[1:]):
        v = [s for q, s in pairs if a <= q < b]
        if len(v) < 40: continue
        m = statistics.median(v)
        if base is None: base = m
        out.append([round(a), round(m - base, 2)])
    return out, base

def exponent(pairs):
    """Depth exponent f in D ∝ Q^f, fitted at the bed offset that maximises R²
    WITHOUT letting the offset run away (deep offsets trivially linearise the log fit)."""
    ss = [p[1] for p in pairs]; smin = min(ss)
    best = None
    for off in (0.3, 0.5, 0.8, 1.2, 1.8, 2.5):
        bed = smin - off; xs = []; ys = []
        for q, s in pairs:
            d = s - bed
            if d <= 0.01: continue
            xs.append(math.log(q)); ys.append(math.log(d))
        if len(xs) < 200: continue
        n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
        sxx = sum((x-mx)**2 for x in xs); sxy = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
        f = sxy/sxx; lc = my - f*mx
        ssr = sum((y-(lc+f*x))**2 for x, y in zip(xs, ys)); sst = sum((y-my)**2 for y in ys)
        r2 = 1 - ssr/sst
        if best is None or r2 > best[2]: best = (f, off, r2)
    return best

want = sys.argv[1:] or list(GAUGES)
res = {}
for rid in want:
    site, label = GAUGES[rid]
    try:
        pr = pairs_for(site)
    except Exception as e:
        print("%-11s FETCH FAILED %s" % (rid, str(e)[:60])); continue
    if len(pr) < 500:
        print("%-11s too few paired points (%d)" % (rid, len(pr))); continue
    cv, base = curve(pr)
    ex = exponent(pr)
    res[rid] = {"site": site, "label": label, "n": len(pr), "base_stage": round(base, 2),
                "q_min": round(min(p[0] for p in pr)), "q_max": round(max(p[0] for p in pr)),
                "exponent": (round(ex[0], 3) if ex else None), "r2": (round(ex[2], 4) if ex else None),
                "rise_curve": cv}
    print("%-11s n=%-7d Q %6d-%-8d f=%-6s R2=%-7s bins=%d"
          % (rid, len(pr), res[rid]["q_min"], res[rid]["q_max"],
             res[rid]["exponent"], res[rid]["r2"], len(cv)))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "depth_curves.json")
json.dump(res, open(out, "w"), indent=1)
print("\nwrote", out)
