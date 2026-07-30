#!/usr/bin/env python3
"""
Elk River · Tims Ford tailwater (TN) — cold put-and-take trout below Tims Ford Dam.
A DIFFERENT model again: this is a TVA-generation-driven trout tailwater, but — unlike the
Caney or Cumberland — there is no clean live release feed for Tims Ford. The only live USGS
gauge (03582000, Elk River above Fayetteville) sits ~30 mi downstream and LAGS the real
release, so it is a rough "is the river up or down" indicator only. The page is honest about
that and pushes you to the TVA Tims Ford generation schedule before you ever wade.
Sources: USGS, Open-Meteo, OpenStreetMap, TVA.
"""
import json,urllib.request,datetime,os,sys
from zoneinfo import ZoneInfo
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import riverlib
CT=ZoneInfo("America/Chicago"); UA={"User-Agent":"elktn/1.0"}
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"out"); os.makedirs(OUT,exist_ok=True)
def get(u,h=None):
    # riverlib.get retries transient TLS/DNS/5xx failures; a single flaky fetch used to
    # build this page with missing data instead of failing (see riverlib.get docstring).
    return riverlib.get(u,{**UA,**(h or {})},timeout=60)
now=datetime.datetime.now(datetime.timezone.utc); now_ct=now.astimezone(CT)
CFG=riverlib.RIVER_CONFIG["elktn"]; SITE=CFG["gauge"]["site"]
GLAT,GLON=35.19,-86.28   # the tailwater (below Tims Ford Dam)
TVA_URL="https://www.tva.com/environment/lake-levels/tims-ford"

# ---- USGS gauge: observed discharge (00060) + stage (00065), ~4 days ----
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
# trend over the last ~6h of discharge
trend="steady"
if len(FLOW)>=2:
    ref=next((o for o in reversed(FLOW) if (FLOW[-1][0]-o[0]).total_seconds()>=5*3600), FLOW[0])
    dv=FLOW[-1][1]-ref[1]
    base=max(150.0,ref[1]*0.08)
    trend="rising" if dv>base else "falling" if dv<-base else "steady"

# ---- fishability (cold trout tailwater; flow in cfs at the downstream gauge) ----
def fish(flow,rising,falling):
    if flow is None: return ("—","Fair","#94a3b1","no gauge data — check the TVA Tims Ford schedule")
    if flow>1200: return ("High","Tough","#8b6cef","big water down here — don't wade; heavy streamers from the bank or sit it out")
    if flow>450:  return ("Up","Fair","#f2a832",
        ("up & still rising — likely generation reaching down; treat it as dangerous to wade" if rising else
         "elevated & easing — generation or rain; it lags up top, so confirm the TVA schedule" if falling else
         "up — generation or rain; the gauge lags the dam, so confirm the TVA schedule before wading"))
    return ("Low","Prime" if not rising else "Good","#28c76f",
        ("near baseflow but ticking up — get your wade time in early, be ready to climb out" if rising else
         "near baseflow — Tims Ford likely off; wade the shoals with midges & scuds and sight-fish"))
FN,FG,FCOL,FNOTE=fish(cur_flow,trend=="rising",trend=="falling")

# ---- weather (Open-Meteo, at the tailwater) ----
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
# tailwater water temp is dam-controlled & cold year-round — not air-driven. Hold a coldwater estimate.
wtemp=54

# ---- observed hydrograph series (downsampled to ~48 pts) ----
series=[]
if FLOW:
    step=max(1,len(FLOW)//48)
    for i in range(0,len(FLOW),step):
        t,v=FLOW[i]; series.append({"t":t.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(v)})
    lt,lv=FLOW[-1]; last={"t":lt.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(lv)}
    if not series or series[-1]!=last: series.append(last)

# ---- solunar + trout hatch + fly matrix (shared components) ----
SOL=riverlib.solunar(now_ct.date(),(WXT or {}).get("sunrise"),(WXT or {}).get("sunset"),CT)
# Tailwater trout forage calendar (0-3 by month). Cold, bug-rich water — scuds & midges never stop.
HATCH={"rows":[
 {"name":"Midge","icon":"🦟","pattern":"zebra midge #18–22","m":[3,3,3,3,2,2,2,2,2,3,3,3]},
 {"name":"Sowbug / scud","icon":"🦐","pattern":"#14–18, the bottom staple","m":[3,3,3,3,3,3,3,3,3,3,3,3]},
 {"name":"Blue-wing olive","icon":"🪰","pattern":"BWO #18–22, cloudy days","m":[1,2,3,2,1,0,0,0,1,2,3,2]},
 {"name":"Sulphur / mayfly","icon":"🌼","pattern":"#14–18, late spring–summer","m":[0,0,1,2,3,3,2,1,1,0,0,0]},
 {"name":"Caddis","icon":"🦋","pattern":"#14–16, spring","m":[0,0,1,2,3,2,1,1,1,1,0,0]},
 {"name":"Sculpin / streamer","icon":"🐠","pattern":"browns, low light & rise","m":[2,2,2,2,1,1,1,1,2,3,3,2]},
 {"name":"Fresh stockers","icon":"🎣","pattern":"pellet/egg behind a stocking","m":[0,0,3,3,3,2,2,2,3,3,3,1]},
]}
# clarity × light fly matrix (trout tailwater). Clarity read off the (downstream) flow band.
FLYMATRIX={
 "clear":   {"label":"Off / low · wadeable","dawn":"Zebra midge #20","low":"Sowbug #16","bright":"Midge #22 (sight)","wind":"Scud #14"},
 "moderate":{"label":"Slight bump","dawn":"Pheasant Tail #16","low":"Sowbug/scud #16","bright":"Zebra midge #20","wind":"Scud #14"},
 "stained": {"label":"Generating","dawn":"Woolly Bugger","low":"Sculpin","bright":"PT #14 dropper","wind":"Sculpin"},
 "muddy":   {"label":"High / off-color","dawn":"Big sculpin","low":"Articulated streamer","bright":"Bugger, black","wind":"Sculpin"},
}
FLYORDER=["clear","moderate","stained","muddy"]; LIGHTS=[("dawn","Dawn"),("low","Low light"),("bright","Bright sun"),("wind","Wind / chop")]
BOXINV=[
 ["Zebra midge","#18–22","The everyday staple — tandem under an indicator, dead-drift the shoals & runs."],
 ["Sowbug / scud","#14–18","Year-round bottom bug — sight-fish it to cruising fish when the water's off."],
 ["Pheasant Tail","#16–20","Spring & fall mayfly nymph — dropper under the midge."],
 ["Blue-wing olive","#18–22","Cloudy spring & fall afternoons — emerger or a small dry in the hatch."],
 ["Sculpin / Woolly Bugger","#4–8","Browns on the rise & generation — swing it or strip from the bank."],
 ["Y2K / egg","#12–14","A little color behind fresh stockers and when the water bumps up."],
]
_dc=cur_flow
_dcl=("clear" if _dc is None or _dc<450 else "moderate" if _dc<900 else "stained" if _dc<1500 else "muddy")
_dh=now_ct.hour; _dcloud=50; _dwind=6
if wx:
    _H=wx["hourly"]; _k=now_ct.strftime("%Y-%m-%dT%H:00")
    if _k in _H["time"]: _wi=_H["time"].index(_k); _dcloud=_H["cloud_cover"][_wi] or 0; _dwind=_H["wind_speed_10m"][_wi] or 0
_dlight=riverlib.light_now(_dh,_dcloud,_dwind)
FLYSEL={"matrix":FLYMATRIX,"order":FLYORDER,"lights":LIGHTS,"boxinv":BOXINV,
  "now":{"clarity":_dcl,"light":_dlight,"fly":FLYMATRIX[_dcl][_dlight]},
  "rig":"Midge & sowbug on the bottom under an indicator, 6–7X to #18–22, is the money rig when the water's off. Sight-fish the shoals. When it's up or generating, clip on a sculpin/bugger and work it from the bank — do not wade a rising river.",
  "sources":[["Middle TN Fly Fishers","https://middletennesseeflyfishers.org/elk-river-tn.html"],["On The Fly South","https://ontheflysouth.com/tims-ford-tailwater-trout/"],["Fly Fish Tennessee","https://flyfishtennessee.com/Tailwaters/elkriver.html"]]}

# ---- guide's take (trout tailwater) ----
tips=[["🌊","Know the generation before you step in. Tims Ford is TVA-run and there's no clean live release feed — the gauge here is ~30 mi downstream and lags, so open the TVA Tims Ford schedule and plan your wade window around water-OFF."]]
if cur_flow is not None and cur_flow<450 and trend!="rising":
    tips.append(["🎣","Water's low — this is the day to wade. Midge/sowbug tandem under an indicator, long light tippet, and sight-fish the shoals from the dam down. Move slow; these are pressured, stocked-and-holdover trout."])
    tips.append(["🔎","Sight-fishing pays: spot a fish, lead it, and let the flies swing to it. First and last light are best; a BWO afternoon in spring/fall brings them up."])
else:
    tips.append(["⚠️","Water's up — treat it as generating and dangerous to wade. Fish streamers (sculpin, bugger) from the bank and the accesses; the rise is when the browns hunt. Get in only once you've confirmed it's off and falling."])
tips.append(["🐟","Put-and-take fishery — TWRA stocks rainbows (and browns/cutthroat) monthly Mar–Dec, ~38k a year. Fresh stockers hold near the access points; holdovers spread into the shoals and wood down toward Old Dam Ford."])
tips.append(["❄️","Cold year-round (~50s °F) — dress for it even in summer, and remember trout stress fast in warm surface air; land them quick and keep them wet."])

# ---- real accesses on the OSM tailwater channel (dam → Farris Bridge → Old Dam Ford) ----
POINTS=[
 {"name":"Below the dam (Hwy 50)","lat":35.20744,"lon":-86.25383,"types":["wade"],
  "info":"TVA tailwater access just below Tims Ford Dam off Hwy 50 — the top of the trout water and the best wade shoals when the water's off. Know the generation schedule and be out before it starts.","rm":0.5},
 {"name":"Farris Creek Bridge","lat":35.19684,"lon":-86.27855,"types":["wade","paddle"],
  "info":"TVA river access at Farris Creek Bridge, mid-tailwater — wade or put a kayak in for the float down toward Old Dam Ford.","rm":6.0},
 {"name":"Old Dam Ford","lat":35.12406,"lon":-86.33227,"types":["wade","paddle"],
  "info":"Lower end of the stocked trout zone, where Beans Creek comes in (~12 river mi from the dam). Trout thin out below here as the water warms.","rm":12.0},
]
POLY=[[35.20471,-86.24607],[35.20804,-86.25679],[35.20436,-86.25426],[35.20096,-86.25049],[35.19664,-86.25564],[35.19927,-86.25984],[35.19994,-86.26465],[35.20709,-86.26722],[35.21291,-86.26963],[35.21179,-86.26113],[35.20969,-86.2746],[35.20432,-86.27439],[35.19769,-86.27791],[35.19506,-86.2784],[35.19245,-86.28065],[35.18579,-86.2814],[35.1847,-86.28253],[35.18641,-86.28588],[35.18897,-86.28803],[35.19195,-86.28937],[35.19528,-86.28991],[35.1965,-86.28907],[35.19662,-86.29195],[35.1931,-86.29537],[35.18993,-86.29756],[35.1904,-86.30054],[35.19569,-86.30806],[35.19643,-86.31081],[35.1954,-86.31201],[35.1915,-86.3103],[35.18749,-86.30619],[35.18587,-86.3062],[35.18223,-86.31076],[35.18095,-86.31045],[35.17761,-86.30008],[35.1774,-86.29276],[35.17603,-86.29094],[35.16713,-86.29486],[35.16661,-86.30327],[35.17137,-86.30811],[35.17152,-86.31394],[35.1653,-86.31799],[35.15947,-86.31921],[35.15346,-86.3199],[35.14755,-86.31653],[35.14683,-86.32026],[35.14902,-86.32523],[35.14914,-86.32804],[35.14677,-86.33352],[35.14459,-86.33137],[35.13685,-86.32132],[35.13532,-86.31585],[35.13303,-86.31348],[35.12609,-86.32017],[35.12262,-86.32714],[35.12362,-86.33277],[35.12705,-86.33619],[35.12913,-86.33911],[35.12909,-86.34464]]

clar="clearing" if trend=="falling" else "rising / up" if trend=="rising" else "steady"
DATA={"today":now_ct.strftime("%A, %B %-d · %-I:%M %p"),"solunar":SOL,"hatch":HATCH,"month":now_ct.month,
      "chatter":riverlib.load_intel("elktn"),"flysel":FLYSEL,"tips":tips,"weather":WXT,"series":series,"tva":TVA_URL,
      "cur":{"flow":round(cur_flow) if cur_flow is not None else None,"stage":round(cur_stage,2) if cur_stage is not None else None,
             "trend":trend,"cond":FN,"grade":FG,"col":FCOL,"note":FNOTE,"clar":clar,"wtemp":wtemp,"asof":asof},
      "points":POINTS,"poly":POLY}

TEMPLATE=r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Elk River · Tims Ford tailwater trout</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#16202b;--muted:#66788a;--faint:#93a3b3;--line:#e6ecf2;--card:#fff;--blue:#0a84ff;--green:#28c76f}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,sans-serif;
 background:radial-gradient(1000px 700px at 82% -6%,#e7f2fb 0,transparent 60%),linear-gradient(180deg,#eef4f9,#e6edf4);min-height:100vh}
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
.safe{display:flex;gap:11px;background:#fff5f4;border:1px solid #f5d7d4;border-radius:14px;padding:13px 15px;margin:12px 0;font-size:12.8px;color:#8a3b34;line-height:1.5}.safe b{color:#6f2a24}
.safe a{color:#b3392f;font-weight:700}
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
__HATCH_CSS__
__CHATTER_CSS__
__LOG_CSS__
__MOONCAL_CSS__
__FLYMATRIX_CSS__
.foot{text-align:center;color:var(--faint);font-size:11.5px;margin-top:26px;line-height:1.6}
@media(max-width:680px){.app{padding:22px 14px 60px}h1{font-size:28px}.wx .m{min-width:0}}
</style></head><body><div class="app">
 __SWITCHER__
 <div class="eyebrow">Tailwater trout · below Tims Ford Dam, TN</div>
 <h1>Elk River · Tims Ford</h1><div class="cap" id="cap"></div>
 <div class="card now" id="now"></div>
 <div class="safe" id="safe"></div>
 <div class="sec">Flow · downstream gauge (last 4 days)</div><div class="card chartc" id="chartc"></div>
 <div class="note" id="chartnote"></div>
 <div class="sec">Live map · tailwater accesses</div>
 <div class="card" style="padding:8px"><div id="lmap"></div></div>
 <div class="maptip">Real TVA / public accesses on the OSM channel · Tims Ford Dam → Old Dam Ford, ~12 river mi · tap a pin for details &amp; a Google Maps link</div>
 <div class="sec">Guide's take</div><div class="card tips" id="tips"></div>
 <div class="sec">Weather</div><div class="card wx" id="wx"></div>
 <div class="sec">Moon &amp; feeding</div><div class="card sol" id="sol"></div>
 <div class="sec">Moon &amp; feeding calendar</div><div class="card mcal" id="mooncal"></div>
 <div class="sec">Hatch calendar</div><div class="card hatch" id="hatch"></div>
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
__HATCH_JS__
__CHATTER_JS__
__LOG_JS__
__MOONCAL_JS__
__FLYMATRIX_JS__
document.getElementById('cap').innerHTML=D.today+' · Elk River above Fayetteville gauge (USGS 03582000) — a downstream, lagging indicator';
(function(){const c=D.cur;document.getElementById('now').innerHTML=
 '<div class="vg" style="background:'+c.col+'">'+c.cond+'</div>'
 +'<div><div class="b1">'+(c.flow!=null?c.flow.toLocaleString()+' cfs':'—')+(c.stage!=null?' · '+c.stage+' ft':'')+' <span style="font-size:14px;color:var(--muted)">'+(c.trend==='rising'?'↑ rising':c.trend==='falling'?'↓ falling':'→ steady')+'</span></div>'
 +'<div class="b2">'+c.note+'</div></div>'
 +'<div class="rt"><b>'+c.grade+'</b>water '+c.clar+'<br>~'+c.wtemp+'°F (cold)<br><span style="font-size:11px">as of '+c.asof+' · ~30 mi downstream</span></div>';})();
document.getElementById('safe').innerHTML='<div style="font-size:16px">⚠</div><div><b>Check generation before you wade.</b> Tims Ford Dam is TVA-operated and generation makes this river rise fast and turn DANGEROUS — the gauge above is ~30 mi downstream and lags the release, so it will look calm here after the water is already coming up at the dam. Open the <a href="'+D.tva+'" target="_blank" rel="noopener">TVA Tims Ford schedule</a> and plan your wade window around water-OFF. Little warning once it moves; be out before it starts.</div>';
// observed hydrograph (downstream gauge)
(function(){const S=D.series;if(!S.length){document.getElementById('chartc').innerHTML='<div style="padding:20px;color:var(--muted)">gauge data unavailable</div>';return;}
 const W=860,H=200,pad=40,fs=S.map(p=>p.f),fmax=Math.max(600,...fs)*1.12,fmin=0;
 const x=i=>pad+i*(W-pad-10)/(S.length-1),y=f=>H-24-(f-fmin)/(fmax-fmin)*(H-44);
 function band(a,b,col){const yb=y(Math.min(b,fmax));return '<rect x="'+pad+'" y="'+yb+'" width="'+(W-pad-10)+'" height="'+Math.max(0,(y(a)-yb))+'" fill="'+col+'"/>';}
 let bands=band(0,450,'rgba(40,199,111,.14)')+band(450,1200,'rgba(242,168,50,.13)')+band(1200,fmax,'rgba(139,108,239,.12)');
 let path='';S.forEach((p,i)=>{path+=(path?' L':'M')+x(i).toFixed(0)+','+y(p.f).toFixed(0);});
 let ax='';for(let i=0;i<S.length;i+=Math.ceil(S.length/6)){ax+='<text x="'+x(i)+'" y="'+(H-6)+'" font-size="10" fill="#93a3b3" text-anchor="middle">'+S[i].t.split(' ')[0]+'</text>';}
 [450,1200].forEach(g=>{ax+='<line x1="'+pad+'" y1="'+y(g)+'" x2="'+(W-10)+'" y2="'+y(g)+'" stroke="#dfe7ee" stroke-dasharray="4 4"/><text x="4" y="'+(y(g)+3)+'" font-size="9" fill="#93a3b3">'+g+'</text>';});
 document.getElementById('chartc').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" width="100%">'+bands
  +'<path d="'+path+'" fill="none" stroke="#1e7ac2" stroke-width="2.5"/>'+ax+'</svg>'
  +'<div class="lgd"><span><i style="background:rgba(40,199,111,.6)"></i>low / likely off</span><span><i style="background:rgba(242,168,50,.6)"></i>up — check TVA</span><span><i style="background:rgba(139,108,239,.5)"></i>high</span></div>';})();
document.getElementById('chartnote').textContent='This is the USGS gauge ~30 mi downstream at Fayetteville — it lags Tims Ford releases by hours and mixes in ~30 mi of extra drainage, so read it as a rough "up or down," not the actual water on your shoal. The TVA schedule is the real signal.';
(function(){let h='';D.tips.forEach(t=>h+='<div class="tip"><div class="i">'+t[0]+'</div><div class="x">'+t[1]+'</div></div>');document.getElementById('tips').innerHTML=h;})();
(function(){const w=D.weather,el=document.getElementById('wx');if(!w){el.innerHTML='<div class="meta">weather unavailable</div>';return;}
 let h='';(w.snaps||[]).forEach(s=>h+='<div class="m"><div class="w">'+s.when+'</div><div class="t">'+s.ico+' '+s.temp+'°</div><div class="d">'+s.sky+' · '+s.wind+' mph'+(s.precip?' · '+s.precip+'%':'')+'</div></div>');
 h+='<div class="meta"><div>High '+(w.hi??'–')+'° · Low '+(w.lo??'–')+'°</div><div>Sun '+w.sunrise+'–'+w.sunset+'</div><div style="color:var(--faint)">water stays cold — dam-controlled</div></div>';el.innerHTML=h;})();
renderSolunar('sol',D.solunar,D.cur.trend!=='rising'?'Best when the water is off: a major feeding window over the shoals at first or last light.':'Water is up — fish the majors from the bank until it drops.');
renderHatch('hatch',D.hatch,D.month);
buildMoonCal('mooncal',35.19,-86.28);
buildFlyMatrix('flysel',D.flysel);
document.getElementById('regs').innerHTML='<b>Regulations.</b> '+__REGS__;
renderChatter('chatter',D.chatter,'chatterSec');
buildLog('log','riverlog-elktn',D.points.map(p=>p.name),null);
document.getElementById('foot').textContent='Flow: USGS 03582000 (Elk River above Fayetteville) — ~30 mi downstream of the trout zone, a lagging indicator; the TVA Tims Ford generation schedule is the real release signal. Fishability & water-temp are estimates — tune from the water. Weather: Open-Meteo. Channel & accesses from OpenStreetMap. Personal use.';
buildRiverMap(D,D.cur.col);
</script></body></html>"""
html=(riverlib.render(TEMPLATE,"elktn")
      .replace("__REGS__",json.dumps(CFG["regs"]))
      .replace("__DATA__",json.dumps(DATA)))
open(os.path.join(OUT,"elktn.html"),"w").write(html)
# ---- HQ status card ----
_TB={"Prime":2.7,"Good":2.2,"Fair":1.3,"Tough":0.7}
riverlib.emit_status("elktn",
    {"grade":FG,"cond":FN,"col":FCOL,"note":FNOTE,
     "detail":(("%s cfs (downstream)"%format(round(cur_flow),",")) if cur_flow is not None else "—"),"asof":asof},
    wx, _TB.get(FG,1.6), CT, ["Trout"], "Trout tailwater", "~90 min · SE of Nashville")
print("wrote out/elktn.html | flow %s cfs %s | grade %s | series %d pts"%(cur_flow,trend,FG,len(series)))
