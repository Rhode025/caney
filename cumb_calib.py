import json,urllib.request,urllib.parse,datetime,statistics,math
UA={"User-Agent":"cumb/0.1"}; START,END="2026-04-01","2026-07-20"
def get(u,h=None): return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={**UA,**(h or {})}),timeout=180))
def hk(e): return int(e//3600)*3600
def rel():
    n="WLCK2-WOLF_CREEK.Flow.Ave.1Hour.1Hour.man-rev"
    u=("https://cwms-data.usace.army.mil/cwms-data/timeseries?office=LRN"
       f"&name={urllib.parse.quote(n)}&begin={START}T00:00:00Z&end={END}T00:00:00Z&unit=cfs&page-size=500000")
    return {hk(t/1000)-3600:v for t,v,q in get(u,{"Accept":"application/json;version=2"})["values"] if v is not None}
def usgs(param):
    u=f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites=03414100&startDT={START}&endDT={END}&parameterCd={param}"
    pts=get(u)["value"]["timeSeries"][0]["values"][0]["value"]; b={}
    for p in pts:
        try: v=float(p["value"])
        except: continue
        if v<-1e5: continue
        b.setdefault(hk(datetime.datetime.fromisoformat(p["dateTime"]).timestamp()),[]).append(v)
    return {k:statistics.mean(x) for k,x in b.items()}
print("fetching..."); R=rel(); Q=usgs("00060"); S=usgs("00065")
print("release hrs",len(R),"| Burkesville Q hrs",len(Q),"| stage hrs",len(S))
common=sorted(set(R)&set(Q))
def pearson(xs,ys):
    n=len(xs);mx=sum(xs)/n;my=sum(ys)/n
    num=sum((x-mx)*(y-my) for x,y in zip(xs,ys));dx=math.sqrt(sum((x-mx)**2 for x in xs));dy=math.sqrt(sum((y-my)**2 for y in ys))
    return num/(dx*dy) if dx and dy else 0
best=(0,-2)
for lag in range(0,34):
    xs=[R[k] for k in common if k+lag*3600 in Q];ys=[Q[k+lag*3600] for k in common if k+lag*3600 in Q]
    if len(xs)<400: continue
    r=pearson(xs,ys)
    if r>best[1]:best=(lag,r)
    if lag%2==0: print(f"  lag {lag:2}h r={r:.3f}")
print("BEST travel time (Wolf Creek->Burkesville ~20mi):",best[0],"h  r=%.3f"%best[1])
# stage-rise by discharge bin
pairs=[(Q[k],S[k]) for k in sorted(set(Q)&set(S))]
print("\nBurkesville stage(ft) by discharge bin:")
for lo,hi,lab in [(500,1500,"min"),(1500,4000,"low"),(4000,8000,"1-2 units"),(8000,16000,"3-4U"),(16000,30000,"big")]:
    v=[s for q,s in pairs if lo<=q<hi]
    if len(v)>=20: print(f"  {lab:10} {lo}-{hi} cfs: stage {statistics.median(v):.2f} ft (n={len(v)})")
