#!/usr/bin/env python3
"""
Cumberland River (KY) — Wolf Creek Dam trophy-trout tailwater, ~34 mi to Burkesville.
Generation-driven like the Caney: the Wolf Creek release forecast (USACE CWMS) drives
wade windows (wadeable at the dam when the water's off, blown when they generate) and the
trophy-brown streamer game on the rise. HONEST NOTE: the downstream routing on this big,
slow river calibrates weakly (Wolf Creek->Burkesville r=0.30), so downstream timing is
approximate; the release SCHEDULE and the at-dam wade windows are the reliable parts.
Sources: USACE CWMS (Wolf Creek), USGS 03414100 (Burkesville), Open-Meteo, OSM.
"""
import json,urllib.request,urllib.parse,datetime,math,os,sys
from zoneinfo import ZoneInfo
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import riverlib
CT=ZoneInfo("America/Chicago"); UA={"User-Agent":"cumb/1.0"}
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"out"); os.makedirs(OUT,exist_ok=True)
def get(u,h=None):
    # riverlib.get retries transient TLS/DNS/5xx failures; a single flaky fetch used to
    # build this page with missing data instead of failing (see riverlib.get docstring).
    return riverlib.get(u,{**UA,**(h or {})},timeout=90)
def hk(e): return int(e//3600)*3600
now=datetime.datetime.now(datetime.timezone.utc); now_ct=now.astimezone(CT)
GLAT,GLON=36.87,-85.15
begin=(now-datetime.timedelta(hours=36)).strftime("%Y-%m-%dT%H:00:00Z"); end=(now+datetime.timedelta(days=6)).strftime("%Y-%m-%dT%H:00:00Z")
def cwms(name):
    u=("https://cwms-data.usace.army.mil/cwms-data/timeseries?office=LRN"
       f"&name={urllib.parse.quote(name)}&begin={begin}&end={end}&unit=cfs&page-size=500000")
    return {hk(t/1000)-3600:v for t,v,q in get(u,{"Accept":"application/json;version=2"})["values"] if v is not None}  # -1h period-ending
rel={}
try: rel.update(cwms("WLCK2-WOLF_CREEK.Flow.Ave.1Hour.1Hour.man-rev"))
except Exception as e: print("actual warn:",e)
try:
    for k,v in cwms("Wolf Creek Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast").items(): rel.setdefault(k,v)
except Exception as e: print("forecast warn:",e)
def rel_at(k):
    if k in rel: return rel[k]
    lo=max((x for x in rel if x<=k),default=None); return rel[lo] if lo is not None else None
# Burkesville gauge (current)
bk=None
try:
    pts=get("https://waterservices.usgs.gov/nwis/iv/?format=json&sites="+riverlib.RIVER_CONFIG["cumberland"]["gauge"]["site"]+"&period=PT3H&parameterCd=00060")["value"]["timeSeries"][0]["values"][0]["value"]
    bk=round(float(pts[-1]["value"]))
except Exception as e: print("gauge warn:",e)

WADE=1500   # release below this ≈ wadeable at the dam/Kendall
def units(cfs): return max(0,round((cfs or 0)/5500))   # Wolf Creek ~6 units
now_hr=hk(now.timestamp()); cur=rel_at(now_hr)

# weather + solunar
wx=None
try:
    wx=get("https://api.open-meteo.com/v1/forecast?latitude=%.2f&longitude=%.2f"
           "&hourly=temperature_2m,precipitation_probability,cloud_cover,wind_speed_10m"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%%2FChicago&forecast_days=7"%(GLAT,GLON))
except Exception as e: print("wx warn:",e)
def ep(d,h): return hk(datetime.datetime(d.year,d.month,d.day,h,tzinfo=CT).timestamp())
def fmt_ap(t): return datetime.datetime.fromtimestamp(t,CT).strftime("%-I%p").lower()
def fmt_hm(t): return datetime.datetime.fromtimestamp(t,CT).strftime("%-I:%M%p").lower()

# generation ramp blocks + wade window, per day
def ramp(d0,d1):
    b=[];cur=None;k=d0
    while k<d1:
        u=units(rel_at(k)); v=rel_at(k) or 0
        if u<1:
            if cur: b.append(cur);cur=None
        elif cur and cur[2]==u: cur[1]=k+3600;cur[3]=max(cur[3],v)
        else:
            if cur: b.append(cur)
            cur=[k,k+3600,u,v]
        k+=3600
    if cur: b.append(cur)
    return b
def wade_window(d):
    # longest daylight (6a-8p) run where release < WADE
    d0=ep(d,0);run=None;best=(0,None,None)
    for h in range(6,20):
        low=(rel_at(ep(d,h)) or 0)<WADE
        if low:
            if run is None: run=h
        else:
            if run is not None and h-run>best[0]: best=(h-run,run,h)
            run=None
    if run is not None and 20-run>best[0]: best=(20-run,run,20)
    return best  # (hours, start_h, end_h)
def hlab(h): return (str((h%12) or 12))+("a" if h<12 else "p")

outlook=[]
for i in range(6):
    d=now_ct.date()+datetime.timedelta(days=i); d0=ep(d,0)
    blk=ramp(d0,d0+86400); peak=max([b[2] for b in blk],default=0)
    hrs,ws,we=wade_window(d)
    genl=(", ".join("%dU %s–%s"%(b[2],fmt_ap(b[0]),fmt_ap(b[1])) for b in blk)) if blk else "min flow all day"
    if hrs>=5 and peak<=3: cond,g,col="Wadeable AM","Prime","#28c76f"; verdict="Wade the shoals below the dam"
    elif hrs>=3: cond,g,col="Split day","Good","#0a84ff"; verdict="Wade early, streamers on the rise"
    elif peak>=1: cond,g,col="Generating","Fair","#f2a832"; verdict="Boat & streamer day — big-brown water"
    else: cond,g,col="Low all day","Prime","#28c76f"; verdict="Wade it — sight-fish the flats"
    wxd=None
    if wx and d.strftime("%Y-%m-%d") in wx["daily"]["time"]:
        j=wx["daily"]["time"].index(d.strftime("%Y-%m-%d")); wxd={"hi":round(wx["daily"]["temperature_2m_max"][j]),"lo":round(wx["daily"]["temperature_2m_min"][j]),"pop":wx["daily"]["precipitation_probability_max"][j]}
    outlook.append({"label":("Today" if i==0 else d.strftime("%a")),"date":d.strftime("%-m/%-d"),"cond":cond,"grade":g,"col":col,
        "verdict":verdict,"wade":("wade %s–%s"%(hlab(ws),hlab(we)) if ws is not None else "no wade window"),"gen":genl,"wx":wxd})

# release series for the chart (next ~5 days hourly)
series=[]; s0=ep(now_ct.date(),0)
for i in range(0,24*5,2):
    k=s0+i*3600; v=rel_at(k)
    if v is None: continue
    series.append({"t":datetime.datetime.fromtimestamp(k,CT).strftime("%-m/%-d %-I%p").lower(),"f":round(v),"h":k})

def wxday():
    if not wx: return None
    H=wx["hourly"]; idx={x:i for i,x in enumerate(H["time"])}; d=now_ct.date()
    def at(hr): return idx.get(datetime.datetime(d.year,d.month,d.day,hr).strftime("%Y-%m-%dT%H:00"))
    def snap(hr,lab):
        i=at(hr)
        if i is None: return None
        cc=H["cloud_cover"][i];pp=H["precipitation_probability"][i] or 0
        ico="☀️" if cc<25 else "⛅" if cc<65 else "☁️"
        if pp>=45: ico="🌧️"
        return {"when":lab,"temp":round(H["temperature_2m"][i]),"sky":"clear" if cc<25 else "partly cloudy" if cc<65 else "overcast","ico":ico,"wind":round(H["wind_speed_10m"][i]),"precip":pp}
    D=wx["daily"];ds=d.strftime("%Y-%m-%d");j=D["time"].index(ds) if ds in D["time"] else None
    return {"snaps":[x for x in [snap(7,"Dawn"),snap(13,"Midday"),snap(19,"Dusk")] if x],"hi":round(D["temperature_2m_max"][j]) if j is not None else None,
            "lo":round(D["temperature_2m_min"][j]) if j is not None else None,"sunrise":(D["sunrise"][j][11:16] if j is not None else ""),"sunset":(D["sunset"][j][11:16] if j is not None else "")}
WXT=wxday()

gen_now=cur and cur>=WADE
tips=[["🌡️","Bottom-release tailwater — cold, clear year-round. World-class wild browns and stocked rainbows; the Cumberland grows giants."]]
tips.append(["🎣",("Water's off — wade the shoals & gravel: #18–22 zebra midge, sowbug/scud, pheasant tail on a long light leader." if not gen_now
 else "Generating — get in the boat and throw meat: big articulated streamers (sculpin/white) on a sink-tip, swung and stripped on the rise. This is when the trophy browns eat.")])
tips.append(["🟤","Trophy-brown move: at first light or on a falling limb, swing a big dark streamer along the banks and drop-offs — Wolf Creek browns hunt low light and moving water."])
tips.append(["🌊","Be OFF the wadeable shoals before they generate — the bump comes fast on this river. Watch the horn/schedule and give yourself a big margin."])

# ---- fly box (mined Cumberland tailwater patterns, dynamic by generation) ----
_stap=["Zebra Midge — black/olive/grey #18–22","Sowbug / scud #14–18","Pheasant Tail / BH Prince #14–18"]
if gen_now:
    _flies=["🐟 Sculpin — brown & white-belly, articulated","Black / Olive Matuka Sculpin","Woolly Bugger · Muddler · Zoo Cougar (big)"]+_stap
    _rig="Generating: throw big streamers on a sink-tip from the boat — swing and strip them on the rise. This is when the trophy browns eat."
else:
    _flies=_stap+["Brassie #16–20 (green/red)","Y2K egg / San Juan worm (a little color)"]
    _rig="Water off: run a tandem midge rig under a small indicator — larva on the bottom, pupa up top; 9–12 ft leader to 6–7X. Sight-fish the shoals."
flybox={"now":_flies,"rig":_rig,
  "sources":[["Perfect Fly","https://perfectflystore.com/your-streams/fly-fishing-on-the-cumberland-river-in-kentucky/"],["KY Fish & Wildlife","https://fw.ky.gov/Education/Pages/Cumberland-River-Tailwater.aspx"],["Southeastern Anglers","https://www.southeasternanglers.com/the-rivers/cumberland-river-fly-fishing-guide-service.html"]]}
# REAL Cumberland tailwater accesses (KY F&W / USACE), CORRECT downstream order + distance below dam.
# Kendall & Burkesville use exact OSM ramp coords; Helm's/Rockhouse/Winfrey's placed on the channel at
# their documented mile-below-dam (Helm's @4.5 reverse-geocodes to the Helm community — confirmed).
ACC_TYPES={"Wolf Creek Dam":[],"Kendall Rec Area":["ramp","wade"],"Helm's Landing":["ramp","wade"],
           "Rockhouse":["paddle","wade"],"Winfrey's Ferry":["ramp","paddle"],"Burkesville City Ramp":["ramp"]}
ACC_INFO={"Wolf Creek Dam":"Release source — cold water off the bottom of Lake Cumberland; generation drives everything below. Not a launch — put in at Kendall just downstream.",
 "Kendall Rec Area":"USACE ramp off US 127, just below the dam (~0.5 mi). Main put-in; wade Boyd's Bar shoal (end of Ray Mann Rd) when the water's off.",
 "Helm's Landing":"Boat ramp off KY 379 (via KY 55 / US 127), ~4.5 mi below the dam.",
 "Rockhouse":"Canoe/kayak takeout off KY 379, ~10 mi below the dam — steep, not for johnboats. Long Bar / Snow Island wade shoal nearby.",
 "Winfrey's Ferry":"Takeout ~16 mi below the dam (cable across the river) — end of the popular upper float for canoes, kayaks & small johnboats.",
 "Burkesville City Ramp":"City ramp at Burkesville (~33 mi below the dam), near the USGS gauge (03414100)."}
SOL=riverlib.solunar(now_ct.date(),(WXT or {}).get("sunrise"),(WXT or {}).get("sunset"),CT)
# Seasonal hatch calendar — cold tailwater; famous for its late-spring/summer sulphur hatch. 0-3 by month.
HATCH={"rows":[
 {"name":"Midge","icon":"🦟","pattern":"zebra #18–22","m":[3,3,2,2,2,2,2,2,2,2,3,3]},
 {"name":"Sowbug / scud","icon":"🦐","pattern":"#14–18, everyday staple","m":[3,3,3,3,3,3,3,3,3,3,3,3]},
 {"name":"Sulphur","icon":"🟡","pattern":"#14–18 — the big Cumberland hatch","m":[0,0,0,1,3,3,3,2,1,0,0,0]},
 {"name":"Blue-winged olive","icon":"🪰","pattern":"BWO #18–22","m":[1,2,3,2,1,0,0,0,1,2,3,1]},
 {"name":"Caddis","icon":"🪰","pattern":"#14–16","m":[0,0,1,2,3,2,1,0,0,1,0,0]},
 {"name":"Cranefly","icon":"🦗","pattern":"larva on the bottom","m":[0,1,2,3,2,1,0,0,0,0,1,1]},
 {"name":"Terrestrials","icon":"🐜","pattern":"ant / beetle / hopper","m":[0,0,0,0,1,2,3,3,3,2,0,0]},
 {"name":"Sculpin / streamer","icon":"🐟","pattern":"trophy browns on the rise","m":[2,2,2,1,1,1,1,1,2,3,3,3]},
]}

# flow-timer timeline: TAILWATER — the Wolf Creek release travels downstream, so each access lags the
# dam by its travel time and the "front" of generating water descends the strip as you scrub/play.
_rel=[p["f"] for p in series]; _nowep=int(now.timestamp())
_cnow=next((i for i,p in enumerate(series) if p["h"]>=_nowep),len(series)-1)
_clag=[("Kendall",0),("Helm's Landing",1),("Rockhouse",3),("Winfrey's Ferry",4),("Burkesville",13)]
def _lag(l): return [_rel[max(0,i-l)] for i in range(len(_rel))]
TIMELINE=({"times":[p["t"] for p in series],"nowFrame":max(0,_cnow),"unit":"cfs","refIdx":0,"refName":"Wolf Creek",
  "front":True,"frontThresh":WADE,"srcLabel":"Wolf Creek Dam ↑","mouthLabel":"Burkesville ↓",
  "bands":[[WADE,"#28c76f","Wadeable"],[8000,"#0a84ff","Generating"],[10**9,"#5e5ce6","High"]],
  "points":[{"name":n,"series":_lag(l)} for n,l in _clag]} if series else None)
# clarity × light fly matrix (shared). Clarity from the release magnitude (off=clear → generating=stained).
FLYORDER=["clear","moderate","stained","muddy"]; LIGHTS=[("dawn","Dawn"),("low","Low light"),("bright","Bright sun"),("wind","Wind / chop")]
FLYMATRIX={
 "clear":   {"label":"Off · wadeable","dawn":"Sulphur emerger #16","low":"Zebra midge #20","bright":"Sowbug #16 (sight)","wind":"Zebra midge #18"},
 "moderate":{"label":"Low gen · rising","dawn":"Sulphur dun #16","low":"Pheasant Tail #16","bright":"Scud #16","wind":"Soft-hackle #14"},
 "stained": {"label":"Generating","dawn":"Sculpin","low":"Woolly Bugger blk/olive","bright":"Big sowbug #14","wind":"Conehead bugger"},
 "muddy":   {"label":"High gen","dawn":"Articulated sculpin","low":"White streamer","bright":"Dark streamer","wind":"Big articulated"},
}
BOXINV_C=[
 ["Zebra midge","#18–22","Tandem under a small indicator when the water's off — larva low, pupa up top."],
 ["Sowbug / scud","#14–18","The everyday staple — sight-fish it on the shoals when it's clear."],
 ["Sulphur emerger / dun","#14–18","The big Cumberland hatch, late spring into summer — fish the film & surface."],
 ["Pheasant Tail / Prince","#14–18","Searching nymph on the drop-offs & current seams."],
 ["Woolly Bugger / sculpin","#2–8","On the generation rise — swing & strip; this is when the trophy browns eat."],
 ["Articulated streamer","#2–4","Big water — get it deep on a sink-tip, tight to the bank & drop-offs."],
]
_cc=cur; _ccl=("clear" if _cc is None or _cc<WADE else "moderate" if _cc<4000 else "stained" if _cc<8000 else "muddy")
_ch=now_ct.hour; _ccloud=50; _cwind=6
if wx:
    _H=wx["hourly"]; _k=now_ct.strftime("%Y-%m-%dT%H:00")
    if _k in _H["time"]: _wi=_H["time"].index(_k); _ccloud=_H["cloud_cover"][_wi] or 0; _cwind=_H["wind_speed_10m"][_wi] or 0
_clight=riverlib.light_now(_ch,_ccloud,_cwind)
FLYSEL={"matrix":FLYMATRIX,"order":FLYORDER,"lights":LIGHTS,"boxinv":BOXINV_C,
  "now":{"clarity":_ccl,"light":_clight,"fly":FLYMATRIX[_ccl][_clight]},
  "rig":"Water off → tandem midge rig under a small indicator, 9–12 ft leader to 6–7X, sight-fish the shoals. Generating → big streamers on a sink-tip from the boat, swung & stripped on the rise.",
  "sources":[["Perfect Fly","https://perfectflystore.com/your-streams/fly-fishing-on-the-cumberland-river-in-kentucky/"],["KY Fish & Wildlife","https://fw.ky.gov/Education/Pages/Cumberland-River-Tailwater.aspx"],["Southeastern Anglers","https://www.southeasternanglers.com/the-rivers/cumberland-river-fly-fishing-guide-service.html"]]}
# generation schedule (shared component): per-day release windows + when it reaches the ramps
CGEN=[]
for _i in range(6):
    _d=now_ct.date()+datetime.timedelta(days=_i); _d0=ep(_d,0); _blk=ramp(_d0,_d0+86400)
    _wins=[{"units":b[2],"span":fmt_ap(b[0])+"–"+fmt_ap(b[1])} for b in _blk]
    _spark=[units(rel_at(_d0+h*3600)) for h in range(24)]
    _rst=_blk[0][0] if _blk else None
    _arr=[[nm,fmt_ap(_rst+lag*3600)] for nm,lag in [("Kendall",0),("Helm's",1),("Winfrey's",4)]] if _rst else None
    CGEN.append({"label":("Today" if _i==0 else _d.strftime("%a")),"date":_d.strftime("%-m/%-d"),
                 "windows":_wins,"spark":_spark,"peak":max([b[2] for b in _blk],default=0),"arr":_arr})
GENHINT=("Wolf Creek generation, midnight→midnight (bar height = units). The release rises at the dam the "
         "moment they start and travels downstream — be off the wade shoals before it. Downstream arrival is "
         "approximate (this big river routes weakly).")
GENLEGEND=('<span><i style="background:#7db8e0"></i>1 unit</span><span><i style="background:#2f92d4"></i>2 units</span>'
           '<span><i style="background:#5e5ce6"></i>3+ units</span><span>Verify against the Wolf Creek horn &amp; TVA schedule.</span>')
# ---- CHANNEL DEPTH & JET FLOATABILITY (measured rise + one tunable threshold) ----
# Fitted from the Burkesville gauge (USGS 03414100), which reports BOTH discharge (00060)
# and gage height (00065): 100,984 paired hourly points, 2015-present, binned by flow and
# referenced to the min-flow stage of 24.71 ft. Reproduce with:
#     python3 depth_fit.py 03414100 "Burkesville (Cumberland KY)" 5500
# This is RISE above minimum flow, not absolute depth. Absolute depth would need a surveyed
# reference depth per ramp, which nobody has for this river — and Caney's equivalent numbers
# (its ACCESS d0 values) are undocumented estimates, so copying that approach would just
# spread an unverified number onto a second river. Rise is what the gauge actually measured.
RISE_CURVE=[[1100,0.0],[1400,0.4],[1800,1.1],[2500,2.1],[3500,3.2],[5000,4.7],
            [7000,6.3],[9500,8.1],[13000,10.6],[18000,13.7],[25000,16.9]]
def rise_at(cfs):
    c=RISE_CURVE
    if cfs is None: return None
    if cfs<=c[0][0]: return 0.0
    for i in range(1,len(c)):
        if cfs<=c[i][0]:
            a,b=c[i-1],c[i]; return a[1]+(b[1]-a[1])*(cfs-a[0])/(b[0]-a[0])
    a,b=c[-2],c[-1]; return b[1]+(b[1]-a[1])*(cfs-b[0])/(b[0]-a[0])

# The one number that is NOT measured. WADE (1500 cfs) is the existing anchor: below it the
# shoals at the dam/Kendall are wadeable, and water you can wade is water a 60/40 jet is
# picking its way through. Everything else is scaled off that. TUNE THESE FROM THE WATER —
# the first trip where the boat drags at a known release replaces the guess.
JET={"skinny":WADE, "good":5000, "pushy":25000}
def jet_read(cfs):
    """(verdict, colour, note) for the 60/40 jet at this release."""
    if cfs is None: return ("—","#93a3b3","no release data")
    if cfs < JET["skinny"]:
        return ("Skinny","#f2a832","water off — shoals are wadeable, so the jet picks its way; fine to run, watch the bars")
    if cfs < JET["good"]:
        return ("Floats","#7db85a","enough water to run the shoals without hunting")
    if cfs < JET["pushy"]:
        return ("Good","#28c76f","plenty of channel — run it anywhere")
    return ("Pushy","#8b6cef","high and fast; plenty deep but heavy water")
# Per-access read. Two different confidence levels, and the payload keeps them apart:
#
#   Burkesville  IS the gauge the rise curve was fitted at, so its depth-rise is measured.
#   Everywhere else  is 20-30 river miles upstream in a completely different channel. The
#   Burkesville stage relationship does NOT transfer there, so those accesses get the
#   release-driven jet verdict and NO depth number. A fabricated "+0.0 ft" at Kendall would
#   look like data and be nothing of the kind.
#
# Note the release is also not the flow: with the dam off, Burkesville still reads thousands
# of cfs from 30 miles of drainage. The upstream verdict is deliberately driven by RELEASE,
# because near the dam that is what governs whether the shoals are floatable.
DEPTH=[]
for _n,_l in _clag:
    _q=rel_at(now_hr-_l*3600)
    _v,_c,_note=jet_read(_q)
    _gauged=(_n=="Burkesville")
    DEPTH.append({"name":_n,"lag":_l,"cfs":(round(_q) if _q is not None else None),
                  "rise":(round(rise_at(bk),1) if (_gauged and bk is not None) else None),
                  "gauged":_gauged,
                  "verdict":_v,"col":_c,"note":_note})
DATA={"depth":DEPTH,"depthRef":"Depth rise measured at the Burkesville gauge (USGS 03414100, 100k paired points). Upstream ramps show the jet read off the release — no stage gauge exists there, so no depth is claimed.",
      "today":now_ct.strftime("%A, %B %-d · %-I:%M %p"),"flysel":FLYSEL,"solunar":SOL,"hatch":HATCH,"month":now_ct.month,"chatter":riverlib.load_intel("cumberland"),"timeline":TIMELINE,
      "gen":CGEN,"genHint":GENHINT,"genLegend":GENLEGEND,"genOpts":{"minLabel":"water off — wade all day","arrLabel":"release reaches"},
      "now":{"cfs":round(cur) if cur is not None else None,"gen":bool(gen_now),"units":units(cur) if gen_now else 0,
             "bk":bk,"state":("Generating" if gen_now else "Wadeable — water off"),
             "col":("#5e5ce6" if (cur and cur>8000) else "#0a84ff" if gen_now else "#28c76f"),
             "asof":now_ct.strftime("%-I:%M %p")},
      "outlook":outlook,"series":series,"weather":WXT,"tips":tips,"wade":WADE,
      "points":[{"name":k,"lat":v[0],"lon":v[1],"types":ACC_TYPES.get(k,[]),"info":ACC_INFO.get(k,"")} for k,v in {"Wolf Creek Dam":[36.86729,-85.14693],"Kendall Rec Area":[36.87013,-85.13305],"Helm's Landing":[36.89801,-85.14509],"Rockhouse":[36.88566,-85.23342],"Winfrey's Ferry":[36.87641,-85.24747],"Burkesville City Ramp":[36.78612,-85.36578]}.items()],
      "poly":[[36.86729,-85.14693],[36.8688,-85.14797],[36.87702,-85.15084],[36.88271,-85.14483],[36.88497,-85.13273],[36.88573,-85.12767],[36.88958,-85.12346],[36.89325,-85.12333],[36.90066,-85.12941],[36.90337,-85.13403],[36.90193,-85.14191],[36.88649,-85.15445],[36.87976,-85.17213],[36.87468,-85.19496],[36.87669,-85.20625],[36.88361,-85.2178],[36.88601,-85.22508],[36.888,-85.22917],[36.88724,-85.23281],[36.88128,-85.2351],[36.87015,-85.22054],[36.8606,-85.21315],[36.8547,-85.2153],[36.85174,-85.22391],[36.85226,-85.2339],[36.85957,-85.24547],[36.87093,-85.24524],[36.87803,-85.24813],[36.87921,-85.25882],[36.87461,-85.26774],[36.86418,-85.26714],[36.83688,-85.25603],[36.82728,-85.25527],[36.82145,-85.26096],[36.82179,-85.27126],[36.84041,-85.28858],[36.85319,-85.30008],[36.85978,-85.31201],[36.85813,-85.32536],[36.85367,-85.32832],[36.84893,-85.32695],[36.8433,-85.32643],[36.83924,-85.33021],[36.83725,-85.34883],[36.82976,-85.36536],[36.82461,-85.36411],[36.82014,-85.35553],[36.8097,-85.34471],[36.802,-85.34514],[36.7941,-85.35694],[36.78788,-85.36355]]}

TEMPLATE=r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Cumberland River KY · trophy trout</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#16202b;--muted:#66788a;--faint:#93a3b3;--line:#e6ecf2;--card:#fff;--blue:#0a84ff;--green:#28c76f}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,sans-serif;
 background:radial-gradient(1000px 700px at 82% -6%,#efeaf9 0,transparent 60%),linear-gradient(180deg,#f2f0f8,#e9e6f0);min-height:100vh}
.app{max-width:900px;margin:0 auto;padding:30px 22px 80px}
__SWITCH_CSS__
.eyebrow{font-size:12px;letter-spacing:.24em;text-transform:uppercase;color:var(--faint);font-weight:600}
h1{margin:6px 0 4px;font-size:32px;font-weight:750;letter-spacing:-.6px}.cap{color:var(--muted);font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 26px rgba(20,50,80,.06)}
.sec{font-size:15px;font-weight:700;margin:26px 2px 12px}
.now{padding:16px 18px;margin:12px 0;display:flex;align-items:center;gap:16px}
.now .vg{flex:none;padding:11px 16px;text-align:center;color:#fff;font-weight:800;font-size:13px;border-radius:12px}
.now .b1{font-size:19px;font-weight:700}.now .b2{font-size:13.5px;color:var(--muted);margin-top:2px}.now .rt{margin-left:auto;text-align:right;font-size:12px;color:var(--faint)}
.chartc{padding:14px 12px 8px}.lgd{font-size:12px;color:var(--muted);display:flex;gap:14px;justify-content:center;margin-top:6px;flex-wrap:wrap}.lgd i{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:5px}
#lmap{height:330px;border-radius:16px}.leaflet-container{border-radius:16px;font-family:inherit}.maptip{font-size:11.5px;color:var(--faint);text-align:center;margin:7px 0 0}
.wk{padding:6px 16px 14px}.wr{display:flex;align-items:center;gap:13px;padding:12px 0;border-top:1px solid var(--line)}.wr:first-child{border-top:0}
.wg{flex:none;width:74px;text-align:center;font-size:10px;font-weight:800;color:#fff;padding:5px 0;border-radius:8px}
.wd{flex:none;width:54px}.wd b{display:block;font-size:15px}.wd span{font-size:11.5px;color:var(--muted)}
.wm{flex:1;min-width:0}.wv{font-size:14.5px;font-weight:600}.ws{font-size:12.5px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wx{display:flex;flex-wrap:wrap}.wx .m{flex:1;min-width:110px;padding:12px 14px;border-right:1px solid var(--line)}.wx .m:last-child{border-right:0}
.wx .w{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);font-weight:600}.wx .t{font-size:24px;font-weight:700;margin:2px 0}.wx .d{font-size:12.5px;color:var(--muted)}
.wx .meta{padding:12px 14px;font-size:12.5px;color:var(--muted);display:flex;flex-direction:column;justify-content:center;gap:3px;min-width:150px}
.tips{padding:6px}.tip{display:flex;gap:12px;padding:11px 12px;border-bottom:1px solid var(--line)}.tip:last-child{border-bottom:0}.tip .i{font-size:20px}.tip .x{font-size:14px;line-height:1.5}
.foot{text-align:center;color:var(--faint);font-size:11.5px;margin-top:26px;line-height:1.6}
__SOLUNAR_CSS__
__HATCH_CSS__
__LOG_CSS__
__MOONCAL_CSS__
__FLOWTIMER_CSS__
__FLYMATRIX_CSS__
__GENSCHED_CSS__
__CHATTER_CSS__
@media(max-width:680px){.app{padding:22px 14px 60px}h1{font-size:27px}.wx .m{min-width:0}}
</style></head><body><div class="app">
 __SWITCHER__
 <div class="eyebrow">Trophy-trout tailwater · Wolf Creek Dam → Burkesville, KY</div>
 <h1>Cumberland River</h1><div class="cap" id="cap"></div>
 <div class="card now" id="now"></div>
 <div class="sec">Generation schedule</div><div class="card gen" id="genc"></div>
 <div class="sec">Channel depth &amp; jet floatability</div><div class="card dep" id="dep"></div>
 <div class="sec">Flow timer · watch the release travel</div><div class="card ft" id="flowtimer"></div>
 <div class="sec">Live map · trophy reach</div>
 <div class="card" style="padding:8px"><div id="lmap"></div></div>
 <div class="maptip">Real KY F&amp;W / USACE ramps in downstream order, Wolf Creek Dam → Burkesville (~33 mi) · tap a pin for details &amp; a Google Maps link
 <div class="sec">6-day outlook · wade vs. boat</div><div class="card wk" id="wk"></div>
 <div class="sec">Weather</div><div class="card wx" id="wx"></div>
 <div class="sec">Moon &amp; feeding</div><div class="card sol" id="sol"></div>
 <div class="sec">Moon &amp; feeding calendar</div><div class="card mcal" id="mooncal"></div>
 <div class="sec">Hatch calendar</div><div class="card hatch" id="hatch"></div>
 <div class="sec">Fly selection · clarity × light</div><div class="card" id="flysel"></div>
 <div class="sec">Guide's take</div><div class="card tips" id="tips"></div>
 <div id="chatterSec" style="display:none"><div class="sec">River chatter · Reddit</div><div class="card chatter" id="chatter"></div></div>
 <div class="sec">My log</div><div class="card logc" id="log"></div>
 <div class="foot" id="foot"></div>
</div>
<script>
const D=__DATA__;
__POPUP_JS__
__MAP_JS__
__SOLUNAR_JS__
__HATCH_JS__
__LOG_JS__
__MOONCAL_JS__
__FLOWTIMER_JS__
__FLYMATRIX_JS__
__GENSCHED_JS__
__CHATTER_JS__
document.getElementById('cap').innerHTML=D.today+' · Wolf Creek Dam release (USACE)';
(function(){const n=D.now;document.getElementById('now').innerHTML=
 '<div class="vg" style="background:'+n.col+'">'+(n.gen?n.units+'-UNIT':'WADEABLE')+'</div>'
 +'<div><div class="b1">'+n.state+' · '+(n.cfs!=null?n.cfs.toLocaleString()+' cfs':'—')+'</div>'
 +'<div class="b2">'+(n.gen?'water’s up — boat &amp; streamers':'water off — wade the shoals below the dam')+(n.bk?' · Burkesville gauge '+n.bk.toLocaleString()+' cfs':'')+'</div></div>'
 +'<div class="rt">as of '+n.asof+'</div>';})();
buildGenSchedule('genc',D.gen,D.genHint,D.genLegend,D.genOpts);
(function(){let h='';D.outlook.forEach(d=>{const wx=d.wx?(' · '+d.wx.hi+'°/'+d.wx.lo+'°'+(d.wx.pop?' · '+d.wx.pop+'%':'')):'';
 h+='<div class="wr"><div class="wg" style="background:'+d.col+'">'+d.grade+'</div><div class="wd"><b>'+d.label+'</b><span>'+d.date+'</span></div>'
  +'<div class="wm"><div class="wv">'+d.cond+' — '+d.verdict+'</div><div class="ws">'+d.wade+' · gen: '+d.gen+wx+'</div></div></div>';});
 document.getElementById('wk').innerHTML=h;})();
(function(){const w=D.weather,el=document.getElementById('wx');if(!w){el.innerHTML='<div class="meta">weather unavailable</div>';return;}
 let h='';(w.snaps||[]).forEach(s=>h+='<div class="m"><div class="w">'+s.when+'</div><div class="t">'+s.ico+' '+s.temp+'°</div><div class="d">'+s.sky+' · '+s.wind+' mph'+(s.precip?' · '+s.precip+'%':'')+'</div></div>');
 h+='<div class="meta"><div>High '+(w.hi??'–')+'° · Low '+(w.lo??'–')+'°</div><div>Sun '+w.sunrise+'–'+w.sunset+'</div></div>';el.innerHTML=h;})();
buildFlyMatrix('flysel',D.flysel);
(function(){let h='';D.tips.forEach(t=>h+='<div class="tip"><div class="i">'+t[0]+'</div><div class="x">'+t[1]+'</div></div>');document.getElementById('tips').innerHTML=h;})();
renderSolunar('sol',D.solunar,D.now.gen?'Best when a major window overlaps the generation rise — that moving water is when the trophy browns hunt.':'Best when a major window lines up with first light on the wadeable shoals.');
renderHatch('hatch',D.hatch,D.month);
buildMoonCal('mooncal',36.87,-85.14);
(function(){
  var el=document.getElementById('dep'); if(!el||!D.depth) return;
  var h='';
  D.depth.forEach(function(p){
    h+='<div class="deprow"><div class="dn">'+p.name
      +'<small>'+(p.lag?('release reaches it ~'+p.lag+' h after the dam'):'at the dam')+'</small></div>'
      +'<div class="dq">'+(p.cfs!=null?('<b>'+p.cfs.toLocaleString()+' cfs</b>'):'<b>—</b>')
      +(p.rise!=null ? ('+'+p.rise.toFixed(1)+' ft over min flow') : 'no stage gauge here')
      +'</div><div class="depv" style="background:'+p.col+'">'+p.verdict+'</div></div>';
  });
  h+='<div class="depnote">'+D.depthRef+' Thresholds for the 60/40 jet are tuned off the wade '
    +'threshold, not surveyed \u2014 the first trip the boat drags at a known release should replace them.</div>';
  el.innerHTML=h;
})();
buildFlowTimer('flowtimer',D.timeline);
renderChatter('chatter',D.chatter,'chatterSec');
buildLog('log','riverlog-cumberland',D.points.map(p=>p.name),null);
document.getElementById('foot').textContent='Release & forecast: USACE CWMS (Wolf Creek Dam). Downstream gauge: USGS 03414100 (Burkesville). This big river routes weakly (Wolf Creek→Burkesville r=0.30) so downstream timing is approximate — the release schedule and at-dam wade windows are the reliable parts. Weather: Open-Meteo. Channel: OpenStreetMap.';
buildRiverMap(D,D.now.col);
</script></body></html>"""
html=riverlib.render(TEMPLATE,"cumberland").replace("__DATA__",json.dumps(DATA))
open(os.path.join(OUT,"cumberland.html"),"w").write(html)
# ---- HQ status card (use today's synthesized outlook) ----
_t=outlook[0] if outlook else {"grade":"Good","cond":"—","col":"#0a84ff","verdict":"tailwater — fishes daily"}

# ---- HQ day state ----
# Wolf Creek has a genuine wade threshold (WADE cfs at the dam/Kendall), so wade-vs-boat
# is a real read here rather than a formality.
def _cumb_day(off):
    d0, _ = riverlib.day_bounds(CT, off)
    cv = riverlib.hourly_curve(rel_at, d0)
    day = [(h, cv[h]) for h in range(6, 21)] if cv else []
    if not day: return riverlib.day_state(headline="No release forecast")
    on = [h for h, v in day if v and v > WADE]
    def _ap(h): return "%d%s" % (h % 12 or 12, "am" if h < 12 else "pm")
    if not on:
        vk, vw, head = "wade", "release under %s cfs — the shoals are fishable" % format(WADE, ","), "Water off — wade it"
        wins = [{"from": _ap(6), "to": _ap(20), "kind": "wade"}]
    elif len(on) >= 13:
        vk, vw = "boat", "generating through the day"
        head = "Generating %s–%s — boat" % (_ap(on[0]), _ap(on[-1] + 1)); wins = [{"from": _ap(on[0]), "to": _ap(on[-1] + 1), "kind": "boat"}]
    else:
        vk, vw = "both", "wade the shoals early, then ride it"
        head = "Wade until %s, then it comes up" % _ap(on[0])
        wins = [{"from": _ap(6), "to": _ap(on[0]), "kind": "wade"}, {"from": _ap(on[0]), "to": _ap(on[-1] + 1), "kind": "boat"}]
    vals = [v for _, v in day if v is not None]
    peak = max(vals); med = sorted(vals)[len(vals)//2]
    lk = "low" if med <= WADE else "prime" if peak < 12000 else "high" if peak < 25000 else "blown"
    return riverlib.day_state(vessel=vk, vessel_why=vw,
        clarity="clear" if med <= WADE else "stained", clarity_why="bottom-release tailwater; colour tracks release volume",
        level=lk, level_detail="%s cfs peak" % format(round(peak), ","),
        curve=cv, curve_unit="cfs", curve_label="Wolf Creek release", curve_src="forecast",
        windows=wins, headline=head)
DAYS = {"today": _cumb_day(0), "tomorrow": _cumb_day(1)}

riverlib.emit_status("cumberland",
    {"grade":_t["grade"],"cond":_t.get("cond","—"),"col":_t["col"],"note":_t.get("verdict",""),
     "detail":(("%s cfs release"%format(round(cur),",")) if cur is not None else "water off"),"asof":now_ct.strftime("%-I:%M %p")},
    wx, [riverlib.GRADE_SCORE.get(o["grade"], 2.0) for o in outlook] or riverlib.GRADE_SCORE.get(_t["grade"],2.0), CT, ["Trout"], "Trophy trout tailwater", "~2.5 hr · destination (KY)", days=DAYS)
print("wrote out/cumberland.html | release now %s cfs (gen=%s) | Burkesville %s | outlook %d"%(cur,gen_now,bk,len(outlook)))
