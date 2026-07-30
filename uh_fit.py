#!/usr/bin/env python3
"""
Fit an empirical UNIT HYDROGRAPH (impulse response) dam-release -> Stonewall:

    stonewall(t) = baseflow + Σ_{τ=0}^{L} w[τ] * dam(t-τ)

Ridge-regularized normal equations (pure Python, 32x32 solve). The kernel w[τ]
captures travel lag, attenuation, and the recession tail in one linear model,
replacing the crude '6h lag + flat +570 cfs' routing. Reports kernel + R^2 vs crude.
"""
import json, urllib.request, urllib.parse, datetime, statistics, math
UA={"User-Agent":"caney-uh/0.1"}; START,END="2025-09-15","2026-07-15"; L=30
def get(u,h=None): return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={**UA,**(h or {})}),timeout=180))
def hk(e): return int(e//3600)*3600
def dam_s():
    n="CETT1-CENTER_HILL.Flow.Ave.1Hour.1Hour.man-rev"
    u=f"https://cwms-data.usace.army.mil/cwms-data/timeseries?office=LRN&name={urllib.parse.quote(n)}&begin={START}T00:00:00Z&end={END}T00:00:00Z&unit=cfs&page-size=500000"
    return {hk(t/1000):v for t,v,q in get(u,{"Accept":"application/json;version=2"})["values"] if v is not None}
def stone_s():
    u=f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites=03424860&startDT={START}&endDT={END}&parameterCd=00060"
    b={}
    for p in get(u)["value"]["timeSeries"][0]["values"][0]["value"]:
        v=float(p["value"])
        if v<0: continue
        b.setdefault(hk(datetime.datetime.fromisoformat(p["dateTime"]).timestamp()),[]).append(v)
    return {k:statistics.mean(x) for k,x in b.items()}
print("fetching..."); dam,stone=dam_s(),stone_s()

P=L+2  # params: intercept + w[0..L]
rows=[k for k in sorted(stone) if all((k-τ*3600) in dam for τ in range(L+1))]
print(f"training rows: {len(rows)}")
# normal equations XtX (PxP), Xty (P)
XtX=[[0.0]*P for _ in range(P)]; Xty=[0.0]*P
for k in rows:
    f=[1.0]+[dam[k-τ*3600] for τ in range(L+1)]
    y=stone[k]
    for i in range(P):
        Xty[i]+=f[i]*y
        fi=f[i]; row=XtX[i]
        for j in range(i,P): row[j]+=fi*f[j]
for i in range(P):
    for j in range(i): XtX[i][j]=XtX[j][i]
# ridge on kernel terms (not intercept)
diag=sum(XtX[i][i] for i in range(1,P))/(P-1)
lam=1e-2*diag
for i in range(1,P): XtX[i][i]+=lam

def solve(A,b):
    n=len(b); M=[row[:]+[b[i]] for i,row in enumerate(A)]
    for c in range(n):
        p=max(range(c,n),key=lambda r:abs(M[r][c])); M[c],M[p]=M[p],M[c]
        pv=M[c][c]
        for r in range(n):
            if r!=c and M[r][c]:
                fac=M[r][c]/pv
                for cc in range(c,n+1): M[r][cc]-=fac*M[c][cc]
    return [M[i][n]/M[i][i] for i in range(n)]

coef=solve(XtX,Xty)
base=coef[0]; w=coef[1:]

def r2(pred):
    ys=[stone[k] for k in rows]; my=sum(ys)/len(ys)
    ssr=sum((stone[k]-pred(k))**2 for k in rows); sst=sum((y-my)**2 for y in ys)
    return 1-ssr/sst
uh_pred=lambda k: base+sum(w[τ]*dam[k-τ*3600] for τ in range(L+1))
crude_pred=lambda k: dam[k-6*3600]+570
print(f"\nR^2  unit-hydrograph = {r2(uh_pred):.3f}")
print(f"R^2  crude(6h+570)   = {r2(crude_pred):.3f}")

gain=sum(w); cent=sum(τ*w[τ] for τ in range(L+1))/gain if gain else 0
peak=max(range(L+1),key=lambda τ:w[τ])
print(f"\nkernel: baseflow={base:.0f} cfs | gain(Σw)={gain:.2f} | peak lag={peak}h | centroid={cent:.1f}h")
print("impulse response w[τ] (fraction of a dam-release unit arriving τ hours later):")
for τ in range(L+1):
    bar="#"*int(max(w[τ],0)*120)
    print(f"  {τ:2}h  {w[τ]:+.3f} {bar}")
# recession: after a sustained pulse stops, how fast does contribution fall?
csum=[sum(w[:τ+1]) for τ in range(L+1)]
half=next((τ for τ in range(L+1) if csum[τ]>=gain*0.5),None)
p90=next((τ for τ in range(L+1) if csum[τ]>=gain*0.9),None)
print(f"\ncumulative arrival: 50% by {half}h, 90% by {p90}h  -> effective recession window")
