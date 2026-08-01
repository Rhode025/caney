#!/usr/bin/env python3
"""
Cumberland River · Nashville — the metro reach, Old Hickory Dam to Cheatham Dam.
A warmwater BIG-RIVER model: this is a navigable impoundment (Cheatham pool), so depth is
stable year-round — you never ground out. The variable is CURRENT, and current is Old Hickory
generation. Striped bass, smallmouth, white bass & panfish, on the fly. Live gauge = USGS 03431500
(Cumberland River at Nashville, discharge + stage). Sources: USGS, USACE, Open-Meteo, OSM.
"""
import json,urllib.request,datetime,os,sys
from zoneinfo import ZoneInfo
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import riverlib
CT=ZoneInfo("America/Chicago"); UA={"User-Agent":"cumbnash/1.0"}
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"out"); os.makedirs(OUT,exist_ok=True)
def get(u,h=None):
    # riverlib.get retries transient TLS/DNS/5xx failures; a single flaky fetch used to
    # build this page with missing data instead of failing (see riverlib.get docstring).
    return riverlib.get(u,{**UA,**(h or {})},timeout=60)
now=datetime.datetime.now(datetime.timezone.utc); now_ct=now.astimezone(CT)
CFG=riverlib.RIVER_CONFIG["cumbnash"]; SITE=CFG["gauge"]["site"]
GLAT,GLON=36.17,-86.74
USACE_URL="https://www.lrn-wc.usace.army.mil/basin_project.shtml?p=oldh"

# ---- USGS gauge: discharge (00060) + stage (00065), ~4 days ----
FLOW=[]; STAGE=[]
try:
    js=get("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=%s&period=P4D&parameterCd=00060,00065"%SITE)
    for ts in js["value"]["timeSeries"]:
        code=ts["variable"]["variableCode"][0]["value"]
        rows=[(datetime.datetime.fromisoformat(v["dateTime"]),float(v["value"]))
              for v in ts["values"][0]["value"] if v["value"] not in (None,"","-999999")]
        if code=="00060": FLOW=rows
        elif code=="00065": STAGE=rows
except Exception as e: print("usgs warn:",e)
FLOW.sort(); STAGE.sort()
cur_flow=FLOW[-1][1] if FLOW else None
cur_stage=STAGE[-1][1] if STAGE else None
asof=(FLOW[-1][0].astimezone(CT).strftime("%-I:%M %p") if FLOW else now_ct.strftime("%-I:%M %p"))
trend="steady"
if len(FLOW)>=2:
    ref=next((o for o in reversed(FLOW) if (FLOW[-1][0]-o[0]).total_seconds()>=4*3600), FLOW[0])
    dv=FLOW[-1][1]-ref[1]
    trend="rising" if dv>1500 else "falling" if dv<-1500 else "steady"


# ---- weather (7-day, for the HQ week outlook) ----
wx=None
try:
    wx=get("https://api.open-meteo.com/v1/forecast?latitude=%.2f&longitude=%.2f"
           "&hourly=temperature_2m,precipitation_probability,cloud_cover,wind_speed_10m"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone=America%%2FChicago&forecast_days=7"%(GLAT,GLON))
except Exception as e: print("wx warn:",e)
def wxday(di):
    if not wx: return None
    H=wx["hourly"]; idx={x:i for i,x in enumerate(H["time"])}
    d=now_ct.date()+datetime.timedelta(days=di)
    def snap(hr,lab):
        k=datetime.datetime(d.year,d.month,d.day,hr).strftime("%Y-%m-%dT%H:00"); i=idx.get(k)
        if i is None: return None
        cc=H["cloud_cover"][i]; pp=H["precipitation_probability"][i] or 0
        ico="☀️" if cc<25 else "⛅" if cc<65 else "☁️"
        if pp>=45: ico="🌧️"
        return {"when":lab,"temp":round(H["temperature_2m"][i]),"sky":"clear" if cc<25 else "partly cloudy" if cc<65 else "overcast",
                "ico":ico,"wind":round(H["wind_speed_10m"][i]),"precip":pp}
    D=wx["daily"]; ds=d.strftime("%Y-%m-%d"); j=D["time"].index(ds) if ds in D["time"] else None
    return {"snaps":[x for x in [snap(7,"Dawn"),snap(13,"Midday"),snap(19,"Dusk")] if x],
            "hi":round(D["temperature_2m_max"][j]) if j is not None else None,"lo":round(D["temperature_2m_min"][j]) if j is not None else None,
            "sunrise":(D["sunrise"][j][11:16] if j is not None else ""),"sunset":(D["sunset"][j][11:16] if j is not None else "")}
WXT=wxday(0)

# ---- observed hydrograph (downsampled) ----
series=[]
if FLOW:
    step=max(1,len(FLOW)//48)
    for i in range(0,len(FLOW),step):
        t,v=FLOW[i]; series.append({"t":t.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(v)})
    lt,lv=FLOW[-1]; last={"t":lt.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(lv)}
    if not series or series[-1]!=last: series.append(last)

# ---- solunar + forage calendar + fly matrix (shared components) ----
SOL=riverlib.solunar(now_ct.date(),(WXT or {}).get("sunrise"),(WXT or {}).get("sunset"),CT)
HATCH={"rows":[
 {"name":"Shad","icon":"🐟","pattern":"baitfish streamer — year-round","m":[3,3,3,3,3,3,3,3,3,3,3,3]},
 {"name":"Skipjack","icon":"🐠","pattern":"big streamer for stripers","m":[1,1,2,3,3,3,3,3,3,2,2,1]},
 {"name":"Striper run","icon":"🎣","pattern":"swing streamers in the tailrace","m":[1,2,3,3,2,1,1,1,1,1,2,2]},
 {"name":"Crawfish","icon":"🦞","pattern":"craw fly on the ledges","m":[1,1,2,3,3,3,3,3,3,2,1,1]},
 {"name":"White bass","icon":"🎏","pattern":"chartreuse Clouser on the current","m":[1,1,2,3,3,2,1,1,2,2,1,1]},
 {"name":"Spring run","icon":"🎣","pattern":"biggest fish of the year move up to the dam","m":[1,1,2,3,3,2,1,1,1,1,1,1]},
 {"name":"Thermal refuge","icon":"🌡️","pattern":"heat stacks them in the cool tailrace","m":[0,0,0,0,1,3,3,3,2,1,0,0]},
]}
FLYMATRIX={
 "clear":   {"label":"Slack · <7k","dawn":"Topwater popper","low":"Sneaky Pete","bright":"Sparse Clouser","wind":"Popper"},
 "moderate":{"label":"Gen · 7–15k","dawn":"Chartreuse Clouser","low":"Deceiver","bright":"Clouser, deep","wind":"Woolly Bugger"},
 "stained": {"label":"Gen · 15–30k","dawn":"Articulated streamer","low":"Big Deceiver","bright":"Clouser on sink-tip","wind":"Chartreuse streamer"},
 "muddy":   {"label":"High · >30k","dawn":"Black articulated","low":"Big black bugger","bright":"Chart/white Clouser","wind":"Big black streamer"},
}
FLYORDER=["clear","moderate","stained","muddy"]; LIGHTS=[("dawn","Dawn"),("low","Low light"),("bright","Bright sun"),("wind","Wind / chop")]
BOXINV=[
 ["Clouser Minnow","#1/0–4","The workhorse — chartreuse/white & olive/white; swing & strip it through the tailrace and along the ledges."],
 ["Lefty's Deceiver / baitfish streamer","#2/0–2","Big-profile shad imitation for stripers & hybrids on a sink-tip when they generate."],
 ["Articulated streamer","#4–2/0","Meat for the biggest fish in stained, higher water — strip it along the wing dams."],
 ["Crawfish / Woolly Bugger","#4–8","Bottom fly for the rock ledges & wing dams — smallmouth eat it on the swing & pause."],
 ["Sneaky Pete / popper","#2–6","Slack, clear water — topwater smallmouth at first & last light."],
 ["Bream bug / small popper","#8–10","Panfish & bluegill in the slack water, backwaters & bank cover."],
]
_dc=cur_flow
_dcl=("clear" if _dc is None or _dc<7000 else "moderate" if _dc<15000 else "stained" if _dc<30000 else "muddy")
_dh=now_ct.hour; _dcloud=50; _dwind=6
if wx:
    _H=wx["hourly"]; _k=now_ct.strftime("%Y-%m-%dT%H:00")
    if _k in _H["time"]: _wi=_H["time"].index(_k); _dcloud=_H["cloud_cover"][_wi] or 0; _dwind=_H["wind_speed_10m"][_wi] or 0
_dlight=riverlib.light_now(_dh,_dcloud,_dwind)
FLYSEL={"matrix":FLYMATRIX,"order":FLYORDER,"lights":LIGHTS,"boxinv":BOXINV,
  "now":{"clarity":_dcl,"light":_dlight,"fly":FLYMATRIX[_dcl][_dlight]},
  "rig":"When they generate, get a streamer on the current: Clouser or Deceiver on a sink-tip, swung and stripped through the tailrace and along the ledges — that's when the stripers & white bass feed. Slack water → slow down and work a crawfish/bugger deep on the ledges, or a popper up top at first light. 7–8 wt, 12–16 lb tippet for the big fish.",
  "sources":[["TWRA Old Hickory","https://www.tn.gov/twra/fishing/where-to-fish/middle-tennessee-r2/old-hickory-reservoir.html"],["TWRA Cheatham","https://www.tn.gov/twra/fishing/where-to-fish/middle-tennessee-r2/cheatham-reservoir.html"],["USGS 03431500","https://waterdata.usgs.gov/monitoring-location/USGS-03431500/"]]}

tips=[["🌊","It's all about current. Depth is stable — you won't ground out on this navigable pool — so plan around Old Hickory GENERATION, not level. Dam idle → slack, slow fishing. Turbines on → the ledges and tailrace light up. Check the USACE Nashville District release before you launch."]]
if cur_flow is not None and cur_flow>=7000:
    tips.append(["🎣","Current's on — go. Swing a Clouser or Deceiver on a sink-tip through the tailrace and down-current of the wing dams and ledges. Stripers, hybrids, white bass & big smallmouth stack where the current breaks."])
else:
    tips.append(["🐟","Slack water — slow down. Work a crawfish or Woolly Bugger deep along the ledges, and throw a popper up top at first light. The bite turns back on the moment they start generating."])
tips.append(["🚤","Big water, big boat sense — the navigation channel carries barge traffic. Cross it, don't idle in it, and take big wakes at an angle. Wing dams and rock ledges lurk just under the surface all through the metro reach."])
tips.append(["🐡","Slack backwaters and bank cover hold bluegill & panfish — a small popper or bream bug on a light rod is a fun change-up while you wait on the generation."])

POINTS=[
 {"name":"Old Hickory Dam Tailwater","lat":36.2988,"lon":-86.6633,"types":["ramp"],
  "info":"USACE concrete ramp immediately below Old Hickory Dam — the striper & smallmouth tailrace. Strong current when they generate; stay off the dam.","rm":216},
 {"name":"Peeler Park","lat":36.2436,"lon":-86.654,"types":["ramp"],
  "info":"Metro Parks concrete ramp at Neely's Bend (~RM 205). Good mid-reach launch above the city bends.","rm":205},
 {"name":"Lock Two","lat":36.2016,"lon":-86.6786,"types":["ramp"],
  "info":"Metro Parks concrete ramp at Pennington Bend (~RM 201).","rm":201},
 {"name":"Shelby Bottoms","lat":36.16359,"lon":-86.73792,"types":["ramp"],
  "info":"Metro Parks concrete ramp just east of downtown — the closest launch to town (~RM 193).","rm":193},
 {"name":"Cleeces Ferry","lat":36.1436,"lon":-86.8908,"types":["ramp"],
  "info":"TWRA concrete ramp in West Nashville (~RM 185), below downtown.","rm":185},
]
POLY=[[36.29774,-86.65989],[36.30089,-86.66868],[36.3005,-86.67336],[36.29803,-86.67768],[36.29354,-86.68152],[36.28862,-86.68557],[36.28597,-86.68684],[36.27998,-86.68656],[36.27507,-86.68483],[36.26911,-86.68145],[36.26332,-86.67545],[36.25924,-86.67231],[36.25505,-86.66847],[36.25091,-86.66259],[36.24572,-86.65897],[36.23617,-86.64935],[36.22647,-86.64455],[36.21235,-86.63954],[36.20791,-86.63871],[36.1985,-86.64832],[36.19365,-86.65862],[36.19295,-86.66755],[36.20196,-86.6739],[36.20695,-86.67648],[36.228,-86.67768],[36.23713,-86.68197],[36.24406,-86.68643],[36.246,-86.69381],[36.24474,-86.70395],[36.23949,-86.7115],[36.23452,-86.71264],[36.22786,-86.70944],[36.21775,-86.70669],[36.2093,-86.70017],[36.19061,-86.69019],[36.18194,-86.69796],[36.17537,-86.70392],[36.16729,-86.7134],[36.16446,-86.72413],[36.16359,-86.73792],[36.16132,-86.74728],[36.15922,-86.75869],[36.16067,-86.77003],[36.16954,-86.77656],[36.17702,-86.78102],[36.18367,-86.78188],[36.19337,-86.78325],[36.19678,-86.78589],[36.20043,-86.79235],[36.20224,-86.80368],[36.20097,-86.8146],[36.19477,-86.82458],[36.18621,-86.83081],[36.17439,-86.83389],[36.1669,-86.83956],[36.16704,-86.84745],[36.17092,-86.85483],[36.17705,-86.86139],[36.18395,-86.86582],[36.19226,-86.87148],[36.20256,-86.88349],[36.20599,-86.89098],[36.2071,-86.89771],[36.20592,-86.90342],[36.20076,-86.90875],[36.19454,-86.91242],[36.18953,-86.91283],[36.18515,-86.91052],[36.17536,-86.90135],[36.16572,-86.89033],[36.15956,-86.88796],[36.14487,-86.89088],[36.13752,-86.89741],[36.13544,-86.90753],[36.1371,-86.91989]]


# ---- Old Hickory generation: the thing that actually drives this reach ----
# This page had a flow number and no schedule behind it, which is the wrong way round: the
# Nashville Cumberland is a navigable pool, so depth barely moves and CURRENT is the whole
# story — and current is Old Hickory releasing. USACE LRN publishes hourly actuals plus ~120 h
# of forecast for every project (see riverlib.dam_release).
# UNIT_CFS is an ESTIMATE, not a backtested constant: Old Hickory runs 4 Kaplan units and the
# per-unit discharge here is inferred from observed release steps, not fitted to a downstream
# gauge the way Caney's constants were (analysis/backtest_flow.py). Treat unit counts as
# indicative. Arrival lags are deliberately absent — see below.
OH_UNIT_CFS=6500
rel,rel_warn=riverlib.dam_release("OHIT1-OLD_HICKORY.Flow.Ave.1Hour.1Hour.man-rev",
                                  "Old Hickory Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast")
for w in rel_warn: print("release warn:",w)
# No arrival times on purpose. This reach is a navigable IMPOUNDMENT (Cheatham pool): a release
# raises current through the whole pool rather than sending a wading-hazard front down a shallow
# tailwater, so a Caney-style "water reaches you at 2:47" would be a confident fiction here.
GEN=riverlib.gen_days(rel,CT,unit_cfs=OH_UNIT_CFS,days=6) if rel else []
GENHINT=("Old Hickory generation, midnight\u2192midnight (bar height = units). This is a navigable pool, so "
         "depth stays put \u2014 what changes is CURRENT. Bars up means the ledges and the tailrace turn on.")
GENLEGEND=('<span><i style="background:#7db8e0"></i>1 unit</span><span><i style="background:#2f92d4"></i>2 units</span>'
           '<span><i style="background:#5e5ce6"></i>3+ units</span><span>Unit counts are estimated from release volume \u2014 verify against USACE before you rely on them.</span>')
_relnow=riverlib.release_at(rel,int(now.timestamp())//3600*3600) if rel else None
# ---- fishability: STRIPED BASS, from riverlib.striper_read ----
# This page is a striped-bass page. The grade is the striper grade: current is the trigger
# (they hold on the seam and eat what the turbines disorient), summer is refuge season, and
# heavy water is capped by boat handling rather than by the fish.
_SR=riverlib.striper_read(_relnow, OH_UNIT_CFS, now_ct.month,
                          water_f=None, at_dam=True)
FN,FG,FCOL,FNOTE=_SR["cond"],_SR["grade"],_SR["col"],_SR["note"]
BASE=riverlib.GRADE_SCORE.get(FG,1.5)

clar="rising / gen on" if trend=="rising" else "falling" if trend=="falling" else "steady"
DATA={"today":now_ct.strftime("%A, %B %-d · %-I:%M %p"),"solunar":SOL,"hatch":HATCH,"month":now_ct.month,
      "chatter":riverlib.load_intel("cumbnash"),"flysel":FLYSEL,"tips":tips,"weather":WXT,"series":series,"usace":USACE_URL,
      "cur":{"flow":round(cur_flow) if cur_flow is not None else None,"stage":round(cur_stage,1) if cur_stage is not None else None,
             "trend":trend,"cond":FN,"grade":FG,"col":FCOL,"note":FNOTE,"clar":clar,"asof":asof},
      "points":POINTS,"poly":POLY,"striper":_SR,
      "gen":GEN,"genHint":GENHINT,"genLegend":GENLEGEND,
      "genOpts":{"minLabel":"no generation \u2014 slack water","arrLabel":"current builds"},
      "relNow":round(_relnow) if _relnow is not None else None,"relUnit":OH_UNIT_CFS}

TEMPLATE=r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Cumberland River · Nashville — striper & smallmouth</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#16202b;--muted:#66788a;--faint:#93a3b3;--line:#e6ecf2;--card:#fff;--blue:#0a84ff;--green:#28c76f}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,sans-serif;
 background:radial-gradient(1000px 700px at 82% -6%,#eef1f6 0,transparent 60%),linear-gradient(180deg,#eef1f5,#e6ebf1);min-height:100vh}
.app{max-width:900px;margin:0 auto;padding:30px 22px 80px}
__SWITCH_CSS__
.eyebrow{font-size:12px;letter-spacing:.26em;text-transform:uppercase;color:var(--faint);font-weight:600}
h1{margin:6px 0 4px;font-size:33px;font-weight:750;letter-spacing:-.6px}.cap{color:var(--muted);font-size:14.5px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 26px rgba(20,50,80,.06)}
.sec{font-size:15px;font-weight:700;color:var(--ink);margin:26px 2px 12px}
.now{padding:16px 18px;margin:12px 0;display:flex;align-items:center;gap:16px}
.now .vg{flex:none;width:76px;text-align:center;color:#fff;font-weight:800;font-size:13px;padding:11px 0;border-radius:12px}
.now .b1{font-size:20px;font-weight:700}.now .b2{font-size:13.5px;color:var(--muted);margin-top:2px}
.now .rt{margin-left:auto;text-align:right;font-size:12.5px;color:var(--faint)}.now .rt b{color:var(--ink);font-size:15px;display:block}
.note0{display:flex;gap:11px;background:#eef4fb;border:1px solid #d5e3f2;border-radius:14px;padding:13px 15px;margin:12px 0;font-size:12.8px;color:#345070;line-height:1.5}.note0 b{color:#22405f}.note0 a{color:#0a5ec2;font-weight:700}
.chartc{padding:14px 12px 8px}.chartc .lgd{font-size:12px;color:var(--muted);display:flex;gap:14px;justify-content:center;margin-top:6px;flex-wrap:wrap}
.chartc .lgd i{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:5px}
.note{font-size:12px;color:var(--faint);padding:0 4px;line-height:1.5}
#lmap{height:340px;border-radius:16px}.leaflet-container{border-radius:16px;font-family:inherit}
.maptip{font-size:11.5px;color:var(--faint);text-align:center;margin:7px 0 0}
.wx{display:flex;flex-wrap:wrap}.wx .m{flex:1;min-width:110px;padding:12px 14px;border-right:1px solid var(--line)}.wx .m:last-child{border-right:0}
.wx .w{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);font-weight:600}.wx .t{font-size:24px;font-weight:700;margin:2px 0}.wx .d{font-size:12.5px;color:var(--muted)}
.wx .meta{padding:12px 14px;font-size:12.5px;color:var(--muted);display:flex;flex-direction:column;justify-content:center;gap:3px;min-width:150px}
.tips{padding:6px}.tip{display:flex;gap:12px;padding:11px 12px;border-bottom:1px solid var(--line)}.tip:last-child{border-bottom:0}.tip .i{font-size:20px}.tip .x{font-size:14px;line-height:1.5}
.regs{padding:14px 16px;font-size:13px;color:var(--muted);line-height:1.55}.regs b{color:var(--ink)}
__SOLUNAR_CSS__
__GENSCHED_CSS__
__HATCH_CSS__
__CHATTER_CSS__
__LOG_CSS__
__MOONCAL_CSS__
__FLYMATRIX_CSS__
.foot{text-align:center;color:var(--faint);font-size:11.5px;margin-top:26px;line-height:1.6}
@media(max-width:680px){.app{padding:22px 14px 60px}h1{font-size:28px}.wx .m{min-width:0}}

/* Striped-bass read. Design-system tokens only (RIVER_SPEC §4): --ink/--muted/--faint/
   --line, 18px card radius, 680px mobile breakpoint. */
.strip{padding:16px 18px}
.strip .shead{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.strip .sgrade{color:#fff;font-weight:800;font-size:12px;letter-spacing:.02em;padding:7px 12px;border-radius:11px;white-space:nowrap}
.strip .scond{font-size:13px;font-weight:700;color:var(--ink)}
.strip .snote{font-size:14px;line-height:1.5;margin-top:11px;color:var(--ink)}
.strip .smeta{display:flex;flex-wrap:wrap;gap:6px;margin-top:11px}
.strip .smeta span{font-size:11px;font-weight:650;color:#4a5a6a;background:#f0f3f7;border-radius:999px;padding:4px 10px;white-space:nowrap}
.strip .srow{display:flex;gap:10px;margin-top:10px;font-size:13px;line-height:1.45;color:var(--ink)}
.strip .srow .k{flex:none;width:52px;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);font-weight:700;padding-top:3px}
.strip .sseason{margin-top:12px;padding-top:10px;border-top:1px solid var(--line);font-size:11.5px;color:var(--faint);line-height:1.45}
@media(max-width:680px){.strip{padding:14px}.strip .srow .k{width:46px}}
</style></head><body><div class="app">
 __SWITCHER__
 <div class="eyebrow">Big-river striper & smallmouth · Old Hickory → Cheatham</div>
 <h1>Cumberland · Nashville</h1><div class="cap" id="cap"></div>
 <div class="card now" id="now"></div>
 <div class="note0" id="note0"></div>
 <div class="sec">Striped bass · today's read</div><div class="card strip" id="striper"></div>
 <div class="sec">Old Hickory generation · what turns the current on</div><div class="card gen" id="genc"></div>
 <div class="sec">Flow &amp; current · Nashville gauge (last 4 days)</div><div class="card chartc" id="chartc"></div>
 <div class="note" id="chartnote"></div>
 <div class="sec">Live map · public concrete ramps</div>
 <div class="card" style="padding:8px"><div id="lmap"></div></div>
 <div class="maptip">Real USACE / Metro / TWRA concrete ramps on the OSM channel · Old Hickory Dam → West Nashville · tap a pin for details &amp; a Google Maps link</div>
 <div class="sec">Guide's take</div><div class="card tips" id="tips"></div>
 <div class="sec">Weather</div><div class="card wx" id="wx"></div>
 <div class="sec">Moon &amp; feeding</div><div class="card sol" id="sol"></div>
 <div class="sec">Moon &amp; feeding calendar</div><div class="card mcal" id="mooncal"></div>
 <div class="sec">Forage calendar</div><div class="card hatch" id="hatch"></div>
 <div class="sec">Fly selection · clarity × light</div><div class="card" id="flysel"></div>
 <div class="sec">Regulations</div><div class="card regs" id="regs"></div>
 <div id="chatterSec" style="display:none"><div class="sec">River chatter · Reddit</div><div class="card chatter" id="chatter"></div></div>
 <div class="sec">My log</div><div class="card logc" id="log"></div>
 <div class="foot" id="foot"></div>
</div>
<script>
const D=__DATA__;
__POPUP_JS__
__MAP_JS__
__SOLUNAR_JS__
__GENSCHED_JS__
__HATCH_JS__
__CHATTER_JS__
__LOG_JS__
__MOONCAL_JS__
__FLYMATRIX_JS__
document.getElementById('cap').innerHTML=D.today+' · Cumberland River at Nashville gauge (USGS 03431500)';
(function(){const c=D.cur;document.getElementById('now').innerHTML=
 '<div class="vg" style="background:'+c.col+'">'+c.cond+'</div>'
 +'<div><div class="b1">'+(c.flow!=null?c.flow.toLocaleString()+' cfs':'—')+(c.stage!=null?' · '+c.stage+' ft':'')+' <span style="font-size:14px;color:var(--muted)">'+(c.trend==='rising'?'↑ current rising':c.trend==='falling'?'↓ easing':'→ steady')+'</span></div>'
 +'<div class="b2">'+c.note+'</div></div>'
 +'<div class="rt"><b>'+c.grade+'</b>'+c.clar+'<br><span style="font-size:11px">as of '+c.asof+' · at Nashville</span></div>';})();
document.getElementById('note0').innerHTML='<div style="font-size:16px">🚤</div><div><b>Current, not depth, is the game.</b> This reach is a navigable impoundment — always deep enough to float and run — so plan around <b>Old Hickory generation</b>. Turbines on = current & feeding fish; dam idle = slack & slow. Check the <a href="'+D.usace+'" target="_blank" rel="noopener">USACE Nashville District release</a> before you launch, and mind barge traffic in the channel.</div>';
(function(){const S=D.series;if(!S.length){document.getElementById('chartc').innerHTML='<div style="padding:20px;color:var(--muted)">gauge data unavailable</div>';return;}
 const W=860,H=200,pad=46,fs=S.map(p=>p.f),fmax=Math.max(12000,...fs)*1.12,fmin=0;
 const x=i=>pad+i*(W-pad-10)/(S.length-1),y=f=>H-24-(f-fmin)/(fmax-fmin)*(H-44);
 function band(a,b,col){const yb=y(Math.min(b,fmax));return '<rect x="'+pad+'" y="'+yb+'" width="'+(W-pad-10)+'" height="'+Math.max(0,(y(a)-yb))+'" fill="'+col+'"/>';}
 let bands=band(0,7000,'rgba(242,168,50,.12)')+band(7000,30000,'rgba(40,199,111,.14)')+band(30000,fmax,'rgba(139,108,239,.12)');
 let path='';S.forEach((p,i)=>{path+=(path?' L':'M')+x(i).toFixed(0)+','+y(p.f).toFixed(0);});
 let ax='';for(let i=0;i<S.length;i+=Math.ceil(S.length/6)){ax+='<text x="'+x(i)+'" y="'+(H-6)+'" font-size="10" fill="#93a3b3" text-anchor="middle">'+S[i].t.split(' ')[0]+'</text>';}
 [7000,30000].forEach(g=>{ax+='<line x1="'+pad+'" y1="'+y(g)+'" x2="'+(W-10)+'" y2="'+y(g)+'" stroke="#dfe7ee" stroke-dasharray="4 4"/><text x="4" y="'+(y(g)+3)+'" font-size="9" fill="#93a3b3">'+(g/1000)+'k</text>';});
 document.getElementById('chartc').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" width="100%">'+bands
  +'<path d="'+path+'" fill="none" stroke="#3a5a8c" stroke-width="2.5"/>'+ax+'</svg>'
  +'<div class="lgd"><span><i style="background:rgba(242,168,50,.6)"></i>slack / no gen</span><span><i style="background:rgba(40,199,111,.6)"></i>generating — bite on</span><span><i style="background:rgba(139,108,239,.5)"></i>high</span></div>';})();
document.getElementById('chartnote').textContent='Discharge at the Nashville gauge tracks Old Hickory generation — the pulses up and down ARE the turbines cycling. Rising discharge = current turning on = feeding window. The impoundment keeps depth constant regardless.';
(function(){let h='';D.tips.forEach(t=>h+='<div class="tip"><div class="i">'+t[0]+'</div><div class="x">'+t[1]+'</div></div>');document.getElementById('tips').innerHTML=h;})();
(function(){const w=D.weather,el=document.getElementById('wx');if(!w){el.innerHTML='<div class="meta">weather unavailable</div>';return;}
 let h='';(w.snaps||[]).forEach(s=>h+='<div class="m"><div class="w">'+s.when+'</div><div class="t">'+s.ico+' '+s.temp+'°</div><div class="d">'+s.sky+' · '+s.wind+' mph'+(s.precip?' · '+s.precip+'%':'')+'</div></div>');
 h+='<div class="meta"><div>High '+(w.hi??'–')+'° · Low '+(w.lo??'–')+'°</div><div>Sun '+w.sunrise+'–'+w.sunset+'</div></div>';el.innerHTML=h;})();
renderSolunar('sol',D.solunar,D.cur.grade==='Prime'?'Current on during a major feeding window — that overlap is when the big stripers hunt.':null);
renderHatch('hatch',D.hatch,D.month);
if(D.gen&&D.gen.length){buildGenSchedule('genc',D.gen,D.genHint,D.genLegend,D.genOpts);}
else{document.getElementById('genc').innerHTML='<div style="padding:14px;color:#66788a;font-size:13px">Old Hickory release schedule unavailable right now (USACE feed). The gauge below still shows what the river is doing.</div>';}
(function(){
  const S=D.striper,el=document.getElementById('striper'); if(!S||!el)return;
  // Each figure is attributed to its own measurement — the release and the downstream gauge
  // are different numbers and were previously run together in one caption.
  const chips=[];
  if(D.relNow!=null) chips.push(D.relNow.toLocaleString()+' cfs release');
  if(D.cur&&D.cur.flow!=null) chips.push(D.cur.flow.toLocaleString()+' cfs at Nashville');
  el.innerHTML='<div class="shead"><span class="sgrade" style="background:'+S.col+'">'+S.grade+'</span>'
    +'<span class="scond">'+S.cond+'</span></div>'
    +(chips.length?'<div class="smeta"><span>'+chips.join('</span><span>')+'</span></div>':'')
    +'<div class="snote">'+S.note+'</div>'
    +(S.where?'<div class="srow"><span class="k">Where</span><span>'+S.where+'</span></div>':'')
    +(S.technique?'<div class="srow"><span class="k">How</span><span>'+S.technique+'</span></div>':'')
    +'<div class="sseason">'+S.season.toUpperCase()+' \u00b7 '+(S.season_note||'')+'</div>';
})();
buildMoonCal('mooncal',36.17,-86.74);
buildFlyMatrix('flysel',D.flysel);
document.getElementById('regs').innerHTML='<b>Regulations.</b> '+__REGS__;
renderChatter('chatter',D.chatter,'chatterSec');
buildLog('log','riverlog-cumbnash',D.points.map(p=>p.name),null);
document.getElementById('foot').textContent='Flow & stage: USGS 03431500 (Cumberland River at Nashville). Depth is stable (navigable pool); current tracks Old Hickory generation — verify the USACE Nashville District release. Fishability is an estimate — tune from the water. Weather: Open-Meteo. Channel & ramps from OpenStreetMap. Personal use.';
buildRiverMap(D,'#3a5a8c');
</script></body></html>"""
html=(riverlib.render(TEMPLATE,"cumbnash")
      .replace("__REGS__",json.dumps(CFG["regs"]))
      .replace("__DATA__",json.dumps(DATA)))
open(os.path.join(OUT,"cumbnash.html"),"w").write(html)

# ---- HQ day state: what the board shows for this river today / tomorrow ----
# Vessel is always boat here and that is not a hedge: this is a navigable impoundment,
# so there is no wadeable water at any release. Clarity is INFERRED from release volume
# (higher release carries more colour on this river) and is labelled as inferred,
# because nothing measures turbidity on this reach.
def _lvl(c):
    if c is None: return "unknown", ""
    if c < 7000:  return "low",   "%s cfs release · little current" % format(round(c), ",")
    if c < 15000: return "prime", "%s cfs release · current on" % format(round(c), ",")
    if c < 30000: return "high",  "%s cfs release · heavy" % format(round(c), ",")
    return "blown", "%s cfs release · blown out" % format(round(c), ",")
def _clr(c):
    if c is None: return "unknown"
    return "clear" if c < 7000 else "stained" if c < 15000 else "colored" if c < 30000 else "muddy"
def _dayst(off):
    d0, _ = riverlib.day_bounds(CT, off)
    cv = riverlib.hourly_curve(lambda k: riverlib.release_at(rel, k), d0) if rel else None
    # Median of the fishing hours (6am-8pm), not a single sample: a one-hour probe lands
    # in a lull on a split-generation day and reports "low" while the river runs 13k.
    dayvals = sorted(x for x in (cv or [])[6:21] if x is not None)
    mid = dayvals[len(dayvals) // 2] if dayvals else None
    lk, ld = _lvl(mid)
    # Count generation in DAYLIGHT only. A 12am-6am release is 6 hours of "generating"
    # that nobody fishes; reporting it as the day's headline sends you to a slack river.
    on = [h for h in range(6, 21) if (cv or [None]*24)[h] and cv[h] >= OH_UNIT_CFS]
    gen_hrs = len(on)
    def _ap(h): return ("%d%s" % (h % 12 or 12, "am" if h < 12 else "pm"))
    span = (" (%s–%s)" % (_ap(on[0]), _ap(on[-1] + 1))) if on else ""
    night = any((cv or [None]*24)[h] and cv[h] >= OH_UNIT_CFS for h in list(range(0, 6)) + list(range(21, 24)))
    return riverlib.day_state(
        vessel=riverlib.craft_label("cumbnash", mid)[0],
        vessel_why=riverlib.craft_label("cumbnash", mid)[2],
        clarity=_clr(mid), clarity_why="inferred from release volume, not measured",
        level=lk, level_detail=ld,
        curve=cv, curve_unit="cfs", curve_label="Old Hickory release", curve_src="forecast",
        headline=("Old Hickory generating %d h%s" % (gen_hrs, span)) if gen_hrs
                 else ("Generation overnight only — slack through the day" if night
                       else "No generation — slack water"))
DAYS = {"today": _dayst(0), "tomorrow": _dayst(1)}

# TWO DIFFERENT MEASUREMENTS, never to be shown as one. The unit count comes from the Old
# Hickory RELEASE (CWMS); cur_flow is the USGS gauge at Nashville, ~25 river miles down, which
# includes the Stones River and other tributary inflow and lags the release. They differed by
# 9,248 cfs when this was caught, so the card read "1 unit \u00b7 15,700 cfs" — and 15,700 would be
# 2.4 units. Each number is now labelled with where it came from.
_rel_txt=("%s cfs release"%format(round(_relnow),",")) if _relnow is not None else "release n/a"
_gauge_txt=("%s cfs at Nashville"%format(round(cur_flow),",")) if cur_flow is not None else ""
riverlib.emit_status("cumbnash",
    {"grade":FG,"cond":(FN+" at the dam"),"col":FCOL,"note":FNOTE,
     "detail":" \u00b7 ".join(x for x in (_rel_txt,_gauge_txt) if x),"asof":asof},
    wx, BASE, CT, ["Striped bass"],
    "Warmwater big river", "~15–30 min · in Nashville", days=DAYS)
print("wrote out/cumbnash.html | flow %s cfs %s | grade %s | series %d"%(cur_flow,trend,FG,len(series)))
