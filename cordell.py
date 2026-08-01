#!/usr/bin/env python3
"""
Cumberland River · Cordell Hull tailwater — Cordell Hull Dam (Carthage) into Old Hickory Lake.
Warmwater big-river model driven by generation. There is NO active USGS gauge on this reach
(Celina 03417500 is above the dam), so unlike the other Cumberland pages the flow signal here
IS the release: USACE LRN hourly actual + ~120 h forecast. Smallmouth, white bass & panfish.
The Caney Fork enters at Carthage just below the dam. Sources: USACE CWMS, Open-Meteo, OSM.
"""
import json,urllib.request,datetime,os,sys
from zoneinfo import ZoneInfo
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import riverlib
CT=ZoneInfo("America/Chicago"); UA={"User-Agent":"cordell/1.0"}
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"out"); os.makedirs(OUT,exist_ok=True)
def get(u,h=None):
    # riverlib.get retries transient TLS/DNS/5xx failures; a single flaky fetch used to
    # build this page with missing data instead of failing (see riverlib.get docstring).
    return riverlib.get(u,{**UA,**(h or {})},timeout=60)
now=datetime.datetime.now(datetime.timezone.utc); now_ct=now.astimezone(CT)
CFG=riverlib.RIVER_CONFIG["cordell"]    # no SITE: this reach runs on the release, not a gauge
GLAT,GLON=36.28,-85.95
USACE_URL="https://www.lrn-wc.usace.army.mil/basin_project.shtml?p=cord"

# ---- release IS the hydrograph here (no USGS gauge on this reach) ----
# Cordell Hull runs 3 units. UNIT_CFS is an ESTIMATE inferred from observed release steps,
# not fitted to a downstream gauge — there isn't one to fit to. The legend says so on the page.
UNIT_CFS=8000
rel,rel_warn=riverlib.dam_release("COHT1-CORDELL_HULL.Flow.Ave.1Hour.1Hour.man-rev",
                                  "Cordell Hull Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast")
for w in rel_warn: print("release warn:",w)
_nowk=int(now.timestamp())//3600*3600
FLOW=[(datetime.datetime.fromtimestamp(k,CT),v) for k,v in sorted(rel.items()) if k<=_nowk]
FLOW.sort()
cur_flow=FLOW[-1][1] if FLOW else None
cur_stage=None   # no stage series on this reach
asof=(FLOW[-1][0].astimezone(CT).strftime("%-I:%M %p") if FLOW else now_ct.strftime("%-I:%M %p"))
trend="steady"
if len(FLOW)>=2:
    ref=next((o for o in reversed(FLOW) if (FLOW[-1][0]-o[0]).total_seconds()>=4*3600), FLOW[0])
    dv=FLOW[-1][1]-ref[1]
    trend="rising" if dv>1500 else "falling" if dv<-1500 else "steady"

# ---- fishability: current (=generation), not depth ----
def fish(flow,rising):
    if flow is None: return ("—","Fair","#94a3b1",1.3,"no gauge data — check the Cordell Hull release schedule")
    if flow>30000: return ("High","Fair","#8b6cef",1.3,"heavy, stained flow — fish eddies, creek mouths & the slack behind wing dams")
    if flow>=7000:
        return ("Gen","Prime" if rising else "Good","#28c76f",(2.9 if rising else 2.3),
            ("current's on and rising — prime; stripers & smallmouth feeding on the ledges & tailrace" if rising
             else "current's on — stripers & smallmouth working the ledges & tailrace"))
    return ("Slack","Slow","#f2a832",0.9,"little current — Cordell Hull idle; slow-fish the ledges, wing dams & structure")
FN,FG,FCOL,BASE,FNOTE=fish(cur_flow,trend=="rising")

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
 {"name":"Bluegill / panfish","icon":"🐡","pattern":"popper & bream bug on the beds","m":[0,0,1,2,3,3,3,3,2,1,0,0]},
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
  "sources":[["TWRA Cordell Hull","https://www.tn.gov/twra/fishing/where-to-fish/middle-tennessee-r2/cordell-hull-reservoir.html"],["USACE Nashville District","https://www.lrn-wc.usace.army.mil/basin_project.shtml?p=cord"]]}

tips=[["🌊","It's all about current. Depth is stable — you won't ground out on this navigable pool — so plan around Cordell Hull GENERATION, not level. Dam idle → slack, slow fishing. Turbines on → the ledges and tailrace light up. Check the USACE Nashville District release before you launch."]]
if cur_flow is not None and cur_flow>=7000:
    tips.append(["🎣","Current's on — go. Swing a Clouser or Deceiver on a sink-tip through the tailrace and down-current of the wing dams and ledges. Stripers, hybrids, white bass & big smallmouth stack where the current breaks."])
else:
    tips.append(["🐟","Slack water — slow down. Work a crawfish or Woolly Bugger deep along the ledges, and throw a popper up top at first light. The bite turns back on the moment they start generating."])
tips.append(["🚤","Big water, big boat sense — the navigation channel carries barge traffic. Cross it, don't idle in it, and take big wakes at an angle. Wing dams and rock ledges lurk just under the surface all through the metro reach."])
tips.append(["🐡","Slack backwaters and bank cover hold bluegill & panfish — a small popper or bream bug on a light rod is a fun change-up while you wait on the generation."])

POINTS=[
 {"name":"Cordell Hull Dam Tailwater","lat":36.285278,"lon":-85.939722,"types":["ramp"],
  "info":"USACE Cordell Hull Dam tailwater access, below the lock and dam at Carthage. Official USACE location (LRN, CORT1). Strong current when they generate; stay off the dam.","rm":313},
]
# NOTE (RIVER_SPEC §2): the ONE access point verified against an authority (USACE CWMS
# official location + coordinates). OSM slipways nearby are unnamed and several sit on
# Cordell Hull LAKE above the dam rather than the tailwater, so they are omitted rather
# than guessed onto the wrong water. Add real ramps once verified.
POLY=[[36.26815, -85.90583], [36.27314, -85.90991], [36.28655, -85.91429], [36.29313, -85.91455], [36.30046, -85.91562], [36.30389, -85.91913], [36.26753, -85.92363], [36.25586, -85.92422], [36.26026, -85.92433], [36.27259, -85.92441], [36.25244, -85.92489], [36.27548, -85.92508], [36.30724, -85.92596], [36.27662, -85.92656], [36.24967, -85.92662], [36.24633, -85.92974], [36.30658, -85.93218], [36.27974, -85.93266], [36.28303, -85.93614], [36.24108, -85.93728], [36.28522, -85.93825], [36.24008, -85.93938], [36.28717, -85.93941], [36.30344, -85.94081], [36.28901, -85.94108], [36.24, -85.94254], [36.29079, -85.94301], [36.2424, -85.94611], [36.29408, -85.94612], [36.30023, -85.94618], [36.29626, -85.9474], [36.24505, -85.94946], [36.24781, -85.95394], [36.25101, -85.95689], [36.25829, -85.95935], [36.26365, -85.96119], [36.26015, -85.96449], [36.26783, -85.96572], [36.26196, -85.96776], [36.26862, -85.96969], [36.26289, -85.97003], [36.26891, -85.97214], [36.26929, -85.97773], [36.26835, -85.98628], [36.26816, -85.99198], [36.29194, -85.99799], [36.26598, -86.00041], [36.28674, -86.00215], [36.29777, -86.00246], [36.28254, -86.00538], [36.2788, -86.00689], [36.26645, -86.00735], [36.30047, -86.00821], [36.27447, -86.009], [36.26787, -86.00981], [36.30206, -86.01319], [36.30002, -86.01969], [36.29639, -86.02189], [36.2925, -86.02622], [36.28875, -86.0297], [36.28601, -86.03456], [36.28687, -86.04036], [36.2903, -86.04505], [36.2934, -86.04754], [36.297, -86.04852], [36.30801, -86.05022], [36.30067, -86.05022], [36.28859, -86.05282], [36.31189, -86.05438], [36.29469, -86.05456], [36.28428, -86.05623], [36.29683, -86.05776], [36.31311, -86.05817], [36.28113, -86.05883], [36.27752, -86.06068], [36.31296, -86.06094], [36.272, -86.06242], [36.299, -86.06268], [36.31163, -86.06395], [36.26864, -86.06499], [36.33142, -86.06717], [36.31048, -86.06739], [36.33449, -86.06758], [36.32882, -86.06765], [36.33576, -86.06807], [36.32749, -86.06818], [36.33679, -86.06867], [36.30863, -86.06895], [36.30319, -86.06907], [36.33778, -86.06942], [36.26457, -86.06988], [36.32396, -86.0703], [36.30498, -86.07031], [36.33871, -86.07032], [36.26347, -86.07219], [36.33994, -86.07242], [36.31754, -86.07549], [36.34107, -86.07597], [36.26344, -86.07627], [36.31354, -86.07859], [36.3416, -86.07873], [36.31221, -86.07996], [36.3419, -86.08019], [36.31055, -86.08187], [36.2665, -86.08225], [36.34197, -86.08231], [36.26966, -86.08456], [36.30863, -86.08486], [36.3416, -86.08708], [36.30681, -86.08811], [36.27301, -86.0885], [36.30531, -86.09001], [36.27833, -86.09098], [36.30398, -86.09115], [36.28309, -86.09366], [36.29839, -86.0954], [36.28686, -86.09584], [36.2967, -86.09647], [36.28883, -86.0966], [36.2953, -86.09708], [36.29078, -86.09712], [36.34178, -86.09767], [36.34408, -86.10568], [36.34555, -86.11434], [36.34616, -86.11919], [36.34775, -86.12913], [36.3487, -86.13418], [36.34895, -86.13902], [36.34857, -86.14492], [36.34899, -86.15372], [36.35102, -86.15798], [36.3556, -86.16023], [36.36334, -86.16449], [36.37064, -86.16772], [36.37316, -86.17383], [36.32829, -86.17597], [36.37365, -86.17703], [36.32567, -86.1773], [36.3346, -86.17749], [36.37363, -86.17792], [36.33779, -86.17877], [36.3236, -86.17887], [36.37342, -86.17942], [36.32216, -86.18024], [36.37307, -86.18049], [36.34233, -86.1808], [36.37259, -86.1815], [36.32115, -86.18153], [36.34492, -86.18185], [36.37205, -86.18215], [36.3471, -86.18252], [36.32051, -86.18258], [36.37144, -86.18263], [36.35058, -86.18329], [36.3596, -86.18343], [36.36907, -86.18352], [36.35324, -86.18353], [36.32, -86.18355], [36.36809, -86.18379], [36.31967, -86.18463], [36.32066, -86.18951], [36.32376, -86.1944], [36.32789, -86.19936]]


# ---- generation schedule off the release fetched above ----
# No arrival times: the tailwater feeds Old Hickory Lake, so a release raises current through
# a pool rather than sending a wading front down a shallow tailwater.
GEN=riverlib.gen_days(rel,CT,unit_cfs=UNIT_CFS,days=6) if rel else []
GENHINT=("Cordell Hull generation, midnight\u2192midnight (bar height = units). No gauge on this reach \u2014 the release IS the signal. Bars up means current through the Carthage bends and the tailrace.")
GENLEGEND=('<span><i style="background:#7db8e0"></i>1 unit</span><span><i style="background:#2f92d4"></i>2 units</span>'
           '<span><i style="background:#5e5ce6"></i>3+ units</span><span>Unit counts are estimated from release volume \u2014 verify against USACE before you rely on them.</span>')
_relnow=riverlib.release_at(rel,int(now.timestamp())//3600*3600) if rel else None

clar="rising / gen on" if trend=="rising" else "falling" if trend=="falling" else "steady"
DATA={"today":now_ct.strftime("%A, %B %-d · %-I:%M %p"),"solunar":SOL,"hatch":HATCH,"month":now_ct.month,
      "chatter":riverlib.load_intel("cordell"),"flysel":FLYSEL,"tips":tips,"weather":WXT,"series":series,"usace":USACE_URL,
      "cur":{"flow":round(cur_flow) if cur_flow is not None else None,"stage":round(cur_stage,1) if cur_stage is not None else None,
             "trend":trend,"cond":FN,"grade":FG,"col":FCOL,"note":FNOTE,"clar":clar,"asof":asof},
      "points":POINTS,"poly":POLY,
      "gen":GEN,"genHint":GENHINT,"genLegend":GENLEGEND,
      "genOpts":{"minLabel":"no generation \u2014 slack water","arrLabel":"current builds"},
      "relNow":round(_relnow) if _relnow is not None else None,"relUnit":UNIT_CFS}

TEMPLATE=r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Cumberland River · Cordell Hull tailwater — smallmouth & white bass</title>
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
</style></head><body><div class="app">
 __SWITCHER__
 <div class="eyebrow">Big-river striper &amp; smallmouth · Cordell Hull Dam → Old Hickory Lake</div>
 <h1>Cumberland · Cordell Hull</h1><div class="cap" id="cap"></div>
 <div class="card now" id="now"></div>
 <div class="note0" id="note0"></div>
 <div class="sec">Cordell Hull generation · the only flow signal on this reach</div><div class="card gen" id="genc"></div>
 <div class="sec">Observed release · Cordell Hull (last 4 days)</div><div class="card chartc" id="chartc"></div>
 <div class="note" id="chartnote"></div>
 <div class="sec">Live map · public concrete ramps</div>
 <div class="card" style="padding:8px"><div id="lmap"></div></div>
 <div class="maptip">USACE Cordell Hull Dam tailwater on the OSM channel · Carthage → Old Hickory Lake · tap a pin for details &amp; a Google Maps link</div>
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
document.getElementById('cap').innerHTML=D.today+' · Cordell Hull release (USACE LRN · COHT1)';
(function(){const c=D.cur;document.getElementById('now').innerHTML=
 '<div class="vg" style="background:'+c.col+'">'+c.cond+'</div>'
 +'<div><div class="b1">'+(c.flow!=null?c.flow.toLocaleString()+' cfs':'—')+(c.stage!=null?' · '+c.stage+' ft':'')+' <span style="font-size:14px;color:var(--muted)">'+(c.trend==='rising'?'↑ current rising':c.trend==='falling'?'↓ easing':'→ steady')+'</span></div>'
 +'<div class="b2">'+c.note+'</div></div>'
 +'<div class="rt"><b>'+c.grade+'</b>'+c.clar+'<br><span style="font-size:11px">as of '+c.asof+' · at Cordell Hull Dam</span></div>';})();
document.getElementById('note0').innerHTML='<div style="font-size:16px">🚤</div><div><b>Current, not depth, is the game.</b> This reach is a navigable impoundment — always deep enough to float and run — so plan around <b>Cordell Hull generation</b>. Turbines on = current & feeding fish; dam idle = slack & slow. Check the <a href="'+D.usace+'" target="_blank" rel="noopener">USACE Nashville District release</a> before you launch, and mind barge traffic in the channel.</div>';
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
document.getElementById('chartnote').textContent='The plotted line IS the USACE Cordell Hull release — the pulses up and down ARE the turbines cycling. Rising release = current turning on = feeding window. The impoundment keeps depth constant regardless.';
(function(){let h='';D.tips.forEach(t=>h+='<div class="tip"><div class="i">'+t[0]+'</div><div class="x">'+t[1]+'</div></div>');document.getElementById('tips').innerHTML=h;})();
(function(){const w=D.weather,el=document.getElementById('wx');if(!w){el.innerHTML='<div class="meta">weather unavailable</div>';return;}
 let h='';(w.snaps||[]).forEach(s=>h+='<div class="m"><div class="w">'+s.when+'</div><div class="t">'+s.ico+' '+s.temp+'°</div><div class="d">'+s.sky+' · '+s.wind+' mph'+(s.precip?' · '+s.precip+'%':'')+'</div></div>');
 h+='<div class="meta"><div>High '+(w.hi??'–')+'° · Low '+(w.lo??'–')+'°</div><div>Sun '+w.sunrise+'–'+w.sunset+'</div></div>';el.innerHTML=h;})();
renderSolunar('sol',D.solunar,D.cur.grade==='Prime'?'Current on during a major feeding window — that overlap is when the big stripers hunt.':null);
renderHatch('hatch',D.hatch,D.month);
if(D.gen&&D.gen.length){buildGenSchedule('genc',D.gen,D.genHint,D.genLegend,D.genOpts);}
else{document.getElementById('genc').innerHTML='<div style="padding:14px;color:#66788a;font-size:13px">Cordell Hull release schedule unavailable right now (USACE feed). The gauge below still shows what the river is doing.</div>';}
buildMoonCal('mooncal',36.28,-85.95);
buildFlyMatrix('flysel',D.flysel);
document.getElementById('regs').innerHTML='<b>Regulations.</b> '+__REGS__;
renderChatter('chatter',D.chatter,'chatterSec');
buildLog('log','riverlog-cordell',D.points.map(p=>p.name),null);
document.getElementById('foot').textContent='No USGS gauge on this reach — the plotted flow IS the USACE Cordell Hull release (LRN, COHT1), hourly actual plus forecast. Verify against the USACE Nashville District schedule.'+' Fishability is an estimate — tune from the water. Weather: Open-Meteo. Channel & ramps from OpenStreetMap. Personal use.';
buildRiverMap(D,'#3a5a8c');
</script></body></html>"""
html=(riverlib.render(TEMPLATE,"cordell")
      .replace("__REGS__",json.dumps(CFG["regs"]))
      .replace("__DATA__",json.dumps(DATA)))
open(os.path.join(OUT,"cordell.html"),"w").write(html)

# ---- HQ day state: what the board shows for this river today / tomorrow ----
# Vessel is always boat here and that is not a hedge: this is a navigable impoundment,
# so there is no wadeable water at any release. Clarity is INFERRED from release volume
# (higher release carries more colour on this river) and is labelled as inferred,
# because nothing measures turbidity on this reach.
def _lvl(c):
    if c is None: return "unknown", ""
    if c < 7000:  return "low",   "%s cfs · little current" % format(round(c), ",")
    if c < 15000: return "prime", "%s cfs · current on" % format(round(c), ",")
    if c < 30000: return "high",  "%s cfs · heavy" % format(round(c), ",")
    return "blown", "%s cfs · blown out" % format(round(c), ",")
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
    on = [h for h in range(6, 21) if (cv or [None]*24)[h] and cv[h] >= UNIT_CFS]
    gen_hrs = len(on)
    def _ap(h): return ("%d%s" % (h % 12 or 12, "am" if h < 12 else "pm"))
    span = (" (%s–%s)" % (_ap(on[0]), _ap(on[-1] + 1))) if on else ""
    night = any((cv or [None]*24)[h] and cv[h] >= UNIT_CFS for h in list(range(0, 6)) + list(range(21, 24)))
    return riverlib.day_state(
        vessel=riverlib.craft_label("cordell", mid)[0],
        vessel_why=riverlib.craft_label("cordell", mid)[2],
        clarity=_clr(mid), clarity_why="inferred from release volume, not measured",
        level=lk, level_detail=ld,
        curve=cv, curve_unit="cfs", curve_label="Cordell Hull release", curve_src="forecast",
        headline=("Cordell Hull generating %d h%s" % (gen_hrs, span)) if gen_hrs
                 else ("Generation overnight only — slack through the day" if night
                       else "No generation — slack water"))
DAYS = {"today": _dayst(0), "tomorrow": _dayst(1)}

riverlib.emit_status("cordell",
    {"grade":FG,"cond":FN,"col":FCOL,"note":FNOTE,"detail":(("%s cfs"%format(round(cur_flow),",")) if cur_flow is not None else "—"),"asof":asof},
    wx, BASE, CT, ["Smallmouth","Largemouth","White bass","Panfish"],
    "Warmwater big river", "~1 hr E of Nashville", days=DAYS)
print("wrote out/cordell.html | flow %s cfs %s | grade %s | series %d"%(cur_flow,trend,FG,len(series)))
