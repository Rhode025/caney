#!/usr/bin/env python3
"""
Harpeth River (Hwy 100 -> the Cumberland confluence) — smallmouth planner.
A DIFFERENT model from the Caney: the Harpeth isn't dam-generation-driven, so this is
observation-based — current level + trend (USGS 03434500 near Kingston Springs) drives
fishability, with the 5-day river forecast as the outlook. Smallmouth love falling,
clearing water in the ~1-2.5 kcfs range. Sources: NOAA NWPS, USGS, Open-Meteo.
"""
import json,urllib.request,urllib.parse,datetime,math,os,sys
from zoneinfo import ZoneInfo
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import riverlib
CT=ZoneInfo("America/Chicago"); UA={"User-Agent":"harpeth/1.0"}
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"out"); os.makedirs(OUT,exist_ok=True)
def get(u,h=None):
    # riverlib.get retries transient TLS/DNS/5xx failures; a single flaky fetch used to
    # build this page with missing data instead of failing (see riverlib.get docstring).
    return riverlib.get(u,{**UA,**(h or {})},timeout=60)
now=datetime.datetime.now(datetime.timezone.utc); now_ct=now.astimezone(CT)
GLAT,GLON=36.12,-87.05   # Harpeth corridor, Cheatham/Davidson Co

# ---- NWS NWPS gauge: observed + forecast stage(ft)/flow(kcfs) ----
KING_SITE="03434500"      # Harpeth near Kingston Springs — the lowest gauge before the Cumberland
OBS=[]; FC=[]             # FC stays EMPTY: NWPS has no forecast point anywhere on the Harpeth
try:
    _ts=get("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=%s&period=P5D&parameterCd=00060,00065"%KING_SITE)["value"]["timeSeries"]
    _q={}; _st={}
    for _s in _ts:
        _code=_s["variable"]["variableCode"][0]["value"]
        for _p in _s["values"][0]["value"]:
            try: _v=float(_p["value"])
            except Exception: continue
            if _v<0: continue
            _t=datetime.datetime.fromisoformat(_p["dateTime"])
            (_q if _code=="00060" else _st)[_t]=_v
    for _t in sorted(_q):
        # (time, stage ft, flow kcfs) — the shape the rest of this generator expects
        OBS.append((_t,_st.get(_t),_q[_t]/1000.0))
except Exception as e: print("usgs warn:",e)
OBS.sort(); FC.sort()
cur_stage=OBS[-1][1] if OBS else (FC[0][1] if FC else None)
cur_flow=OBS[-1][2] if OBS else (FC[0][2] if FC else None)   # kcfs
# trend: change over last ~6h of obs
trend="steady";
if len(OBS)>=2:
    ref=next((o for o in reversed(OBS) if (OBS[-1][0]-o[0]).total_seconds()>=5*3600), OBS[0])
    dv=OBS[-1][2]-ref[2]
    trend="rising" if dv>0.15 else "falling" if dv<-0.15 else "steady"

# ---- weather + rain (Open-Meteo) ----
wx=None
try:
    wx=get("https://api.open-meteo.com/v1/forecast?latitude=%.2f&longitude=%.2f"
           "&hourly=temperature_2m,precipitation_probability,cloud_cover,wind_speed_10m,surface_pressure"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone=America%%2FChicago&forecast_days=7"%(GLAT,GLON))
except Exception as e: print("wx warn:",e)

# ---- fishability (smallmouth, flow in kcfs + trend) ----
def fish(flow,rising,falling):
    if flow is None: return ("—","Fair","#94a3b1","no data")
    if flow>4.5: return ("Blown","Tough","#8b6cef","high & muddy — sit it out or fish a feeder creek")
    if flow>2.5: return ("High","Good" if falling else "Fair","#f2a832",
        ("up but dropping — fish the banks, eddies & creek mouths" if falling else "up & rising — off-color, slow & bright" if rising else "up — off-color; work the banks & eddies"))
    if flow>=0.9: return ("Prime","Prime" if falling else "Good","#28c76f",
        ("dropping & clearing — ideal; wade the shoals, crawfish & topwater" if falling else "in the zone; clarity firming up"))
    return ("Low","Fair","#20b2aa","skinny & clear — small water, light tackle, dawn/dusk topwater")
FN,FG,FC_,FNOTE=fish(cur_flow,trend=="rising",trend=="falling")

# ---- 5-day outlook from the forecast (daily representative flow ~ midday, else min) ----
def day_flow(d):
    pts=[(t.astimezone(CT),v) for t,s,v in FC if t.astimezone(CT).date()==d]
    pts+=[(t.astimezone(CT),v) for t,s,v in OBS if t.astimezone(CT).date()==d]
    if not pts: return None
    noon=min(pts,key=lambda p:abs(p[0].hour-13)); return noon[1]
def stage_for(d):
    pts=[(t.astimezone(CT),s) for t,s,v in FC if t.astimezone(CT).date()==d]+[(t.astimezone(CT),s) for t,s,v in OBS if t.astimezone(CT).date()==d]
    if not pts: return None
    return min(pts,key=lambda p:abs(p[0].hour-13))[1]
_OUTLOOK_BASE=[]; prevf=cur_flow
for i in range(6):
    d=now_ct.date()+datetime.timedelta(days=i); f=day_flow(d)
    if f is None: continue
    dv=(f-prevf) if prevf is not None else 0; ris=dv>0.15; fal=dv<-0.15; prevf=f
    nm,g,col,note=fish(f,ris,fal)
    tr="↑" if ris else "↓" if fal else "→"
    wxd=None
    if wx:
        ds=d.strftime("%Y-%m-%d")
        if ds in wx["daily"]["time"]:
            j=wx["daily"]["time"].index(ds); wxd={"hi":round(wx["daily"]["temperature_2m_max"][j]),"lo":round(wx["daily"]["temperature_2m_min"][j]),"pop":wx["daily"]["precipitation_probability_max"][j]}
    _OUTLOOK_BASE.append({"label":("Today" if i==0 else d.strftime("%a")),"date":d.strftime("%-m/%-d"),
        "flow":round(f,2),"stage":round(stage_for(d) or 0,1),"trend":tr,"cond":nm,"grade":g,"col":col,"note":note,"wx":wxd})

# forecast series for the chart (kcfs over time), obs + forecast
series=[]
for t,s,v in OBS[-8:]: series.append({"t":t.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(v,2),"obs":True})
for t,s,v in FC: series.append({"t":t.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(v,2),"obs":False})

# weather digest (tomorrow-ish / today)
def wxday(di):
    if not wx: return None
    H=wx["hourly"]; idx={x:i for i,x in enumerate(H["time"])}
    d=now_ct.date()+datetime.timedelta(days=di)
    def at(hr):
        k=datetime.datetime(d.year,d.month,d.day,hr).strftime("%Y-%m-%dT%H:00"); return idx.get(k)
    def snap(hr,lab):
        i=at(hr)
        if i is None: return None
        cc=H["cloud_cover"][i]; pp=H["precipitation_probability"][i] or 0
        ico="☀️" if cc<25 else "⛅" if cc<65 else "☁️"
        if pp>=45: ico="🌧️"
        return {"when":lab,"temp":round(H["temperature_2m"][i]),"sky":"clear" if cc<25 else "partly cloudy" if cc<65 else "overcast","ico":ico,"wind":round(H["wind_speed_10m"][i]),"precip":pp}
    D=wx["daily"]; ds=d.strftime("%Y-%m-%d"); j=D["time"].index(ds) if ds in D["time"] else None
    return {"snaps":[x for x in [snap(7,"Dawn"),snap(13,"Midday"),snap(19,"Dusk")] if x],
            "hi":round(D["temperature_2m_max"][j]) if j is not None else None,"lo":round(D["temperature_2m_min"][j]) if j is not None else None,
            "sunrise":(D["sunrise"][j][11:16] if j is not None else ""),"sunset":(D["sunset"][j][11:16] if j is not None else "")}
WXT=wxday(0)
# water temp estimate: smallmouth rivers track air; use ~ mean of today's hi/lo, damped toward 78 in summer
wtemp=None
if WXT and WXT["hi"] and WXT["lo"]:
    wtemp=round(0.5*(WXT["hi"]+WXT["lo"])*0.55+72*0.45)   # damped estimate
clar="stained/rising" if trend=="rising" else "clearing" if trend=="falling" else "steady"

# smallmouth tips
tips=[["🦞","Smallmouth staple: crawfish. Dead-drift or hop a #4–8 crawfish/Clouser near the bottom along rock, ledges and current seams."]]
if cur_flow is not None and cur_flow<2.5 and trend!="rising":
    tips.append(["🎣","Clear & fishable — wade the shoals and gravel bars. Light tippet, natural colors; a subtle crawfish fly crawled on the bottom."])
    tips.append(["💥","Low-light topwater — a popper or walking bug over shoals and bank cover at dawn and the last hour of light."])
else:
    tips.append(["🌊","Up / off-color — slow down, go bigger and brighter (chartreuse/black), and fish tight to the banks, eddies and creek mouths where fish get out of the current."])
if wtemp and wtemp>=80: tips.append(["🌡️","Water's warm (~%d°F) — smallmouth chase early and late; midday, go deep and slow in the shade."%wtemp])
tips.append(["🛶","Float the sections when it's up (Hidden Lake→Kingston Springs, or the Narrows loop); wade the shoals when it drops in. Match the reach to the level."])

def fmt_hm(dt): return dt.astimezone(CT).strftime("%-I:%M%p").lower()

# ---- float planner: which section to run, whether the level's right, when to put in ----
col_flow=None   # upstream Bellevue gauge (kcfs) — the river runs skinnier up top
try:
    p=get("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=03433500&period=PT3H&parameterCd=00060")["value"]["timeSeries"][0]["values"][0]["value"]
    col_flow=round(float(p[-1]["value"])/1000.0,2)
except Exception as e: print("bellevue warn:",e)
cen_flow=cur_flow
# REAL Harpeth River accesses (TWRA / higherpursuits paddler access table), upstream->downstream:
# (name, river-mile, channel-frac). River miles are mouth-referenced; frac is position along
# our OSM channel (approximate: TWRA publishes no river miles for the Harpeth). Section distance = ΔRM.
ACC=[("Hwy 100 Access",55.2,0.0),("Harpeth River Park",51.5,0.067),("Newsom Station",46.7,0.154),
     ("Hidden Lake",43.7,0.208),("Kingston Springs",28.1,0.491),("Gossett Tract",26.5,0.520),
     ("Narrows of the Harpeth",24.4,0.558),("Harpeth River Bridge",0.0,1.0)]
def local_flow(f,scale=1.0):
    if col_flow is None: return (cen_flow*scale if cen_flow else None)
    if cen_flow is None: return col_flow*scale
    return round((col_flow+f*(cen_flow-col_flow))*scale,2)
# craft-aware floatability. The user runs a 60/40 jet (needs more water over the bars
# but handles high water); a kayak/canoe floats skinnier but high fast water is dangerous.
# Thresholds mirrored in JS (floatabJS) so the on-page toggle is live.
CRAFT={"jet":  {"skinny":1.3,"push":4.5,"blown":6.5,
                "skN":"thin for a jet — dragging over gravel bars; drop to a kayak or wait for water",
                "okN":"good level — the jet runs the shoals with room to spare",
                "puN":"up & fast — powered boat handles it, but mind floating debris & strainers",
                "blN":"high & muddy — sit it out"},
       "paddle":{"skinny":0.6,"push":3.5,"blown":5.0,
                "skN":"bony but paddleable — expect to drag a few shallow bars",
                "okN":"good level — put in & go",
                "puN":"up & fast — solid paddling; scout blind bends, mind strainers",
                "blN":"too high & fast to paddle safely — stay off"}}
def floatab(fl,craft="jet"):
    if fl is None: return ("—","#94a3b1","")
    c=CRAFT[craft]
    if fl<c["skinny"]: return ("Skinny","#20b2aa",c["skN"])
    if fl<=c["push"]:  return ("Floatable","#28c76f",c["okN"])
    if fl<=c["blown"]: return ("Pushy","#f2a832",c["puN"])
    return ("Blown","#8b6cef",c["blN"])
CRAFT0="paddle"  # the Harpeth is canoe/kayak water (WATER_MODEL: too skinny for a jet)
# real access coordinates, placed on the OSM channel at each ramp's river mile
# (town/bridge coordinates along the corridor; the Harpeth has no published ramp table)
# Coordinates are the ACTUAL road-over-river crossings, found by intersecting OSM highway
# geometry with the OSM Harpeth River centreline (analysis: 19 bridges cross the river; these
# six match the named accesses). The first cut of this page geocoded TOWN CENTRES, which put
# Kingston Springs 1,236 m and Hwy 100 Access 1,099 m from the water -- a Google Maps pin in the middle
# of town rather than at the launch. Bridge crossings are where the public access actually is on
# this river: TWRA publishes no ramp coordinates for the Harpeth.
COORD_ALL={"Hwy 100 Access":(36.05410,-86.92900),"Harpeth River Park":(36.07839,-86.95945),
       "Newsom Station":(36.07987,-86.99644),"Hidden Lake":(36.09175,-87.02992),
       "Kingston Springs":(36.12204,-87.09889),"Gossett Tract":(36.13648,-87.10484),
       "Narrows of the Harpeth":(36.14800,-87.11853),"Harpeth River Bridge":(36.28450,-87.14528)}
# hazards — no dams anywhere on the Harpeth; the risks are strainers, low water and a flashy rise.
DAM_WARN=("No dam on the Harpeth \u2014 it is a Tennessee State Scenic River. Nothing buffers a rain\n          event, and the gradient is low, so it comes up fast and drops slowly.")
GEN_HAZ="Watch for strainers, logjams & deadfall on the outside of bends — worst right after high water."
def hazard_for(i): return DAM_WARN if i==0 else GEN_HAZ
def mins(hm):
    try: h,m=map(int,hm.split(":")); return h*60+m
    except: return 6*60+30
def tlab(m):
    m=int(round(m))%1440; h=m//60; ap="a" if h<12 else "p"; return "%d:%02d%s"%((h%12) or 12,m%60,ap)
sr_min=mins(WXT["sunrise"]) if WXT and WXT.get("sunrise") else 6*60+30
ss_min=mins(WXT["sunset"]) if WXT and WXT.get("sunset") else 20*60

# ---------------------------------------------------------------------------
# The Harpeth runs as one continuous free-flowing river, so it is a
# single page. Sections below are the float reaches between public accesses (the TWRA/paddler access table
# marks which accesses take motorized boats; canoe-only accesses are not section boundaries
# because you cannot end a jet trip at one).
#
# Each section gets its own page. `rm0`/`rm1` are mouth-referenced river miles, `f0`/`f1` the
# matching positions along the shared OSM channel polyline.
RIVER_KEY="harpeth"
ROUTE_FALLBACK=(5, 0.8784, 1.48, 5.42, 4303)
# ROUTING — how a rise moves down the river. MEASURED, not assumed.
# analysis/duck_routing.py cross-correlates the two gauges; analysis/backtest_route.py then
# scores candidate transfer models on HELD-OUT data (fit on the first 70%, scored on the last
# 30%). The obvious model -- multiply the upstream reading by a constant gain -- turned out to be
# the WORST of the candidates: NSE 0.22 at the measured lag, a +345 cfs bias, and it loses to
# plain persistence at every horizon. A power law fitted in log space scores NSE 0.81. The
# generator therefore reads the WINNING transfer out of the JSON rather than hardcoding a gain.
try:
    _RT = json.load(open(os.path.join(HERE, "analysis", "duck_routing.json")))["rivers"][RIVER_KEY]
    ROUTE_LAG_H, ROUTE_R, ROUTE_GAIN = _RT["lag_h"], _RT["r"], _RT["gain_median"]
    ROUTE_MPH, ROUTE_N = _RT["mph"], _RT["n_hours"]
    ROUTE_TF, ROUTE_MINH = _RT["transfer"], _RT.get("useful_from_h", 12)
except Exception as _e:
    print("routing warn (using last measured):", _e)
    ROUTE_LAG_H, ROUTE_R, ROUTE_GAIN, ROUTE_MPH, ROUTE_N = ROUTE_FALLBACK
    ROUTE_TF, ROUTE_MINH = {"kind": "const", "gain": ROUTE_GAIN, "test_mae": None, "compared": {}}, 12

def route_predict(q_up):
    """Upstream reading -> downstream flow, using whichever transfer actually won the backtest."""
    if q_up is None: return None
    k = ROUTE_TF.get("kind")
    if k == "power":  return ROUTE_TF["a"] * (max(q_up, 1.0) ** ROUTE_TF["b"])
    if k == "linear": return max(0.0, ROUTE_TF["a"] + ROUTE_TF["b"] * q_up)
    return q_up * ROUTE_TF.get("gain", 1.0)

def route_lag_h(frac):
    """Hours a rise takes to reach channel position `frac` from the upstream gauge."""
    return ROUTE_LAG_H * max(0.0, min(1.0, frac))

SECTIONS = [
  {"id":"harpeth","label":"Harpeth","seat":"Kingston Springs","rm0":55.2,"rm1":0.0,"f0":0.0,"f1":1.0,"p0":0,"p1":135,
   "blurb":"Hwy 100 to the Cumberland confluence — a State Scenic River through Harpeth River State Park."},
]
# Harpeth River centreline traced from OSM waterway=river geometry (nearest-neighbour chained
# from the Hwy 100 access downstream, simplified to ~600 m spacing). Traced from
# TOWN CENTRES, so the mapped channel did not follow the river.
# Harpeth centreline: shortest path along the OSM river graph from the Hwy 100 access to the
# Harpeth River Bridge at the Cumberland confluence. 135 points, 55.2 river miles.
POLY_ALL = [[36.05421, -86.92855], [36.05471, -86.93543], [36.05085, -86.94086], [36.04942, -86.94917], [36.05376, -86.94517], [36.05895, -86.94316], [36.06193, -86.94881], [36.06599, -86.95452], [36.07223, -86.95428], [36.07754, -86.95812], [36.07547, -86.96435], [36.0692, -86.96455], [36.06455, -86.96954], [36.06736, -86.97554], [36.06492, -86.98241], [36.06139, -86.9875], [36.06694, -86.98858], [36.07287, -86.98742], [36.07563, -86.98152], [36.08116, -86.98355], [36.08189, -86.99084], [36.08089, -86.99765], [36.08661, -86.99979], [36.09325, -86.99958], [36.09446, -87.00736], [36.09051, -87.01495], [36.08548, -87.01905], [36.0867, -87.02568], [36.09172, -87.02868], [36.09535, -87.03405], [36.09018, -87.03608], [36.08332, -87.03546], [36.08361, -87.04243], [36.08819, -87.04657], [36.09271, -87.05191], [36.09592, -87.05854], [36.09329, -87.06442], [36.08714, -87.06231], [36.08221, -87.05925], [36.08231, -87.06621], [36.08608, -87.07128], [36.08508, -87.07812], [36.08163, -87.08404], [36.08493, -87.08999], [36.08994, -87.08624], [36.09454, -87.08126], [36.09936, -87.07645], [36.10514, -87.073], [36.11157, -87.07685], [36.11413, -87.08356], [36.11039, -87.08995], [36.10799, -87.09608], [36.10316, -87.10006], [36.09497, -87.10187], [36.09174, -87.10744], [36.09836, -87.10877], [36.10367, -87.1053], [36.10815, -87.10926], [36.10717, -87.1174], [36.10387, -87.12424], [36.10438, -87.1311], [36.11062, -87.12902], [36.11449, -87.12373], [36.11637, -87.11371], [36.1194, -87.10641], [36.12091, -87.09997], [36.12637, -87.0995], [36.13101, -87.1051], [36.13531, -87.10988], [36.13811, -87.10393], [36.13755, -87.09626], [36.14274, -87.09821], [36.14022, -87.10422], [36.14288, -87.11077], [36.14798, -87.11563], [36.14541, -87.12172], [36.14003, -87.12111], [36.13492, -87.12591], [36.13048, -87.13117], [36.13083, -87.13981], [36.13117, -87.14673], [36.13549, -87.15174], [36.14128, -87.15002], [36.14351, -87.14388], [36.14453, -87.13712], [36.14666, -87.12932], [36.14814, -87.12265], [36.1529, -87.1193], [36.1582, -87.11717], [36.16217, -87.1121], [36.16764, -87.11109], [36.17016, -87.11802], [36.16834, -87.12457], [36.16489, -87.13204], [36.16374, -87.13898], [36.16128, -87.14506], [36.15944, -87.15184], [36.15917, -87.15872], [36.15639, -87.16449], [36.15855, -87.17089], [36.16482, -87.17129], [36.16978, -87.167], [36.17229, -87.16025], [36.1745, -87.15331], [36.18085, -87.15137], [36.18609, -87.15494], [36.19097, -87.15866], [36.19252, -87.16639], [36.19568, -87.17196], [36.20167, -87.17026], [36.20638, -87.17368], [36.2105, -87.17946], [36.21006, -87.18634], [36.21543, -87.18726], [36.22207, -87.18427], [36.2267, -87.18073], [36.22614, -87.17348], [36.22931, -87.16673], [36.23501, -87.16506], [36.24036, -87.16716], [36.24532, -87.17033], [36.24709, -87.17731], [36.24439, -87.18352], [36.24359, -87.19014], [36.24912, -87.19316], [36.25394, -87.18836], [36.25762, -87.18265], [36.26144, -87.17742], [36.26453, -87.17185], [36.26678, -87.1657], [36.26987, -87.15827], [36.27546, -87.15523], [36.28059, -87.15842], [36.28461, -87.15362], [36.28498, -87.14506]]
ACC_ALL = list(ACC)

TEMPLATE=r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Harpeth River · smallmouth</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#16202b;--muted:#66788a;--faint:#93a3b3;--line:#e6ecf2;--card:#fff;--blue:#0a84ff;--green:#28c76f}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,sans-serif;
 background:radial-gradient(1000px 700px at 82% -6%,#eaf6ee 0,transparent 60%),linear-gradient(180deg,#f0f6f2,#e6efe9);min-height:100vh}
.app{max-width:900px;margin:0 auto;padding:30px 22px 80px}
__SWITCH_CSS__
.eyebrow{font-size:12px;letter-spacing:.26em;text-transform:uppercase;color:var(--faint);font-weight:600}
h1{margin:6px 0 4px;font-size:33px;font-weight:750;letter-spacing:-.6px}.rte{font-size:12px;color:var(--faint);margin-top:4px;line-height:1.45}
.cap{color:var(--muted);font-size:14.5px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 26px rgba(20,50,80,.06)}
.sec{font-size:15px;font-weight:700;color:var(--ink);margin:26px 2px 12px}
.now{padding:16px 18px;margin:12px 0;display:flex;align-items:center;gap:16px}
.now .vg{flex:none;width:76px;text-align:center;color:#fff;font-weight:800;font-size:13px;padding:11px 0;border-radius:12px}
.now .b1{font-size:20px;font-weight:700}.now .b2{font-size:13.5px;color:var(--muted);margin-top:2px}
.now .rt{margin-left:auto;text-align:right;font-size:12.5px;color:var(--faint)}.now .rt b{color:var(--ink);font-size:15px;display:block}
.chartc{padding:14px 12px 8px}.chartc .lgd{font-size:12px;color:var(--muted);display:flex;gap:14px;justify-content:center;margin-top:6px;flex-wrap:wrap}
.chartc .lgd i{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:5px}
.wk{padding:6px 16px 14px}.wr{display:flex;align-items:center;gap:13px;padding:12px 0;border-top:1px solid var(--line)}.wr:first-child{border-top:0}
.wg{flex:none;width:58px;text-align:center;font-size:10.5px;font-weight:800;color:#fff;padding:5px 0;border-radius:8px}
.wd{flex:none;width:56px}.wd b{display:block;font-size:15px}.wd span{font-size:11.5px;color:var(--muted)}
.wm{flex:1;min-width:0}.wv{font-size:14.5px;font-weight:600}.ws{font-size:12.5px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#lmap{height:340px;border-radius:16px}.leaflet-container{border-radius:16px;font-family:inherit}
.maptip{font-size:11.5px;color:var(--faint);text-align:center;margin:7px 0 0}
.wx{display:flex;flex-wrap:wrap}.wx .m{flex:1;min-width:110px;padding:12px 14px;border-right:1px solid var(--line)}.wx .m:last-child{border-right:0}
.wx .w{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);font-weight:600}.wx .t{font-size:24px;font-weight:700;margin:2px 0}.wx .d{font-size:12.5px;color:var(--muted)}
.wx .meta{padding:12px 14px;font-size:12.5px;color:var(--muted);display:flex;flex-direction:column;justify-content:center;gap:3px;min-width:150px}
.tips{padding:6px}.tip{display:flex;gap:12px;padding:11px 12px;border-bottom:1px solid var(--line)}.tip:last-child{border-bottom:0}.tip .i{font-size:20px}.tip .x{font-size:14px;line-height:1.5}
.sug{padding:16px 18px;margin-bottom:10px;background:linear-gradient(135deg,#eafaf0,#eef7ff)}
.sug .h{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#2a8a52;font-weight:700;margin-bottom:5px}
.sug .b1{font-size:17px;font-weight:700;letter-spacing:-.2px}.sug .b2{font-size:13.5px;color:var(--muted);margin-top:3px}
.fl{padding:6px 16px 12px}.frow{display:flex;align-items:center;gap:12px;padding:11px 0;border-top:1px solid var(--line)}.frow:first-child{border-top:0}
.fcond{flex:none;width:74px;text-align:center;font-size:10.5px;font-weight:800;color:#fff;padding:5px 0;border-radius:8px}
.fmid{flex:1;min-width:0}.fnm{font-size:14.5px;font-weight:600}.fnm b{font-weight:700}.fsub{font-size:12.5px;color:var(--muted);margin-top:1px}
.fmi{flex:none;text-align:right;font-size:12.5px;color:var(--muted)}.fmi b{color:var(--ink);display:block;font-size:14px}
.crafttog{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;font-size:11.5px;font-weight:700}
.crafttog a{padding:5px 10px;color:var(--muted);cursor:pointer;background:#fff;user-select:none}.crafttog a.on{background:#eef7ff;color:#0a5ec2}
.hazrow{font-size:11.5px;color:#a2603a;margin-top:3px;line-height:1.45}
.safe{display:flex;gap:10px;background:#fff5f4;border:1px solid #f5d7d4;border-radius:14px;padding:12px 14px;margin-top:10px;font-size:12.5px;color:#8a3b34;line-height:1.5}.safe b{color:#6f2a24}
__SOLUNAR_CSS__
__HATCH_CSS__
__CHATTER_CSS__
__LOG_CSS__
__MOONCAL_CSS__
__FLOWTIMER_CSS__
__FLYMATRIX_CSS__
.foot{text-align:center;color:var(--faint);font-size:11.5px;margin-top:26px;line-height:1.6}
@media(max-width:680px){.app{padding:22px 14px 60px}h1{font-size:28px}.wx .m{min-width:0}}
</style></head><body><div class="app">
 __SWITCHER__
 <div class="eyebrow">Smallmouth planner · Harpeth River · free-flowing State Scenic River</div>
 <h1>Harpeth River</h1><div class="cap" id="cap"></div>
 <div class="card now" id="now"></div>
 <div class="sec">Flow forecast</div><div class="card chartc" id="chartc"></div>
 <div class="sec">Flow timer · scrub obs → forecast</div><div class="card ft" id="flowtimer"></div>
 <div class="sec" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">Where &amp; when to launch
   <span class="crafttog" id="crafttog"><a data-c="jet" class="on">🚤 Jet boat</a><a data-c="paddle">🛶 Kayak/canoe</a></span></div>
 <div class="card sug" id="sug"></div>
 <div class="card fl" id="fl"></div>
 <div class="safe" id="safe"></div>
 <div class="sec">Live map · float accesses</div>
 <div class="card" style="padding:8px"><div id="lmap"></div></div>
 <div class="maptip">Harpeth River State Park accesses on the OSM channel · Hwy 100 → the Cumberland confluence, 55 river mi · tap a pin for details &amp; a Google Maps link
 <div class="sec">6-day outlook</div><div class="card wk" id="wk"></div>
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
__CHATTER_JS__
__LOG_JS__
__MOONCAL_JS__
__FLOWTIMER_JS__
__FLYMATRIX_JS__
(function(){const R=D.route;
 let fwd='';
 if(R.upNow!=null&&R.pred!=null&&R.predAt>=R.minH){
   fwd='<div class="rte"><b>Routed forecast.</b> The upstream gauge reads '+R.upNow.toLocaleString()
     +' cfs now, which puts this river near <b>'+R.pred.toLocaleString()+' cfs</b> at the bottom of the reach in about '
     +R.predAt+' h. Model: '+R.tf+' transfer, held-out MAE '+(R.tfMae!=null?Math.round(R.tfMae)+' cfs':'n/a')
     +'. Below ~'+R.minH+' h ahead this is no better than assuming the river stays put, so it is not a short-range forecast.</div>';
 }
 document.getElementById('cap').innerHTML=D.today+' · '+R.src+'<div class="rte">'+R.why+'</div>'+fwd;})();
(function(){const c=D.cur;document.getElementById('now').innerHTML=
 '<div class="vg" style="background:'+c.col+'">'+c.cond+'</div>'
 +'<div><div class="b1">'+(c.flow!=null?c.flow.toLocaleString()+'k cfs':'—')+' · '+(c.stage!=null?c.stage+' ft':'')+' <span style="font-size:14px;color:var(--muted)">'+(c.trend==='rising'?'↑ rising':c.trend==='falling'?'↓ falling & clearing':'→ steady')+'</span></div>'
 +'<div class="b2">'+c.note+'</div></div>'
 +'<div class="rt"><b>'+c.grade+'</b>water '+c.clar+(c.wtemp?'<br>~'+c.wtemp+'°F':'')+'<br><span style="font-size:11px">as of '+c.asof+'</span></div>';})();
// forecast hydrograph
(function(){const S=D.series;if(!S.length){document.getElementById('chartc').innerHTML='<div style="padding:20px;color:var(--muted)">forecast unavailable</div>';return;}
 const W=860,H=200,pad=34,fs=S.map(p=>p.f),fmax=Math.max(3,...fs)*1.1,fmin=0;
 const x=i=>pad+i*(W-pad-10)/(S.length-1),y=f=>H-24-(f-fmin)/(fmax-fmin)*(H-44);
 // fishability bands: prime .9-2.5 green, high 2.5-4.5 amber, blown >4.5 red, low <.9 gray
 function band(a,b,col){var yb=y(Math.min(b,fmax));return '<rect x="'+pad+'" y="'+yb+'" width="'+(W-pad-10)+'" height="'+Math.max(0,(y(Math.min(a,fmax))-yb))+'" fill="'+col+'"/>';}
 let bands=band(0,0.9,'rgba(148,163,177,.13)')+band(0.9,2.5,'rgba(40,199,111,.15)')+band(2.5,4.5,'rgba(242,168,50,.15)')+band(4.5,fmax,'rgba(139,108,239,.13)');
 let obsPath='',fcPath='',split=S.findIndex(p=>!p.obs);
 S.forEach((p,i)=>{const pt=x(i).toFixed(0)+','+y(p.f).toFixed(0);if(p.obs)obsPath+=(obsPath?' L':'M')+pt;});
 const s0=Math.max(0,split-1);S.forEach((p,i)=>{if(i>=s0)fcPath+=(fcPath?' L':'M')+x(i).toFixed(0)+','+y(p.f).toFixed(0);});
 const nowx=x(Math.max(0,split-1));
 let ax='';for(let i=0;i<S.length;i+=Math.ceil(S.length/6)){ax+='<text x="'+x(i)+'" y="'+(H-6)+'" font-size="10" fill="#93a3b3" text-anchor="middle">'+S[i].t.split(' ')[0]+'</text>';}
 [1,2.5,4.5].forEach(g=>{ax+='<text x="4" y="'+(y(g)+3)+'" font-size="9" fill="#93a3b3">'+g+'k</text>';});
 document.getElementById('chartc').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" width="100%">'+bands
  +'<line x1="'+nowx+'" y1="20" x2="'+nowx+'" y2="'+(H-22)+'" stroke="#16202b" stroke-width="1.5" stroke-dasharray="3 3"/>'
  +'<text x="'+nowx+'" y="16" font-size="10" fill="#16202b" text-anchor="middle">now</text>'
  +'<path d="'+obsPath+'" fill="none" stroke="#3a7bb8" stroke-width="2.5"/>'
  +'<path d="'+fcPath+'" fill="none" stroke="#0a84ff" stroke-width="2.5" stroke-dasharray="5 4"/>'+ax+'</svg>'
  +'<div class="lgd"><span><i style="background:rgba(40,199,111,.6)"></i>prime .9–2.5k</span><span><i style="background:rgba(242,168,50,.6)"></i>high</span><span><i style="background:rgba(139,108,239,.5)"></i>blown</span><span>— observed (no forecast published for this river)</span></div>';})();
// outlook
(function(){let h='';D.outlook.forEach(d=>{const wx=d.wx?(' · '+d.wx.hi+'°/'+d.wx.lo+'°'+(d.wx.pop?' · '+d.wx.pop+'%':'')):'';
 h+='<div class="wr"><div class="wg" style="background:'+d.col+'">'+d.grade+'</div><div class="wd"><b>'+d.label+'</b><span>'+d.date+'</span></div>'
  +'<div class="wm"><div class="wv">'+d.cond+' — '+d.flow+'k cfs '+d.trend+'</div><div class="ws">'+d.stage+' ft · '+d.note+wx+'</div></div></div>';});
 document.getElementById('wk').innerHTML=h;})();
(function(){const w=D.weather,el=document.getElementById('wx');if(!w){el.innerHTML='<div class="meta">weather unavailable</div>';return;}
 let h='';(w.snaps||[]).forEach(s=>h+='<div class="m"><div class="w">'+s.when+'</div><div class="t">'+s.ico+' '+s.temp+'°</div><div class="d">'+s.sky+' · '+s.wind+' mph'+(s.precip?' · '+s.precip+'%':'')+'</div></div>');
 h+='<div class="meta"><div>High '+(w.hi??'–')+'° · Low '+(w.lo??'–')+'°</div><div>Sun '+w.sunrise+'–'+w.sunset+'</div></div>';el.innerHTML=h;})();
// float planner — craft toggle drives live floatability (thresholds shared from Python)
(function(){let craft=D.craft0||'jet';
 function floatab(fl,cr){if(fl==null)return['—','#94a3b1',''];const c=D.craft[cr];
  if(fl<c.skinny)return['Skinny','#20b2aa',c.skN];
  if(fl<=c.push)return['Floatable','#28c76f',c.okN];
  if(fl<=c.blown)return['Pushy','#f2a832',c.puN];
  return['Blown','#8b6cef',c.blN];}
 const sug=document.getElementById('sug'),flEl=document.getElementById('fl'),safe=document.getElementById('safe');
 function renderSug(){const s=D.suggest;if(!s){sug.style.display='none';return;}
  sug.innerHTML='<div class="h">Best float this week</div>'
   +'<div class="b1">'+s.day+' '+s.date+' — put in at <b>'+s.frm+'</b> ~'+s.putin+', take out <b>'+s.to+'</b> ~'+s.takeout+'</div>'
   +'<div class="b2">'+s.mi+' mi · ~'+s.hrs+' hrs on the water · ~'+s.flow+'k cfs ('+s.grade+'). '
    +'Road shuttle ~'+s.shuttle+' mi between ramps — spot a vehicle first. Sized for your jet; launch at first light for the morning bite.</div>';}
 function renderSecs(){const S=D.sections;
  let h='<div class="fsub" style="padding:8px 0 4px;color:var(--faint)">Float sections at today\'s level'
   +(D.colflow!=null?' (Bellevue '+D.colflow+'k → Kingston Springs '+(D.cur.flow||'?')+'k — the upper river runs skinnier)':'')
   +' · sized for <b>'+(craft==='jet'?'a jet boat':'a kayak / canoe')+'</b>:</div>';
  S.forEach(x=>{const fb=floatab(x.flow,craft),red=x.haz.indexOf('⚠')===0;
   h+='<div class="frow"><div class="fcond" style="background:'+fb[1]+'">'+fb[0]+'</div>'
    +'<div class="fmid"><div class="fnm"><b>'+x.from+'</b> → <b>'+x.to+'</b></div>'
    +'<div class="fsub">'+(x.flow!=null?'~'+x.flow+'k cfs · ':'')+fb[2]+'</div>'
    +'<div class="hazrow"'+(red?' style="color:#b3392f;font-weight:600"':'')+'>'+x.haz+'</div></div>'
    +'<div class="fmi"><b>'+x.mi+' mi</b>~'+x.hrs+' hrs<span style="display:block;color:var(--faint);font-size:11px">shuttle ~'+x.shuttle+' mi</span></div></div>';});
  flEl.innerHTML=h;}
 safe.innerHTML='<div style="font-size:16px">⚠</div><div><b>Float safety.</b> There is no dam anywhere on the Harpeth — it is a free-flowing State Scenic River, so nothing buffers a rain event. It comes up fast and drops fast. Wear a PFD, scout blind bends, and expect fresh strainers after high water. Check the gauge the morning you go, not the night before.</div>';
 document.querySelectorAll('#crafttog a').forEach(a=>a.onclick=()=>{craft=a.dataset.c;
  document.querySelectorAll('#crafttog a').forEach(z=>z.classList.toggle('on',z.dataset.c===craft));renderSug();renderSecs();});
 renderSug();renderSecs();})();
buildFlyMatrix('flysel',D.flysel);
(function(){let h='';D.tips.forEach(t=>h+='<div class="tip"><div class="i">'+t[0]+'</div><div class="x">'+t[1]+'</div></div>');document.getElementById('tips').innerHTML=h;})();
renderSolunar('sol',D.solunar,D.cur.trend==='falling'?'Sweet spot: a falling, clearing river during a major window is prime smallmouth timing.':null);
renderHatch('hatch',D.hatch,D.month);
buildMoonCal('mooncal',35.80,-87.37);
buildFlowTimer('flowtimer',D.timeline);
renderChatter('chatter',D.chatter,'chatterSec');
buildLog('log','riverlog-duck',D.points.map(p=>p.name),null);
document.getElementById('foot').textContent='Flow: USGS real-time gauges (no NWPS forecast exists for the Harpeth) (USGS 03434500, Harpeth near Kingston Springs). Fishability bands & water-temp are estimates — tune from the water. Weather: Open-Meteo. River channel from OpenStreetMap.';
buildRiverMap(D,D.cur.col);
</script></body></html>"""

def build_section(_S):
    ACC=[a for a in ACC_ALL if _S["rm1"]-0.05 <= a[1] <= _S["rm0"]+0.05]
    if len(ACC)<2: ACC=list(ACC_ALL)
    COORD={k:v for k,v in COORD_ALL.items() if k in {a[0] for a in ACC}}
    _frac=(_S["f0"]+_S["f1"])/2.0
    _lag=route_lag_h(_frac)
    # THIS reach's water, not Kingston Springs's. The Harpeth gains about half again between Bellevue and
    # Kingston Springs (measured median gain x1.46), so quoting the downstream gauge on the upper
    # river overstates it by nearly 2x -- the difference between "prime" and "skinny".
    cur_flow=local_flow(_frac)
    FN,FG,FC_,FNOTE=fish(cur_flow,trend=="rising",trend=="falling")
    clar="stained/rising" if trend=="rising" else "clearing" if trend=="falling" else "steady"
    # The outlook is the Kingston Springs forecast scaled to this reach by the same channel position.
    _oscale=(cur_flow/cen_flow) if (cen_flow and cur_flow) else 1.0
    outlook=[]
    for _o in _OUTLOOK_BASE:
        _f=round(_o["flow"]*_oscale,2)
        _cond,_g,_col,_note=fish(_f,_o["trend"]=="↑",_o["trend"]=="↓")
        outlook.append(dict(_o,flow=_f,cond=_cond,grade=_g,col=_col,note=_note))
    # Where this reach's forward signal comes from. Kingston Springs is the ONLY NWPS forecast point
    # on the Harpeth, so the upper reaches are predicted by routing the Bellevue gauge downstream.
    _upnow=(col_flow*1000.0) if col_flow is not None else None
    _pred=route_predict(_upnow)
    ROUTE={"lagH":round(_lag,1),"gain":ROUTE_GAIN,"r":ROUTE_R,"mph":ROUTE_MPH,"n":ROUTE_N,
           "lead":round(ROUTE_LAG_H-_lag,1),
           "tf":ROUTE_TF.get("kind"),"tfMae":ROUTE_TF.get("test_mae"),"minH":ROUTE_MINH,
           "upNow":round(_upnow) if _upnow else None,
           "pred":round(_pred) if _pred else None,
           "predAt":round(ROUTE_LAG_H,1),
           "src":("Bellevue gauge (USGS 03433500) — this reach's own water" if _S["id"]=="duckup"
                  else ("routed from Bellevue — a rise there lands here about %.0f h later"%_lag) if _S["id"]=="duckmid"
                  else "USGS gauge at Kingston Springs (03434500) — observed, not forecast"),
           "why":("The Bellevue gauge sits at the top of this water and runs "
                  "%d h ahead of Kingston Springs, which makes it the earliest warning on the river."%ROUTE_LAG_H
                  if _S["id"]=="duckup" else
                  ("No gauge sits on this reach. Bellevue is above it and Kingston Springs below, so the level "
                   "here is interpolated between the two, and a rise at Bellevue reaches this water about "
                   "%.0f h later — leaving roughly %.0f h of warning before it arrives."%(_lag,_lag))
                  if _S["id"]=="duckmid" else
                  "Kingston Springs is the last gauge before the Cumberland. NWPS publishes no forecast anywhere "
                  "on the Harpeth, so everything ahead of now is routed from the Bellevue gauge, not forecast.")}
    sections=[]
    for i in range(len(ACC)-1):
        a,rma,fa=ACC[i]; b,rmb,fb=ACC[i+1]; mi=round(rma-rmb,1); fl=local_flow((fa+fb)/2)
        cond,col,note=floatab(fl,CRAFT0); pace=1.0+min(1.6,(fl or 1)*0.35); hrs=round(mi/pace,1)
        shut=riverlib.shuttle_miles(COORD[a],COORD[b])
        sections.append({"from":a,"to":b,"mi":mi,"flow":fl,"cond":cond,"col":col,"note":note,"hrs":hrs,
                         "fa":fa,"fb":fb,"shuttle":shut,"haz":hazard_for(i)})
    # best upcoming day (from the forecast) + pick a section that floats at that day's level (for the user's craft)
    best_day=next((o for o in outlook if o["grade"]=="Prime"),None) or next((o for o in outlook if o["grade"]=="Good"),None) or (outlook[0] if outlook else None)
    scale=(best_day["flow"]/cen_flow) if (best_day and cen_flow) else 1.0
    def sec_at(s,scale):
        fl=local_flow((s["fa"]+s["fb"])/2,scale); cond,col,note=floatab(fl,CRAFT0); return fl,cond
    cands=[s for s in sections if sec_at(s,scale)[1] in ("Floatable","Pushy")]
    def score(s): fl=sec_at(s,scale)[0]; return abs((fl or 2)-2.0)+(5 if s["mi"]>13 else 0)+(3 if s["hrs"]>(ss_min-sr_min)/60-1 else 0)
    best_sec=min(cands,key=score) if cands else (sections[-1] if sections else None)
    FLOAT=None
    if best_sec and best_day:
        fl_bs=sec_at(best_sec,scale)[0]
        FLOAT={"day":best_day["label"],"date":best_day["date"],"grade":best_day["grade"],"dayflow":best_day["flow"],
               "frm":best_sec["from"],"to":best_sec["to"],"mi":best_sec["mi"],"hrs":best_sec["hrs"],
               "putin":tlab(sr_min+30),"takeout":tlab(sr_min+30+best_sec["hrs"]*60),"flow":fl_bs,
               "shuttle":best_sec["shuttle"],"haz":best_sec["haz"]}

    # ---- fly box (mined smallmouth patterns, dynamic by flow/trend/season) ----
    mon=now_ct.month; season="summer" if 6<=mon<=8 else "fall" if 9<=mon<=11 else "winter" if mon in(12,1,2) else "spring"
    low=(cur_flow is not None and cur_flow<2.5)
    flies=["🦞 Crawfish / crawdad #4–8 (dead-drift on the bottom)","Clouser Minnow — olive/white & chartreuse/white"]
    if low and trend!="rising": flies+=["Natural Clouser — subtle, clear water","Small streamer / Woolly Bugger swung on the shoals"]
    else: flies+=["Go bigger & brighter — chartreuse Clouser","Murdich Minnow / Game Changer (push water)","Dark bugger tight to the bank & eddies"]
    if season=="summer": flies+=["Popper / walking bug — dawn & the last hour of light"]
    elif season in("spring","fall"): flies+=["Bigger streamers — pre-spawn & fall feed grabs the biggest fish"]
    flybox={"season":season,"clar":clar,"now":flies,
      "rig":"Get crawfish & Clousers on the bottom along rock, ledges and current seams (split-shot or a sink-tip), 8–10 lb tippet. Fish topwater on a floating line at first and last light.",
      "sources":[["FlyFishFinder","https://flyfishfinder.com/pages/best-smallmouth-bass-rivers-in-tennessee/"],["River Run Angling","https://riverrunangling.com/blog/bass-fishing-in-tennessee/"],["Wooly Buggin'","https://woolybuggin.com/smallies-on-the-fly-a-guide-for-river-smallmouth-bass/"]]}
    ACC_TYPES={"Hwy 100 Access":["ramp","paddle"],"Harpeth River Park":["ramp","paddle"],
           "Newsom Station":["paddle"],"Kingston Springs":["ramp","paddle"],"Harpeth River Bridge":["ramp","paddle"]}
    ACC_INFO={"Hwy 100 Access":"Harpeth River State Park at Hwy 100. Top of the mapped reach \u2014 the USGS Bellevue gauge (03433500) sits here, which makes it the earliest reading on the river and a %d h head start on Kingston Springs."%ROUTE_LAG_H,
 "Harpeth River Park":"Bellevue city park river access.",
 "Newsom Station":"Harpeth River State Park unit at Newsom Mill \u2014 the 1862 mill ruin stands on the bank.",
 "Hidden Lake":"Harpeth River State Park. The lake is a flooded quarry; the access is on the river.",
 "Kingston Springs":"USGS gauge 03434500 (683 sq mi) \u2014 the last gauge before the Cumberland, and what the lower river is read from.",
 "Gossett Tract":"Harpeth River State Park canoe access, just upstream of the Narrows.",
 "Narrows of the Harpeth":"The landmark. The river loops about five miles and comes back within a few hundred feet of itself; Montgomery Bell cut a tunnel through the neck in 1819. The standard Narrows float puts in and takes out here.",
 "Harpeth River Bridge":"Bridge access at the Cumberland confluence \u2014 the bottom of the river."}
    SOL=riverlib.solunar(now_ct.date(),(WXT or {}).get("sunrise"),(WXT or {}).get("sunset"),CT)
    # Seasonal forage calendar for river smallmouth (warmwater — dormant in the cold). 0-3 by month.
    HATCH={"rows":[
     {"name":"Crayfish","icon":"🦞","pattern":"craw / craw-Clouser #4–8","m":[1,1,2,2,3,3,3,3,3,2,1,1]},
     {"name":"Shad / baitfish","icon":"🐟","pattern":"Clouser, white/chartreuse","m":[2,2,2,2,2,2,2,2,3,3,2,2]},
     {"name":"Hellgrammite","icon":"🐛","pattern":"black/olive #4–6","m":[0,0,1,2,3,3,2,2,1,0,0,0]},
     {"name":"Topwater","icon":"💥","pattern":"popper / walker, dawn & dusk","m":[0,0,0,1,2,3,3,3,3,2,1,0]},
     {"name":"Hopper / terrestrial","icon":"🦗","pattern":"tight to the banks","m":[0,0,0,0,1,2,3,3,3,2,0,0]},
     {"name":"Damsel / dragon","icon":"🪰","pattern":"shoals & weed edges","m":[0,0,0,0,1,2,3,3,2,1,0,0]},
     {"name":"Sculpin / streamer","icon":"🐠","pattern":"pre-spawn & fall grabs","m":[1,1,2,3,2,1,1,1,2,3,2,1]},
    ]}
    # flow-timer timeline: scrub obs+forecast. Flow river (whole reach moves together) but with the
    # Bellevue→Kingston Springs gradient, so upstream ramps read skinnier than the Kingston Springs gauge.
    _ft=series
    _now=next((i for i,p in enumerate(_ft) if not p.get("obs")),len(_ft))-1
    def _dscale(fr):
        if col_flow is None or not cen_flow: return 1.0
        return max(0.25,(col_flow+fr*(cen_flow-col_flow))/cen_flow)
    _dord=[(a[0].replace(" Access","").replace("Harpeth River ",""),a[2]) for a in ACC]
    TIMELINE=({"times":[p["t"] for p in _ft],"nowFrame":max(0,_now),"unit":"kcfs","dec":2,"refIdx":len(_dord)-1,"refName":_dord[-1][0],
      "front":False,"frontThresh":0,"srcLabel":_dord[0][0]+" ↑","mouthLabel":_dord[-1][0]+" ↓",
      "bands":[[0.9,"#20b2aa","Low"],[2.5,"#28c76f","Prime"],[4.5,"#f2a832","High"],[10**9,"#8b6cef","Blown"]],
      "points":[{"name":n,"series":[round(p["f"]*_dscale(fr),2) for p in _ft]} for n,fr in _dord]} if _ft else None)
    # clarity × light fly matrix (shared component). Clarity from the flow band; light from hour + sky.
    FLYORDER=["clear","moderate","stained","muddy"]; LIGHTS=[("dawn","Dawn"),("low","Low light"),("bright","Bright sun"),("wind","Wind / chop")]
    FLYMATRIX={
     "clear":   {"label":"Low · <0.9k","dawn":"Small popper #6","low":"Sneaky Pete #6","bright":"Sparse Clouser #6","wind":"Small popper #6"},
     "moderate":{"label":"Prime · 0.9–2.5k","dawn":"Boogle Bug #4","low":"Deer-hair diver #4","bright":"Clouser (craw) #4","wind":"Popper #4"},
     "stained": {"label":"High · 2.5–4.5k","dawn":"Black diver #2","low":"Boogle Bug blk #2","bright":"Chart/white Clouser","wind":"Black popper #2"},
     "muddy":   {"label":"Blown · >4.5k","dawn":"Black gurgler #2","low":"Black popper #2","bright":"Black Game Changer","wind":"Black popper #2"},
    }
    BOXINV_D=[
     ["Crawfish, rust & olive","#4–8","Bottom fly for rock, ledges & gravel — short strips, long pauses, eat on the pause."],
     ["Clouser Minnow","#2–8","The workhorse once the sun's up — olive/white & chartreuse/white; vary eye weight for depth."],
     ["Boogle Bug popper","#2–6","Loud & durable — the default when the water has any color; work the banks & shade."],
     ["Sneaky Pete slider","#4–8","Clear-water topwater — quieter than a popper, won't spook a fish in low, gin water."],
     ["Deer-hair diver","#2–6","Dives on the strip, floats on the pause — over shoals & shade lines at first light."],
     ["Woolly Bugger, black & olive","#4–8","Never wrong — dead-drift through a boulder pocket when nothing else works."],
    ]
    _dc=cur_flow; _dcl=("clear" if _dc is None or _dc<0.9 else "moderate" if _dc<=2.5 else "stained" if _dc<=4.5 else "muddy")
    _dh=now_ct.hour; _dcloud=50; _dwind=6
    if wx:
        _H=wx["hourly"]; _k=now_ct.strftime("%Y-%m-%dT%H:00")
        if _k in _H["time"]: _wi=_H["time"].index(_k); _dcloud=_H["cloud_cover"][_wi] or 0; _dwind=_H["wind_speed_10m"][_wi] or 0
    _dlight=riverlib.light_now(_dh,_dcloud,_dwind)
    FLYSEL={"matrix":FLYMATRIX,"order":FLYORDER,"lights":LIGHTS,"boxinv":BOXINV_D,
      "now":{"clarity":_dcl,"light":_dlight,"fly":FLYMATRIX[_dcl][_dlight]},
      "rig":"Crawfish & Clousers on the bottom along rock, ledges & seams (split-shot or a sink-tip), 8–10 lb tippet. Topwater on a floating line at first & last light.",
      "sources":[["FlyFishFinder","https://flyfishfinder.com/pages/best-smallmouth-bass-rivers-in-tennessee/"],["River Run Angling","https://riverrunangling.com/blog/bass-fishing-in-tennessee/"],["Wooly Buggin'","https://woolybuggin.com/smallies-on-the-fly-a-guide-for-river-smallmouth-bass/"]]}
    DATA={"today":now_ct.strftime("%A, %B %-d · %-I:%M %p"),"flysel":FLYSEL,"colflow":col_flow,"solunar":SOL,"hatch":HATCH,"month":now_ct.month,"chatter":riverlib.load_intel("harpeth"),"timeline":TIMELINE,
          "sections":sections,"suggest":FLOAT,"route":ROUTE,"sec":_S,"craft":CRAFT,"craft0":CRAFT0,
          "cur":{"flow":round(cur_flow,2) if cur_flow is not None else None,"stage":round(cur_stage,1) if cur_stage is not None else None,
                 "trend":trend,"cond":FN,"grade":FG,"col":FC_,"note":FNOTE,"clar":clar,"wtemp":wtemp,
                 "asof":(OBS[-1][0].astimezone(CT).strftime("%-I:%M %p") if OBS else now_ct.strftime("%-I:%M %p"))},
          "outlook":outlook,"series":series,"weather":WXT,"tips":tips,
          "points":[{"name":k,"lat":COORD[k][0],"lon":COORD[k][1],"types":ACC_TYPES.get(k,[]),"info":ACC_INFO.get(k,""),
                     "twra":riverlib.twra_for(COORD[k][0],COORD[k][1],"buffalo river")} for k in COORD],
          "poly":POLY_ALL[_S["p0"]:_S["p1"]]}

    html=riverlib.render(TEMPLATE,_S["id"]).replace("__DATA__",json.dumps(DATA))
    open(os.path.join(OUT,_S["id"]+".html"),"w").write(html)
    # ---- HQ status card ----

    # ---- HQ day state ----
    # The only non-dam river with a real forward flow forecast: NWPS publishes observed +
    # observed stage/flow from USGS. Rows are (time, stage_ft, flow_kcfs), so scale to cfs.
    _CURVE_LABEL="Harpeth near Kingston Springs (USGS 03434500)"
    def _buff_day(off):
        d0, _ = riverlib.day_bounds(CT, off)
        rows = [(t, (v * 1000 * _oscale if v is not None else None)) for t, s, v in (OBS + FC)]
        cv = riverlib.curve_from_rows(rows, d0)
        vals = [v for v in (cv or []) if v is not None]
        if not vals:
            return riverlib.day_state(headline="No NWPS reading for this day")
        med = sorted(vals)[len(vals) // 2]
        # Vessel from the sourced model (riverlib.WATER_MODEL), not from guessed bands.
        vk, _vlabel, vw, _conf = riverlib.craft_label("harpeth", med)
        lk = "low" if med < 400 else "prime" if med < 3000 else "high" if med < 8000 else "blown"
        ck = "clear" if med < 1200 else "stained" if med < 4000 else "colored" if med < 8000 else "muddy"
        # Anything past the last observation is forecast; before that it is measured.
        last_obs = OBS[-1][0].timestamp() if OBS else 0
        src = "forecast" if (d0 + 86400) > last_obs else "observed"
        return riverlib.day_state(vessel=vk, vessel_why=vw, vessel_label=_vlabel,
            clarity=ck, clarity_why="inferred from flow; the Harpeth runs clear and colours up fast after rain",
            level=lk, level_detail=format(round(med), ",") + " cfs",
            curve=cv, curve_unit="cfs", curve_label=_CURVE_LABEL, curve_src=src,
            headline=format(round(med), ",") + " cfs \u00b7 " + {"wade":"skinny","both":"prime float","boat":"pushy","":""}.get(vk, ""))
    DAYS = {"today": _buff_day(0), "tomorrow": _buff_day(1)}

    riverlib.emit_status(_S["id"],
        {"grade":FG,"cond":FN,"col":FC_,"note":FNOTE,
         "detail":(("%s cfs"%format(round(cur_flow*1000),",")) if cur_flow is not None else "—"),
         "asof":(OBS[-1][0].astimezone(CT).strftime("%-I:%M %p") if OBS else now_ct.strftime("%-I:%M %p"))},
        wx, [o["grade"] for o in outlook] or riverlib.GRADE_SCORE.get(FG,1.3), CT, ["Smallmouth","Panfish"], "Warmwater smallmouth", "~95 min · Kingston Springs", days=DAYS)
    print("wrote out/%s.html | %s %s\u2013%s | flow %s kcfs %s | grade %s | lag %.1fh"%(_S["id"],_S["label"],ACC[0][0],ACC[-1][0],cur_flow,trend,FG,_lag))


for _S in SECTIONS:
    build_section(_S)