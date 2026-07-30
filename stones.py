#!/usr/bin/env python3
"""
Stones River — below J. Percy Priest Dam to the Cumberland confluence.
A PEAKING tailwater: one turbine, near-zero release between generation pulses. The lower reach
(Heartland ramp → Cumberland confluence) stays floatable because the Cumberland (Cheatham pool)
backs it up — that's the reliable power-drifter water. The upper tailwater is skinny & wadeable
when the dam's off. White bass, striper, panfish + a stocked WINTER trout run, all on the fly.
Live gauge = USGS 03430200 (Stones River at US-70 near Donelson). Sources: USGS, USACE, OSM.
"""
import json,urllib.request,datetime,os,sys
from zoneinfo import ZoneInfo
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import riverlib
CT=ZoneInfo("America/Chicago"); UA={"User-Agent":"stones/1.0"}
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"out"); os.makedirs(OUT,exist_ok=True)
def get(u,h=None):
    with urllib.request.urlopen(urllib.request.Request(u,headers={**UA,**(h or {})}),timeout=60) as r: return json.load(r)
now=datetime.datetime.now(datetime.timezone.utc); now_ct=now.astimezone(CT)
CFG=riverlib.RIVER_CONFIG["stones"]; SITE=CFG["gauge"]["site"]
GLAT,GLON=36.185,-86.665
USACE_URL="https://www.lrn-wc.usace.army.mil/basin_project.shtml?p=jpp"

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
    ref=next((o for o in reversed(FLOW) if (FLOW[-1][0]-o[0]).total_seconds()>=3*3600), FLOW[0])
    dv=FLOW[-1][1]-ref[1]
    trend="rising" if dv>150 else "falling" if dv<-150 else "steady"

def fish(flow,rising):
    if flow is None: return ("—","Fair","#94a3b1",1.3,"no gauge data — check the Percy Priest release schedule")
    if flow>4000: return ("High","Fair","#8b6cef",1.3,"heavy release — strong current below the dam; fish the eddies, creek mouths & slack")
    if flow>=200:
        return ("Gen","Prime" if rising else "Good","#28c76f",(2.7 if rising else 2.4),
            ("turbine running and rising — current's on; white bass & stripers stacking in the tailrace" if rising
             else "turbine running — white bass & stripers in the tailrace; current's on"))
    return ("Off","Slow","#f2a832",1.1,"Priest idle — upper reach skinny & wadeable; power-drift only the lower slackwater near the Cumberland")
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

series=[]
if FLOW:
    step=max(1,len(FLOW)//48)
    for i in range(0,len(FLOW),step):
        t,v=FLOW[i]; series.append({"t":t.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(v)})
    lt,lv=FLOW[-1]; last={"t":lt.astimezone(CT).strftime("%-m/%-d %-I%p").lower(),"f":round(lv)}
    if not series or series[-1]!=last: series.append(last)

SOL=riverlib.solunar(now_ct.date(),(WXT or {}).get("sunrise"),(WXT or {}).get("sunset"),CT)
HATCH={"rows":[
 {"name":"White bass run","icon":"🎏","pattern":"chartreuse Clouser in the tailrace","m":[1,2,3,3,2,1,1,1,1,1,1,1]},
 {"name":"Striper / hybrid","icon":"🎣","pattern":"baitfish streamer on the current","m":[1,1,2,3,3,2,2,2,2,2,1,1]},
 {"name":"Shad","icon":"🐟","pattern":"match-the-baitfish streamer","m":[3,3,3,3,3,3,3,3,3,3,3,3]},
 {"name":"Crawfish","icon":"🦞","pattern":"craw fly on the rock","m":[1,1,2,3,3,3,3,3,3,2,1,1]},
 {"name":"Bluegill / panfish","icon":"🐡","pattern":"popper & bream bug, backwaters","m":[0,0,1,2,3,3,3,3,2,1,0,0]},
 {"name":"Winter trout","icon":"❄️","pattern":"stocked rainbows, midge rig","m":[3,3,1,0,0,0,0,0,0,0,0,3]},
]}
FLYMATRIX={
 "clear":   {"label":"Off · <200","dawn":"Small popper","low":"Sparse Clouser","bright":"Midge / nymph","wind":"Woolly Bugger"},
 "moderate":{"label":"Gen · 200–1k","dawn":"Chartreuse Clouser","low":"Woolly Bugger","bright":"Clouser, deep","wind":"Bugger, dark"},
 "stained": {"label":"Gen · 1–4k","dawn":"Baitfish streamer","low":"Big Clouser","bright":"Clouser on sink-tip","wind":"Chartreuse streamer"},
 "muddy":   {"label":"High · >4k","dawn":"Black streamer","low":"Big black bugger","bright":"Chart/white Clouser","wind":"Big black streamer"},
}
FLYORDER=["clear","moderate","stained","muddy"]; LIGHTS=[("dawn","Dawn"),("low","Low light"),("bright","Bright sun"),("wind","Wind / chop")]
BOXINV=[
 ["Chartreuse Clouser","#4–6","The Stones white-bass fly — swing & strip it through the tailrace on the current."],
 ["Woolly Bugger","#4–8","Swung on the current or crawled on the rock — white bass, hybrids & smallmouth."],
 ["Baitfish streamer (Clouser / Deceiver)","#2–2/0","Shad imitation for stripers & hybrids on a sink-tip when they generate."],
 ["Crawfish fly","#6–10","Dead-drift on the bottom in the ledges & slots below the dam."],
 ["Bream bug / small popper","#8–10","Panfish & bluegill in the slack water & backwaters."],
 ["Midge / small nymph","#16–20","Winter only — stocked rainbows below the dam Dec–Feb, under an indicator."],
]
_dc=cur_flow
_dcl=("clear" if _dc is None or _dc<200 else "moderate" if _dc<1000 else "stained" if _dc<4000 else "muddy")
_dh=now_ct.hour; _dcloud=50; _dwind=6
if wx:
    _H=wx["hourly"]; _k=now_ct.strftime("%Y-%m-%dT%H:00")
    if _k in _H["time"]: _wi=_H["time"].index(_k); _dcloud=_H["cloud_cover"][_wi] or 0; _dwind=_H["wind_speed_10m"][_wi] or 0
_dlight=riverlib.light_now(_dh,_dcloud,_dwind)
FLYSEL={"matrix":FLYMATRIX,"order":FLYORDER,"lights":LIGHTS,"boxinv":BOXINV,
  "now":{"clarity":_dcl,"light":_dlight,"fly":FLYMATRIX[_dcl][_dlight]},
  "rig":"When they generate, work the tailrace with a streamer: a chartreuse Clouser or Woolly Bugger swung on the current is the white-bass fly; step up to a baitfish streamer on a sink-tip for stripers. In winter, switch to a midge rig for the stocked rainbows below the dam. Down at the Heartland reach it fishes like slackwater — strip a streamer or throw a popper for panfish. 6–7 wt, 8–12 lb tippet.",
  "sources":[["TWRA Percy Priest","https://www.tn.gov/twra/fishing/where-to-fish/middle-tennessee-r2/percy-priest-reservoir.html"],["USGS 03430200","https://waterdata.usgs.gov/monitoring-location/USGS-03430200/"],["USACE Percy Priest","https://www.lrn-wc.usace.army.mil/basin_project.shtml?p=jpp"]]}

tips=[["🌊","Read the water, not the clock. Percy Priest is a single-turbine PEAKING dam — near-zero between pulses. The lower reach at the Heartland ramp stays floatable (the Cumberland backs it up), but the upper tailwater below the dam is skinny and wadeable when the dam's off. Check the USACE Percy Priest release before you plan a power-drift up top."]]
if cur_flow is not None and cur_flow>=200:
    tips.append(["🎣","Current's on — the tailrace fishes. Swing a chartreuse Clouser or Woolly Bugger through the current for white bass; step up to a baitfish streamer on a sink-tip for stripers. Get on it while the turbine runs."])
else:
    tips.append(["🐟","Dam's off — launch at Heartland and fish the lower slackwater near the Cumberland (strip a streamer along the wood, or throw a popper for panfish). Save the upper tailwater for a generation window or wade it on foot."])
tips.append(["❄️","Winter bonus: TWRA/Dale Hollow NFH stocks rainbow trout below the dam (first Friday of December, then Jan/Feb). Cold deep-gate releases hold them — a midge rig under an indicator in the tailrace."])
tips.append(["🎏","Spring white-bass run is the event here — March–April they pour up into the tailrace; a chartreuse Clouser on a fly rod and you'll wear your arm out."])

POINTS=[
 {"name":"Heartland Park ramp","lat":36.1851,"lon":-86.6651,"types":["ramp","paddle"],
  "info":"TWRA/Metro concrete ramp in Donelson near the Cumberland confluence — the reliable power-drifter launch. The lower reach here is deep slackwater backed up by the Cumberland regardless of generation.","rm":0.5},
 {"name":"Percy Priest Tailwater","lat":36.1585,"lon":-86.6189,"types":["wade"],
  "info":"USACE day-use area immediately below the dam — wade & bank access to the tailrace (NOT a trailer ramp). The white-bass & striper spot; runs skinny when the dam's off, rises fast when it generates.","rm":6.8},
 {"name":"Kohl's / Lebanon Pike","lat":36.1745,"lon":-86.6480,"types":["paddle"],
  "info":"Kayak hand-launch on the Stones River Greenway (built by TSRA) — no trailer ramp. Mid-reach paddle access.","rm":3.5},
]
POLY=[[36.15713,-86.61835],[36.15801,-86.61934],[36.1593,-86.62041],[36.16041,-86.62095],[36.16116,-86.62175],[36.1617,-86.62286],[36.16204,-86.62394],[36.16212,-86.62418],[36.16253,-86.62535],[36.16295,-86.62629],[36.16378,-86.62767],[36.16468,-86.62857],[36.16565,-86.6293],[36.16621,-86.62973],[36.16721,-86.63089],[36.16839,-86.63247],[36.16939,-86.63376],[36.16978,-86.63444],[36.17047,-86.63565],[36.17094,-86.63747],[36.17175,-86.63984],[36.17216,-86.64088],[36.17267,-86.64144],[36.17319,-86.64153],[36.17372,-86.64153],[36.17487,-86.6414],[36.1757,-86.64101],[36.17677,-86.63955],[36.17736,-86.63848],[36.17805,-86.63685],[36.17847,-86.63531],[36.17923,-86.6344],[36.18051,-86.63342],[36.18071,-86.63335],[36.18124,-86.63316],[36.18259,-86.63316],[36.18429,-86.6332],[36.18603,-86.63343],[36.18661,-86.63363],[36.18675,-86.63415],[36.18682,-86.63505],[36.18675,-86.63604],[36.18682,-86.63728],[36.18716,-86.64024],[36.18744,-86.6438],[36.18758,-86.64698],[36.18713,-86.64925],[36.18595,-86.65131],[36.18422,-86.65273],[36.18214,-86.65346],[36.17975,-86.6541],[36.17705,-86.6544],[36.17518,-86.65505],[36.17369,-86.65578],[36.17275,-86.65651],[36.17203,-86.65801],[36.17158,-86.65912],[36.17123,-86.66063],[36.17116,-86.662],[36.17147,-86.66303],[36.17223,-86.66457],[36.17369,-86.66616],[36.17497,-86.66698],[36.17636,-86.66715],[36.1781,-86.66711],[36.17816,-86.66711],[36.17982,-86.66646],[36.1836,-86.66492],[36.18543,-86.66449],[36.18748,-86.66423],[36.18942,-86.66324],[36.19101,-86.66273],[36.19281,-86.66334]]

clar="rising / gen on" if trend=="rising" else "falling" if trend=="falling" else "steady"
DATA={"today":now_ct.strftime("%A, %B %-d · %-I:%M %p"),"solunar":SOL,"hatch":HATCH,"month":now_ct.month,
      "chatter":riverlib.load_intel("stones"),"flysel":FLYSEL,"tips":tips,"weather":WXT,"series":series,"usace":USACE_URL,
      "cur":{"flow":round(cur_flow) if cur_flow is not None else None,"stage":round(cur_stage,2) if cur_stage is not None else None,
             "trend":trend,"cond":FN,"grade":FG,"col":FCOL,"note":FNOTE,"clar":clar,"asof":asof},
      "points":POINTS,"poly":POLY}

TEMPLATE=r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Stones River · Percy Priest tailwater</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#16202b;--muted:#66788a;--faint:#93a3b3;--line:#e6ecf2;--card:#fff;--blue:#0a84ff;--green:#28c76f}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,sans-serif;
 background:radial-gradient(1000px 700px at 82% -6%,#eef0ec 0,transparent 60%),linear-gradient(180deg,#eef1ec,#e7ebe4);min-height:100vh}
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
.safe{display:flex;gap:11px;background:#fff5f4;border:1px solid #f5d7d4;border-radius:14px;padding:13px 15px;margin:12px 0;font-size:12.8px;color:#8a3b34;line-height:1.5}.safe b{color:#6f2a24}.safe a{color:#b3392f;font-weight:700}
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
 <div class="eyebrow">Peaking tailwater · below J. Percy Priest Dam</div>
 <h1>Stones River</h1><div class="cap" id="cap"></div>
 <div class="card now" id="now"></div>
 <div class="safe" id="safe"></div>
 <div class="sec">Flow · downstream gauge (last 4 days)</div><div class="card chartc" id="chartc"></div>
 <div class="note" id="chartnote"></div>
 <div class="sec">Live map · accesses</div>
 <div class="card" style="padding:8px"><div id="lmap"></div></div>
 <div class="maptip">Real ramp &amp; accesses on the OSM channel · Percy Priest Dam → Cumberland confluence, ~7 river mi · tap a pin for details &amp; a Google Maps link</div>
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
__HATCH_JS__
__CHATTER_JS__
__LOG_JS__
__MOONCAL_JS__
__FLYMATRIX_JS__
document.getElementById('cap').innerHTML=D.today+' · Stones River at US-70 near Donelson (USGS 03430200)';
(function(){const c=D.cur;document.getElementById('now').innerHTML=
 '<div class="vg" style="background:'+c.col+'">'+c.cond+'</div>'
 +'<div><div class="b1">'+(c.flow!=null?c.flow.toLocaleString()+' cfs':'—')+(c.stage!=null?' · '+c.stage+' ft':'')+' <span style="font-size:14px;color:var(--muted)">'+(c.trend==='rising'?'↑ rising — gen on':c.trend==='falling'?'↓ dropping':'→ steady')+'</span></div>'
 +'<div class="b2">'+c.note+'</div></div>'
 +'<div class="rt"><b>'+c.grade+'</b>'+c.clar+'<br><span style="font-size:11px">as of '+c.asof+'</span></div>';})();
document.getElementById('safe').innerHTML='<div style="font-size:16px">⚠</div><div><b>Peaking dam — the river rises fast.</b> Percy Priest runs one turbine and can jump from near-zero to several thousand cfs quickly; the tailwater below the dam is a wade spot when it\'s off and dangerous when it starts. Read the <a href="'+D.usace+'" target="_blank" rel="noopener">USACE Percy Priest release</a> (or call TVA 1-800-238-2264) before you wade. Power-drifters: the reliable float is the LOWER reach from the Heartland ramp to the Cumberland — the upper tailwater goes skinny when the dam is off.</div>';
(function(){const S=D.series;if(!S.length){document.getElementById('chartc').innerHTML='<div style="padding:20px;color:var(--muted)">gauge data unavailable</div>';return;}
 const W=860,H=200,pad=44,fs=S.map(p=>p.f),fmax=Math.max(1200,...fs)*1.14,fmin=0;
 const x=i=>pad+i*(W-pad-10)/(S.length-1),y=f=>H-24-(f-fmin)/(fmax-fmin)*(H-44);
 function band(a,b,col){const yb=y(Math.min(b,fmax));return '<rect x="'+pad+'" y="'+yb+'" width="'+(W-pad-10)+'" height="'+Math.max(0,(y(a)-yb))+'" fill="'+col+'"/>';}
 let bands=band(0,200,'rgba(242,168,50,.12)')+band(200,4000,'rgba(40,199,111,.14)')+band(4000,fmax,'rgba(139,108,239,.12)');
 let path='';S.forEach((p,i)=>{path+=(path?' L':'M')+x(i).toFixed(0)+','+y(p.f).toFixed(0);});
 let ax='';for(let i=0;i<S.length;i+=Math.ceil(S.length/6)){ax+='<text x="'+x(i)+'" y="'+(H-6)+'" font-size="10" fill="#93a3b3" text-anchor="middle">'+S[i].t.split(' ')[0]+'</text>';}
 [200,4000].forEach(g=>{ax+='<line x1="'+pad+'" y1="'+y(g)+'" x2="'+(W-10)+'" y2="'+y(g)+'" stroke="#dfe7ee" stroke-dasharray="4 4"/><text x="4" y="'+(y(g)+3)+'" font-size="9" fill="#93a3b3">'+(g>=1000?(g/1000)+'k':g)+'</text>';});
 document.getElementById('chartc').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" width="100%">'+bands
  +'<path d="'+path+'" fill="none" stroke="#5a6b52" stroke-width="2.5"/>'+ax+'</svg>'
  +'<div class="lgd"><span><i style="background:rgba(242,168,50,.6)"></i>off / minimum</span><span><i style="background:rgba(40,199,111,.6)"></i>generating — bite on</span><span><i style="background:rgba(139,108,239,.5)"></i>high</span></div>';})();
document.getElementById('chartnote').textContent='The square pulses are Percy Priest cycling its single turbine — near-zero between, a few thousand cfs when it runs. Rising = generation = the tailrace bite turns on. The lower reach near the Cumberland stays floatable through all of it.';
(function(){let h='';D.tips.forEach(t=>h+='<div class="tip"><div class="i">'+t[0]+'</div><div class="x">'+t[1]+'</div></div>');document.getElementById('tips').innerHTML=h;})();
(function(){const w=D.weather,el=document.getElementById('wx');if(!w){el.innerHTML='<div class="meta">weather unavailable</div>';return;}
 let h='';(w.snaps||[]).forEach(s=>h+='<div class="m"><div class="w">'+s.when+'</div><div class="t">'+s.ico+' '+s.temp+'°</div><div class="d">'+s.sky+' · '+s.wind+' mph'+(s.precip?' · '+s.precip+'%':'')+'</div></div>');
 h+='<div class="meta"><div>High '+(w.hi??'–')+'° · Low '+(w.lo??'–')+'°</div><div>Sun '+w.sunrise+'–'+w.sunset+'</div></div>';el.innerHTML=h;})();
renderSolunar('sol',D.solunar,D.cur.grade==='Prime'?'Generation during a major feeding window — the white bass & stripers go on the chew.':'Fish the majors; best when the turbine is running.');
renderHatch('hatch',D.hatch,D.month);
buildMoonCal('mooncal',36.185,-86.665);
buildFlyMatrix('flysel',D.flysel);
document.getElementById('regs').innerHTML='<b>Regulations.</b> '+__REGS__;
renderChatter('chatter',D.chatter,'chatterSec');
buildLog('log','riverlog-stones',D.points.map(p=>p.name),null);
document.getElementById('foot').textContent='Flow: USGS 03430200 (Stones River at US-70 near Donelson). Percy Priest is a peaking dam — verify the USACE release before wading. The lower reach (Heartland→Cumberland) floats a power-drifter; the upper tailwater is generation-dependent. Fishability is an estimate. Weather: Open-Meteo. Channel & accesses from OpenStreetMap. Personal use.';
buildRiverMap(D,'#5a6b52');
</script></body></html>"""
html=(riverlib.render(TEMPLATE,"stones")
      .replace("__REGS__",json.dumps(CFG["regs"]))
      .replace("__DATA__",json.dumps(DATA)))
open(os.path.join(OUT,"stones.html"),"w").write(html)
riverlib.emit_status("stones",
    {"grade":FG,"cond":FN,"col":FCOL,"note":FNOTE,"detail":(("%s cfs"%format(round(cur_flow),",")) if cur_flow is not None else "—"),"asof":asof},
    wx, BASE, CT, ["White bass","Striped bass","Largemouth","Smallmouth","Trout","Panfish"],
    "Peaking tailwater", "~20 min · east of Nashville")
print("wrote out/stones.html | flow %s cfs %s | grade %s | series %d"%(cur_flow,trend,FG,len(series)))
