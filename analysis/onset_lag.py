#!/usr/bin/env python3
"""
Measure, from real data, the two DIFFERENT lags a tailwater has — because conflating
them is what put two disagreeing clocks on the Caney page.

  1. RESPONSE lag  — when the gauge first *moves* after a release starts. This is the
     pressure/kinematic wave, and it is fast: the river is a connected body, so stage
     downstream begins rising long before the released water gets there.
  2. TRANSPORT lag — when the released WATER arrives. Slower. This is what the
     2.5 mph rule describes and what matters for "be off the flats before the bump".

Both are real. The bug was using one where the other belongs.

    python3 analysis/onset_lag.py [days]
"""
import urllib.request, urllib.parse, json, datetime, math, sys, statistics

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 120
UA = {"User-Agent": "onset/1.0"}
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
    if v is not None: rel[hk(t/1000) - 3600] = v
b = {}
u = ("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=" + GAUGE
     + "&startDT=" + beg[:10] + "&endDT=" + end[:10] + "&parameterCd=00060")
for p in get(u)["value"]["timeSeries"][0]["values"][0]["value"]:
    try: v = float(p["value"])
    except Exception: continue
    if v < 0: continue
    b.setdefault(hk(datetime.datetime.fromisoformat(p["dateTime"]).timestamp()), []).append(v)
obs = {k: sum(x)/len(x) for k, x in b.items()}

ks = sorted(rel)
events = []                      # release starts: off -> on
for i in range(1, len(ks)):
    a, c = ks[i-1], ks[i]
    if c - a != 3600: continue
    if rel[a] < 800 <= rel[c]:
        pk = max((rel.get(c + h*3600, 0) for h in range(0, 12)), default=0)
        events.append((c, pk))
print("release starts found: %d (peak >= 800 cfs)\n" % len(events))

def lag_to(ev_t, frac_of_peak, peak, base):
    """Hours until the gauge reaches base + frac*(peak-base)."""
    target = base + frac_of_peak * max(0.0, peak - base)
    for h in range(0, 25):
        v = obs.get(ev_t + h*3600)
        if v is not None and v >= target: return h
    return None

rows = {"response (+5% of rise)": [], "quarter (+25%)": [], "half (+50%)": [], "peak-ish (+90%)": []}
for t, pk in events:
    pre = [obs.get(t - h*3600) for h in (1, 2, 3)]
    pre = [x for x in pre if x is not None]
    if not pre or pk < 1500: continue
    base = statistics.median(pre)
    obs_pk = max((obs.get(t + h*3600, 0) for h in range(0, 24)), default=0)
    if obs_pk < base + 400: continue
    for lab, fr in (("response (+5% of rise)", 0.05), ("quarter (+25%)", 0.25),
                    ("half (+50%)", 0.50), ("peak-ish (+90%)", 0.90)):
        L = lag_to(t, fr, obs_pk, base)
        if L is not None: rows[lab].append(L)

print("Lag from release start to each stage of the gauge response at Stonewall (15 mi):")
print("  %-24s %5s %7s %7s %7s   implied mph"%("STAGE","n","median","p25","p75"))
for lab, v in rows.items():
    if len(v) < 5: print("  %-24s %5d  (too few)"%(lab, len(v))); continue
    v = sorted(v); med = statistics.median(v)
    p25, p75 = v[len(v)//4], v[(3*len(v))//4]
    mph = (15.0/med) if med else float("nan")
    print("  %-24s %5d %7.1f %7.1f %7.1f   %.2f" % (lab, len(v), med, p25, p75, mph))
print()
print("The FIRST row is the pressure/kinematic wave — the gauge twitching.")
print("The LATER rows are the water actually showing up. The wading decision")
print("belongs to the later rows; the 'is it rising yet' readout belongs to the first.")
