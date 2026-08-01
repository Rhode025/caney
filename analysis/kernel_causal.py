#!/usr/bin/env python3
"""
Test a CAUSAL routing kernel against the deployed one, on real data.

The deployed CALIB_KERNEL merges translation and attenuation into one unit hydrograph.
That is physically wrong in a specific, measurable way: it puts mass at lags shorter
than the water can possibly travel. At Stonewall (15 mi, backtested front 6 h) it
delivers 27% of a release by hour 5 — water that has not arrived yet. That phantom
mass is what makes the planner announce a rise hours before it happens.

The candidate model separates the two, as river routing physically works:
    advection (pure dead time, from the backtested 2.5 mph) THEN diffusion (the shape)

Implemented by enforcing CAUSALITY on the kernel: zero every weight at a lag shorter
than the travel time, renormalise (mass-conserving). Nothing else changes.

Then replay both against the real Stonewall gauge and let the data pick.

    python3 analysis/kernel_causal.py [days]
"""
import urllib.request, urllib.parse, json, datetime, math, sys

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 120
UA = {"User-Agent": "kernel-causal/1.0"}
CALIB_KERNEL = [0.0,0.010,0.010,0.044,0.089,0.131,0.156,0.142,0.110,0.083,
                0.071,0.060,0.045,0.024,0.013,0.016,0.020,0.016,0.009,0.001]
BASEFLOW, WATER_MPH, MFD_STONE = 205.0, 2.5, 15.0
GAUGE, CWMS = "03424860", "CETT1-CENTER_HILL.Flow.Ave.1Hour.1Hour.man-rev"

def hk(e): return int(e//3600)*3600
def get(u, h=None):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(u, headers={**UA, **(h or {})}), timeout=300))

now = datetime.datetime.now(datetime.timezone.utc)
beg = (now - datetime.timedelta(days=DAYS)).strftime("%Y-%m-%dT%H:00:00Z")
end = now.strftime("%Y-%m-%dT%H:00:00Z")

rel = {}
u = ("https://cwms-data.usace.army.mil/cwms-data/timeseries?office=LRN&name="
     + urllib.parse.quote(CWMS) + "&begin=" + beg + "&end=" + end + "&unit=cfs&page-size=500000")
for t, v, q in get(u, {"Accept": "application/json;version=2"})["values"]:
    if v is not None: rel[hk(t/1000) - 3600] = v          # period-ending -> clock time

obs = {}
u = ("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=" + GAUGE
     + "&startDT=" + beg[:10] + "&endDT=" + end[:10] + "&parameterCd=00060")
b = {}
for p in get(u)["value"]["timeSeries"][0]["values"][0]["value"]:
    try: v = float(p["value"])
    except Exception: continue
    if v < 0: continue
    b.setdefault(hk(datetime.datetime.fromisoformat(p["dateTime"]).timestamp()), []).append(v)
obs = {k: sum(x)/len(x) for k, x in b.items()}

def norm(k):
    s = sum(k) or 1.0
    return [x/s for x in k]

def causal(kernel, dead_h):
    """Zero out mass arriving sooner than the water can travel, then renormalise."""
    out = [0.0 if i < dead_h else w for i, w in enumerate(kernel)]
    return norm(out)

DEPLOYED = norm(CALIB_KERNEL)
DEAD = int(round(MFD_STONE / WATER_MPH))            # 6 h at Stonewall
CAUSAL = causal(CALIB_KERNEL, DEAD)

def predict(kern):
    out = {}
    for k in obs:
        acc, ok = 0.0, False
        for i, w in enumerate(kern):
            d = rel.get(k - i*3600)
            if d is not None: acc += w*d; ok = True
        if ok: out[k] = BASEFLOW + acc
    return out

def stats(pred, label):
    ks = sorted(set(pred) & set(obs))
    if not ks: return None
    e = [pred[k]-obs[k] for k in ks]
    o = [obs[k] for k in ks]; p = [pred[k] for k in ks]
    n = len(ks); mo = sum(o)/n
    bias = sum(e)/n
    mae = sum(abs(x) for x in e)/n
    rmse = math.sqrt(sum(x*x for x in e)/n)
    nse = 1 - sum(x*x for x in e)/sum((y-mo)**2 for y in o)
    mp = sum(p)/n
    num = sum((a-mp)*(bb-mo) for a, bb in zip(p, o))
    den = math.sqrt(sum((a-mp)**2 for a in p)*sum((bb-mo)**2 for bb in o)) or 1
    print("  %-22s n=%-6d bias=%+7.0f  MAE=%6.0f  RMSE=%6.0f  NSE=%+.3f  r=%.3f"
          % (label, n, bias, mae, rmse, nse, num/den))
    return {"mae": mae, "rmse": rmse, "nse": nse, "r": num/den}

def lag_xcorr(pred, label):
    """Best cross-correlation lag: how far the model is shifted from reality."""
    ks = sorted(set(pred) & set(obs))
    best = (None, -9)
    for L in range(-8, 9):
        pair = [(pred[k], obs[k+L*3600]) for k in ks if (k+L*3600) in obs]
        if len(pair) < 200: continue
        n = len(pair); ma = sum(a for a, _ in pair)/n; mb = sum(b for _, b in pair)/n
        num = sum((a-ma)*(b-mb) for a, b in pair)
        den = math.sqrt(sum((a-ma)**2 for a, _ in pair)*sum((b-mb)**2 for _, b in pair)) or 1
        if num/den > best[1]: best = (L, num/den)
    print("    %-20s best lag %+d h (r=%.3f)  [0 = correctly timed]" % (label, best[0], best[1]))
    return best[0]

print("Caney routing: deployed unit hydrograph vs causal (advection + diffusion)")
print("%d days | %d release hrs | %d gauge hrs | dead time at Stonewall = %d h\n"
      % (DAYS, len(rel), len(obs), DEAD))
pd, pc = predict(DEPLOYED), predict(CAUSAL)
print("MAGNITUDE")
sd = stats(pd, "deployed (merged UH)")
sc = stats(pc, "causal (delay+shape)")
print("\nTIMING")
ld = lag_xcorr(pd, "deployed")
lc = lag_xcorr(pc, "causal")
print("\nKERNEL ONSET")
print("    deployed: first non-zero weight at lag %d h" % next(i for i, w in enumerate(DEPLOYED) if w > 0))
print("    causal  : first non-zero weight at lag %d h (= backtested front)" % next(i for i, w in enumerate(CAUSAL) if w > 0))
print("\nVERDICT")
if sd and sc:
    for k, better_is_low in (("mae", True), ("rmse", True), ("nse", False)):
        d, c = sd[k], sc[k]
        win = ("causal" if ((c < d) if better_is_low else (c > d)) else "deployed")
        print("    %-5s deployed=%8.3f  causal=%8.3f  -> %s" % (k.upper(), d, c, win))
