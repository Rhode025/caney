#!/usr/bin/env python3
"""
Fit at-a-station depth-vs-flow from the Stonewall gauge, which reports BOTH
discharge (00060) and gage height / stage (00065).

Hydraulic geometry (Leopold & Maddock): mean depth D = c · Q^f, so stage rises as
a power law of discharge. We fit:  log(stage - bed) = log c + f·log Q
grid-searching the effective bed stage. f (~0.3-0.45 typically) is the depth exponent
we transfer to ungauged spots:  depth(Q) = d_ref · (Q / Q_ref)^f
"""
import json, urllib.request, datetime, statistics, math
UA={"User-Agent":"caney-depth/0.1"}; START,END="2015-01-01","2026-07-15"
def get(u): return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=180))
def hk(e): return int(e//3600)*3600

url=(f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites=03424860"
     f"&startDT={START}&endDT={END}&parameterCd=00060,00065")
d=get(url)
series={}
for ts in d["value"]["timeSeries"]:
    code=ts["variable"]["variableCode"][0]["value"]
    b={}
    for p in ts["values"][0]["value"]:
        try: v=float(p["value"])
        except: continue
        if v<=-999: continue
        b.setdefault(hk(datetime.datetime.fromisoformat(p["dateTime"]).timestamp()),[]).append(v)
    series[code]={k:statistics.mean(x) for k,x in b.items()}
Q=series.get("00060",{}); S=series.get("00065",{})
common=sorted(set(Q)&set(S))
pairs=[(Q[k],S[k]) for k in common if Q[k]>0]
print(f"paired hourly (Q, stage) points: {len(pairs)}")
qs=[p[0] for p in pairs]; ss=[p[1] for p in pairs]
print(f"discharge range: {min(qs):.0f} – {max(qs):,.0f} cfs")
print(f"stage range:     {min(ss):.2f} – {max(ss):.2f} ft (gage height)")

def logfit(f_bed):
    xs=[]; ys=[]
    for q,s in pairs:
        d=s-f_bed
        if d<=0.01 or q<=0: continue
        xs.append(math.log(q)); ys.append(math.log(d))
    n=len(xs)
    if n<200: return None
    mx=sum(xs)/n; my=sum(ys)/n
    sxx=sum((x-mx)**2 for x in xs); sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    f=sxy/sxx; logc=my-f*mx
    ssr=sum((y-(logc+f*x))**2 for x,y in zip(xs,ys)); sst=sum((y-my)**2 for y in ys)
    return f, math.exp(logc), 1-ssr/sst, n

smin=min(ss)
print("\ngrid effective bed stage (ft below min observed stage):")
best=None
for off in [0.1,0.3,0.5,0.8,1.2,1.8,2.5,3.5,5.0]:
    bed=smin-off; r=logfit(bed)
    if not r: continue
    f,c,r2,n=r; tag=""
    if best is None or r2>best[-1]: best=(bed,f,c,r2); tag=" <-"
    print(f"  bed={bed:6.2f} (min-{off:.1f})  f={f:.3f}  c={c:.3f}  R2={r2:.3f}  n={n}{tag}")

bed,f,c,r2=best
print(f"\nBEST(full range): depth exponent f={f:.3f}  (R2={r2:.3f}, effective bed {bed:.2f} ft)")

# ASSUMPTION-FREE: median stage in the flows that matter (exclude floods)
print("\nassumption-free median gage height by flow bin (feet):")
bins=[(200,320,"~min flow"),(320,700,"low"),(700,1400,"~edge"),
      (1400,3000,"rising"),(3200,4600,"1 unit"),(6500,8500,"2 units"),(9500,12500,"3 units")]
base=None; rows=[]
for lo,hi,lab in bins:
    v=[s for q,s in pairs if lo<=q<hi]
    if len(v)<30: rows.append((lab,None,None)); continue
    m=statistics.median(v);
    if base is None: base=m
    rows.append((lab,m,m-base))
for lab,m,r in rows:
    if m is None: print(f"  {lab:10}  (sparse)")
    else: print(f"  {lab:10}  stage {m:5.2f} ft   +{r:4.1f} ft over min flow")

# fit f only over the wade->1-unit regime (exclude floods & big multi-unit)
reg=[(q,s) for q,s in pairs if 175<=q<=4600]
smin_r=min(s for q,s in reg)
def logfit_reg(bed):
    xs=[];ys=[]
    for q,s in reg:
        d=s-bed
        if d<=.01: continue
        xs.append(math.log(q));ys.append(math.log(d))
    n=len(xs); mx=sum(xs)/n;my=sum(ys)/n
    sxx=sum((x-mx)**2 for x in xs);sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    ff=sxy/sxx;lc=my-ff*mx
    ssr=sum((y-(lc+ff*x))**2 for x,y in zip(xs,ys));sst=sum((y-my)**2 for y in ys)
    return ff,1-ssr/sst
print("\nexponent fit over WADE->1-unit regime only (Q<=4600, floods excluded):")
for off in [0.5,1.2,2.5,3.5]:
    ff,rr=logfit_reg(smin_r-off); print(f"  bed=min-{off}: f={ff:.3f} R2={rr:.3f}")
# relative depth multiplier vs a 300 cfs reference
print("\nrelative depth vs 300 cfs (multiplier), using depth ∝ Q^f:")
for q in [250,500,1000,2000,4000,7000,11000]:
    print(f"  {q:>6,} cfs  ->  {(q/300)**f:.2f}× the 300-cfs depth")
print(f"\nInterpretation: going 300 -> ~3,900 cfs (1 unit) multiplies depth by {(3900/300)**f:.2f};")
print(f"300 -> 11,000 cfs (3 units) multiplies depth by {(11000/300)**f:.2f}.")
