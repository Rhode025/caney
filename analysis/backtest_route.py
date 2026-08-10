#!/usr/bin/env python3
"""
Backtest and optimise the Duck/Buffalo flow-prediction engine.

Two independent claims are on those pages, and each is tested separately here.

  A. TEMPORAL — "a rise at Columbia reaches Centerville ~14 h later", so the upstream gauge is a
     head start on the lower river. Tested by forecasting Centerville h hours ahead from
     Columbia and scoring against PERSISTENCE (assume the river stays where it is). Beating
     persistence is the entire bar: if it cannot, the head start is decorative.

  B. SPATIAL — the middle reach has no gauge, so its level is interpolated between Columbia and
     Centerville. Normally untestable. But COLUMBIA ITSELF sits between two other gauges
     (Milltown RM 179, Centerville RM 74), so it can be hidden, predicted from its neighbours,
     and the interpolation method scored against a real reading. That is a genuine held-out test
     of the method the middle page depends on.

Every model is fitted on the first 70% of the record and scored ONLY on the last 30%, so a
flexible model cannot win by memorising. Metrics: MAE, RMSE, bias, Nash-Sutcliffe (NSE > 0 beats
predicting the mean; NSE > persistence's is the real bar).

    python3 analysis/backtest_route.py [days]

Writes analysis/backtest_route.json. Nothing here is assumed; re-run it and the numbers move.
"""
import json, math, os, sys, datetime, urllib.request

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 180
HERE = os.path.dirname(os.path.abspath(__file__))

# site -> (label, river mile, drainage area mi2). Areas from the USGS site service.
SITES = {
    "03599240": ("Duck above Milltown", 179.0, 916.0),
    "03599500": ("Duck at Columbia",    133.3, 1208.0),
    "03601990": ("Duck at Centerville",  74.0, 2048.0),
    "03604000": ("Buffalo at Flat Woods", 47.0, 447.0),
    "03604400": ("Buffalo below Lobelville", 19.0, 702.0),
}


def hourly(site, days):
    u = ("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=%s&parameterCd=00060"
         "&startDT=%s&endDT=%s" % (site,
         (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%d"),
         datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")))
    for a in range(3):
        try:
            v = json.load(urllib.request.urlopen(u, timeout=240))["value"]["timeSeries"][0]["values"][0]["value"]; break
        except Exception as e:
            if a == 2: raise
            print("   retry %s" % e)
    b = {}
    for p in v:
        try: q = float(p["value"])
        except Exception: continue
        if q < 0: continue
        b.setdefault(int(datetime.datetime.fromisoformat(p["dateTime"]).timestamp() // 3600) * 3600, []).append(q)
    return {k: sum(x) / len(x) for k, x in b.items()}


def stats(obs, pred):
    """MAE / RMSE / bias / NSE / r over paired lists."""
    n = len(obs)
    if n < 10: return None
    e = [p - o for o, p in zip(obs, pred)]
    mo = sum(obs) / n
    sse = sum(x * x for x in e)
    sst = sum((o - mo) ** 2 for o in obs)
    mp = sum(pred) / n
    va = math.sqrt(sum((o - mo) ** 2 for o in obs)); vb = math.sqrt(sum((p - mp) ** 2 for p in pred))
    r = sum((o - mo) * (p - mp) for o, p in zip(obs, pred)) / (va * vb) if va and vb else 0.0
    return {"n": n, "mae": round(sum(abs(x) for x in e) / n, 1), "rmse": round(math.sqrt(sse / n), 1),
            "bias": round(sum(e) / n, 1), "nse": round(1 - sse / sst, 4) if sst else None, "r": round(r, 4)}


def fit_pow(xs, ys):
    """Least squares in log space: y = a * x^b. Standard hydrologic transfer between gauges."""
    pts = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if x > 1 and y > 1]
    n = len(pts)
    if n < 20: return None
    sx = sum(p[0] for p in pts); sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts); sxy = sum(p[0] * p[1] for p in pts)
    d = n * sxx - sx * sx
    if abs(d) < 1e-9: return None
    b = (n * sxy - sx * sy) / d
    a = math.exp((sy - b * sx) / n)
    return a, b


def fit_lin(xs, ys):
    n = len(xs)
    sx = sum(xs); sy = sum(ys); sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
    d = n * sxx - sx * sx
    if abs(d) < 1e-9: return None
    b = (n * sxy - sx * sy) / d
    return (sy - b * sx) / n, b


def fit_kernel(X, y, L):
    """Least-squares FIR kernel y[t] = sum_i w_i x[t-i], solved by normal equations + ridge."""
    m = len(y)
    A = [[0.0] * L for _ in range(L)]; c = [0.0] * L
    for t in range(m):
        row = X[t]
        for i in range(L):
            c[i] += row[i] * y[t]
            for j in range(L):
                A[i][j] += row[i] * row[j]
    for i in range(L): A[i][i] += 1e-6 * (A[i][i] or 1.0)      # ridge, keeps it invertible
    # gaussian elimination
    for i in range(L):
        p = max(range(i, L), key=lambda k: abs(A[k][i]))
        if abs(A[p][i]) < 1e-12: return None
        A[i], A[p] = A[p], A[i]; c[i], c[p] = c[p], c[i]
        for k in range(i + 1, L):
            f = A[k][i] / A[i][i]
            for j in range(i, L): A[k][j] -= f * A[i][j]
            c[k] -= f * c[i]
    w = [0.0] * L
    for i in range(L - 1, -1, -1):
        w[i] = (c[i] - sum(A[i][j] * w[j] for j in range(i + 1, L))) / A[i][i]
    return w


print("fetching %d days ..." % DAYS)
S = {k: hourly(k, DAYS) for k in SITES}
for k, v in S.items(): print("  %-10s %-26s %5d hours" % (k, SITES[k][0], len(v)))
OUT = {"days": DAYS, "measured": datetime.datetime.now(datetime.timezone.utc).isoformat()}

# ══════════════════════════════════════════════════════════════════════════════
# A. TEMPORAL — does the upstream gauge actually forecast the downstream one?
# ══════════════════════════════════════════════════════════════════════════════
def temporal(up_site, dn_site, horizons, tag):
    up, dn = S[up_site], S[dn_site]
    ks = sorted(set(up) & set(dn))
    if len(ks) < 800: print("  not enough overlap for %s" % tag); return None
    cut = ks[int(len(ks) * 0.7)]
    res = {}
    print("\n── A. TEMPORAL · %s ──" % tag)
    print("   %s -> %s   train %d h / test %d h"
          % (SITES[up_site][0], SITES[dn_site][0], sum(1 for k in ks if k < cut), sum(1 for k in ks if k >= cut)))
    print("   %-26s %7s %7s %8s %8s   %s" % ("model", "MAE", "RMSE", "bias", "NSE", "verdict"))
    for h in horizons:
        pairs = [(k, up[k], dn[k + h * 3600]) for k in ks if (k + h * 3600) in dn]
        if len(pairs) < 400: continue
        tr = [p for p in pairs if p[0] < cut]; te = [p for p in pairs if p[0] >= cut]
        if len(te) < 200: continue
        obs = [p[2] for p in te]
        cand = {}
        # persistence: the river stays where it is. The bar every other model must clear.
        pers = [dn[p[0]] for p in te if p[0] in dn]
        if len(pers) == len(te): cand["persistence"] = pers
        # constant gain, as deployed
        g = sorted(y / x for _, x, y in tr if x > 20)
        gm = g[len(g) // 2] if g else 1.0
        cand["lag+const gain"] = [x * gm for _, x, _ in te]
        # linear and power-law transfer, fitted on train only
        lin = fit_lin([x for _, x, _ in tr], [y for _, _, y in tr])
        if lin: cand["lag+linear fit"] = [max(0.0, lin[0] + lin[1] * x) for _, x, _ in te]
        pw = fit_pow([x for _, x, _ in tr], [y for _, _, y in tr])
        if pw: cand["lag+power law"] = [pw[0] * (x ** pw[1]) if x > 0 else 0.0 for _, x, _ in te]
        # convolution kernel over the preceding L hours of upstream flow (the Caney approach)
        L = 30
        def win(k):
            return [up.get(k - i * 3600) for i in range(L)]
        trw = [(win(p[0]), p[2]) for p in tr if all(v is not None for v in win(p[0]))]
        tew = [(win(p[0]), p[2]) for p in te if all(v is not None for v in win(p[0]))]
        if len(trw) > 400 and len(tew) > 150:
            w = fit_kernel([a for a, _ in trw], [b for _, b in trw], L)
            if w:
                ko = [b for _, b in tew]; kp = [sum(wi * xi for wi, xi in zip(w, a)) for a, _ in tew]
                cand["_kernel"] = (ko, kp)
        row = {}
        for name, pr in cand.items():
            if name == "_kernel":
                st = stats(pr[0], pr[1]); name = "lag+FIR kernel (%dh)" % L
            else:
                st = stats(obs, pr)
            if st: row[name] = st
        base = row.get("persistence", {}).get("nse")
        print("   h = %d hours ahead" % h)
        for name, st in sorted(row.items(), key=lambda kv: -(kv[1]["nse"] or -9)):
            v = ""
            if base is not None and name != "persistence":
                v = "BEATS persistence" if (st["nse"] or -9) > base else "loses to persistence"
            print("     %-24s %7.1f %7.1f %8.1f %8.4f   %s" % (name, st["mae"], st["rmse"], st["bias"], st["nse"] or 0, v))
        res[h] = row
    return res

OUT["temporal_duck"] = temporal("03599500", "03601990", [6, 12, 14, 18, 24], "Duck")
OUT["temporal_buffalo"] = temporal("03604000", "03604400", [12, 18, 22, 30], "Buffalo")

# ══════════════════════════════════════════════════════════════════════════════
# B. SPATIAL — held-out test of the ungauged-reach interpolation.
#    Hide Columbia; predict it from Milltown (above) and Centerville (below).
# ══════════════════════════════════════════════════════════════════════════════
print("\n── B. SPATIAL · predicting a HIDDEN gauge from its neighbours ──")
up, mid, dn = S["03599240"], S["03599500"], S["03601990"]
ks = sorted(set(up) & set(mid) & set(dn))
print("   Milltown(RM179, 916mi2) ? Columbia(RM133.3, 1208mi2) ? Centerville(RM74, 2048mi2)")
print("   %d aligned hours" % len(ks))
if len(ks) >= 500:
    rm_u, rm_m, rm_d = 179.0, 133.3, 74.0
    a_u, a_m, a_d = 916.0, 1208.0, 2048.0
    f_dist = (rm_u - rm_m) / (rm_u - rm_d)          # 0.435 — position by river mile
    f_area = (a_m - a_u) / (a_d - a_u)              # 0.258 — position by drainage area
    obs = [mid[k] for k in ks]
    models = {
        # what the page does today: straight-line blend on channel position
        "linear in river mile":   [up[k] + f_dist * (dn[k] - up[k]) for k in ks],
        # same blend, but positioned by drainage area instead of distance
        "linear in drainage area": [up[k] + f_area * (dn[k] - up[k]) for k in ks],
        # scale the nearest upstream gauge by area ratio ^0.9 (standard ungauged-basin transfer)
        "area ratio ^0.9 from up": [up[k] * (a_m / a_u) ** 0.9 for k in ks],
        "area ratio ^1.0 from up": [up[k] * (a_m / a_u) for k in ks],
        "area ratio ^1.0 from dn": [dn[k] * (a_m / a_d) for k in ks],
        # geometric (log-space) blend by drainage area — respects the multiplicative nature of flow
        "log blend by area":      [math.exp(math.log(max(up[k],1)) + f_area * (math.log(max(dn[k],1)) - math.log(max(up[k],1)))) for k in ks],
        # lag-aware: the water at Columbia now passed Milltown earlier and reaches Centerville later
        "log blend, lag-aware":   [math.exp(math.log(max(up.get(k - 6 * 3600, up[k]),1))
                                   + f_area * (math.log(max(dn.get(k + 8 * 3600, dn[k]),1)) - math.log(max(up.get(k - 6 * 3600, up[k]),1)))) for k in ks],
    }
    print("   %-26s %7s %7s %8s %8s" % ("method", "MAE", "RMSE", "bias", "NSE"))
    sp = {}
    for name, pr in models.items():
        st = stats(obs, pr)
        if st: sp[name] = st; print("     %-24s %7.1f %7.1f %8.1f %8.4f" % (name, st["mae"], st["rmse"], st["bias"], st["nse"] or 0))
    OUT["spatial"] = sp
    best = max(sp.items(), key=lambda kv: kv[1]["nse"] or -9)
    cur = sp.get("linear in river mile", {})
    print("\n   BEST: %s (NSE %.4f, MAE %.0f)" % (best[0], best[1]["nse"], best[1]["mae"]))
    print("   deployed today: linear in river mile (NSE %.4f, MAE %.0f)" % (cur.get("nse") or 0, cur.get("mae") or 0))
    if cur and best[1]["mae"] < cur["mae"]:
        print("   -> improvement available: MAE %.0f -> %.0f cfs (%.0f%% better)"
              % (cur["mae"], best[1]["mae"], 100 * (cur["mae"] - best[1]["mae"]) / cur["mae"]))
    OUT["spatial_best"] = best[0]

json.dump(OUT, open(os.path.join(HERE, "backtest_route.json"), "w"), indent=1)
print("\nwrote analysis/backtest_route.json")
