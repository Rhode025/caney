#!/usr/bin/env python3
"""
Fit the rain->runoff term for the Caney routing model.

residual(t) = stonewall_obs(t) - dam_release(t - 6h)      # baseflow + rain runoff
model:        residual(t) ~ b0 + b1 * API(t)
              API(t) = rain(t) + decay*API(t-1),  decay = exp(-1/T)   [recession EMA]

Grid-search T (recession timescale, hours); pick max R^2. b0 ~ tributary baseflow,
b1*API = rain-driven runoff. Prints fitted params for briefing.py.
"""
import json, urllib.request, urllib.parse, datetime, statistics, math

UA = {"User-Agent": "caney-runoff/0.1"}
START, END = "2025-09-15", "2026-07-15"   # END backed off ~10d for Open-Meteo archive lag
LAG_H = 6

def get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)
def hk(e): return int(e // 3600) * 3600

def dam_series():
    name = "CETT1-CENTER_HILL.Flow.Ave.1Hour.1Hour.man-rev"
    url = ("https://cwms-data.usace.army.mil/cwms-data/timeseries?office=LRN"
           f"&name={urllib.parse.quote(name)}&begin={START}T00:00:00Z&end={END}T00:00:00Z"
           "&unit=cfs&page-size=500000")
    d = get(url, {"Accept": "application/json;version=2"})
    return {hk(t/1000): v for t, v, q in d["values"] if v is not None}

def stone_series():
    url = ("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=03424860"
           f"&startDT={START}&endDT={END}&parameterCd=00060")
    pts = get(url)["value"]["timeSeries"][0]["values"][0]["value"]
    b = {}
    for p in pts:
        v = float(p["value"])
        if v < 0: continue
        e = datetime.datetime.fromisoformat(p["dateTime"]).timestamp()
        b.setdefault(hk(e), []).append(v)
    return {k: statistics.mean(vs) for k, vs in b.items()}

def rain_series():
    url = ("https://archive-api.open-meteo.com/v1/archive?latitude=36.10&longitude=-85.83"
           f"&start_date={START}&end_date={END}&hourly=precipitation&timezone=GMT")
    h = get(url)["hourly"]
    out = {}
    for tstr, mm in zip(h["time"], h["precipitation"]):
        if mm is None: continue
        e = datetime.datetime.fromisoformat(tstr).replace(tzinfo=datetime.timezone.utc).timestamp()
        out[hk(e)] = mm
    return out

print("fetching ...", flush=True)
dam, stone, rain = dam_series(), stone_series(), rain_series()
print(f"  dam={len(dam)} stone={len(stone)} rain={len(rain)}")

hours = sorted(k for k in stone if (k - LAG_H*3600) in dam)
resid = {k: stone[k] - dam[k - LAG_H*3600] for k in hours}

# QUIESCENT mask: no generation pulse passing Stonewall at time k.
# Stonewall(k) reflects dam release ~6h earlier, so require dam < 800 cfs
# across the window [k-12h, k-2h]. Isolates baseflow+runoff from pulse noise.
def quiescent(k):
    for h in range(2, 13):
        v = dam.get(k - h*3600)
        if v is None or v >= 800:
            return False
    return True
quiet = [k for k in hours if quiescent(k)]
print(f"  usable residual hours: {len(resid)}  | quiescent (no-gen) hours: {len(quiet)}")
print(f"  quiescent residual: median={statistics.median([resid[k] for k in quiet]):.0f} "
      f"min={min(resid[k] for k in quiet):.0f} max={max(resid[k] for k in quiet):.0f} cfs")

def fit_for_T(T):
    decay = math.exp(-1.0/T)
    # build API over full continuous rain timeline
    api = {}
    prev, prevk = 0.0, None
    for k in sorted(rain):
        if prevk is not None:
            gap = (k - prevk)//3600
            prev *= decay**max(gap, 1)
        prev = rain[k] + prev
        api[k] = prev
        prevk = k
    xs, ys = [], []
    for k in quiet:
        if k in api:
            xs.append(api[k]); ys.append(resid[k])
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs); sxy = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    b1 = sxy/sxx if sxx else 0.0
    b0 = my - b1*mx
    ss_res = sum((y-(b0+b1*x))**2 for x,y in zip(xs,ys))
    ss_tot = sum((y-my)**2 for y in ys)
    r2 = 1 - ss_res/ss_tot if ss_tot else 0.0
    return b0, b1, r2, n

print("\ngrid-search recession timescale T:")
best = None
for T in [12,18,24,36,48,60,72,96,120,168,240]:
    b0,b1,r2,n = fit_for_T(T)
    flag = ""
    if best is None or r2 > best[3]: best = (T,b0,b1,r2); flag=" <-"
    print(f"  T={T:3}h  decay={math.exp(-1/T):.3f}  b0={b0:6.0f}  b1={b1:6.2f}  R2={r2:.3f}{flag}")

T,b0,b1,r2 = best
print(f"\nBEST: T={T}h  baseflow b0={b0:.0f} cfs  runoff b1={b1:.2f} cfs per API-mm  R2={r2:.3f}")

# illustrate on the biggest rain event in window
tot = {}
win = 48
for k in sorted(rain):
    tot[k] = sum(rain.get(k-i*3600,0) for i in range(win))
peak_k = max(tot, key=tot.get)
decay=math.exp(-1/T); api={}; prev=0.0; pk=None
for k in sorted(rain):
    if pk is not None: prev*= decay**max((k-pk)//3600,1)
    prev=rain[k]+prev; api[k]=prev; pk=k
dt=datetime.datetime.utcfromtimestamp(peak_k)
print(f"\nbiggest 48h rain event ~ {dt:%Y-%m-%d}: {tot[peak_k]:.0f} mm")
print(f"  predicted added flow at that peak: {b0+b1*api.get(peak_k,0):,.0f} cfs "
      f"(baseflow {b0:.0f} + runoff {b1*api.get(peak_k,0):,.0f})")
print(f"  actual residual then: {resid.get(peak_k, float('nan')):,.0f} cfs")
