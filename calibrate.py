#!/usr/bin/env python3
"""
Caney Fork travel-time calibration.
Cross-correlates Center Hill Dam outflow (USACE CWMS) against the downstream
USGS gauge at Stonewall (03424860) to MEASURE travel time + attenuation.
Adds basin rainfall (Open-Meteo) to characterize the tributary/runoff residual.
No API keys required.
"""
import json, urllib.request, urllib.parse, datetime, statistics, math

UA = {"User-Agent": "caney-calib/0.1"}

def get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

# ---- window: last ~10 months ----
START = "2025-09-15"
END   = "2026-07-25"
def iso_z(d): return d + "T00:00:00Z"

# ---------- 1. Center Hill actual hourly outflow (CWMS, cfs) ----------
def cwms_outflow():
    name = "CETT1-CENTER_HILL.Flow.Ave.1Hour.1Hour.man-rev"
    url = ("https://cwms-data.usace.army.mil/cwms-data/timeseries?office=LRN"
           f"&name={urllib.parse.quote(name)}"
           f"&begin={iso_z(START)}&end={iso_z(END)}&unit=cfs&page-size=500000")
    d = get(url, {"Accept": "application/json;version=2"})
    out = {}
    for t, v, q in d["values"]:
        if v is None: continue
        hr = int(t // 3600000) * 3600  # epoch-hour (UTC seconds)
        out[hr] = v
    return out

# ---------- 2. USGS Stonewall discharge (cfs), averaged to hourly ----------
def usgs_stonewall():
    url = ("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=03424860"
           f"&startDT={START}&endDT={END}&parameterCd=00060")
    d = get(url)
    pts = d["value"]["timeSeries"][0]["values"][0]["value"]
    buckets = {}
    for p in pts:
        v = float(p["value"])
        if v < 0: continue
        dt = datetime.datetime.fromisoformat(p["dateTime"])
        epoch = int(dt.timestamp())
        hr = (epoch // 3600) * 3600
        buckets.setdefault(hr, []).append(v)
    return {hr: statistics.mean(vs) for hr, vs in buckets.items()}

# ---------- 3. Basin rainfall (Open-Meteo archive, hourly mm) ----------
def basin_rain():
    # point near mid-tailwater basin (between dam and Stonewall)
    url = ("https://archive-api.open-meteo.com/v1/archive?latitude=36.10&longitude=-85.83"
           f"&start_date={START}&end_date={END}&hourly=precipitation&timezone=GMT")
    d = get(url)
    h = d["hourly"]
    out = {}
    for tstr, mm in zip(h["time"], h["precipitation"]):
        if mm is None: continue
        dt = datetime.datetime.fromisoformat(tstr).replace(tzinfo=datetime.timezone.utc)
        out[(int(dt.timestamp()) // 3600) * 3600] = mm
    return out

print("fetching CWMS dam outflow ...", flush=True)
dam = cwms_outflow()
print(f"  dam hourly points: {len(dam)}")
print("fetching USGS Stonewall ...", flush=True)
stone = usgs_stonewall()
print(f"  stonewall hourly points: {len(stone)}")
print("fetching basin rainfall ...", flush=True)
rain = basin_rain()
print(f"  rain hourly points: {len(rain)}  | total {sum(rain.values()):.0f} mm over window")

# ---------- dry-hour mask: exclude 48h following any hour with >2mm rain ----------
wet = set()
for hr, mm in rain.items():
    if mm and mm > 2.0:
        for k in range(0, 48):
            wet.add(hr + k * 3600)

common = sorted(set(dam) & set(stone))
print(f"\noverlapping hours: {len(common)}")

def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x-mx)**2 for x in xs)); dy = math.sqrt(sum((y-my)**2 for y in ys))
    return num/(dx*dy) if dx and dy else 0.0

def xcorr(dry_only):
    best = (None, -2)
    curve = []
    for lag in range(0, 25):
        xs, ys = [], []
        for hr in common:
            sh = hr + lag*3600
            if sh in stone:
                if dry_only and (hr in wet or sh in wet): continue
                xs.append(dam[hr]); ys.append(stone[sh])
        if len(xs) < 500: continue
        r = pearson(xs, ys)
        curve.append((lag, r, len(xs)))
        if r > best[1]: best = (lag, r)
    return best, curve

for label, dry in [("ALL data", False), ("DRY periods only", True)]:
    (blag, br), curve = xcorr(dry)
    print(f"\n=== {label} ===  best lag = {blag} h  (r={br:.3f})")
    for lag, r, n in curve:
        if abs(lag-blag) <= 4:
            bar = "#"*int(r*40)
            print(f"  lag {lag:2}h  r={r:.3f}  n={n:5}  {bar}")

# ---------- attenuation: peak dam gen vs peak stonewall response (dry) ----------
best_lag = xcorr(True)[0][0] or xcorr(False)[0][0]
dam_peaks, stone_peaks = [], []
for hr in common:
    sh = hr + best_lag*3600
    if sh in stone and hr not in wet and sh not in wet:
        dam_peaks.append(dam[hr]); stone_peaks.append(stone[sh])
if dam_peaks:
    hi = sorted(zip(dam_peaks, stone_peaks))[-200:]  # highest-flow hours
    dmax = max(d for d, s in hi); smax = max(s for d, s in hi)
    print(f"\nattenuation (dry, lag {best_lag}h): dam peak ~{dmax:,.0f} cfs -> "
          f"stonewall peak ~{smax:,.0f} cfs  ({smax/dmax*100:.0f}% of dam peak)")

# ---------- rainfall residual: flow at stonewall NOT explained by dam ----------
# baseline residual on dry vs wet hours
res_dry, res_wet = [], []
for hr in common:
    sh = hr + best_lag*3600
    if sh not in stone: continue
    resid = stone[sh] - dam[hr]      # crude: unrouted local contribution
    (res_wet if (hr in wet or sh in wet) else res_dry).append(resid)
def med(x): return statistics.median(x) if x else float('nan')
print(f"\nrainfall residual (stonewall minus dam outflow, lag-aligned):")
print(f"  DRY hours  median extra flow: {med(res_dry):+,.0f} cfs  (n={len(res_dry)})")
print(f"  WET hours  median extra flow: {med(res_wet):+,.0f} cfs  (n={len(res_wet)})")
print(f"  -> rain adds ~{med(res_wet)-med(res_dry):,.0f} cfs of tributary flow the dam schedule can't see")
