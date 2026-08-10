#!/usr/bin/env python3
"""
Elk River (AL — Wheeler) — summer smallmouth planner.  Built from the Elk River Field Atlas
(Edition One) and driven by live data.  Model = the atlas's flow doctrine:

  • THE RIVER (Zones C/D): governed by the Elk's own discharge — USGS 03584600, Elk River at
    Prospect TN.  Five flow bands (very low <300 · low/clear 300–700 · prime 700–1,800 ·
    high/stained 1,800–3,500 · blown >3,500) and the rule that FALLING beats level, RISING is
    the worst.  A long lag from Tims Ford means the gauge trace, not the dam, is the signal.
  • THE BACKWATER (Zones A/B): governed by TVA — current in the Elk embayment appears only when
    Wheeler is generating.  (No clean TVA API; the page links out for pool/generation.)

Centerpiece = the Plan A / Plan B turn decision: prime/high-and-stained + falling → turn UPSTREAM
to the current (shoals); very-low, blown, or rising → turn DOWNSTREAM to the structure.
Base: Joe Wheeler State Park.  Primary launch: Hatchery Rd ramp (Buck Island), AL-99 north bank.
Sources: USGS 03584600, TVA Wheeler, Open-Meteo, OpenStreetMap.  Planning use — verify before launch.
"""
import json,urllib.request,urllib.parse,datetime,math,os,sys
from zoneinfo import ZoneInfo
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import riverlib
CT=ZoneInfo("America/Chicago"); UA={"User-Agent":"elk/1.0"}
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"out"); os.makedirs(OUT,exist_ok=True)
def get(u,h=None):
    # riverlib.get retries transient TLS/DNS/5xx failures; a single flaky fetch used to
    # build this page with missing data instead of failing (see riverlib.get docstring).
    return riverlib.get(u,{**UA,**(h or {})},timeout=60)
now=datetime.datetime.now(datetime.timezone.utc); now_ct=now.astimezone(CT)
GLAT,GLON=34.902,-87.078   # Hatchery Rd / Buck Island launch area

# ---- live discharge: USGS 03584600 Elk River at Prospect, TN ----
ECFG=riverlib.RIVER_CONFIG["elk"]           # shared source of truth (gauge, zones)
SITE=ECFG["gauge"]["site"]; OBS=[]
try:
    d=get("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=%s&period=P4D&parameterCd=00060"%SITE)
    for ts in d["value"]["timeSeries"]:
        for p in ts["values"][0]["value"]:
            try: v=float(p["value"])
            except: continue
            if v<-100: continue
            OBS.append((datetime.datetime.fromisoformat(p["dateTime"]),v))
except Exception as e: print("usgs warn:",e)
OBS.sort()
cur_cfs=OBS[-1][1] if OBS else None
# trend over the last ~6h
trend="steady"
if len(OBS)>=2 and cur_cfs is not None:
    ref=next((o for o in reversed(OBS) if (OBS[-1][0]-o[0]).total_seconds()>=6*3600),OBS[0])
    dv=cur_cfs-ref[1]; thr=max(25.0,0.03*cur_cfs)
    trend="rising" if dv>thr else "falling" if dv<-thr else "steady"

# ---- atlas flow bands (Sheet 09) ----
def band(cfs):
    if cfs is None: return ("na","—","#94a3b1","no gauge reading","")
    if cfs<300:   return ("vlow","Very low","#20b2aa","concentrated & spooky — riffle heads and shade hold everything","Long casts, 10–12 ft leaders, small flies. Fish shade & oxygenated riffles; wade where you can.")
    if cfs<=700:  return ("low","Low & clear","#37b3a1","holding well but easily pushed off","Stealth. Kill the outboard early, use the trolling motor, stay off the fish, lengthen everything.")
    if cfs<=1800: return ("prime","Prime","#28c76f","spread across every seam, boulder & transition","The day the boat earns its keep — cover water efficiently, fish every seam.")
    if cfs<=3500: return ("high","High & stained","#f2a832","pushed to banks, flooded wood & current breaks","Often excellent. Bigger flies with more movement, tight to the bank, shorter/stouter leaders.")
    return ("blown","Blown out","#8b6cef","scattered & hard to reach","Turn downstream to structure or fish cleaner tributary inflows. Watch for floating debris.")
BK,BLABEL,BCOL,BFISH,BDO=band(cur_cfs)

# ---- Plan A / Plan B decision (Sheet 06) ----
# prime/high-and-stained + falling -> upstream (A); very-low, blown, or rising -> downstream (B)
if cur_cfs is None:
    plan="B"
elif trend=="rising":
    plan="B"
elif BK in ("prime","high"):
    plan="A"
else:
    plan="B"
PLAN_A={"key":"A","turn":"Upstream — to the current","water":"Zones C & D · shoals, seams, boulder gardens, tailouts, wood bends",
        "how":"Run upstream first while the light's bad, then fish your way back down. Hold the boat off the shoal, cast down & across — don't drift over fish. 6-wt through the whole prime window. Set your downstream turn time before you launch.",
        "when":"the Elk is prime or high-and-stained and falling"}
PLAN_B={"key":"B","turn":"Downstream — to the structure","water":"Zone B & top of A · bluff walls, riprap, laydowns, points, creek mouths",
        "how":"Work the shade line as it retreats up the bluff — cast tight, let it sit, move it once. Fish riprap where the rock meets the channel. Any current is TVA's: when Wheeler's generating, points & creek mouths that funnel it are the best water. 7-wt with a sink tip; getting 6–10 ft down beats reaching seams.",
        "when":"very low & clear, blown out, or rising fast — depth substitutes for current"}
PLAN=PLAN_A if plan=="A" else PLAN_B
plan_reason=("%s cfs (%s) and %s → "%(int(cur_cfs),BLABEL.lower(),trend) if cur_cfs is not None else "no gauge reading → ")+ \
    ("turn upstream to the shoals." if plan=="A" else ("turn downstream to the backwater structure." if cur_cfs is not None else "turn downstream — Plan B works in everything."))

# ---- clarity × light fly matrix (Sheet 11) ----
FLYMATRIX={
 "clear":   {"label":"Clear · >4 ft","dawn":"Small diver #6","low":"Sneaky Pete #6","bright":"Sparse Clouser #4–6","wind":"Small popper #6"},
 "moderate":{"label":"Moderate · 2–4 ft","dawn":"Sneaky Pete #4","low":"Deer-hair diver #2","bright":"Clouser (crawfish) #4","wind":"Small popper #4"},
 "stained": {"label":"Stained · 1–2 ft","dawn":"Black diver #2/0","low":"Boogle Bug blk/olive #2","bright":"Clouser / white","wind":"Deer-hair diver #2/0"},
 "muddy":   {"label":"Muddy · <1 ft","dawn":"Black gurgler #2","low":"Black popper #2","bright":"Black/chart Game Changer","wind":"Black popper #2"},
}
FLYORDER=["clear","moderate","stained","muddy"]
LIGHTS=[("dawn","Dawn"),("low","Low light"),("bright","Bright sun"),("wind","Wind / chop")]
BOXINV=[
 ["Deer-hair diver, black & olive","1/0–4","First-light fly — dives on the strip, floats on the pause. Long pauses over seams & shade lines."],
 ["Boogle Bug popper (blk/chart/white)","1–6","Loud, durable, easy to cast — the default when the water has any color."],
 ["Sneaky Pete slider","2–8","Clear-water topwater — quieter than a popper, moves water without alarming fish in gin."],
 ["Clouser Minnow (chart/olive/white)","2–8","The workhorse once the sun's up. Vary eye weight, not pattern, to change depth."],
 ["Game Changer / articulated","3–5","Big-fish fly for stained water & low light. Slow, wide, jointed movement."],
 ["Woolly Bugger, black & olive (cone)","4–8","Never wrong — dead-drift through a boulder pocket when nothing else works."],
 ["Crayfish, rust & olive","4–8","Bottom fly for gravel-to-rock transitions. Short strips, long pauses, eat on the pause."],
]
# clarity from band; light from hour + sky
clarity={"vlow":"clear","low":"clear","prime":"moderate","high":"stained","blown":"muddy","na":"moderate"}[BK]

# ---- weather (Open-Meteo) ----
wx=None
try:
    wx=get("https://api.open-meteo.com/v1/forecast?latitude=%.3f&longitude=%.3f"
           "&hourly=temperature_2m,precipitation_probability,cloud_cover,wind_speed_10m"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone=America%%2FChicago&forecast_days=7"%(GLAT,GLON))
except Exception as e: print("wx warn:",e)
def wxday(di=0):
    if not wx: return None
    H=wx["hourly"]; idx={x:i for i,x in enumerate(H["time"])}
    dd=now_ct.date()+datetime.timedelta(days=di)
    def at(hr):
        k=datetime.datetime(dd.year,dd.month,dd.day,hr).strftime("%Y-%m-%dT%H:00"); return idx.get(k)
    def snap(hr,lab):
        i=at(hr)
        if i is None: return None
        cc=H["cloud_cover"][i]; pp=H["precipitation_probability"][i] or 0
        ico="☀️" if cc<25 else "⛅" if cc<65 else "☁️"
        if pp>=45: ico="🌧️"
        return {"when":lab,"temp":round(H["temperature_2m"][i]),"sky":"clear" if cc<25 else "partly cloudy" if cc<65 else "overcast","ico":ico,"wind":round(H["wind_speed_10m"][i]),"precip":pp}
    D=wx["daily"]; ds=dd.strftime("%Y-%m-%d"); j=D["time"].index(ds) if ds in D["time"] else None
    return {"snaps":[x for x in [snap(6,"Dawn"),snap(13,"Midday"),snap(19,"Dusk")] if x],
            "hi":round(D["temperature_2m_max"][j]) if j is not None else None,"lo":round(D["temperature_2m_min"][j]) if j is not None else None,
            "sunrise":(D["sunrise"][j][11:16] if j is not None else ""),"sunset":(D["sunset"][j][11:16] if j is not None else "")}
WXT=wxday(0)
# current light: hour + sky/wind
_h=now_ct.hour; _cloud=50; _wind=6
if wx:
    H=wx["hourly"]; k=now_ct.strftime("%Y-%m-%dT%H:00")
    if k in H["time"]:
        i=H["time"].index(k); _cloud=H["cloud_cover"][i] or 0; _wind=H["wind_speed_10m"][i] or 0
light=riverlib.light_now(_h,_cloud,_wind)
FLYNOW={"clarity":clarity,"light":light,"fly":FLYMATRIX[clarity][light]}

# ---- recent discharge series for the chart (last ~3 days, hourly-ish) ----
series=[]
if OBS:
    step=max(1,len(OBS)//60)
    for i in range(0,len(OBS),step):
        t,v=OBS[i]; series.append({"t":t.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(v)})
    lt,lv=OBS[-1]; series.append({"t":lt.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(lv)})

# ---- solunar + hatch (shared) ----
SOL=riverlib.solunar(now_ct.date(),(WXT or {}).get("sunrise"),(WXT or {}).get("sunset"),CT)
HATCH={"rows":[
 {"name":"Crayfish","icon":"🦞","pattern":"rust/olive, gravel-to-rock","m":[1,1,2,2,3,3,3,3,3,2,1,1]},
 {"name":"Shad / baitfish","icon":"🐟","pattern":"Clouser, chart/white","m":[2,2,2,2,2,2,2,2,3,3,2,2]},
 {"name":"Topwater (diver/popper)","icon":"💥","pattern":"first light & shade lines","m":[0,0,0,1,2,3,3,3,3,2,1,0]},
 {"name":"Hellgrammite","icon":"🐛","pattern":"black/olive, boulder pockets","m":[0,0,1,2,3,3,2,2,1,0,0,0]},
 {"name":"Damsel / dragon","icon":"🪰","pattern":"weed edges & shoals","m":[0,0,0,0,1,2,3,3,2,1,0,0]},
 {"name":"Sculpin / streamer","icon":"🐠","pattern":"Game Changer, stained water","m":[1,1,2,3,2,1,1,1,2,3,2,1]},
]}

# ---- zones (from the shared RIVER_CONFIG) + access (real OSM ramps) ----
ZONES=ECFG["zones"]
ACCESS=[
 {"name":"Joe Wheeler State Park","lat":34.79309,"lon":-87.36951,"zone":"base","types":["ramp"],
  "info":"Trip base — lodging & fuel (park 256-247-5466 · marina 256-247-6971). On the Tennessee River, a 9–10 mi open-water run to the Elk mouth. Don't run the boat to the river from here — trailer to Hatchery Rd."},
 {"name":"Elk River US-72","lat":34.80717,"lon":-87.23358,"zone":"B","types":["ramp","paddle"],
  "info":"US-72 bridge over the lower Elk (~RM 6, Zone B backwater). Nearest ramp to the mouth."},
 {"name":"Sportsman's Park","lat":34.84758,"lon":-87.11714,"zone":"C","types":["ramp"],
  "info":"Off Elk River Mills Rd (~RM 15, Zone C transition)."},
 {"name":"Hatchery Rd (Buck Island)","lat":34.90206,"lon":-87.07802,"zone":"C/D","types":["ramp"],"primary":True,
  "info":"PRIMARY LAUNCH — Hatchery Rd off AL-99, north bank, Limestone Co (~RM 21). Single lane, ~20 unpaved spaces, no facilities. Puts you straight into the transition water: Zone D up, Zone B down. Scout it in daylight first; assume no cell service."},
 {"name":"Easter Ferry","lat":34.92265,"lon":-87.04910,"zone":"D","types":["ramp"],
  "info":"~RM 26, Zone D riverine shoals — near the AL/TN line (TN license above it)."},
 {"name":"Maples Bridge","lat":34.96758,"lon":-87.01820,"zone":"D","types":["ramp"],
  "info":"~RM 30, Zone D — upper river, Tennessee side."},
 {"name":"Veto Access","lat":35.01373,"lon":-86.99561,"zone":"D","types":["ramp"],
  "info":"~RM 36, at the USGS Prospect gauge — the flow number this whole page runs on. Tennessee; TN license required."},
]
# Attach the state's published record per site where TWRA maps one within 400 m.
for _p in ACCESS:
    if "lat" in _p: _p["twra"]=riverlib.twra_for(_p["lat"],_p["lon"],"elk river")

POLY=[[34.74922,-87.27827],[34.75934,-87.2673],[34.77261,-87.27748],[34.78541,-87.26898],[34.80516,-87.23131],[34.80729,-87.22817],[34.81269,-87.22049],[34.82981,-87.20152],[34.83266,-87.18701],[34.821,-87.17671],[34.81998,-87.14671],[34.82829,-87.12903],[34.84651,-87.12273],[34.84732,-87.11857],[34.84807,-87.11751],[34.85105,-87.1141],[34.85431,-87.11124],[34.86155,-87.10925],[34.87268,-87.10787],[34.87775,-87.10552],[34.87936,-87.10519],[34.88104,-87.10485],[34.88715,-87.10787],[34.89616,-87.11103],[34.90434,-87.10828],[34.90508,-87.10579],[34.89966,-87.09581],[34.89936,-87.0936],[34.90147,-87.08386],[34.90169,-87.0828],[34.90181,-87.07931],[34.89906,-87.06601],[34.89883,-87.05942],[34.89906,-87.0562],[34.89568,-87.04678],[34.89494,-87.04232],[34.89663,-87.04049],[34.89925,-87.04077],[34.90149,-87.04279],[34.90362,-87.05275],[34.90816,-87.06219],[34.91126,-87.0635],[34.91472,-87.06341],[34.91695,-87.06102],[34.91803,-87.05942],[34.92243,-87.05081],[34.92283,-87.04968],[34.92309,-87.04898],[34.92389,-87.04715],[34.92695,-87.04255],[34.92872,-87.04207],[34.93115,-87.04216],[34.93703,-87.04155],[34.94053,-87.0412],[34.94321,-87.04269],[34.94537,-87.0428],[34.94707,-87.0424],[34.95099,-87.04227],[34.95368,-87.03942],[34.95887,-87.03594],[34.96423,-87.03043],[34.96603,-87.02608],[34.96765,-87.01895],[34.96781,-87.01858],[34.971,-87.01125],[34.97416,-87.00621],[34.97623,-87.00529],[34.98406,-87.00624],[34.98755,-87.00828],[34.99071,-87.02147],[34.99141,-87.02587],[34.99239,-87.02792],[34.99454,-87.02976],[34.99864,-87.0305],[35.00044,-87.02906],[35.00072,-87.02497],[34.99976,-87.01597],[35.00141,-87.01299],[35.00692,-87.00866],[35.01184,-87.00486],[35.01423,-87.00096],[35.01404,-86.99552]]

# ---- hazards & regulations (Sheets 13–14) ----
HAZARDS=[
 ["🪵","Floating & submerged wood after any rise — the Elk carries a lot of it. Idle unfamiliar shoals before you run them on plane."],
 ["🌊","Sudden stage change when TVA starts or stops generating in the lake zones. Barge & rec traffic on the Tennessee main channel at the mouth — cross it, don't linger."],
 ["🌡️","Heat is the real emergency here, not the boat. A gallon of water per person, electrolytes, long sleeves & a wide brim; hard stop when anyone stops sweating."],
 ["🦺","PFD on every run, kill-switch lanyard clipped in, polarized glasses (they're the only thing between you and a rock at 25 mph). File a float plan at the lodge; assume no cell in the upper zones."],
]
REGS=("Alabama license required (Sep 1–Aug 31); Tennessee license required above the state line — an AL license "
      "doesn't cover Elkton or Prospect. Wheeler: 10 black bass aggregate, no more than 5 smallmouth, 15\" smallmouth "
      "minimum. In midsummer, land them fast, keep them wet, and release everything.")

# split the OSM channel into zone-colored segments so "fish Zones C & D" is SHOWN on the map.
# Zones by river mile from the mouth (atlas): A 0–5 · B 5–12 · C 12–20 · D 20+.
ZCOL={"A":"#4a90c4","B":"#2ba99f","C":"#e6a12e","D":"#d1562f"}
_cum=[0.0]
for _i in range(1,len(POLY)): _cum.append(_cum[-1]+riverlib.haversine(POLY[_i-1],POLY[_i]))
def _zone(rm): return "A" if rm<5 else "B" if rm<12 else "C" if rm<20 else "D"
zoneSegs=[]; _start=0; _zp=_zone(_cum[0])
for _i in range(1,len(POLY)):
    _z=_zone(_cum[_i])
    if _z!=_zp:
        zoneSegs.append({"zone":_zp,"color":ZCOL[_zp],"poly":POLY[_start:_i+1]}); _start=_i; _zp=_z
zoneSegs.append({"zone":_zp,"color":ZCOL[_zp],"poly":POLY[_start:]})
_tgt=("C","D") if plan=="A" else ("A","B")   # Plan A → the river shoals; Plan B → the backwater
for _s in zoneSegs: _s["target"]=_s["zone"] in _tgt

# flow-timer timeline: scrub the observed hydrograph. The Elk is a flow river — no dam pulse to route,
# so the whole reach rises & falls together; the diagram colors every access by the level at that time.
_fr=[]
if OBS:
    _st=max(1,len(OBS)//48)
    for _i in range(0,len(OBS),_st): _fr.append(OBS[_i])
    if _fr[-1]!=OBS[-1]: _fr.append(OBS[-1])
_series=[round(v) for t,v in _fr]
_order=["Veto Access","Maples Bridge","Easter Ferry","Hatchery Rd (Buck Island)","Sportsman's Park","Elk River US-72"]
TIMELINE=({"times":[t.astimezone(CT).strftime("%-m/%-d %-I%p").lower() for t,v in _fr],
  "nowFrame":max(0,len(_fr)-1),"unit":"cfs","refIdx":0,"refName":"Prospect","front":False,"frontThresh":0,
  "srcLabel":"Prospect ↑","mouthLabel":"mouth ↓",
  "bands":[[300,"#20b2aa","Very low"],[700,"#37b3a1","Low & clear"],[1800,"#28c76f","Prime"],[3500,"#f2a832","High & stained"],[10**9,"#8b6cef","Blown out"]],
  "points":[{"name":n,"series":_series} for n in _order]} if _fr else None)

DATA={"today":now_ct.strftime("%A, %B %-d · %-I:%M %p"),"month":now_ct.month,"zoneSegs":zoneSegs,"timeline":TIMELINE,
      "cur":{"cfs":int(cur_cfs) if cur_cfs is not None else None,"band":BLABEL,"bk":BK,"col":BCOL,"trend":trend,
             "fish":BFISH,"do":BDO,"asof":(OBS[-1][0].astimezone(CT).strftime("%-I:%M %p") if OBS else now_ct.strftime("%-I:%M %p"))},
      "plan":{"key":PLAN["key"],"turn":PLAN["turn"],"water":PLAN["water"],"how":PLAN["how"],"reason":plan_reason,
              "alt":(PLAN_B if plan=="A" else PLAN_A)},
      "bands":[["Very low","<300"],["Low & clear","300–700"],["Prime","700–1,800"],["High & stained","1,800–3,500"],["Blown","3,500+"]],
      "series":series,"weather":WXT,"solunar":SOL,"hatch":HATCH,
      "flysel":{"matrix":FLYMATRIX,"order":FLYORDER,"lights":LIGHTS,"boxinv":BOXINV,"now":FLYNOW,
        "rig":"6-wt through the topwater window; drop to a Clouser on a short sink-tip once the sun's up — vary eye weight, not pattern, to change depth.",
        "sources":[["Elk River Field Atlas · Sheet 11","#"],["The Perfect Fly Store","https://perfectflystore.com/your-streams/"]]},
      "zones":ZONES,"access":ACCESS,"points":ACCESS,"poly":POLY,"hazards":HAZARDS,"regs":REGS,
      "chatter":riverlib.load_intel("elk"),
      "gauge":"USGS "+SITE+" · "+ECFG["gauge"]["label"]}

TEMPLATE=r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Elk River · smallmouth (Wheeler)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#16202b;--muted:#66788a;--faint:#93a3b3;--line:#e6ecf2;--card:#fff;--blue:#0a84ff;--green:#28c76f;--amber:#b5651d}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,sans-serif;
 background:radial-gradient(1000px 700px at 82% -6%,#f7efe4 0,transparent 60%),linear-gradient(180deg,#f6f2ec,#efe9e0);min-height:100vh}
.app{max-width:900px;margin:0 auto;padding:30px 22px 80px}
__SWITCH_CSS__
.eyebrow{font-size:12px;letter-spacing:.24em;text-transform:uppercase;color:var(--faint);font-weight:600}
h1{margin:6px 0 4px;font-size:33px;font-weight:750;letter-spacing:-.6px}.cap{color:var(--muted);font-size:14.5px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 26px rgba(20,50,80,.06)}
.sec{font-size:15px;font-weight:700;color:var(--ink);margin:26px 2px 12px}
.now{padding:16px 18px;margin:12px 0;display:flex;align-items:center;gap:16px}
.now .vg{flex:none;padding:11px 14px;text-align:center;color:#fff;font-weight:800;font-size:13px;border-radius:12px;min-width:96px}
.now .b1{font-size:20px;font-weight:700}.now .b2{font-size:13.5px;color:var(--muted);margin-top:2px}
.now .rt{margin-left:auto;text-align:right;font-size:12.5px;color:var(--faint)}.now .rt b{color:var(--ink);font-size:15px;display:block}
.plan{padding:0;margin:12px 0;overflow:hidden}
.plan .ph{padding:16px 18px;color:#fff;background:linear-gradient(135deg,#b5651d,#8a4e16)}
.plan.B .ph{background:linear-gradient(135deg,#0a6bbf,#0a4e8a)}
.plan .pk{font-size:11px;letter-spacing:.16em;text-transform:uppercase;font-weight:700;opacity:.9}
.plan .pt{font-size:21px;font-weight:750;letter-spacing:-.3px;margin-top:3px}
.plan .pr{font-size:13.5px;opacity:.92;margin-top:4px}
.plan .pb{padding:14px 18px}
.plan .pw{font-size:13px;color:var(--ink);font-weight:600}.plan .pw span{color:var(--muted);font-weight:400}
.plan .ph2{font-size:13.5px;color:var(--muted);line-height:1.55;margin-top:8px}
.plan .pmap{font-size:12px;font-weight:600;margin-top:7px}
.plan .alt{font-size:12px;color:var(--faint);border-top:1px solid var(--line);margin-top:12px;padding-top:10px}
.zoneleg{display:flex;flex-wrap:wrap;gap:6px 13px;justify-content:center;margin-top:9px;font-size:11.5px;color:var(--muted)}
.zli{display:inline-flex;align-items:center;gap:5px}.zli i{width:17px;height:4px;border-radius:2px;display:inline-block}
.zli.on{color:var(--ink);font-weight:700}.zli.on i{height:6px}
.chartc{padding:14px 12px 8px}.chartc .lgd{font-size:12px;color:var(--muted);display:flex;gap:12px;justify-content:center;margin-top:6px;flex-wrap:wrap}
.chartc .lgd i{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:5px}
#lmap{height:340px;border-radius:16px}.leaflet-container{border-radius:16px;font-family:inherit}
.maptip{font-size:11.5px;color:var(--faint);text-align:center;margin:7px 0 0}
.zones{padding:6px 16px 12px}.zr{display:flex;gap:12px;padding:11px 0;border-top:1px solid var(--line)}.zr:first-child{border-top:0}
.zr .zc{flex:none;width:30px;height:30px;border-radius:8px;background:#fbeee0;color:#b5651d;font-weight:800;text-align:center;line-height:30px}
.zr .zt{font-size:14px;font-weight:650}.zr .zs{font-size:12.5px;color:var(--muted);margin-top:1px;line-height:1.45}
.acc{padding:6px 16px 12px}.ar{display:flex;align-items:center;gap:12px;padding:11px 0;border-top:1px solid var(--line)}.ar:first-child{border-top:0}
.acc .az{flex:none;width:44px;text-align:center;font-size:10.5px;font-weight:800;color:#fff;padding:5px 0;border-radius:8px;background:#9db0be}
.acc .az.pri{background:#b5651d}.acc .az.base{background:#0a6bbf}
.acc .an{font-size:14px;font-weight:600}.acc .an .pri{font-size:9.5px;font-weight:800;color:#fff;background:#b5651d;border-radius:5px;padding:1px 5px;margin-left:6px;letter-spacing:.03em;vertical-align:1px}
.acc .as{font-size:12.5px;color:var(--muted);margin-top:1px;line-height:1.45}
.acc .ag{margin-top:3px;font-size:11.5px}.acc .ag a{color:#5a86a8;text-decoration:none}
.wx{display:flex;flex-wrap:wrap}.wx .m{flex:1;min-width:110px;padding:12px 14px;border-right:1px solid var(--line)}.wx .m:last-child{border-right:0}
.wx .w{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);font-weight:600}.wx .t{font-size:24px;font-weight:700;margin:2px 0}.wx .d{font-size:12.5px;color:var(--muted)}
.wx .meta{padding:12px 14px;font-size:12.5px;color:var(--muted);display:flex;flex-direction:column;justify-content:center;gap:3px;min-width:150px}
__FLYMATRIX_CSS__
.tips{padding:6px}.tip{display:flex;gap:12px;padding:11px 12px;border-bottom:1px solid var(--line)}.tip:last-child{border-bottom:0}.tip .i{font-size:20px}.tip .x{font-size:13.5px;line-height:1.5}
.regs{padding:14px 16px;font-size:12.5px;color:var(--muted);line-height:1.6}.regs b{color:var(--ink)}
__SOLUNAR_CSS__
__HATCH_CSS__
__CHATTER_CSS__
__LOG_CSS__
__MOONCAL_CSS__
__FLOWTIMER_CSS__
.foot{text-align:center;color:var(--faint);font-size:11.5px;margin-top:26px;line-height:1.6}
@media(max-width:680px){.app{padding:22px 14px 60px}h1{font-size:28px}.wx .m{min-width:0}}
</style></head><body><div class="app">
 __SWITCHER__
 <div class="eyebrow">Summer smallmouth · Elk River, Wheeler Lake → the Tennessee line</div>
 <h1>Elk River</h1><div class="cap" id="cap"></div>
 <div class="card now" id="now"></div>
 <div class="sec">The call · which way to turn</div>
 <div class="card plan" id="plan"></div>
 <div class="sec">Elk at Prospect · last 3 days</div><div class="card chartc" id="chartc"></div>
 <div class="sec">Flow timer · scrub the hydrograph</div><div class="card ft" id="flowtimer"></div>
 <div class="sec">Live map · zones &amp; ramps</div>
 <div class="card" style="padding:8px"><div id="lmap"></div></div>
 <div class="maptip">Real ramps on the OSM Elk channel · mouth → Prospect (~36 river mi) · tap a pin for details &amp; a Google Maps link</div>
 <div class="zoneleg" id="zoneleg"></div>
 <div class="sec">The three rivers in one name · zones</div><div class="card zones" id="zones"></div>
 <div class="sec">Ramps &amp; access</div><div class="card acc" id="acc"></div>
 <div class="sec">Weather</div><div class="card wx" id="wx"></div>
 <div class="sec">Moon &amp; feeding</div><div class="card sol" id="sol"></div>
 <div class="sec">Moon &amp; feeding calendar</div><div class="card mcal" id="mooncal"></div>
 <div class="sec">Fly selection · clarity × light</div><div class="card" id="flysel"></div>
 <div class="sec">Hatch calendar</div><div class="card hatch" id="hatch"></div>
 <div class="sec">Jet doctrine, hazards &amp; rules</div><div class="card tips" id="haz"></div>
 <div class="card regs" id="regs"></div>
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
document.getElementById('cap').innerHTML=D.today+' · '+D.gauge;
(function(){const c=D.cur;document.getElementById('now').innerHTML=
 '<div class="vg" style="background:'+c.col+'">'+c.band+'</div>'
 +'<div><div class="b1">'+(c.cfs!=null?c.cfs.toLocaleString()+' cfs':'—')+' <span style="font-size:14px;color:var(--muted)">'+(c.trend==='rising'?'↑ rising':c.trend==='falling'?'↓ falling':'→ steady')+'</span></div>'
 +'<div class="b2">'+c.fish+'</div></div>'
 +'<div class="rt"><b>'+(c.trend==='falling'?'falling — good':c.trend==='rising'?'rising — tough':'steady')+'</b>as of '+c.asof+'</div>';})();
(function(){const p=D.plan,el=document.getElementById('plan');el.className='card plan '+p.key;
 const ptr=p.key==='A'?'→ Head upstream to the bold amber &amp; red water on the map below — Zones C &amp; D.':'→ Head downstream to the bold blue &amp; teal water on the map below — Zones B &amp; A.';
 el.innerHTML='<div class="ph"><div class="pk">Plan '+p.key+'</div><div class="pt">'+p.turn+'</div><div class="pr">'+p.reason+'</div></div>'
  +'<div class="pb"><div class="pw">Water · <span>'+p.water+'</span></div><div class="ph2">'+p.how+'</div>'
  +'<div class="pmap" style="color:'+(p.key==='A'?'#c0452e':'#0a6bbf')+'">'+ptr+'</div>'
  +'<div class="alt">If it flips: Plan '+p.alt.key+' — '+p.alt.turn.toLowerCase()+' when '+p.alt.when+'.</div></div>';})();
(function(){var Z=[['A','Mouth','#4a90c4'],['B','Backwater','#2ba99f'],['C','Transition','#e6a12e'],['D','River','#d1562f']];
 var tgt=D.plan.key==='A'?['C','D']:['A','B'];var h='';
 Z.forEach(function(z){var on=tgt.indexOf(z[0])>=0;h+='<span class="zli'+(on?' on':'')+'"><i style="background:'+z[2]+'"></i>'+z[0]+' · '+z[1]+(on?' ← today':'')+'</span>';});
 document.getElementById('zoneleg').innerHTML=h;})();
// discharge chart with atlas bands
(function(){const S=D.series,el=document.getElementById('chartc');
 if(!S.length){el.innerHTML='<div style="padding:20px;color:var(--muted)">gauge unavailable</div>';return;}
 const W=860,H=200,pad=40,fs=S.map(p=>p.f),fmax=Math.max(2000,Math.max(...fs)*1.1);
 const x=i=>pad+i*(W-pad-10)/(S.length-1),y=f=>H-24-f/fmax*(H-44);
 function bnd(a,b,c){var yb=y(Math.min(b,fmax));return '<rect x="'+pad+'" y="'+yb+'" width="'+(W-pad-10)+'" height="'+Math.max(0,(y(Math.min(a,fmax))-yb))+'" fill="'+c+'"/>';}
 let bands=bnd(0,300,'rgba(32,178,170,.10)')+bnd(300,700,'rgba(55,179,161,.12)')+bnd(700,1800,'rgba(40,199,111,.15)')+bnd(1800,3500,'rgba(242,168,50,.15)')+bnd(3500,fmax,'rgba(139,108,239,.13)');
 let path='';S.forEach((p,i)=>{path+=(path?' L':'M')+x(i).toFixed(0)+','+y(p.f).toFixed(0);});
 let ax='';for(let i=0;i<S.length;i+=Math.ceil(S.length/6)){ax+='<text x="'+x(i)+'" y="'+(H-6)+'" font-size="10" fill="#93a3b3" text-anchor="middle">'+S[i].t.split(' ')[0]+'</text>';}
 [700,1800,3500].forEach(g=>{if(g<fmax)ax+='<text x="4" y="'+(y(g)+3)+'" font-size="9" fill="#93a3b3">'+(g>=1000?(g/1000)+'k':g)+'</text>';});
 document.getElementById('chartc').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" width="100%">'+bands
  +'<path d="'+path+'" fill="none" stroke="#8a4e16" stroke-width="2.5"/>'+ax
  +'<circle cx="'+x(S.length-1)+'" cy="'+y(S[S.length-1].f)+'" r="4" fill="#8a4e16"/></svg>'
  +'<div class="lgd"><span><i style="background:rgba(40,199,111,.6)"></i>prime .7–1.8k</span><span><i style="background:rgba(242,168,50,.6)"></i>high/stained</span><span><i style="background:rgba(139,108,239,.5)"></i>blown</span></div>';})();
(function(){let h='';D.zones.forEach(z=>{h+='<div class="zr"><div class="zc">'+z[0]+'</div><div><div class="zt">'+z[1]+'</div><div class="zs">'+z[2]+'</div></div></div>';});document.getElementById('zones').innerHTML=h;})();
(function(){let h='';D.access.forEach(a=>{const pri=a.primary,base=a.zone==='base';
  h+='<div class="ar"><div class="az'+(pri?' pri':base?' base':'')+'">'+(base?'BASE':a.zone)+'</div>'
   +'<div style="flex:1;min-width:0"><div class="an">'+a.name+(pri?'<span class="pri">PRIMARY</span>':'')+'</div>'
   +'<div class="as">'+a.info+'</div>'
   +'<div class="ag"><a href="https://www.google.com/maps/search/?api=1&query='+a.lat+','+a.lon+'" target="_blank" rel="noopener">📍 Open in Google Maps →</a></div></div></div>';});
  document.getElementById('acc').innerHTML=h;})();
(function(){const w=D.weather,el=document.getElementById('wx');if(!w){el.innerHTML='<div class="meta">weather unavailable</div>';return;}
 let h='';(w.snaps||[]).forEach(s=>h+='<div class="m"><div class="w">'+s.when+'</div><div class="t">'+s.ico+' '+s.temp+'°</div><div class="d">'+s.sky+' · '+s.wind+' mph'+(s.precip?' · '+s.precip+'%':'')+'</div></div>');
 h+='<div class="meta"><div>High '+(w.hi??'–')+'° · Low '+(w.lo??'–')+'°</div><div>Sun '+w.sunrise+'–'+w.sunset+'</div><div>Feed hard the first 2 hrs; done by mid-morning.</div></div>';el.innerHTML=h;})();
renderSolunar('sol',D.solunar,D.cur.trend==='falling'?'Falling water on a major window is the best card this river deals — be on the shoals at first light.':'Fish the first two hours hard; these are oxygen-and-shade fish, effectively done by mid-morning.');
buildMoonCal('mooncal',34.902,-87.078);
buildFlowTimer('flowtimer',D.timeline);
// fly matrix
buildFlyMatrix('flysel',D.flysel);
renderHatch('hatch',D.hatch,D.month);
(function(){let h='';D.hazards.forEach(t=>h+='<div class="tip"><div class="i">'+t[0]+'</div><div class="x">'+t[1]+'</div></div>');document.getElementById('haz').innerHTML=h;})();
document.getElementById('regs').innerHTML='<b>Rules & licenses.</b> '+D.regs;
renderChatter('chatter',D.chatter,'chatterSec');
buildLog('log','riverlog-elk',D.access.map(a=>a.name),null);
document.getElementById('foot').textContent='Flow: USGS 03584600 (Elk River at Prospect, TN). Backwater current is TVA (Wheeler pool & generation). Flow bands, Plan A/B, zones, fly matrix & hazards from the Elk River Field Atlas (Edition One) — a planning document; verify ramps, depths & regs before you launch. Weather: Open-Meteo. Channel & ramps: OpenStreetMap.';
buildRiverMap(D,'#b5651d',D.zoneSegs);
</script></body></html>"""
html=riverlib.render(TEMPLATE,"elk").replace("__DATA__",json.dumps(DATA))
open(os.path.join(OUT,"elk.html"),"w").write(html)
# ---- HQ status card ----
_EB={"prime":("Prime",3.0),"low":("Good",2.3),"high":("Good",2.0),"vlow":("Fair",1.3),"blown":("Slow",0.8),"na":("Fair",1.6)}
_eg,_ebase=_EB.get(BK,("Fair",1.6))

# ---- HQ day state ----
# NO FLOW FORECAST EXISTS for this river: the only forward data is weather, not water.
# Today's curve is therefore what the gauge has ALREADY recorded (src="observed", partial
# by definition) and tomorrow has no curve at all. Inventing one would make a flat line
# look like a prediction.
_LO = 200
def _lvl_g(m):
    if m < _LO:        return "low",   format(round(m), ",") + " cfs \u00b7 skinny"
    if m < _LO * 8:    return "prime", format(round(m), ",") + " cfs"
    if m < _LO * 25:   return "high",  format(round(m), ",") + " cfs \u00b7 pushy"
    return "blown", format(round(m), ",") + " cfs \u00b7 blown"
def _gauge_day(off):
    d0, _ = riverlib.day_bounds(CT, off)
    if off != 0:
        return riverlib.day_state(vessel="boat", vessel_why="jet / kayak float river",
            headline="No flow forecast for this river \u2014 check the gauge on the day")
    cv = riverlib.curve_from_rows(OBS, d0)
    vals = [v for v in (cv or []) if v is not None]
    if not vals:
        return riverlib.day_state(vessel="boat", vessel_why="jet / kayak float river", headline="No gauge reading today")
    med = sorted(vals)[len(vals) // 2]
    lk, ld = _lvl_g(med)
    # Vessel from the sourced model (riverlib.WATER_MODEL) rather than a fixed guess.
    # craft_label honours the user-stated craft set for this reach (riverlib.WATER_MODEL),
    # so the board never suggests a vessel this river does not take.
    _vk, _vlabel, _vw, _conf = riverlib.craft_label("elk", med)
    ck = "clear" if med < _LO * 4 else "stained" if med < _LO * 12 else "colored"
    return riverlib.day_state(vessel=_vk, vessel_why=_vw, vessel_label=_vlabel,
        clarity=ck, clarity_why="inferred from flow, not measured",
        level=lk, level_detail=ld,
        curve=cv, curve_unit="cfs", curve_label="Observed flow (gauge)", curve_src="observed",
        headline=format(round(med), ",") + " cfs \u2014 observed only, no forecast")
DAYS = {"today": _gauge_day(0), "tomorrow": _gauge_day(1)}

riverlib.emit_status("elk",
    {"grade":_eg,"cond":BLABEL,"col":BCOL,"note":BFISH,
     "detail":(("%s cfs"%format(int(cur_cfs),",")) if cur_cfs is not None else "—"),
     "asof":(OBS[-1][0].astimezone(CT).strftime("%-I:%M %p") if OBS else now_ct.strftime("%-I:%M %p"))},
    wx, _ebase, CT, ["Smallmouth","Panfish"], "Warmwater smallmouth", "~2 hr · destination (AL)", days=DAYS)
print("wrote out/elk.html | %s cfs %s | band %s | Plan %s"%(cur_cfs,trend,BLABEL,plan))
