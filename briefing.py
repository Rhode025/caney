#!/usr/bin/env python3
"""
Caney Fork — field app (v7): + drift take-out & manual itinerary, + mined fly box.

Live: Center Hill release (USACE CWMS), Stonewall gauge (USGS), weather (Open-Meteo).
UH routing (R^2=0.89) + measured stage-rise depth. Two modes (Drift ↓ / Motor up ↑),
each with a From/To selector and a generated itinerary. Fly box mined from Caney Fork
fly-shop/guide reports (Trout Zone Anglers, Perfect Fly, Guide Recommended, Canoe the
Caney), surfaced dynamically by season + clarity + generation, with source attribution.
Estimates to tune from the water: river miles, reference depths, drift speed, boat bands.
"""
import json, urllib.request, urllib.parse, datetime, os, math, sys
from zoneinfo import ZoneInfo
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import riverlib
CT=ZoneInfo("America/Chicago"); UA={"User-Agent":"caney/7.0"}
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"out"); os.makedirs(OUT,exist_ok=True)

# leading 0.0 compensates the -1h period-ending shift above, so the fitted dam->Stonewall routing (R²=0.89) is preserved
CALIB_KERNEL=[0.0,0.010,0.010,0.044,0.089,0.131,0.156,0.142,0.110,0.083,0.071,0.060,0.045,0.024,0.013,0.016,0.020,0.016,0.009,0.001]
CALIB_BASEFLOW=205.0; DAM_RM,STONE_RM=26.6,10.0   # zero-release intercept; 90-day backtest vs Stonewall gauge (see analysis/backtest_flow.py): least-squares intercept 204, min-flow check 205+166≈372=observed min. Was 375 (ran +170 cfs high).
# LEADING-EDGE SPEED — backtested, not folklore. A longtime guide gave the real miles-from-dam
# (Happy Hollow 6, Betty's Island 9, Stonewall 15) and said the bump runs ~3 mph. A 90-day backtest of
# 80 generation events at the Stonewall gauge (analysis/backtest_flow.py) CONFIRMS the distances but
# corrects the speed: the detectable rise at Stonewall (15 mi) has median AND modal lag 6 h (49 of 80
# events) → ~2.5 mph, size-independent. So `mfd` drives routing and arrival = (miles-from-dam)/2.5 h.
WATER_MPH=2.5; MFD_STONE=15.0
_g=sum(CALIB_KERNEL); KERNEL=[w/_g for w in CALIB_KERNEL]; CENTROID=sum(i*w for i,w in enumerate(KERNEL))
# d0 below is a REFERENCE DEPTH ESTIMATE with no recorded provenance — it arrived in the
# initial commit undocumented, unlike every other calibrated number here. RISE_CURVE does
# trace to depth_fit.py (its values match that fit's bin medians to a tenth). Treat any
# absolute depth shown on this page as rise-over-minimum plus an unverified base.
RISE_CURVE=[[260,0.0],[500,0.5],[1000,1.3],[2000,2.7],[3900,4.4],[7500,7.2],[11000,10.1]]
ACCESS=[
 {"name":"Long Branch","note":"at the dam","rm":26.4,"mfd":0.0,"types":["wade","paddle","ramp"],"reach":"trout","d0":1.8},
 {"name":"Buffalo Valley","note":"dam, river-left","rm":26.1,"mfd":0.3,"types":["paddle","ramp"],"reach":"trout","d0":2.0},
 {"name":"Lancaster","note":"Hwy 96","rm":24.0,"mfd":2.5,"types":["wade"],"reach":"trout","d0":2.0},
 {"name":"Happy Hollow","note":"off I-40","rm":19.0,"mfd":6.0,"types":["wade","paddle","ramp"],"reach":"trout","d0":2.2},
 {"name":"I-40 Welcome Ctr","note":"bank access","rm":18.0,"mfd":7.0,"types":["wade","paddle"],"reach":"trout","d0":2.3},
 {"name":"Betty's Island","note":"the flats","rm":15.0,"mfd":9.0,"types":["wade","paddle","ramp"],"reach":"trout","d0":1.6},
 {"name":"Stonewall","note":"Gordonsville gauge","rm":10.0,"mfd":15.0,"types":["wade","paddle","ramp"],"reach":"trout","d0":2.8},
 {"name":"South Carthage","note":"Bob Lowery ramp","rm":3.0,"mfd":22.0,"types":["ramp"],"reach":"lower","d0":6.0},
 {"name":"Carthage","note":"Cumberland mouth","rm":0.5,"mfd":24.5,"types":["ramp"],"reach":"lower","d0":8.0},
]
def frac(mfd): return max(0.03, mfd/MFD_STONE)   # kernel-routing position, anchored on the guide's real distances
def travel_h(mfd): return mfd/WATER_MPH          # leading-edge arrival: backtested ~2.5-mph rule (see WATER_MPH note)
def compressed_kernel(f):
    # redistribute kernel mass by area (each weight w[i] lands at output lag i*f) — mass-conserving,
    # correct even for tiny f near the dam (point-sampling used to zero those out)
    L=max(1,int(math.ceil((len(KERNEL)-1)*f))+1); out=[0.0]*(L+1)
    for i,w in enumerate(KERNEL):
        pos=i*f; lo=int(pos); fr=pos-lo
        out[lo]+=w*(1-fr)
        if lo+1<=L: out[lo+1]+=w*fr
    s=sum(out) or 1.0; return [x/s for x in out]
# baseflow is CONSTANT along the reach (not frac-scaled): the compressed kernel already conserves mass,
# so every point converges to the same steady flow — a frac-scaled baseflow would settle two points fed the
# same sustained release at different flows, which is impossible with no tributary gain. (backtest finding)
for s in ACCESS: s["kernel"]=compressed_kernel(frac(s["mfd"])); s["baseflow"]=CALIB_BASEFLOW
# on-river coordinates (walked along the real Caney Fork channel from OpenStreetMap) + polyline for the satellite map
_COORDS={"Long Branch":[36.10008,-85.83181],"Buffalo Valley":[36.10178,-85.8341],"Lancaster":[36.1189,-85.84255],
 "Happy Hollow":[36.13574,-85.82606],"I-40 Welcome Ctr":[36.14672,-85.83753],"Betty's Island":[36.14889,-85.8739],
 "Stonewall":[36.19569,-85.91774],"South Carthage":[36.23924,-85.9086],"Carthage":[36.23816,-85.93415]}
for s in ACCESS: s["lat"],s["lon"]=_COORDS[s["name"]]
RIVER_POLY=[[36.098,-85.82633],[36.10387,-85.83965],[36.10947,-85.85155],[36.12086,-85.84187],[36.12823,-85.83537],[36.12257,-85.82596],[36.12932,-85.81278],[36.13329,-85.80541],[36.13805,-85.80305],[36.14135,-85.8036],[36.14214,-85.81095],[36.13852,-85.81969],[36.13594,-85.82657],[36.14433,-85.83465],[36.14678,-85.83908],[36.14824,-85.84456],[36.14969,-85.86014],[36.14316,-85.86597],[36.13968,-85.86988],[36.14434,-85.87618],[36.14991,-85.87354],[36.15366,-85.87074],[36.15718,-85.87194],[36.16099,-85.87521],[36.16461,-85.88182],[36.16917,-85.89096],[36.17114,-85.89563],[36.17322,-85.90126],[36.17718,-85.90746],[36.17953,-85.90941],[36.18555,-85.90561],[36.19192,-85.904],[36.19535,-85.91016],[36.19896,-85.9269],[36.20265,-85.93565],[36.20696,-85.94516],[36.21367,-85.9516],[36.22372,-85.94275],[36.22356,-85.93078],[36.21204,-85.92484],[36.21762,-85.91578],[36.23064,-85.90877],[36.24552,-85.9043],[36.2451,-85.91868],[36.23843,-85.94015],[36.24,-85.94254]]

def get(u,h=None):
    # riverlib.get retries transient TLS/DNS/5xx failures; a single flaky fetch used to
    # build this page with missing data instead of failing (see riverlib.get docstring).
    return riverlib.get(u,{**UA,**(h or {})},timeout=120)
def hr_key(e): return int(e//3600)*3600
now=datetime.datetime.now(datetime.timezone.utc); now_ct=now.astimezone(CT)
begin=(now-datetime.timedelta(hours=48)).strftime("%Y-%m-%dT%H:00:00Z"); end=(now+datetime.timedelta(days=8)).strftime("%Y-%m-%dT%H:00:00Z")
def cwms(name):
    u=("https://cwms-data.usace.army.mil/cwms-data/timeseries?office=LRN"
       f"&name={urllib.parse.quote(name)}&begin={begin}&end={end}&unit=cfs&page-size=500000")
    # CWMS hourly averages are PERIOD-ENDING (value stamped T = avg over T-1h..T); shift to true clock time
    return {hr_key(t/1000)-3600:v for t,v,q in get(u,{"Accept":"application/json;version=2"})["values"] if v is not None}
dam={}
try: dam.update(cwms("CETT1-CENTER_HILL.Flow.Ave.1Hour.1Hour.man-rev"))
except Exception as e: print("actual warn:",e)
try:
    for k,v in cwms("Center Hill Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast").items(): dam.setdefault(k,v)
except Exception as e: print("forecast warn:",e)
# resilience: cache last-good release data; fall back to it if the USACE API is down
CACHE=os.path.join(HERE,"cache_dam.json"); dam_stale=None
if len([k for k in dam if k>=now.timestamp()])>=12:   # got a real forward forecast -> cache it
    try: json.dump({"ts":now.isoformat(),"dam":{str(k):v for k,v in dam.items()}},open(CACHE,"w"))
    except Exception as e: print("cache-write warn:",e)
else:                                                  # API thin/down -> use cache
    try:
        c=json.load(open(CACHE));
        for k,v in c["dam"].items(): dam.setdefault(int(k),v)
        dam_stale=c.get("ts"); print("USING CACHED release data from",dam_stale)
    except Exception as e: print("no usable cache:",e)
wx=None
try:
    wx=get("https://api.open-meteo.com/v1/forecast?latitude=36.10&longitude=-85.83"
           "&hourly=temperature_2m,precipitation_probability,cloud_cover,wind_speed_10m,surface_pressure"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone=America%2FChicago&forecast_days=8")
except Exception as e: print("wx warn:",e)

def dam_at(k):
    if k in dam: return dam[k]
    lo=max((x for x in dam if x<=k),default=None); return dam[lo] if lo is not None else None
def flow_at(s,k):
    acc,ok=0.0,False
    for i,w in enumerate(s["kernel"]):
        d=dam_at(k-i*3600)
        if d is not None: acc+=w*d; ok=True
    return (s["baseflow"]+acc) if ok else None
def units(cfs): return max(1,round((cfs-250)/3650))
def ep(d,h): return hr_key(datetime.datetime(d.year,d.month,d.day,h,tzinfo=CT).timestamp())
def fmt_ap(t): return datetime.datetime.fromtimestamp(t,CT).strftime("%-I%p").lower()
def fmt_hm(t): return datetime.datetime.fromtimestamp(t,CT).strftime("%-I:%M%p").lower()
tom=now_ct.date()+datetime.timedelta(days=1); tom_mid=ep(tom,0); twe=tom_mid+86400
tod_mid=ep(now_ct.date(),0)   # planner flow spans today 00:00 -> +7.5 days so any day is selectable

# --- auto-calibrate baseflow to the live Stonewall gauge over recent low-flow (baseflow-dominated) hours ---
CALIB_ADJ=0
try:
    _stw=next(s for s in ACCESS if s["name"]=="Stonewall")
    _pts=get("https://waterservices.usgs.gov/nwis/iv/?format=json&sites="+riverlib.RIVER_CONFIG["caney"]["gauge"]["site"]+"&period=P2D&parameterCd=00060")["value"]["timeSeries"][0]["values"][0]["value"]
    _resid=[]
    for p in _pts:
        try: gv=float(p["value"])
        except: continue
        if gv<0: continue
        k=hr_key(datetime.datetime.fromisoformat(p["dateTime"]).timestamp()); m=flow_at(_stw,k)
        if m is not None and m<700: _resid.append(gv-m)   # only hours where flow ≈ baseflow
    if len(_resid)>=6:
        _resid.sort(); CALIB_ADJ=max(-250,min(250,_resid[len(_resid)//2]))   # clamped median offset
        for s in ACCESS: s["baseflow"]=(CALIB_BASEFLOW+CALIB_ADJ)   # constant along the reach (see above)
        print("gauge auto-calibration: baseflow %+.0f cfs (n=%d low-flow hrs)"%(CALIB_ADJ,len(_resid)))
except Exception as e: print("calib warn:",e)

points=[{"name":s["name"],"note":s["note"],"rm":s["rm"],"mfd":s["mfd"],"types":s["types"],"reach":s["reach"],"d0":s["d0"],
         "lat":s["lat"],"lon":s["lon"],
         "flow":[round(flow_at(s,tod_mid+h*3600) or 0) for h in range(180)]} for s in ACCESS]

def gen_windows():
    res,run,pk=[],None,0
    for k in sorted(dam):
        v=dam[k]
        if v>=800 and run is None: run,pk=k,v
        elif v>=800: pk=max(pk,v)
        elif run is not None: res.append((run,k,pk)); run=None
    if run is not None: res.append((run,sorted(dam)[-1],pk))
    return res
GW=gen_windows()
def unit_ct(v): return max(0,round(((v or 0)-250)/3650))
def ramp_blocks(d0,d1):   # merge consecutive hours by unit count -> the actual 1->2->3->2->1 ramp
    blocks=[]; cur=None; k=d0
    while k<d1:
        u=unit_ct(dam_at(k)); v=dam_at(k) or 0
        if u<1:
            if cur: blocks.append(cur); cur=None
        elif cur and cur[2]==u: cur[1]=k+3600; cur[3]=max(cur[3],v)
        else:
            if cur: blocks.append(cur)
            cur=[k,k+3600,u,v]
        k+=3600
    if cur: blocks.append(cur)
    return blocks
_tb=ramp_blocks(tod_mid,tod_mid+86400)
dam_cap=("Center Hill today: "+", ".join("%dU %s–%s"%(u,fmt_ap(a),fmt_ap(b)) for a,b,u,pk in _tb)) if _tb else "Center Hill: minimum flow all day (no generation)"
parts=[f"{units(pk)}U {fmt_ap(max(a,tom_mid))}–{fmt_ap(min(b,twe))}" for a,b,pk in GW if not(b<=tom_mid or a>=twe)]

def wx_pack(day):
    if not wx: return None
    H=wx["hourly"]; idx={t:i for i,t in enumerate(H["time"])}
    def at(hr): return idx.get(datetime.datetime(day.year,day.month,day.day,hr).strftime("%Y-%m-%dT%H:00"))
    def snap(hr,label):
        i=at(hr)
        if i is None: return None
        cc=H["cloud_cover"][i]; pp=H["precipitation_probability"][i] or 0
        ico="☀️" if cc<25 else "⛅" if cc<65 else "☁️"
        if pp>=45: ico="🌧️"
        return {"when":label,"temp":round(H["temperature_2m"][i]),"sky":"clear" if cc<25 else "partly cloudy" if cc<65 else "overcast","ico":ico,"wind":round(H["wind_speed_10m"][i]),"precip":pp}
    snaps=[x for x in [snap(7,"Dawn"),snap(13,"Midday"),snap(19,"Dusk")] if x]
    i6,i18=at(6),at(18); ptr="steady"
    if i6 is not None and i18 is not None:
        dp=H["surface_pressure"][i18]-H["surface_pressure"][i6]; ptr="falling" if dp<-1.5 else "rising" if dp>1.5 else "steady"
    D=wx["daily"]; di=D["time"].index(day.strftime("%Y-%m-%d")) if day.strftime("%Y-%m-%d") in D["time"] else None
    g=lambda a: D[a][di] if di is not None else None
    return {"hi":round(g("temperature_2m_max")) if di is not None else None,"lo":round(g("temperature_2m_min")) if di is not None else None,
            "sunrise":(g("sunrise") or "")[11:16],"sunset":(g("sunset") or "")[11:16],"pressure":ptr,"snaps":snaps,"precipMax":g("precipitation_probability_max")}
WXDAYS=[wx_pack(now_ct.date()+datetime.timedelta(days=di)) for di in range(7)]
WX=WXDAYS[1]
clar_word="stained" if (WX and (WX["precipMax"] or 0)>70) else "some color" if (WX and (WX["precipMax"] or 0)>35) else "clear"

# ---- live "right now": current release + Stonewall gauge vs model ----
now_hr=hr_key(now.timestamp()); stw=next(x for x in ACCESS if x["name"]=="Stonewall")
cur=dam_at(now_hr); now_stone=None
try:
    pts=get("https://waterservices.usgs.gov/nwis/iv/?format=json&sites="+riverlib.RIVER_CONFIG["caney"]["gauge"]["site"]+"&period=PT4H&parameterCd=00060")["value"]["timeSeries"][0]["values"][0]["value"]
    now_stone=round(float(pts[-1]["value"]))
except Exception as e: print("gauge warn:",e)
_prev=dam_at(now_hr-3600)
NOW={"cfs":round(cur) if cur else None,"units":units(cur) if (cur and cur>=800) else 0,"gen":bool(cur and cur>=800),
     "trend":("rising" if (cur and _prev and cur>_prev+150) else "falling" if (cur and _prev and cur<_prev-150) else "steady"),
     "stone":now_stone,"model":round(flow_at(stw,now_hr) or 0),"clarity":clar_word,"asof":now_ct.strftime("%-I:%M %p"),
     "stale":dam_stale,"calib":round(CALIB_ADJ)}

# ---- solunar feeding windows (real API) ----
def fmt12(hm):
    try: h,m=map(int,hm.split(":")); return "%d:%02d%s"%((h%12) or 12,m,"am" if h<12 else "pm")
    except: return hm
# computed locally: moon age (exact) + real sunrise/sunset. Majors = moon over/underfoot; minors = moonrise/set.
def _fmin(m): m=int(round(m))%1440; return fmt12("%d:%02d"%(m//60,m%60))
def _solunar(day,wxd):
    if not (wxd and wxd.get("sunrise") and wxd.get("sunset")): return None
    def _m(hm): h,mn=map(int,hm.split(":")); return h*60+mn
    noon=(_m(wxd["sunrise"])+_m(wxd["sunset"]))/2.0
    ref=datetime.datetime(2000,1,6,18,14,tzinfo=datetime.timezone.utc).timestamp(); syn=29.530588853
    tnoon=datetime.datetime(day.year,day.month,day.day,12,0,tzinfo=CT).timestamp()
    age=((tnoon-ref)/86400.0)%syn; frac=age/syn
    illum=round((1-math.cos(2*math.pi*frac))/2*100)
    moon=next(n for f,n in [(.02,"New"),(.24,"Waxing crescent"),(.28,"First quarter"),(.47,"Waxing gibbous"),
              (.53,"Full"),(.72,"Waning gibbous"),(.78,"Last quarter"),(.98,"Waning crescent"),(2,"New")] if frac<=f)
    ut=(noon+age*48.8)%1440; lt=(ut+720)%1440
    d=min(frac,abs(frac-.5),abs(frac-1.0)); rating=max(1,min(5,round(1+(1-d/0.25)*4)))
    return {"rating":rating,"moon":"%s · %d%% lit"%(moon,illum),"approx":True,
            "major":[[_fmin(ut-60),_fmin(ut+60)],[_fmin(lt-60),_fmin(lt+60)]],
            "minor":[[_fmin(ut-368),_fmin(ut-308)],[_fmin(ut+308),_fmin(ut+368)]]}
SOLDAYS=[_solunar(now_ct.date()+datetime.timedelta(days=di),WXDAYS[di]) for di in range(7)]
SOL=SOLDAYS[1]

# tips
tips=[["🌡️","Bottom-release tailwater — water stays cold (~50°F) year-round. Midges and sowbugs/scuds are the everyday staple; trout feed through the day."]]
tips.append(["🌊",(f"Generation scheduled ({', '.join(parts)}). Wade early and be off the flats before the bump reaches you; then fish the rise from the boat and nymph the falling limb as it clears." if parts
 else "Minimum flow all day — classic sight-fishing. Wade the flats with light tippet and delicate presentations.")])
tips.append(["⏱️","How the water travels (backtested against 80 releases at the Stonewall gauge): the generating bump moves ~2.5 mph, so it reaches Happy Hollow ~2½ h after release, Betty's Island ~3½ h, and Stonewall ~6 h. Wade the flats until it's due, then be in the boat riding the rise. The water's always on time — that predictability is the edge."])
if WX:
    if WX["pressure"]=="falling": tips.append(["📉","Barometer dropping ahead of weather — often a feeding window. Fish the front edge hard before the rain."])
    elif WX["pressure"]=="rising": tips.append(["📈","Rising/high pressure, bright sky — fish deeper and smaller, lengthen the leader, target shade and riffles."])
    if WX["hi"] and WX["hi"]>=80: tips.append(["🦗","Warm summer day — terrestrials (ant, beetle, small hopper) tight to the bank, caddis/sulphurs at last light."])
    if any(s["wind"]>=13 for s in WX["snaps"]): tips.append(["🌬️","Breezy — shorten the leader, add a hair of weight, use the wind to cover your approach."])
if SOL and SOL["major"]:
    tips.append(["🌙","Solunar majors (peak feeding): "+", ".join("%s–%s"%(w[0],w[1]) for w in SOL["major"])+". When one lines up with the rising release, that's the hot window."])

# ---- mined fly box (dynamic by season + clarity + generation) ----
m=tom.month; season="summer" if 6<=m<=8 else "fall" if 9<=m<=11 else "winter" if m in (12,1,2) else "spring"
flies=["Black Zebra Midge #18–22","BH Sowbug / Scud #14–16","Pheasant Tail #16–18"]
flies += {"clear":["Tiny midge — WD-40 / Black Beauty #20–22 (6–7X)"],
          "some color":["Zebra Midge #16–18","Small pink or orange egg"],
          "stained":["San Juan Worm","Woolly Bugger (olive/black)","Bright egg"]}[clar_word]
flies += {"summer":["Cinnamon / Little Sister Caddis #16","Sulphur / PMD","Beetle · Ant · Chubby Chernobyl (grassy banks)"],
          "fall":["Blue-Winged Olive #18–22","Trico #22"],
          "winter":["Blue-Winged Olive #18–22","Gray Midge #18–22","Blue Quill #16–20"],
          "spring":["Hendrickson · March Brown · Red Quill","Blue-Winged Olive #18–22"]}[season]
if parts: flies.append("Small streamer — Woolly Bugger / sculpin on the swing (when they bump water)")
flybox={"season":season,"now":flies,
        "rig":"Go-to rig: double nymph — Zebra Midge over a sowbug/scud, 9–12 ft leader to 6X, weight to ride just off the bottom. Small streamers when the water comes up; sight-fish the flats at dead low.",
        "hatch":[["Spring","Hendrickson, March Brown, Red Quill, BWO"],["Summer","Caddis (cinnamon/little sister), Sulphur/PMD, terrestrials, Trico (Aug)"],
                 ["Fall","BWO, Trico, midges"],["Winter","BWO, Gray Midge, Blue Quill, midges"]],
        "sources":[["Trout Zone Anglers","https://troutzoneanglers.com/tennessee-tailwaters/caney-fork-river-fly-fishing-guide/"],
                   ["Perfect Fly","https://perfectflystore.com/your-streams/fly-fishing-on-the-caney-fork-river-in-tennessee/"],
                   ["Guide Recommended","https://guiderecommended.com/guide-to-fly-fishing-the-caney-fork-tennessee-maps-flies-and-technique/"],
                   ["Canoe the Caney","https://www.canoethecaney.com/the-caney-fork-river/caney-fork-fly-fishing.html"]],
        "asof":now_ct.strftime("%b %-d, %Y")}

# calendar + daily itinerary
HH=next(s for s in ACCESS if s["name"]=="Happy Hollow")
BI=next(s for s in ACCESS if s["name"]=="Betty's Island")
SW=next(s for s in ACCESS if s["name"]=="Stonewall")
def cond_flow(cfs): return "high" if cfs is not None and cfs>4500 else "wade" if (cfs is not None and cfs<1000) else "boat" if cfs is not None else "na"
def itinerary(day,short):
    onwin=next(((a,b,pk) for a,b,pk in GW if ep(day,5)<=a<ep(day,21)),None)
    lag_b=travel_h(BI["mfd"]); lag_s=travel_h(SW["mfd"])   # backtested ~2.5-mph leading edge: Betty's ~3½h, Stonewall ~6h
    if onwin:
        a,b,pk=onwin; pb=a+lag_b*3600; ps=a+lag_s*3600
        if short: return f"Wade AM · {units(pk)}U release {fmt_ap(a)} · boat PM"
        return (f"Put in low (Stonewall or Betty's) early and motor up to the flats — wadeable through the morning. "
                f"The {units(pk)}-unit release starts {fmt_hm(a)}; the bump reaches Betty's Island ~{fmt_hm(pb)} and Stonewall ~{fmt_hm(ps)}. "
                f"Be off the flats before it arrives, then ride the rise fishing from the boat (prime 1,000–4,000 cfs) back downstream. Off before dark.")
    if short: return "Low all day · wade the flats"
    return ("Minimum flow all day — skinny up high for the 1654. Launch low where there's floating water, motor up and wade the gravel bars "
            "(long leaders, light tippet), and keep the boat to the lower, deeper reaches.")
cal=[]
for di in range(7):
    d=now_ct.date()+datetime.timedelta(days=di)
    states=[cond_flow(flow_at(HH,ep(d,h))) for h in range(24)]
    dd=None
    if WX and d.strftime("%Y-%m-%d") in wx["daily"]["time"]:
        j=wx["daily"]["time"].index(d.strftime("%Y-%m-%d"))
        dd={"hi":round(wx["daily"]["temperature_2m_max"][j]),"lo":round(wx["daily"]["temperature_2m_min"][j]),"pop":wx["daily"]["precipitation_probability_max"][j]}
    cal.append({"label":("Today" if di==0 else d.strftime("%a")),"date":d.strftime("%-m/%-d"),"states":states,"plan":itinerary(d,True),"wx":dd})

# ---- event-driven timed itinerary, for ANY day (reads the actual flow curve) ----
def _pin(c,x):
    if x<=c[0][0]: return c[0][1]
    for i in range(1,len(c)):
        if x<=c[i][0]: a=c[i-1];b2=c[i];return a[1]+(b2[1]-a[1])*(x-a[0])/(b2[0]-a[0])
    a=c[-2];b2=c[-1];return b2[1]+(b2[1]-a[1])*(x-b2[0])/(b2[0]-a[0])
_st=next(x for x in ACCESS if x["name"]=="Stonewall"); _bt=next(x for x in ACCESS if x["name"]=="Betty's Island")
def condp(s,cfs):
    # Wade threshold is MEASURED, not assumed: USGS field measurements at 03424860 show
    # crews waded 80% of the time at 272 cfs, 75% at 398, but only 20% at 582 and never
    # above 1,824 (analysis/channel_geom.py, n=110). This used to call anything under
    # 1,000 cfs wadeable, which is well past the flow professionals stop getting in.
    # d0 is an UNVERIFIED reference depth (see ACCESS below) so it only narrows the call,
    # it never widens it.
    d=s["d0"]+_pin(RISE_CURVE,cfs)
    return "high" if cfs>4500 else ("wade" if (cfs<riverlib.WATER_MODEL["caney"]["wade_marginal"] and d<3.2) else "boat")
def _hm2ep(d,s,fb):
    if s and ":" in s: h,mn=s.split(":");return datetime.datetime(d.year,d.month,d.day,int(h),int(mn),tzinfo=CT).timestamp()
    return datetime.datetime(d.year,d.month,d.day,fb,0,tzinfo=CT).timestamp()
def _daysun(d):
    if WX and d.strftime("%Y-%m-%d") in wx["daily"]["time"]:
        j=wx["daily"]["time"].index(d.strftime("%Y-%m-%d"))
        return _hm2ep(d,wx["daily"]["sunrise"][j][11:16],6),_hm2ep(d,wx["daily"]["sunset"][j][11:16],20)
    return _hm2ep(d,None,6),_hm2ep(d,None,20)
# the wade-fishing tour, upstream -> downstream (the bars you actually work)
TOUR=[s for nm in ["Lancaster","Happy Hollow","Betty's Island","Stonewall"] for s in ACCESS if s["name"]==nm]
def day_steps(d):
    sr,ss=_daysun(d); k0=hr_key(sr); k1=hr_key(ss)
    def fl(s,k): return flow_at(s,k) or 0
    def rise(s):                       # the bump's leading edge arrives — the backtested ~2.5-mph rule, not the
        # kernel's dispersed crossing (which runs early on big releases). Leading edge reaches s at
        # release-start + (miles-from-dam)/2.5 mph: Happy Hollow ~2½h, Betty's ~3½h, Stonewall ~6h.
        on=next(((a,b,pk) for a,b,pk in GW if k0-2*3600<=a<=k1),None)
        if not on: return None
        t=hr_key(on[0]+travel_h(s["mfd"])*3600)
        return t if t<=k1+2*3600 else None
    km=k0+2*3600; sflow=fl(_st,k0)
    srw=[s for s in TOUR if condp(s,fl(s,k0))=="wade"]      # wadeable at first light
    mw=[s for s in TOUR if condp(s,fl(s,km))=="wade"]        # wadeable a couple hrs in (after carryover drains)
    ev=[]
    if srw:
        s0="First light — launch at <b>Stonewall</b> (~%0.0f cfs) and run up. Wade the bars top-down: <b>%s</b> — the upper spots take the bump first, so fish down through the morning."%(sflow," → ".join(s["name"] for s in srw))
    elif mw:
        s0="First light — launch at <b>Stonewall</b> (~%0.0f cfs). Overnight water is still draining; as it drops out mid-morning, wade the bars top-down: <b>%s</b>."%(sflow," → ".join(s["name"] for s in mw))
    else:
        s0="First light — launch at <b>Stonewall</b> (~%0.0f cfs). The reach is boat water — fish from the boat: streamers on the swing, nymph the seams."%sflow
    ev.append((k0,fmt_hm(sr),s0))
    gen=False
    for a,b,pk in GW:
        if k0<=a<=k1: gen=True; ev.append((a,fmt_hm(a),"%d-unit release starts at Center Hill — get on the leading edge up top and ride it down."%units(pk)))
    rises=sorted([(c,s) for c,s in ((rise(s),s) for s in TOUR) if c is not None],key=lambda e:e[0])
    for n,(c,s) in enumerate(rises):
        if n<len(rises)-1:
            tx="Leading edge at <b>%s</b> (~%0.0f cfs) — hold on the rise in the sweet 1,500–3,000 cfs (on the oars) and drift down with it toward <b>%s</b>; no need to stop unless it goes flat."%(s["name"],fl(s,c),rises[n+1][1]["name"])
        else:
            tx="Edge reaches <b>%s</b> (~%0.0f cfs) — ride it out fishing the prime water down to the take-out."%(s["name"],fl(s,c))
        ev.append((c,fmt_hm(c),tx))
    if not gen and not rises:
        ev.append((hr_key(ss)-3600,fmt_hm(ss-3600),"Low and clear all day — no bump coming, so work the bars top-to-bottom (%s) at your own pace; the last hour at dusk is prime (caddis/sulphurs)."%", ".join(s["name"] for s in TOUR)))
    ev.append((ss+1,fmt_hm(ss),"Last light — off the water."))
    ev.sort(key=lambda e:e[0]); return [{"t":e[1],"x":e[2]} for e in ev]
for _i in range(7): cal[_i]["steps"]=day_steps(now_ct.date()+datetime.timedelta(days=_i))
itin_steps=day_steps(tom)

# ---- score each of the 7 days -> "best bet this week" ----
def moon_rating(d):
    ref=datetime.datetime(2000,1,6,18,14,tzinfo=datetime.timezone.utc).timestamp(); syn=29.530588853
    tn=datetime.datetime(d.year,d.month,d.day,12,0,tzinfo=CT).timestamp()
    frac=(((tn-ref)/86400.0)%syn)/syn; dist=min(frac,abs(frac-.5),abs(frac-1.0))
    return max(1,min(5,round(1+(1-dist/0.25)*4)))
def score_day(di,d):
    d0=ep(d,0); blk=ramp_blocks(d0,d0+86400)
    peak_u=max([b[2] for b in blk],default=0)
    gs=min([b[0] for b in blk],default=None); ge=max([b[1] for b in blk],default=None)
    mr=moon_rating(d)
    gen=(45 if peak_u<=2 else 36) if peak_u>=1 else 28
    wxd=WXDAYS[di] or {}; pop=wxd.get("precipMax") or 0; hi=wxd.get("hi")
    mid=next((s for s in wxd.get("snaps",[]) if s["when"]=="Midday"),None)
    ico=mid["ico"] if mid else "🌡️"
    wsc=15 if pop<=30 else 10 if pop<=60 else 3
    score=round(mr/5*40+gen+wsc)
    grade="Prime" if score>=88 else "Good" if score>=78 else "Fair" if score>=68 else "Tough"
    if peak_u>=1:
        window="rise %s–%s"%(fmt_ap(gs),fmt_ap(ge)); verdict="%d-unit afternoon rise%s"%(peak_u," · strong moon feed" if mr>=4 else "")
    else:
        window="wade dawn–dusk"; verdict="Low & clear — sight-fish the flats"
    return {"i":di,"label":cal[di]["label"],"date":cal[di]["date"],"score":score,"grade":grade,
            "units":peak_u,"moon":mr,"ico":ico,"hi":hi,"pop":pop,"verdict":verdict,"window":window,
            "blurb":"%s · moon %d/5"%(("%d-unit release %s"%(peak_u,fmt_ap(gs))) if peak_u else "minimum flow",mr)}
_scores=[score_day(di, now_ct.date()+datetime.timedelta(days=di)) for di in range(7)]
_top=sorted(_scores,key=lambda x:-x["score"])[:2]
WEEK_SYNTH="Best days: "+", ".join("%s (%s)"%(t["label"],t["grade"]) for t in _top)+" — "+_top[0]["verdict"].lower()+"."
BEST=max(_scores,key=lambda x:x["score"]); DAYSCORES=[s["score"] for s in _scores]

# ---- detailed generation schedule per day ----
GEN=[]
for di in range(7):
    d=now_ct.date()+datetime.timedelta(days=di); d0=ep(d,0); d1=d0+86400
    wins=[{"span":"%s–%s"%(fmt_ap(a),fmt_ap(b)),"units":u,"cfs":round(pk),"hrs":round((b-a)/3600)}
          for a,b,u,pk in ramp_blocks(d0,d1)]
    spark=[unit_ct(dam_at(d0+h*3600)) for h in range(24)]
    _rb=ramp_blocks(d0,d1)
    _rst=min(b[0] for b in _rb) if _rb else None   # release-start epoch (front origin)
    # when the bump reaches the key ramps — the backtested ~2.5-mph leading edge (mfd/2.5 after release start)
    _arr=[[s["name"].replace("Happy Hollow","Happy Hollow").replace("Betty's Island","Betty's"),
           fmt_ap(_rst+s["mfd"]/WATER_MPH*3600)] for s in (HH,BI,SW)] if _rst else None
    GEN.append({"label":cal[di]["label"],"date":cal[di]["date"],"windows":wins,"spark":spark,"peak":max(spark),
                "span":(fmt_ap(_rst) +"–"+ fmt_ap(max(b[1] for b in _rb))) if wins else None,
                "relStart":int((_rst-d0)//60) if _rst else None,
                "arr":_arr,
                "genhrs":sum(w["hrs"] for w in wins)})

# fishing-weather verdict per day (pressure + sky), graded
def wx_verdict(wxd):
    if not wxd: return {"grade":"—","why":"no data"}
    pop=wxd.get("precipMax") or 0; pr=wxd.get("pressure")
    mid=next((s for s in wxd.get("snaps",[]) if s["when"]=="Midday"),{})
    sky=mid.get("sky",""); sc=2; why=[]
    if pr=="falling": sc+=1; why.append("falling barometer")
    elif pr=="rising": sc-=1; why.append("high/rising pressure")
    else: why.append("steady pressure")
    if sky in ("overcast","partly cloudy"): sc+=1; why.append("cloud cover")
    else: why.append("bright sun")
    if pop>60: sc-=1; why.append("rain likely")
    return {"grade":["Tough","Fair","Good","Great"][max(0,min(3,sc))],"why":" · ".join(why[:2])}
WXV=[wx_verdict(w) for w in WXDAYS]

# Seasonal hatch/forage calendar (cold bottom-release tailwater — bugs year-round). 0-3 intensity by month.
HATCH={"rows":[
 {"name":"Midge","icon":"🦟","pattern":"zebra/black #18–22","m":[3,3,2,2,2,2,2,2,2,2,3,3]},
 {"name":"Scud / sowbug","icon":"🦐","pattern":"#14–18, the everyday staple","m":[3,3,3,3,3,3,3,3,3,3,3,3]},
 {"name":"Blue-winged olive","icon":"🪰","pattern":"BWO #18–22","m":[1,2,3,2,1,0,0,0,1,2,3,1]},
 {"name":"Sulphur","icon":"🟡","pattern":"#16–18","m":[0,0,0,1,3,3,2,1,0,0,0,0]},
 {"name":"Caddis","icon":"🪰","pattern":"elk-hair / pupa #14–16","m":[0,0,1,3,2,1,0,0,0,1,0,0]},
 {"name":"Cranefly","icon":"🦗","pattern":"larva on the bottom","m":[1,2,3,2,1,0,0,0,0,0,1,1]},
 {"name":"Terrestrials","icon":"🐜","pattern":"ant / beetle / hopper","m":[0,0,0,0,1,2,3,3,3,2,0,0]},
 {"name":"Sculpin / streamer","icon":"🐟","pattern":"browns on the rise","m":[2,2,2,1,1,1,1,1,2,3,3,3]},
]}

# clarity × light fly matrix (shared). Clarity from the current release/generation state.
FLYORDER=["clear","moderate","stained","muddy"]; LIGHTS=[("dawn","Dawn"),("low","Low light"),("bright","Bright sun"),("wind","Wind / chop")]
FLYMATRIX={
 "clear":   {"label":"Min flow · off","dawn":"BWO emerger #20","low":"Zebra midge #20","bright":"Sowbug #18 (sight)","wind":"Zebra midge #18"},
 "moderate":{"label":"Edge · rising","dawn":"Sulphur soft-hackle #16","low":"Pheasant Tail #16","bright":"Scud #16","wind":"San Juan worm"},
 "stained": {"label":"1 unit","dawn":"Small streamer","low":"Woolly Bugger","bright":"Sowbug #14 (deep)","wind":"Conehead bugger"},
 "muddy":   {"label":"2–3 units","dawn":"Sculpin","low":"Articulated streamer","bright":"White streamer","wind":"Big bugger"},
}
BOXINV_K=[
 ["Zebra midge","#18–22","The everyday staple — under an indicator; larva low, pupa up top."],
 ["Sowbug / scud","#14–18","Year-round bottom bug — sight-fish the flats at minimum flow."],
 ["Sulphur / soft-hackle","#14–18","Late spring & summer — swing it on the edge as the water bumps."],
 ["Pheasant Tail / Prince","#14–18","Searching nymph through seams & drop-offs."],
 ["Woolly Bugger / sculpin","#2–8","On the generation rise — swing & strip for the browns."],
 ["Articulated streamer","#2–4","Big water (2–3 units) — deep on a sink-tip, tight to the bank."],
]
_kc=cur; _kcl=("clear" if not _kc or _kc<800 else "moderate" if _kc<4500 else "stained" if _kc<8000 else "muddy")
_kh=now_ct.hour; _kcloud=50; _kwind=6
if wx:
    _H=wx["hourly"]; _k=now_ct.strftime("%Y-%m-%dT%H:00")
    if _k in _H["time"]: _wi=_H["time"].index(_k); _kcloud=_H["cloud_cover"][_wi] or 0; _kwind=_H["wind_speed_10m"][_wi] or 0
_klight=riverlib.light_now(_kh,_kcloud,_kwind)
FLYSEL={"matrix":FLYMATRIX,"order":FLYORDER,"lights":LIGHTS,"boxinv":BOXINV_K,
  "now":{"clarity":_kcl,"light":_klight,"fly":FLYMATRIX[_kcl][_klight]},
  "rig":"Water off → tandem midge/sowbug rig under an indicator, long 6–7X leader; sight-fish the flats. On the bump → swing a soft-hackle on the edge, then streamers as it comes up.",
  "sources":[["Trout Zone Anglers","https://troutzoneanglers.com/tennessee-tailwaters/caney-fork-river-fly-fishing-guide/"],["The Perfect Fly Store","https://perfectflystore.com/your-streams/fly-fishing-on-the-caney-fork-river-in-tennessee/"]]}
# R3 — release events for the arrival strip, as machine-readable epochs.
# Source is GW (gen_windows): maximal runs above 800 cfs, i.e. the actual release EVENT.
# Deliberately NOT GEN[].relStart — that comes from ramp_blocks, which splits on unit-count
# change (a 1U->2U->1U day is three blocks but one front) and only ever reports the first
# block of the day, so a countdown built on it is silently wrong for an afternoon release.
# Keep windows that ended within the last 6 h so the "water is here" state still resolves.
_arr_cut = now.timestamp() - 6*3600
ARRIVAL = {"id":"caney", "mph":WATER_MPH, "validated":True,
           "spots":[{"name":s["name"], "mfd":s["mfd"]} for s in (HH,BI,SW)],
           "rel":[[int(a), int(b), round(pk)] for a,b,pk in GW if b >= _arr_cut]}
DATA={"arrival":ARRIVAL,
      "todayLabel":now_ct.strftime("%A, %B %-d · %-I:%M %p"),"dateLabel":tom.strftime("%A, %B %-d"),"hatch":HATCH,"month":now_ct.month,"chatter":riverlib.load_intel("caney"),"flysel":FLYSEL,
      "damCap":dam_cap,"clarity":clar_word,"points":points,"riseCurve":RISE_CURVE,"weather":WX,"tips":tips,
      "calendar":cal,"itinerary":itin_steps,"now":NOW,"solunar":SOL,"best":BEST,"dayscores":DAYSCORES,
      "wxDays":WXDAYS,"solDays":SOLDAYS,"gen":GEN,"week":_scores,"weekSynth":WEEK_SYNTH,"wxv":WXV,"riverPoly":RIVER_POLY,
      "genHint":"Center Hill generation, midnight→midnight (bar height = units). Then the bump travels ~2.5 mph downstream — arrival times backtested at the Stonewall gauge (Happy Hollow ~2½h · Betty's ~3½h · Stonewall ~6h after release).",
      "genLegend":'<span><i style="background:#7db8e0"></i>1 unit</span><span><i style="background:#2f92d4"></i>2 units</span><span><i style="background:#5e5ce6"></i>3 units</span><span>Verify against TVA before you launch.</span>',
      "genOpts":{"minLabel":"minimum flow — wade all day","arrLabel":"bump reaches"},
      "sliderMin":300,"sliderMax":1200,"sliderStep":15,"launchDefault":420,"planDefault":1,"mph":WATER_MPH,
      "wadeMax":riverlib.WATER_MODEL["caney"]["wade_marginal"],
      "arrivalStages":{k:{"mph":v["mph"],"early":v["mph_early"],"late":v["mph_late"],"label":v["label"]}
                       for k,v in riverlib.ARRIVAL_STAGES.items()}}

TEMPLATE=r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Caney Fork</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#16202b;--muted:#66788a;--faint:#93a3b3;--line:#e6ecf2;--blue:#0a84ff;--green:#28c76f;--indigo:#5e5ce6;--card:#fff}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,sans-serif;
 background:radial-gradient(1000px 700px at 82% -6%,#eaf3fb 0,transparent 60%),linear-gradient(180deg,#f0f5fa,#e4edf5);min-height:100vh}
.app{max-width:900px;margin:0 auto;padding:32px 22px 140px}
.eyebrow{font-size:12px;letter-spacing:.26em;text-transform:uppercase;color:var(--faint);font-weight:600}
__SWITCH_CSS__
h1{margin:6px 0 4px;font-size:34px;font-weight:700;letter-spacing:-.6px}
.cap{color:var(--muted);font-size:14.5px}.cap b{color:var(--ink)}
.sec{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--faint);font-weight:600;margin:30px 2px 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 26px rgba(20,50,80,.06)}
.plan{background:#fff;border:1px solid var(--line);border-radius:16px;padding:6px 18px 14px;box-shadow:0 4px 16px rgba(20,50,80,.05)}
.plan .h{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--blue);font-weight:700;margin:12px 0 4px}.plan .b{font-size:15px;line-height:1.55}
.plan .step{display:flex;gap:14px;padding:9px 0;border-top:1px solid var(--line)}.plan .step:first-child{border-top:0}
.plan .st{flex:none;width:112px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--blue);font-size:14px}
.plan .sx{font-size:14px;line-height:1.45}
.nowstrip{padding:12px 16px;margin:14px 0 0;font-size:14px;display:flex;align-items:center;flex-wrap:wrap;gap:4px}
.best{margin:12px 0 0;padding:15px 18px;cursor:pointer;display:flex;align-items:center;gap:15px}
.best .tg{flex:none;width:64px;text-align:center;color:#fff;font-weight:800;font-size:12px;letter-spacing:.03em;padding:9px 0;border-radius:10px}
.best .bmid{flex:1;min-width:0}.best .bt{font-size:15.5px;font-weight:700;color:var(--ink)}
.best .bb{font-size:13px;color:var(--muted);margin-top:2px}.best .bb b{color:var(--ink);font-weight:600}
.best .go{flex:none;color:var(--blue);font-weight:700;font-size:13px;white-space:nowrap}
.safety{padding:11px 14px;border-radius:12px;font-size:13.5px;margin-bottom:12px;font-weight:500}
.safety.ok{background:#eafaf0;color:#1e7a45;border:1px solid #bfe6cf}
.safety.warn{background:#fdeceb;color:#b0392f;border:1px solid #f3c9c5}
.cscore{flex:none;font-size:11.5px;font-weight:700;border-radius:20px;padding:3px 9px;text-align:center;min-width:34px}
.crow.bestrow{background:linear-gradient(90deg,rgba(255,247,224,.7),rgba(255,247,224,0));border-radius:12px;margin:0 -8px;padding-left:8px;padding-right:8px}
__GENSCHED_CSS__
__ARRIVAL_CSS__
.wxverdict{display:flex;align-items:center;gap:10px;font-size:13.5px;color:var(--muted);margin-bottom:12px}
.wxverdict .vg{flex:none;color:#fff;font-weight:800;font-size:11px;padding:4px 11px;border-radius:8px}.wxverdict b{color:var(--ink);font-weight:600}
.planwx{font-size:12.5px;color:var(--muted);padding:11px 14px;background:#f3f8fd;border:1px solid #e4eef7;border-radius:12px;margin-bottom:12px;line-height:1.85}.planwx b{color:var(--ink);font-weight:600}
.crafts button{font-size:13px}#modeWrap{margin-top:2px}
.nowstrip .dotlg{width:11px;height:11px;border-radius:50%;margin-right:8px}
.nowstrip .mchk{color:var(--muted);font-size:12.5px} .nowstrip .asof{color:var(--faint);font-size:12px;margin-left:auto}
.wxrow{display:flex;gap:14px;align-items:stretch}.wxrow .wx{flex:2}.wxrow .feed{flex:1;min-width:220px}
.feed{padding:14px 16px}.feed .fh{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);font-weight:600;margin-bottom:8px;display:flex;justify-content:space-between}
.feed .stars{color:#f0a52b;letter-spacing:1px}.feed .fx{font-size:13.5px;margin:4px 0;color:var(--muted)}.feed .fx b{color:var(--ink);font-weight:650;margin-right:6px}.feed .moon{color:var(--faint);margin-top:8px}
.wx{display:flex;flex-wrap:wrap}.wx .m{flex:1;min-width:120px;padding:12px 16px;border-right:1px solid var(--line)}.wx .m:last-child{border-right:0}
.wx .w{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);font-weight:600}.wx .t{font-size:25px;font-weight:700;margin:2px 0}.wx .d{font-size:12.5px;color:var(--muted)}
.wx .meta{font-size:12.5px;color:var(--muted);padding:12px 16px;display:flex;flex-direction:column;justify-content:center;gap:3px;min-width:150px}
.tips{padding:6px}.tip{display:flex;gap:12px;padding:11px 12px;border-bottom:1px solid var(--line)}.tip:last-child{border-bottom:0}.tip .i{font-size:20px}.tip .x{font-size:14px;line-height:1.5}
/* graphical river — stations placed by true river mile (to scale) */
.stage{position:relative;width:620px;height:780px;margin:2px auto}
#rsvg{position:absolute;left:0;top:0}
.mtick{position:absolute;left:4px;transform:translateY(-50%);font-size:10.5px;color:var(--faint);font-weight:600}
.endlbl{position:absolute;transform:translate(-50%,-50%);font-size:11px;font-weight:700;color:#5a86a8;white-space:nowrap}
.gdot{position:absolute;transform:translate(-50%,-50%);width:26px;height:26px;border-radius:50%;background:#fff;border:3px solid var(--faint);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:var(--faint);cursor:pointer;box-shadow:0 2px 8px rgba(20,50,80,.14);z-index:3;transition:width .18s,height .18s}
.gdot.launch{width:34px;height:34px;border-width:4px;box-shadow:0 6px 18px rgba(10,132,255,.4);z-index:4}
.gdot.edge{border-color:#28c76f !important;box-shadow:0 0 0 5px rgba(40,199,111,.28),0 6px 18px rgba(40,199,111,.45);z-index:5}
.gdot.dim{opacity:.4}
.glbl{position:absolute;left:306px;transform:translateY(-50%);width:296px}
.glbl.dim{opacity:.45}
.gnm{font-weight:650;font-size:14px;display:flex;align-items:center;gap:6px}.gnm .ic{font-size:12px}.gnm .rm{font-size:11px;color:var(--faint);font-weight:500;margin-left:auto}
.gval{font-size:12px;color:var(--muted);margin-top:2px;font-variant-numeric:tabular-nums}.gval b{color:var(--ink)}
.badge{display:inline-block;padding:1px 7px;border-radius:20px;color:#fff;font-size:10.5px;font-weight:700}
.tag{font-size:10px;font-weight:700;letter-spacing:.04em;color:#fff;padding:2px 6px;border-radius:6px}
.keys{display:flex;flex-wrap:wrap;gap:12px 18px;justify-content:center;margin:12px 0 2px;font-size:12.5px;color:var(--muted)}
.keys span{display:inline-flex;align-items:center;gap:6px}.keys i{width:12px;height:12px;border-radius:4px}
.controls{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 26px rgba(20,50,80,.06);padding:14px 18px 16px;margin-top:14px}
.modes{display:flex;gap:6px;background:#e9eef4;border-radius:13px;padding:4px;margin-bottom:12px}
.modes button{flex:1;border:0;background:transparent;border-radius:10px;padding:10px;font-size:13.5px;font-weight:650;color:var(--muted);cursor:pointer;font-family:inherit;transition:.16s}
.modes button.on{background:#fff;color:var(--ink);box-shadow:0 2px 8px rgba(20,50,80,.14)}
.ctitle{font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);font-weight:700;margin:11px 0 5px}
.controls .modes{margin-bottom:2px}#modeWrap{margin-bottom:2px}
.cintro{font-size:13px;color:var(--muted);margin:2px 0 4px}
.crafts{display:flex;gap:8px}
.crafts button{flex:1;border:1.5px solid var(--line);background:#fff;border-radius:14px;padding:11px 6px;cursor:pointer;font-family:inherit;display:flex;flex-direction:column;align-items:center;gap:2px;font-size:13px;font-weight:650;color:var(--muted);transition:.16s}
.crafts button span{font-size:21px;line-height:1.1}.crafts button small{font-size:10.5px;font-weight:500;color:var(--faint)}
.crafts button.on{border-color:var(--blue);background:#f2f8ff;color:var(--ink);box-shadow:0 3px 12px rgba(10,132,255,.16)}
.crafts button.on small{color:var(--blue)}
.modes.appr button{flex-direction:column;gap:1px;padding:9px 6px;line-height:1.25}
.modes.appr button small{display:block;font-size:10px;font-weight:500;color:var(--faint);text-transform:none;letter-spacing:0}
.modes.appr button.on small{color:var(--muted)}
.seg{display:flex;gap:5px;background:#eef2f7;border-radius:13px;padding:4px;overflow:auto}
.seg button{flex:1;border:0;background:transparent;border-radius:10px;padding:8px 5px;font-size:12px;font-weight:600;color:var(--muted);cursor:pointer;white-space:nowrap;transition:.16s;font-family:inherit}
.seg button.on{background:#fff;color:var(--ink);box-shadow:0 2px 8px rgba(20,50,80,.12)}.seg button.dis{opacity:.32;pointer-events:none}
.timerow{display:flex;align-items:baseline;justify-content:space-between;margin:15px 2px 4px}.timerow .t{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}.timerow .lab{font-size:13px;color:var(--muted)}
input[type=range]{-webkit-appearance:none;width:100%;height:6px;border-radius:6px;background:linear-gradient(90deg,#dfe7ef,#cfdae6);outline:none;margin:6px 0 4px}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:30px;height:30px;border-radius:50%;background:#fff;border:1px solid #d3dde7;box-shadow:0 4px 12px rgba(20,50,80,.25);cursor:pointer}
.ticks{display:flex;justify-content:space-between;font-size:11px;color:var(--faint);margin-top:2px}
.summary{margin-top:12px;font-size:14px;color:var(--muted);line-height:1.55}.summary b{color:var(--ink)}.summary .warn{color:#c0392b;font-weight:600}
.cal{padding:8px 16px 14px}
.wksyn{font-size:13.5px;color:var(--ink);background:#eef6ff;border:1px solid #dbeafe;border-radius:12px;padding:11px 14px;margin:2px 0 10px;font-weight:500}
.wkrow{display:flex;align-items:center;gap:13px;padding:12px 4px;border-top:1px solid var(--line);cursor:pointer}
.wksyn+.wkrow{border-top:0}
.wkrow.best{background:linear-gradient(90deg,rgba(255,247,224,.65),transparent);border-radius:12px;margin:0 -8px;padding-left:12px;padding-right:12px}
.wkg{flex:none;width:56px;text-align:center;font-size:10.5px;font-weight:800;letter-spacing:.02em;color:#fff;padding:5px 0;border-radius:8px}
.wkd{flex:none;width:52px}.wkd b{display:block;font-size:15px;font-weight:700;line-height:1.1}.wkd span{font-size:11.5px;color:var(--muted)}
.wkm{flex:1;min-width:0}.wkv{font-size:14.5px;font-weight:600;color:var(--ink)}
.wkstat{font-size:12.5px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.wkstat i{color:var(--faint);font-style:normal;margin:0 4px}
.calx{display:flex;padding:6px 0 8px}.cxs{width:132px;flex:none}.cxl{flex:1;display:flex;justify-content:space-between;font-size:11px;color:var(--faint)}
.crow{display:flex;align-items:center;gap:14px;padding:13px 0;border-top:1px solid var(--line);cursor:pointer}.crow:first-child{border-top:0}
.cd{width:118px;flex:none}.cd .dl{font-weight:700;font-size:16px;letter-spacing:-.2px}.cd .ds{font-size:12px;color:var(--muted);margin-top:1px}
.cmid{flex:1;min-width:0}.cbar{display:flex;height:16px;border-radius:6px;overflow:hidden;box-shadow:inset 0 0 0 1px rgba(20,50,80,.05)}.cbar span{display:block}
.chead{font-size:13.5px;color:var(--ink);margin-top:7px;font-weight:500}
.chev{flex:none;color:var(--faint);font-size:20px;transition:transform .2s}.crow.open .chev{transform:rotate(90deg)}
.csteps{display:none;padding:0 0 14px 72px}.csteps.open{display:block}
.step2{display:flex;gap:14px;padding:6px 0;border-top:1px solid var(--line)}
.st2{flex:none;width:96px;font-weight:700;color:#2c5f86;font-size:13px;font-variant-numeric:tabular-nums}
.step2 .sx2{font-size:13.5px;color:var(--muted);line-height:1.45}
/* collapsible sections */
.sec.fold{cursor:pointer;display:flex;align-items:center;gap:12px;margin:22px 4px 12px;padding-bottom:11px;
  border-bottom:1px solid var(--line);text-transform:none;letter-spacing:0}
.sec.fold .sect{flex:none;font-size:16px;font-weight:700;color:var(--ink)}
.sec.fold .ssum{flex:1;font-weight:400;color:var(--muted);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sec.fold.open .ssum{display:none}
.sec.fold .fchev{flex:none;width:24px;height:24px;border-radius:50%;background:#eef2f7;color:var(--muted);font-size:15px;
  display:flex;align-items:center;justify-content:center;transition:transform .2s,background .2s;line-height:1}
.sec.fold.open .fchev{transform:rotate(90deg);background:#e3f0ff;color:var(--blue)}
.secbody{display:none}.secbody.open{display:block}
/* date selector */
.dates{display:flex;gap:5px;background:#eef2f7;border-radius:13px;padding:4px;overflow:auto;margin-bottom:14px}
.dates button{flex:1;min-width:56px;border:0;background:transparent;border-radius:10px;padding:8px 6px;font-size:13px;font-weight:650;color:var(--muted);cursor:pointer;white-space:nowrap;font-family:inherit;transition:.16s;line-height:1.15}
.dates button.on{background:#fff;color:var(--ink);box-shadow:0 2px 8px rgba(20,50,80,.12)}
.dates button small{display:block;font-size:10px;color:var(--faint);font-weight:500;margin-top:1px}.dates button.on small{color:var(--muted)}
__HATCH_CSS__
__CHATTER_CSS__
__MOONCAL_CSS__
__FLYMATRIX_CSS__
.foot{text-align:center;color:var(--faint);font-size:11.5px;margin-top:26px;line-height:1.6}
.rivercard{overflow-x:auto}
.viewtog{display:flex;gap:5px;background:#eef2f7;border-radius:12px;padding:4px;margin-bottom:10px;width:fit-content}
.viewtog button{border:0;background:transparent;border-radius:9px;padding:7px 16px;font-size:13px;font-weight:650;color:var(--muted);cursor:pointer;font-family:inherit;transition:.16s}
.viewtog button.on{background:#fff;color:var(--ink);box-shadow:0 2px 8px rgba(20,50,80,.12)}
.mapcard{overflow-x:auto;padding:0}
#lmap{height:360px;width:100%;border-radius:16px;background:#dfe7ef}
.leaflet-container{border-radius:16px;font-family:inherit}.leaflet-popup-content{font:13px/1.4 -apple-system,sans-serif}
.pmk{position:relative;width:100%;height:100%}
.pmk .dot{position:absolute;inset:0;border-radius:50%;border:2.5px solid #fff;box-shadow:0 1px 6px rgba(0,0,0,.6);color:#fff;font-weight:800;display:flex;align-items:center;justify-content:center}
.pmk .ring{position:absolute;left:50%;top:50%;width:100%;height:100%;border-radius:50%;transform:translate(-50%,-50%);animation:pulsering 1.5s ease-out infinite;z-index:-1}
@keyframes pulsering{0%{transform:translate(-50%,-50%) scale(.55);opacity:.7}100%{transform:translate(-50%,-50%) scale(2.6);opacity:0}}
.maptip{font-size:11.5px;color:var(--faint);text-align:center;margin:7px 0 0}
.frontmk{position:relative;width:18px;height:18px}
.frontmk .core{position:absolute;inset:0;border-radius:50%;background:#eafcff;border:2px solid #06b6d4;box-shadow:0 0 9px 2px rgba(6,182,212,.85)}
.frontmk .fr{position:absolute;left:50%;top:50%;width:18px;height:18px;border-radius:50%;background:#22d3ee;transform:translate(-50%,-50%);animation:pulsering 1.1s ease-out infinite;z-index:-1}
.timebar .timerow{align-items:center}
.play{border:0;background:var(--blue);color:#fff;width:36px;height:36px;border-radius:50%;font-size:14px;cursor:pointer;margin:0 12px;flex:none;box-shadow:0 3px 10px rgba(10,132,255,.35)}
.mapcard .stage{margin:2px auto}
.timebar{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 4px 14px rgba(20,50,80,.05);padding:8px 16px 12px;margin-top:12px}
.timebar .timerow{margin:4px 2px 2px}
.summary{margin:12px 2px 0}.summary .frn{color:var(--blue);font-weight:600}
__LOG_CSS__
@media(max-width:680px){
 .app{padding:20px 12px 130px}h1{font-size:27px}
 .grid,.wxrow{grid-template-columns:1fr;display:grid;gap:12px}
 .wx .m{min-width:0;flex:1;padding:10px 8px;border-right:1px solid var(--line)}.wx .t{font-size:21px}.wx .d{font-size:11px}.wx .meta{min-width:100%;border-top:1px solid var(--line)}
 .crafts button{font-size:12px;padding:10px 4px}.crafts button span{font-size:19px}.crafts button small{font-size:9.5px}
 .wkg{width:50px;font-size:9.5px}.wkstat{font-size:11.5px}
 .nowstrip .asof{margin-left:0;width:100%}
 .cd{width:96px}.cxs{width:110px}.csteps{padding-left:110px}
 .modes button{font-size:12.5px}.seg button{font-size:11px}.dates button{font-size:12px}
}
</style></head><body><div class="app">
 __SWITCHER__
 <div class="eyebrow">Fly-fishing planner · DeKalb County, TN</div><h1>Caney Fork</h1><div class="cap" id="cap"></div>
 <div class="card nowstrip" id="nowstrip"></div>
 <div class="card arrival" id="arrival"></div>
 <div class="card best" id="best"></div>

 <div class="sec fold open" data-t="bWx"><span class="sect" id="wxSecLabel">Conditions</span><span class="ssum" id="sumWx"></span><span class="fchev">›</span></div>
 <div class="secbody open" id="bWx"><div class="wxverdict" id="wxverdict"></div><div class="wxrow"><div class="card wx" id="wx"></div><div class="card feed" id="feed"></div></div></div>

 <div class="sec fold" data-t="bGen"><span class="sect">Generation schedule</span><span class="ssum" id="sumGen"></span><span class="fchev">›</span></div>
 <div class="secbody" id="bGen"><div class="card gen" id="genc"></div></div>

 <div class="sec fold" data-t="bTips"><span class="sect">Guide's take</span><span class="ssum" id="sumTips"></span><span class="fchev">›</span></div>
 <div class="secbody" id="bTips"><div class="card tips" id="tips"></div></div>

 <div class="sec fold" data-t="bFb"><span class="sect">Fly box</span><span class="ssum" id="sumFb"></span><span class="fchev">›</span></div>
 <div class="secbody" id="bFb"><div class="card" id="flysel"></div></div>
 <div class="sec fold" data-t="bHatch"><span class="sect">Hatch calendar</span><span class="ssum" id="sumHatch"></span><span class="fchev">›</span></div>
 <div class="secbody" id="bHatch"><div class="card hatch" id="hatch"></div></div>
 <div class="sec fold" data-t="bMoon"><span class="sect">Moon &amp; feeding calendar</span><span class="ssum" id="sumMoon"></span><span class="fchev">›</span></div>
 <div class="secbody" id="bMoon"><div class="card mcal" id="mooncal"></div></div>
 <div id="chatterSec" style="display:none">
  <div class="sec fold" data-t="bChat"><span class="sect">River chatter</span><span class="ssum" id="sumChat"></span><span class="fchev">›</span></div>
  <div class="secbody" id="bChat"><div class="card chatter" id="chatter"></div></div>
 </div>

 <div class="sec fold open" data-t="bPlan"><span class="sect">Plan &amp; river</span><span class="ssum" id="sumPlan"></span><span class="fchev">›</span></div>
 <div class="secbody open" id="bPlan">
   <div class="dates" id="dates"></div>
   <div class="planwx" id="planwx"></div>
   <div class="viewtog"><button data-v="sat" class="on">🛰 Satellite</button><button data-v="diagram">📈 Diagram</button></div>
   <div class="card mapcard"><div id="lmap"></div><div class="stage" id="river" style="display:none"><svg id="rsvg" width="620" height="780"></svg></div></div>
   <div class="maptip" id="maptip">Pins sit on the OSM channel · pulsing pin = water arriving there now · tap to plan from it · drag to fine-tune its spot</div>
   <div class="keys"><span><i style="background:#28c76f"></i>wade (low)</span><span><i style="background:#0a84ff"></i>prime boat (1–4k cfs)</span><span><i style="background:#5e5ce6"></i>high &amp; fast</span></div>
   <div class="timebar">
     <div class="timerow"><div class="t" id="tread"></div><button id="playbtn" class="play">▶</button><div class="lab">drag, or press play to watch the water move</div></div>
     <input type="range" id="slider"><div class="ticks" id="ticks"></div>
   </div>
   <div class="safety" id="safety"></div>
   <div class="summary" id="summary"></div>
   <div class="controls">
     <div class="cintro">Tell me how you're fishing and I'll build the plan.</div>
     <div class="ctitle">1 · How are you fishing?</div>
     <div class="crafts" id="crafts">
       <button data-c="wade"><span>🥾</span>Wade<small>on foot</small></button>
       <button data-c="raft"><span>🛶</span>Raft / kayak<small>float &amp; row</small></button>
       <button data-c="power" class="on"><span>🚤</span>Powerboat<small>motor &amp; hold</small></button>
     </div>
     <div id="modeWrap"><div class="ctitle">2 · Your approach</div>
       <div class="modes appr"><button data-m="drift" class="on">Float a stretch<small>put in high, drift down</small></button><button data-m="up">Chase the rise<small>hold on the bump</small></button></div></div>
     <div class="ctitle" id="lblFrom">Put-in</div><div class="seg" id="segFrom"></div>
     <div class="ctitle" id="lblTo">Take-out</div><div class="seg" id="segTo"></div>
   </div>
   <div class="plan" style="margin-top:14px"><div class="h" id="planh"></div><div class="b" id="itin"></div></div>
 </div>

 <div class="sec fold open" data-t="bCal"><span class="sect">7-day outlook</span><span class="ssum" id="sumCal"></span><span class="fchev">›</span></div>
 <div class="secbody open" id="bCal"><div class="card cal" id="cal"></div></div>

 <div class="sec fold" data-t="bLog"><span class="sect">My log</span><span class="ssum" id="sumLog"></span><span class="fchev">›</span></div>
 <div class="secbody" id="bLog"><div class="card logc" id="log"></div></div>

 <div class="foot" id="foot"></div>
</div>
<script>
__POPUP_JS__
__HATCH_JS__
__CHATTER_JS__
__LOG_JS__
__MOONCAL_JS__
__FLYMATRIX_JS__
__GENSCHED_JS__
__ARRIVAL_JS__
const DATA=__DATA__,P=DATA.points,N=P.length,ICON={wade:'🥾',paddle:'🛶',ramp:'🚤'};
const COND={wade:{c:'#28c76f',t:'wadeable'},boat:{c:'#0a84ff',t:'prime boat'},high:{c:'#5e5ce6',t:'high & fast'}};
let mode='drift',fromIdx=0,toIdx=6,launchMin=DATA.launchDefault,dsel=DATA.planDefault,daybase=DATA.planDefault*1440,craft='power';
function interp(c,x){if(x<=c[0][0])return c[0][1];for(let i=1;i<c.length;i++){if(x<=c[i][0]){const a=c[i-1],b=c[i];return a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0]);}}const n=c.length,a=c[n-2],b=c[n-1];return b[1]+(b[1]-a[1])*(x-b[0])/(b[0]-a[0]);}
function depthAt(i,cfs){return P[i].d0+interp(DATA.riseCurve,cfs);}
// Wade threshold is MEASURED (USGS gaugings, see riverlib.WATER_MODEL) and arrives via
// DATA.wadeMax — the page must never carry its own copy of a calibrated number.
function condFor(i,cfs){const d=depthAt(i,cfs);return cfs>4500?'high':(cfs<DATA.wadeMax&&d<3.2)?'wade':'boat';}
// "fish the edge" scoring: prize RISING water in the sweet holdable band (peak ~2,200 cfs)
const IDEAL=2200;
// only the trout reach, and only water that is actually RISING (the leading edge), scored by nearness to ideal flow
function edgeScore(i,m){if(P[i].reach!=='trout')return 0;const f=flowAt(i,m),df=f-flowAt(i,m-60);if(df<=120||f<700||f>4800)return 0;return Math.max(0.05,1-Math.abs(f-IDEAL)/2200);}
function bestEdge(m){let bi=-1,bs=0.22;for(let i=0;i<N;i++){const s=edgeScore(i,m);if(s>bs){bs=s;bi=i;}}return bi;}
function driftSpeed(cfs){return 1.0+3.6*Math.pow(Math.min(cfs,11000)/11000,0.6);}
function flowAt(i,min){const a=P[i].flow,h=Math.max(0,Math.min((daybase+min)/60,a.length-1.001)),lo=Math.floor(h),fr=h-lo;return a[lo]*(1-fr)+a[lo+1]*fr;}
function timeStr(m){m=((Math.round(m/5)*5)%1440+1440)%1440;let h=Math.floor(m/60),mm=m%60,ap=h<12?'AM':'PM',hh=(h%12)||12;return hh+':'+String(mm).padStart(2,'0')+' '+ap;}
function waterArrival(i,fromMin){if(flowAt(i,fromMin)>=1000)return -1;for(let m=Math.ceil(fromMin/60)*60;m<=29*60;m+=60){if(flowAt(i,m)>=1000)return m;}return null;}
function driftPlan(){const arr=new Array(N).fill(null),fl=new Array(N).fill(null);arr[fromIdx]=launchMin;fl[fromIdx]=flowAt(fromIdx,launchMin);
 for(let j=fromIdx;j<N-1;j++){const f=flowAt(j,arr[j]),dist=P[j].rm-P[j+1].rm,dt=dist/driftSpeed(f)*60;arr[j+1]=arr[j]+dt;fl[j+1]=flowAt(j+1,arr[j+1]);}return{arr,fl};}
function ic(t){return t.map(x=>ICON[x]).join('');}

document.getElementById('cap').innerHTML=DATA.todayLabel+' &nbsp;·&nbsp; Center Hill tailwater &nbsp;·&nbsp; water '+DATA.clarity;
(function(){const n=DATA.now,g=n.gen?'#5e5ce6':'#28c76f';
 let chk='';if(n.stone!=null){const off=Math.abs(n.stone-n.model);chk=' <span class="mchk">gauge '+n.stone.toLocaleString()+' cfs · model '+n.model.toLocaleString()+(off<400?' ✓':' (±'+off.toLocaleString()+')')+(n.calib?' · auto-tuned '+(n.calib>0?'+':'')+n.calib+' cfs':'')+'</span>';}
 const stale=n.stale?' <span style="color:#c0392b;font-weight:600">⚠ cached schedule (USACE API down)</span>':'';
 const tr=n.trend==='rising'?' ↑ rising':n.trend==='falling'?' ↓ falling':'';
 document.getElementById('nowstrip').innerHTML='<span class="dotlg" style="background:'+g+'"></span><b>Right now</b> · Center Hill '+(n.gen?(n.units+'-unit generating'):'minimum flow')+' ~'+(n.cfs||'–').toLocaleString()+' cfs'+tr+' · Stonewall'+chk+' · water '+n.clarity+stale+' <span class="asof">as of '+n.asof+'</span>';})();
const GCOL={Prime:'#28c76f',Good:'#0a84ff',Fair:'#f2a832',Tough:'#94a3b1',Great:'#28c76f','—':'#94a3b1'};
(function(){const t=DATA.week[0],el=document.getElementById('best');
 const move=t.units?'Wade the flats early, then work the rise from the boat':'Sight-fish the flats — light tippet, dawn &amp; dusk';
 el.innerHTML='<div class="tg" style="background:'+GCOL[t.grade]+'">'+t.grade+'</div>'
   +'<div class="bmid"><div class="bt">Today, '+t.date+' — '+t.verdict+'</div>'
   +'<div class="bb">'+move+' · <b>prime window '+t.window+'</b></div></div><div class="go">plan →</div>';
 el.onclick=()=>{dsel=0;daybase=0;document.querySelectorAll('#dates button').forEach((x,j)=>x.classList.toggle('on',j===0));renderDay();render();document.getElementById('bPlan').scrollIntoView({behavior:'smooth'});};})();
function renderFeed(di){const s=DATA.solDays[di],el=document.getElementById('feed');if(!s){el.innerHTML='<div class="fh">Feeding times</div><div class="fx">unavailable</div>';return;}
 const stars=s.rating!=null?'★'.repeat(Math.max(1,Math.min(5,Math.round(s.rating))))+'☆'.repeat(5-Math.max(1,Math.min(5,Math.round(s.rating)))):'';
 let h='<div class="fh">Feeding times '+(stars?'<span class="stars">'+stars+'</span>':'')+'</div>';
 h+='<div class="fx"><b>Major</b> '+(s.major.map(w=>w[0]+'–'+w[1]).join(' · ')||'–')+'</div>';
 h+='<div class="fx"><b>Minor</b> '+(s.minor.map(w=>w[0]+'–'+w[1]).join(' · ')||'–')+'</div>';
 if(s.moon)h+='<div class="fx moon">🌙 '+s.moon+'</div>';if(s.approx)h+='<div class="fx" style="color:var(--faint);font-size:11px">computed from moon phase &amp; sun times</div>';el.innerHTML=h;}
function renderPlan(){const d=DATA.calendar[dsel];let h='';(d.steps||[]).forEach(s=>h+='<div class="step"><span class="st">'+s.t+'</span><span class="sx">'+s.x+'</span></div>');document.getElementById('itin').innerHTML=h;document.getElementById('planh').textContent='Timed plan · '+d.label+' '+d.date;}
function renderWx(di){const w=DATA.wxDays[di],el=document.getElementById('wx');document.getElementById('wxSecLabel').textContent='Conditions · '+DATA.calendar[di].label+' '+DATA.calendar[di].date;
 const v=DATA.wxv[di];document.getElementById('wxverdict').innerHTML=v?'<span class="vg" style="background:'+(GCOL[v.grade]||"#94a3b1")+'">'+v.grade+'</span> Fishing weather — <b>'+v.why+'</b>':'';
 if(!w){el.innerHTML='<div class="meta">weather unavailable</div>';return;}
 let h='';w.snaps.forEach(s=>h+='<div class="m"><div class="w">'+s.when+'</div><div class="t">'+s.ico+' '+s.temp+'°</div><div class="d">'+s.sky+' · '+s.wind+' mph'+(s.precip?' · '+s.precip+'%':'')+'</div></div>');
 h+='<div class="meta"><div>High '+(w.hi??'–')+'° · Low '+(w.lo??'–')+'°</div><div>Sun '+w.sunrise+'–'+w.sunset+'</div><div>Pressure '+w.pressure+(w.precipMax?' · rain '+w.precipMax+'%':'')+'</div></div>';el.innerHTML=h;}
function renderPlanWx(di){const w=DATA.wxDays[di],s=DATA.solDays[di],g=DATA.gen[di],el=document.getElementById('planwx');let p=[];
 if(w){const mid=(w.snaps||[]).find(x=>x.when==='Midday')||(w.snaps||[])[0];p.push((mid?mid.ico+' <b>'+mid.temp+'°</b>':'')+' · hi '+(w.hi??'–')+'/lo '+(w.lo??'–'));p.push('☀ '+w.sunrise+'–'+w.sunset);p.push('baro '+w.pressure);}
 if(s)p.push('🌙 '+s.moon+' · <b>'+(s.rating||'')+'/5</b>');
 p.push('⚡ '+(g&&g.windows.length?g.windows.map(x=>x.units+'U '+x.span).join(', '):'min flow all day'));
 el.innerHTML=p.filter(Boolean).join(' &nbsp;·&nbsp; ');}
function renderGen(){buildGenSchedule('genc',DATA.gen,DATA.genHint,DATA.genLegend,DATA.genOpts);}
buildArrival('arrival',DATA.arrival);
function renderDay(){renderPlan();renderWx(dsel);renderFeed(dsel);renderPlanWx(dsel);}
(function(){let h='';DATA.tips.forEach(t=>h+='<div class="tip"><div class="i">'+t[0]+'</div><div class="x">'+t[1]+'</div></div>');document.getElementById('tips').innerHTML=h;})();
buildFlyMatrix('flysel',DATA.flysel);
(function(){const gcol={Prime:'#28c76f',Good:'#0a84ff',Fair:'#f2a832',Tough:'#94a3b1'};
 let h='<div class="wksyn">🎯 '+DATA.weekSynth+'</div>';
 DATA.week.forEach((d,di)=>{
  const st=((DATA.calendar[di]||{}).steps||[]).map(s=>'<div class="step2"><span class="st2">'+s.t+'</span><span class="sx2">'+s.x+'</span></div>').join('');
  const best=(DATA.best&&di===DATA.best.i);
  h+='<div class="wkrow'+(best?' best':'')+'" data-di="'+di+'">'
    +'<div class="wkg" style="background:'+gcol[d.grade]+'">'+d.grade+'</div>'
    +'<div class="wkd"><b>'+d.label+(best?' ⭐':'')+'</b><span>'+d.date+'</span></div>'
    +'<div class="wkm"><div class="wkv">'+d.verdict+'</div>'
    +'<div class="wkstat">'+d.ico+' '+(d.hi!=null?d.hi+'°':'')+' <i>·</i> ⚡'+(d.units?d.units+'U':'off')+' <i>·</i> 🌙'+d.moon+'/5 <i>·</i> '+d.window+'</div></div>'
    +'<div class="chev">›</div></div><div class="csteps" id="cs'+di+'">'+st+'</div>';});
 document.getElementById('cal').innerHTML=h;
 document.querySelectorAll('#cal .wkrow').forEach(r=>r.onclick=()=>{const p=document.getElementById('cs'+r.dataset.di);r.classList.toggle('open',p.classList.toggle('open'));});})();
document.getElementById('foot').textContent='UH routing off the Center Hill release forecast (R²=0.89), anchored on a longtime guide’s real miles-from-dam with a backtested ~2.5 mph leading edge (Happy Hollow ~2½h · Betty’s ~3½h · Stonewall ~6h from release). Depth from measured Stonewall stage-rise; drift speed ≈ flow (1–4.6 mph); boatable ≈ 1,000–4,000 cfs. Trout reach (dam→Stonewall) calibrated; lower ramps are backwater approximations. Sources: USACE CWMS · USGS · Open-Meteo.';

// river + segs
const stage=document.getElementById('river'),svg=document.getElementById('rsvg');
const RH=760,padT=40,padB=34,cx=145,amp=44;
const rms=P.map(p=>p.rm),rmMax=Math.max(...rms),rmMin=Math.min(...rms);
const ry=rm=>padT+(rmMax-rm)/(rmMax-rmMin)*(RH-padT-padB);
const mx=y=>cx+amp*Math.sin((y-padT)/66);
let dpath='M'+mx(padT).toFixed(1)+','+padT;for(let y=padT+4;y<=RH-padB;y+=5)dpath+=' L'+mx(y).toFixed(1)+','+y;
svg.innerHTML='<defs><linearGradient id="rg" x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color="#8fd0f2"/><stop offset=1 stop-color="#3f8fc4"/></linearGradient></defs>'
 +'<path d="'+dpath+'" fill=none stroke="url(#rg)" stroke-width=20 stroke-linecap=round opacity=".9"/>'
 +'<path d="'+dpath+'" fill=none stroke="#eafaff" stroke-width=2.5 stroke-linecap=round opacity=".55" stroke-dasharray="2 15"><animate attributeName="stroke-dashoffset" from=0 to="-200" dur=6s repeatCount=indefinite/></path>'
 +'<g id="lead" stroke="#c7d5e2" stroke-width=1.3></g>';
const lead=svg.querySelector('#lead');
for(let mile=0;mile<=Math.ceil(rmMax);mile+=5){if(mile<rmMin-1)continue;const t=document.createElement('div');t.className='mtick';t.style.top=ry(mile)+'px';t.textContent='rm '+mile;stage.appendChild(t);}
const dtop=document.createElement('div');dtop.className='endlbl';dtop.style.top=(padT-24)+'px';dtop.style.left=mx(padT)+'px';dtop.textContent='▲ Center Hill Dam';stage.appendChild(dtop);
const dbot=document.createElement('div');dbot.className='endlbl';dbot.style.top=(RH-padB+16)+'px';dbot.style.left=mx(RH-padB)+'px';dbot.textContent='Cumberland R. ▼';stage.appendChild(dbot);
const dyT=P.map(p=>ry(p.rm)),order=P.map((_,i)=>i).sort((a,b)=>dyT[a]-dyT[b]);
const dyN=[],lyN=[];{let l=-1e9;order.forEach(i=>{dyN[i]=Math.max(dyT[i],l+16);l=dyN[i];});}
{let l=-1e9;order.forEach(i=>{lyN[i]=Math.max(dyN[i],l+44);l=lyN[i];});}
P.forEach((p,i)=>{const x=mx(dyN[i]);
 const dot=document.createElement('div');dot.className='gdot';dot.id='gd'+i;dot.style.left=x+'px';dot.style.top=dyN[i]+'px';dot.textContent=i+1;dot.onclick=()=>{fromIdx=i;fixTo();render();};stage.appendChild(dot);
 const lbl=document.createElement('div');lbl.className='glbl';lbl.id='gl'+i;lbl.style.top=lyN[i]+'px';stage.appendChild(lbl);
 const ln=document.createElementNS('http://www.w3.org/2000/svg','line');ln.setAttribute('x1',x);ln.setAttribute('y1',dyN[i]);ln.setAttribute('x2',298);ln.setAttribute('y2',lyN[i]);lead.appendChild(ln);});
function mkseg(id,cb){const seg=document.getElementById(id);P.forEach((p,i)=>{const b=document.createElement('button');b.textContent=p.name;b.id=id+i;b.onclick=()=>cb(i);seg.appendChild(b);});}
mkseg('segFrom',i=>{fromIdx=i;fixTo();render();});
mkseg('segTo',i=>{toIdx=i;render();});
const slider=document.getElementById('slider');slider.min=DATA.sliderMin;slider.max=DATA.sliderMax;slider.step=DATA.sliderStep;slider.value=launchMin;
slider.oninput=()=>{launchMin=+slider.value;render();};
let playT=null;const playbtn=document.getElementById('playbtn');
playbtn.onclick=()=>{ if(playT){clearInterval(playT);playT=null;playbtn.textContent='▶';return;}
 playbtn.textContent='⏸';
 playT=setInterval(()=>{launchMin+=12; if(launchMin>DATA.sliderMax)launchMin=DATA.sliderMin; slider.value=launchMin; render(); },260); };
const ticks=document.getElementById('ticks');for(let mm=DATA.sliderMin;mm<=DATA.sliderMax;mm+=180){const s=document.createElement('span');s.textContent=timeStr(mm).replace(':00','');ticks.appendChild(s);}
document.querySelectorAll('#modeWrap .modes button').forEach(b=>b.onclick=()=>{mode=b.dataset.m;
 if(mode==='drift'){fromIdx=0;toIdx=6;}else{fromIdx=CRAFT[craft].up?6:0;}
 document.querySelectorAll('#modeWrap .modes button').forEach(x=>x.classList.toggle('on',x===b));
 updateControls();render();});
function fixTo(){if(mode==='drift'&&toIdx<=fromIdx)toIdx=Math.min(N-1,fromIdx+1);}

function render(){document.getElementById('tread').textContent=timeStr(launchMin);
 P.forEach((p,i)=>{const bf=document.getElementById('segFrom'+i),bt=document.getElementById('segTo'+i);
  bf.classList.toggle('on',i===fromIdx);bt.classList.toggle('on',i===toIdx);
  bt.classList.toggle('dis', mode==='drift'? i<=fromIdx : i>=fromIdx);});
 const head=i=>'<div class="gnm">'+P[i].name+' <span class="ic">'+ic(P[i].types)+'</span><span class="rm">rm '+P[i].rm+'</span></div>';
 let s='';
 if(craft==='wade'){
  P.forEach((p,i)=>{const dot=document.getElementById('gd'+i),lbl=document.getElementById('gl'+i);
   const f=flowAt(i,launchMin),dep=depthAt(i,f),k=condFor(i,f),wade=(k==='wade'&&P[i].reach==='trout');
   dot.className='gdot'+(wade?' edge':' dim')+'';lbl.className='glbl'+(wade?'':' dim');
   const col=wade?'#28c76f':COND[k].c;dot.style.borderColor=col;dot.style.color=col;
   const tag=wade?' <span class="tag" style="background:#28c76f">🥾 WADE</span>':'';
   const note=wade?('<b>~'+dep.toFixed(1)+' ft</b> · '+Math.round(f).toLocaleString()+' cfs'):(Math.round(f).toLocaleString()+' cfs · ~'+dep.toFixed(1)+' ft <span class="badge" style="background:'+COND[k].c+'">'+COND[k].t+'</span>');
   lbl.innerHTML=head(i)+'<div class="gval">'+tag+' '+note+'</div>';});
  const wl=[];for(let i=0;i<N;i++){if(P[i].reach==='trout'&&condFor(i,flowAt(i,launchMin))==='wade')wl.push(i);}
  if(wl.length)s='🥾 At <b>'+timeStr(launchMin)+'</b> these flats are <b>wadeable</b>: '+wl.map(i=>P[i].name).join(', ')+'. Start high at <b>'+P[wl[0]].name+'</b> and work down — the upper bars blow out first when they cut water on. Check the safety line before you step in.';
  else s='🥾 <span class="warn">No wadeable water at <b>'+timeStr(launchMin)+'</b> — the river is up. Wait for it to drop, or fish from the boat.</span>';
 } else if(mode==='drift'){
  const dp=driftPlan();
  P.forEach((p,i)=>{const dot=document.getElementById('gd'+i),lbl=document.getElementById('gl'+i),active=(i>=fromIdx&&i<=toIdx);
   dot.className='gdot'+(active?'':' dim')+(i===fromIdx?' launch':'');lbl.className='glbl'+(active?'':' dim');
   if(!active){dot.style.borderColor='var(--faint)';dot.style.color='var(--faint)';lbl.innerHTML=head(i);return;}
   const cfs=dp.fl[i],dep=depthAt(i,cfs),k=condFor(i,cfs);dot.style.borderColor=COND[k].c;dot.style.color=COND[k].c;
   let tag='';if(i===fromIdx)tag=' <span class="tag" style="background:#0a84ff">PUT-IN</span>';else if(i===toIdx)tag=' <span class="tag" style="background:#16a34a">TAKE-OUT</span>';
   const extra=(i===fromIdx?'launch <b>'+timeStr(launchMin)+'</b>':'arrive <b>'+timeStr(dp.arr[i])+'</b>');
   lbl.innerHTML=head(i)+'<div class="gval">'+extra+tag+' · '+Math.round(cfs).toLocaleString()+' cfs · ~'+dep.toFixed(1)+' ft <span class="badge" style="background:'+COND[k].c+'">'+COND[k].t+'</span></div>';});
  const miles=(P[fromIdx].rm-P[toIdx].rm).toFixed(1),dur=Math.round(dp.arr[toIdx]-launchMin),d0=depthAt(fromIdx,dp.fl[fromIdx]);
  s='⬇ Put in at <b>'+P[fromIdx].name+'</b> <b>'+timeStr(launchMin)+'</b> ('+Math.round(dp.fl[fromIdx]).toLocaleString()+' cfs, ~'+d0.toFixed(1)+' ft). Float <b>'+miles+' mi</b> to <b>'+P[toIdx].name+'</b> ≈ <b>'+(dur>=60?Math.floor(dur/60)+'h '+(dur%60)+'m':dur+'m')+'</b>, take out <b>'+timeStr(dp.arr[toIdx])+'</b> ('+Math.round(dp.fl[toIdx]).toLocaleString()+' cfs). ';
  let w=null;for(let i=fromIdx+1;i<=toIdx;i++){if(condFor(i,dp.fl[i])==='high'&&condFor(fromIdx,dp.fl[fromIdx])!=='high'){w=i;break;}}
  s+=w!==null?'<span class="warn">⚠ The release catches you near '+P[w].name+' ~'+timeStr(dp.arr[w])+' — ride it down fishing the leading edge.</span>':'Water holds steady through the float.';
 } else {
  const bi=bestEdge(launchMin);
  P.forEach((p,i)=>{const dot=document.getElementById('gd'+i),lbl=document.getElementById('gl'+i);
   const f=flowAt(i,launchMin),df=f-flowAt(i,launchMin-60),dep=depthAt(i,f),k=condFor(i,f),rising=df>120;
   const dim=(P[i].reach!=='trout')||(k==='high'&&i!==bi);
   dot.className='gdot'+(dim?' dim':'')+(i===fromIdx?' launch':'')+(i===bi?' edge':'');lbl.className='glbl'+(dim?' dim':'');
   const col=(i===bi)?'#28c76f':COND[k].c;dot.style.borderColor=col;dot.style.color=col;
   let tag='';if(i===bi)tag=' <span class="tag" style="background:#28c76f">◎ FISH THE EDGE</span>';else if(i===fromIdx)tag=' <span class="tag" style="background:#0a84ff">LAUNCH</span>';
   let note;if(i===bi)note='<b>leading edge · '+Math.round(f).toLocaleString()+' cfs, rising</b> — hold here in the sweet flow';
   else if(rising&&f<4800)note=Math.round(f).toLocaleString()+' cfs · coming up';
   else note=Math.round(f).toLocaleString()+' cfs · ~'+dep.toFixed(1)+' ft <span class="badge" style="background:'+COND[k].c+'">'+COND[k].t+'</span>';
   lbl.innerHTML=head(i)+'<div class="gval">'+tag+' '+note+'</div>';});
  // REACHABILITY. A target is only a plan if you can physically get to it: the boat has
  // to cover the distance in the time available, and the water in between has to float it.
  // Without this the planner sorted every rising point by time and picked the earliest,
  // which is always the one nearest the dam — so it would tell you to launch at Stonewall
  // and be at Long Branch, 15 miles upstream, through six stretches it had just labelled
  // wade water.
  const UP_MPH=6.0;      // 60/40 jet working upstream against current, conservative
  function reachable(i,byMin){
    if(i===fromIdx)return true;
    const up=(i<fromIdx);                                  // lower index = closer to the dam = upstream
    if(up&&!CRAFT[craft].up)return false;                  // drift craft do not go up
    const miles=Math.abs(P[i].mfd-P[fromIdx].mfd);
    const mins=byMin-launchMin;
    if(mins<=0)return false;
    // travel time: motoring up at UP_MPH, or drifting down at the reach's own drift speed
    const spd=up?UP_MPH:Math.max(1.0,driftSpeed(flowAt(i,byMin)));
    if(miles/spd*60>mins)return false;                     // cannot get there in time
    // and every access you must pass has to be floatable at the time you would pass it
    const lo=Math.min(i,fromIdx),hi=Math.max(i,fromIdx);
    for(let k=lo;k<=hi;k++){
      const t=launchMin+(Math.abs(P[k].mfd-P[fromIdx].mfd)/spd)*60;
      const tt=Math.min(t,byMin);
      if(condFor(k,flowAt(k,tt))==='wade')return false;   // too skinny to run a boat through
    }
    return true;
  }
  let seq=[];for(let i=0;i<N;i++){let t=null;for(let m=launchMin;m<=20*60;m+=30){if(edgeScore(i,m)>0.42&&reachable(i,m)){t=m;break;}}if(t!==null)seq.push([t,i]);}
  seq.sort((a,b)=>a[0]-b[0]);
  const lc=flowAt(fromIdx,launchMin),C=CRAFT[craft];
  s='⬆ '+(C.up?'Launch low at ':'Put in up top at ')+'<b>'+P[fromIdx].name+'</b> <b>'+timeStr(launchMin)+'</b> ('+Math.round(lc).toLocaleString()+' cfs). ';
  if(bi>=0){s+='🎯 '+(C.up?'Motor up and work':'Drift down onto')+' the <b>rising edge at '+P[bi].name+'</b> (~'+Math.round(flowAt(bi,launchMin)).toLocaleString()+' cfs) — '+C.hold+' in the sweet '+C.lo.toLocaleString()+'–'+C.hi.toLocaleString()+' cfs. ';
   const rest=seq.filter(e=>e[1]>bi).slice(0,3);
   s+=rest.length?'Drift down with the front: '+rest.map(e=>'<b>'+P[e[1]].name+'</b> ~'+timeStr(e[0])).join(' → ')+'.':'Ride it out to the take-out as it builds.';
  } else {
   const nx=seq.find(e=>e[0]>launchMin);
   if(nx){const w=frontWindow(nx[1]);
    s+='Nothing rising yet — pre-fish the flats. <b>'+P[nx[1]].name+'</b> starts moving <b>'
      +(w?timeStr(w[0])+'\u2013'+timeStr(w[1]):'~'+timeStr(nx[0]))+'</b>'
      +(w?' (most likely '+timeStr(frontArrival(nx[1]))+')':'')+' — be set up before the early end.';}
   else if(P.some((p,i)=>flowAt(i,launchMin)<900))s+='Minimum flow, no bump coming — wade the flats (small midges, light tippet) or wait for a release.';
   else s+='Water is up hard everywhere — fish the drop with streamers, or wait for it to fall back into the sweet 1,500–3,000 cfs.';
  }
 }
 // Arrival is a BAND, not a moment. Measured over 144 releases (analysis/onset_lag.py):
 // the first rise at 15 mi has median 6 h but p25 3 h and p75 7 h. Printing a single
 // clock time claims a precision the river does not have, and it is why the same event
 // appeared twice on this page with different times.
 if(craft!=='wade'){const fp=frontArrival(fromIdx),ft=frontArrival(toIdx),parts=[];
   const bw=frontWindow(fromIdx);
   if(fp!=null)parts.push('<b>'+P[fromIdx].name+'</b> '+(bw?timeStr(bw[0])+'\u2013'+timeStr(bw[1]):'~'+timeStr(fp)));
   if(ft!=null&&toIdx!==fromIdx)parts.push('<b>'+P[toIdx].name+'</b> ~'+timeStr(ft));
   if(parts.length)s+=' <span class="frn">⚡ release reaches '+parts.join(' · ')+'</span>';}
 document.getElementById('summary').innerHTML=s;
 // wading safety (day- & time-aware, at the Betty's flats)
 (function(){const bi=P.findIndex(p=>p.name.indexOf('Betty')>=0),el=document.getElementById('safety');if(bi<0){el.textContent='';return;}
  let rise=null;for(let m=300;m<=1200;m+=30){if(condFor(bi,flowAt(bi,m))!=='wade'){rise=m;break;}}
  if(condFor(bi,flowAt(bi,launchMin))==='wade'){el.className='safety ok';
   el.innerHTML=(rise&&rise>launchMin)?'🟢 Flats wadeable until ~<b>'+timeStr(rise)+'</b> — be off the water before the release pushes through.':'🟢 Flats wadeable — low water, no release in the fishing window.';
  } else {el.className='safety warn';el.innerHTML='🔴 Water\'s up at the flats — <b>not a wading window</b>. Fish from the boat; never wade a rising tailwater.';}})();
 document.querySelectorAll('#modeWrap .modes button').forEach(x=>x.classList.toggle('on',x.dataset.m===mode));
 syncMap();}
function mkIcon(n,col,size,dim,rising){return L.divIcon({className:'',iconSize:[size,size],iconAnchor:[size/2,size/2],popupAnchor:[0,-size/2],html:
  '<div class="pmk" style="opacity:'+(dim?0.5:1)+'">'+(rising?'<span class="ring" style="background:'+col+'"></span>':'')+
  '<div class="dot" style="background:'+col+';font-size:'+(size>28?13.5:11.5)+'px">'+n+'</div></div>'});}
function syncMap(){if(!window._lmap)return;P.forEach((p,i)=>{const mk=LM[i];if(!mk)return;
  const dot=document.getElementById('gd'+i),col=getComputedStyle(dot).borderTopColor||'#94a3b1';
  const dim=dot.classList.contains('dim'),big=dot.classList.contains('launch')||dot.classList.contains('edge');
  const f=flowAt(i,launchMin),rising=(f-flowAt(i,launchMin-30))>60&&f<5200&&f>500;   // water actively arriving here
  mk.setIcon(mkIcon(i+1,col,big?38:28,dim,rising));
  const gv=document.getElementById('gl'+i).querySelector('.gval');
  mk.setPopupContent('<b>'+p.name+'</b>'+(gv?'<br>'+gv.innerHTML:''));});
  const map=window._lmap,fi=frontInfo(launchMin);
  if(window._front){
    if(fi){const frac=(26.6-fi.rm)/26.6,c=unitCol(fi.flow);
      window._front.setLatLng(window._polyAt(frac)).setIcon(frontIcon(c));if(!map.hasLayer(window._front))window._front.addTo(map);
      window._risen.setLatLngs(window._polySub(frac)).setStyle({color:c});if(!map.hasLayer(window._risen))window._risen.addTo(map);
    } else {if(map.hasLayer(window._front))map.removeLayer(window._front);if(map.hasLayer(window._risen))map.removeLayer(window._risen);}
  }}
function frontInfo(t){   // {rm, flow} of the leading edge — backtested ~2.5-mph rule: mfd = mph·(t − release start)
  const g=DATA.gen[dsel]; if(!g||g.relStart==null)return null;
  const mfd=DATA.mph*(t-g.relStart)/60;                // miles from dam the leading edge has traveled
  if(mfd<=0.2||mfd>P[N-1].mfd+1)return null;            // not yet started, or already past the mouth
  if(mfd>=P[N-1].mfd)return {rm:P[N-1].rm,flow:flowAt(N-1,t)};
  for(let i=0;i<N-1;i++){if(P[i].mfd<=mfd&&mfd<=P[i+1].mfd){
    const fr=(mfd-P[i].mfd)/(P[i+1].mfd-P[i].mfd+1e-6),rm=P[i].rm+fr*(P[i+1].rm-P[i].rm);
    return {rm:rm,flow:flowAt(i,t)};}}
  return null;}
function unitCol(f){return f>9000?'#5e5ce6':f>5200?'#4f5bd5':f>1800?'#0a84ff':'#22d3ee';}   // colour by the water it's carrying
function frontIcon(col){return L.divIcon({className:'',iconSize:[18,18],iconAnchor:[9,9],html:'<div class="frontmk"><span class="fr" style="background:'+col+'"></span><span class="core" style="border-color:'+col+';box-shadow:0 0 10px 3px '+col+'"></span></div>'});}
// Arrival = the MEASURED first-rise rule (mfd / 2.5 mph), the same model the generation
// schedule and the arrival strip use. Previously this scanned for a 1,000 cfs crossing of
// the routed hydrograph, an arbitrary threshold that fired hours before the strip said the
// water arrived — two clocks on one page for the same release.
function frontArrival(i){const g=DATA.gen[dsel];if(!g||g.relStart==null)return null;
 const st=DATA.arrivalStages.first;const m=g.relStart+(P[i].mfd/st.mph)*60;return (m>=0&&m<=1439)?m:null;}
function frontWindow(i){const g=DATA.gen[dsel];if(!g||g.relStart==null)return null;
 const st=DATA.arrivalStages.first;
 return [g.relStart+(P[i].mfd/st.early)*60, g.relStart+(P[i].mfd/st.late)*60];}
// satellite map (Esri imagery) — access points on the real channel; clicking a pin sets the put-in
let LM=[];
if(typeof L!=='undefined'){
  let PINS={}; try{PINS=JSON.parse(localStorage.getItem('caneyPins')||'{}');}catch(e){}
  P.forEach(p=>{if(PINS[p.name]){p.lat=PINS[p.name][0];p.lon=PINS[p.name][1];}});   // apply saved corrections
  const map=L.map('lmap',{scrollWheelZoom:false});window._lmap=map;
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:18,attribution:'Esri, Maxar, USGS'}).addTo(map);
  L.polyline(DATA.riverPoly,{color:'#8fd6ff',weight:3,opacity:.85}).addTo(map);
  P.forEach((p,i)=>{const mk=L.marker([p.lat,p.lon],{icon:mkIcon(i+1,'#94a3b1',28,false,false),draggable:true,autoPan:true}).addTo(map).bindPopup(accessPopup(p));
    wireHover(mk);
    mk.on('click',()=>{if(craft!=='wade'){fromIdx=i;fixTo();}render();});
    mk.on('dragend',e=>{const ll=e.target.getLatLng();p.lat=ll.lat;p.lon=ll.lng;PINS[p.name]=[+ll.lat.toFixed(5),+ll.lng.toFixed(5)];try{localStorage.setItem('caneyPins',JSON.stringify(PINS));}catch(e){}});
    LM[i]=mk;});
  map.fitBounds(DATA.riverPoly,{padding:[26,26]});
  // leading-edge "front" marker that glides along the channel by river-mile
  const POLY=DATA.riverPoly,PCUM=[0];
  for(let i=1;i<POLY.length;i++){const dy=POLY[i][0]-POLY[i-1][0],dx=(POLY[i][1]-POLY[i-1][1])*Math.cos(POLY[i][0]*Math.PI/180);PCUM.push(PCUM[i-1]+Math.hypot(dx,dy));}
  const PTOT=PCUM[PCUM.length-1];
  window._polyAt=function(fr){const t=Math.max(0,Math.min(1,fr))*PTOT;for(let i=1;i<POLY.length;i++){if(PCUM[i]>=t){const r=(t-PCUM[i-1])/(PCUM[i]-PCUM[i-1]+1e-9);return [POLY[i-1][0]+r*(POLY[i][0]-POLY[i-1][0]),POLY[i-1][1]+r*(POLY[i][1]-POLY[i-1][1])];}}return POLY[POLY.length-1];};
  window._polySub=function(fr){const tt=Math.max(0,Math.min(1,fr))*PTOT,out=[POLY[0]];for(let i=1;i<POLY.length;i++){if(PCUM[i]<tt)out.push(POLY[i]);else{const r=(tt-PCUM[i-1])/(PCUM[i]-PCUM[i-1]+1e-9);out.push([POLY[i-1][0]+r*(POLY[i][0]-POLY[i-1][0]),POLY[i-1][1]+r*(POLY[i][1]-POLY[i-1][1])]);break;}}return out;};
  window._risen=L.polyline([],{color:'#0a84ff',weight:7,opacity:.5,lineCap:'round'});   // "already up" wet reach behind the front
  window._front=L.marker([P[0].lat,P[0].lon],{icon:frontIcon('#22d3ee'),interactive:false,zIndexOffset:1000});
}
document.querySelectorAll('.viewtog button').forEach(b=>b.onclick=()=>{const sat=b.dataset.v==='sat';
  document.querySelectorAll('.viewtog button').forEach(x=>x.classList.toggle('on',x===b));
  document.getElementById('lmap').style.display=sat?'':'none';
  document.getElementById('river').style.display=sat?'none':'';
  if(sat&&window._lmap)setTimeout(()=>{window._lmap.invalidateSize();},60);
  render();});
// date selector — drives the timed plan + the river planner
(function(){const el=document.getElementById('dates');DATA.calendar.forEach((d,i)=>{const b=document.createElement('button');b.innerHTML=d.label+'<small>'+d.date+'</small>';b.id='dt'+i;if(i===dsel)b.className='on';
 b.onclick=()=>{dsel=i;daybase=i*1440;document.querySelectorAll('#dates button').forEach((x,j)=>x.classList.toggle('on',j===i));renderDay();render();};el.appendChild(b);});})();
// craft selector — reconfigures the planner for how you're on the water
const CRAFT={wade:{},raft:{hold:'row to hold with the oars',lo:1000,hi:3000,up:false,verb:'put in up top and drift down onto'},power:{hold:'hold with the trolling motor / oars',lo:1000,hi:4000,up:true,verb:'launch low and motor up to'}};
function updateControls(){const isWade=craft==='wade';
 document.getElementById('modeWrap').style.display=isWade?'none':'';
 document.getElementById('lblFrom').style.display=isWade?'none':'';document.getElementById('segFrom').style.display=isWade?'none':'';
 const showTo=!isWade&&mode==='drift';document.getElementById('lblTo').style.display=showTo?'':'none';document.getElementById('segTo').style.display=showTo?'':'none';
 document.getElementById('lblFrom').textContent=(isWade?'':'3 · ')+(mode==='drift'?'Put in at':(craft==='power'?'Launch at (low)':'Put in up top at'));}
document.querySelectorAll('#crafts button').forEach(b=>b.onclick=()=>{craft=b.dataset.c;
 document.querySelectorAll('#crafts button').forEach(x=>x.classList.toggle('on',x===b));
 if(craft!=='wade'&&mode==='up')fromIdx=CRAFT[craft].up?6:0;
 updateControls();render();});
// collapsible sections
document.querySelectorAll('.sec.fold').forEach(sec=>{const body=document.getElementById(sec.dataset.t);sec.onclick=()=>{const o=sec.classList.toggle('open');body.classList.toggle('open',o);};});
// section summaries (shown when collapsed)
(function(){const w=DATA.weather,S=DATA.solunar;
 document.getElementById('sumWx').textContent=[w?((w.hi??'')+'°/'+(w.lo??'')+'° · '+w.pressure):'',S?(S.moon.split(' · ')[0]+' '+(S.rating||'')+'/5'):''].filter(Boolean).join(' · ');
 (function(){const g=DATA.gen[0];let s=g&&g.windows.length?'today '+g.peak+'U '+g.span:'today min flow';if(g&&g.arr)s+=' · Stonewall ~'+g.arr[2][1];document.getElementById('sumGen').textContent=s;})();
 document.getElementById('sumTips').textContent=DATA.tips.length+' notes';
 document.getElementById('sumFb').textContent=DATA.flysel.now.fly;
 renderHatch('hatch',DATA.hatch,DATA.month);
 (function(){var mi=(DATA.month||1)-1,on=(DATA.hatch.rows||[]).filter(r=>(r.m[mi]||0)>=2).map(r=>r.name);
  document.getElementById('sumHatch').textContent=(on.length?on.slice(0,3).join(', '):'year-round staples');})();
 renderChatter('chatter',DATA.chatter,'chatterSec');
 (function(){var d=DATA.chatter;if(d&&d.posts&&d.posts.length){var n=d.posts.filter(p=>p.new).length;
  document.getElementById('sumChat').textContent=d.posts.length+' recent'+(n?' · '+n+' new':'');}})();
 document.getElementById('sumPlan').textContent='pick a day · craft · drift or work the rise';
 document.getElementById('sumCal').textContent=DATA.calendar[0].label+'–'+DATA.calendar[DATA.calendar.length-1].label;})();
// --- trip log (shared riverlib component; keeps the legacy caneyLog key) ---
// R4: hand the log a snapshot fn so each entry records what the TOOL predicted, not just
// what happened. Prediction + outcome together is what makes a wrong call falsifiable, and
// it is the evidence that decides whether the routing constants need another backtest.
buildLog('log','caneyLog',P.map(p=>p.name),'sumLog',null,function(spotName){
  const A=DATA.arrival; if(!A||!A.validated||!window.__arrivalPick) return null;
  const spot=(A.spots||[]).find(s=>s.name===spotName); if(!spot) return null;
  const r=window.__arrivalPick(A.rel, spot.mfd, A.mph, Date.now());
  if(!r || r.state==='none') return null;
  return {spot:spot.name, mfd:spot.mfd, mph:A.mph, state:r.state,
          arrival:Math.round(r.arrival), win:r.win,
          dataAgeMin: window.__builtEpoch ? Math.round((Date.now()/1000-window.__builtEpoch)/60) : null};
});
buildMoonCal('mooncal',36.10,-85.83);
document.getElementById('sumMoon').textContent='monthly feeding view';
renderGen();renderDay();updateControls();render();
</script></body></html>"""
html=riverlib.render(TEMPLATE,"caney").replace("__DATA__",json.dumps(DATA))
open(os.path.join(OUT,"caney.html"),"w").write(html)
# ---- HQ status card ----
if not NOW["gen"]:
    _cg,_ccond,_ccol,_cbase="Prime","Wadeable — water off","#28c76f",2.8
elif NOW["units"]<=1:
    _cg,_ccond,_ccol,_cbase="Good","Generating 1 unit — boat & edge","#0a84ff",2.2
else:
    _cg,_ccond,_ccol,_cbase="Fair","Generating %d units — high & fast"%NOW["units"],"#f2a832",1.4

# ---- HQ day state: wade or boat, clarity, level, and the day's release shape ----
# Caney is the one river where wade-vs-boat is a real decision rather than a formality:
# at minimum flow you sight-fish the flats, and when Center Hill generates the flats go
# away. So the vessel read is driven by whether a release reaches the daylight hours.
def _caney_day(off):
    d0, _ = riverlib.day_bounds(CT, off)
    cv = riverlib.hourly_curve(dam_at, d0)
    day = [(h, cv[h]) for h in range(6, 21)] if cv else []
    on = [h for h, v in day if v and v >= 800]        # 800 cfs = generation, same threshold as GW
    def _ap(h): return "%d%s" % (h % 12 or 12, "am" if h < 12 else "pm")
    if not day:
        return riverlib.day_state(headline="No release forecast")
    if not on:
        vk, vw = "wade", "minimum flow all day — the flats are fishable"
        head = "Minimum flow — wade it"
        wins = [{"from": _ap(6), "to": _ap(20), "kind": "wade"}]
    elif len(on) >= 13:
        vk, vw = "boat", "generating through the day — no wadeable window"
        head = "Generating %s–%s — boat" % (_ap(on[0]), _ap(on[-1] + 1))
        wins = [{"from": _ap(on[0]), "to": _ap(on[-1] + 1), "kind": "boat"}]
    else:
        vk, vw = "both", "wade early, then be off the flats before the bump"
        head = "Wade until %s, then it comes up" % _ap(on[0])
        wins = [{"from": _ap(6), "to": _ap(on[0]), "kind": "wade"},
                {"from": _ap(on[0]), "to": _ap(on[-1] + 1), "kind": "boat"}]
    peak = max((v for _, v in day if v is not None), default=0)
    lk, ld = (("low", "minimum flow · %s cfs" % format(round(min(v for _, v in day if v is not None)), ","))
              if not on else
              ("prime", "%s cfs peak" % format(round(peak), ",")) if peak < 4500 else
              ("high", "%s cfs peak" % format(round(peak), ",")) if peak < 9000 else
              ("blown", "%s cfs peak" % format(round(peak), ",")))
    # clar_word is the rain-driven read computed above; map it onto the board's vocabulary
    ck = {"clear": "clear", "some color": "stained", "stained": "colored"}.get(clar_word, "unknown")
    return riverlib.day_state(
        vessel=vk, vessel_why=vw,
        clarity=ck, clarity_why="from rain in the forecast; this is a bottom-release tailwater so it clears fast",
        level=lk, level_detail=ld,
        curve=cv, curve_unit="cfs", curve_label="Center Hill release", curve_src="forecast",
        windows=wins, headline=head)
DAYS = {"today": _caney_day(0), "tomorrow": _caney_day(1)}

riverlib.emit_status("caney",
    {"grade":_cg,"cond":_ccond,"col":_ccol,
     "note":("sight-fish the minimum-flow flats" if not NOW["gen"] else "ride the rise downstream from the boat"),
     "detail":(("%s cfs"%format(NOW["cfs"],",")) if NOW["cfs"] else "water off"),"asof":NOW["asof"]},
    wx, _cbase, CT, ["Trout"], "Trout tailwater", "~70 min · east of Nashville", days=DAYS)
print("wrote",os.path.join(OUT,"caney.html"),"| tomorrow:",DATA["dateLabel"])
print("dam:",dam_cap,"| clarity:",clar_word,"| tips:",len(tips),"| flies now:",len(flybox["now"]),"season:",flybox["season"])
