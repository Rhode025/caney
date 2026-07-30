#!/usr/bin/env python3
"""Diagnose what drives Stonewall flow above dam release: recession tail vs rain."""
import json, urllib.request, urllib.parse, datetime, statistics, math
UA={"User-Agent":"caney-diag/0.1"}; START,END="2025-09-15","2026-07-15"; LAG=6
def get(u,h=None):
    r=urllib.request.Request(u,headers={**UA,**(h or {})})
    return json.load(urllib.request.urlopen(r,timeout=180))
def hk(e): return int(e//3600)*3600
def dam_s():
    n="CETT1-CENTER_HILL.Flow.Ave.1Hour.1Hour.man-rev"
    u=f"https://cwms-data.usace.army.mil/cwms-data/timeseries?office=LRN&name={urllib.parse.quote(n)}&begin={START}T00:00:00Z&end={END}T00:00:00Z&unit=cfs&page-size=500000"
    return {hk(t/1000):v for t,v,q in get(u,{"Accept":"application/json;version=2"})["values"] if v is not None}
def stone_s():
    u=f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites=03424860&startDT={START}&endDT={END}&parameterCd=00060"
    b={}
    for p in get(u)["value"]["timeSeries"][0]["values"][0]["value"]:
        v=float(p["value"]);
        if v<0: continue
        b.setdefault(hk(datetime.datetime.fromisoformat(p["dateTime"]).timestamp()),[]).append(v)
    return {k:statistics.mean(x) for k,x in b.items()}
def rain_s():
    u=f"https://archive-api.open-meteo.com/v1/archive?latitude=36.10&longitude=-85.83&start_date={START}&end_date={END}&hourly=precipitation&timezone=GMT"
    h=get(u)["hourly"]; out={}
    for t,mm in zip(h["time"],h["precipitation"]):
        if mm is None: continue
        out[hk(datetime.datetime.fromisoformat(t).replace(tzinfo=datetime.timezone.utc).timestamp())]=mm
    return out
print("fetching..."); dam,stone,rain=dam_s(),stone_s(),rain_s()

# hours-since-generation, measured at the dam frame shifted by LAG
def hours_since_gen(k):
    # count hours dam has been <800 ending at (k - LAG)
    base=k-LAG*3600; h=0
    while h<120:
        v=dam.get(base-h*3600)
        if v is None: return None
        if v>=800: return h
        h+=1
    return 120
hrs=sorted(x for x in stone if (x-LAG*3600) in dam)
resid={k:stone[k]-dam[k-LAG*3600] for k in hrs}

print("\nResidual (Stonewall minus routed dam release) bucketed by HOURS SINCE GENERATION:")
buckets={}
for k in hrs:
    hs=hours_since_gen(k)
    if hs is None: continue
    lab = "still gen (<0)" if hs==0 and dam[k-LAG*3600]>=800 else f"{(hs//6)*6:>2}-{(hs//6)*6+6}h"
    if hs>=48: lab=">=48h (drained)"
    buckets.setdefault(lab,[]).append(resid[k])
order=sorted(buckets, key=lambda s:(999 if s.startswith("still") else int(s.split('-')[0]) if s[0].isdigit() else 48))
for lab in order:
    vs=buckets[lab]
    print(f"  {lab:16} n={len(vs):5}  median residual = {statistics.median(vs):6.0f} cfs")

# CLEANEST rain test: deeply drained hours (>=48h since gen) -> residual ~ baseflow+runoff
deep=[k for k in hrs if (hours_since_gen(k) or 0)>=48]
print(f"\nDeeply-drained hours (>=48h no gen): n={len(deep)}")
if deep:
    rv=[resid[k] for k in deep]
    print(f"  residual: median={statistics.median(rv):.0f} min={min(rv):.0f} max={max(rv):.0f} cfs  (this ~ true baseflow floor + rain)")
    # regress deep residual vs antecedent-rain API, grid T
    best=None
    for T in [24,48,72,120,168]:
        d=math.exp(-1/T); api={}; prev=0.0; pk=None
        for k in sorted(rain):
            if pk is not None: prev*=d**max((k-pk)//3600,1)
            prev=rain[k]+prev; api[k]=prev; pk=k
        xs=[api[k] for k in deep if k in api]; ys=[resid[k] for k in deep if k in api]
        n=len(xs); mx=sum(xs)/n; my=sum(ys)/n
        sxx=sum((x-mx)**2 for x in xs); sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
        b1=sxy/sxx if sxx else 0; b0=my-b1*mx
        r2=1-sum((y-(b0+b1*x))**2 for x,y in zip(xs,ys))/sum((y-my)**2 for y in ys)
        tag=""
        if best is None or r2>best[-1]: best=(T,b0,b1,r2); tag=" <-"
        print(f"    rain fit T={T:3}h: b0={b0:5.0f} b1={b1:5.2f} R2={r2:.3f}{tag}")
