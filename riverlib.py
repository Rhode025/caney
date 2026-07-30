#!/usr/bin/env python3
"""
riverlib — shared infrastructure for every river page (Caney, Duck, Cumberland, …).

Goal: DON'T REPEAT YOURSELF. Anything common to all rivers lives here ONCE and is
injected into each page's TEMPLATE via string tokens. Add a river → edit RIVERS only.
Add a shared feature → add a token here + drop the token into each TEMPLATE once.

How a generator uses it:
    import riverlib
    html = riverlib.render(TEMPLATE, "duck").replace("__DATA__", json.dumps(DATA))

Shared tokens a TEMPLATE may include (all optional; unused tokens are simply blank):
    __SWITCH_CSS__   CSS for the river switcher (put inside <style>)
    __SWITCHER__     the switcher nav for THIS river (put at top of <body>)
    __CREDIT__       shared data-source credit line (put in the footer)

See RIVER_SPEC.md for the full standard feature spec every river page targets.
"""
import json, urllib.request, math, os, datetime as _dt

# ── the single source of truth for which rivers exist ────────────────────────
# Adding a river here updates the switcher on EVERY page automatically.
RIVERS = [
    {"id": "caney",      "name": "Caney Fork",  "emoji": "🎣", "file": "caney.html",
     "on_bg": "#eaf3fb", "on_fg": "#0a5ec2", "species": "Trout (dam tailwater)"},
    {"id": "cumbnash",   "name": "Cumberland · Nashville", "emoji": "🌉", "file": "cumbnash.html",
     "on_bg": "#eef1f6", "on_fg": "#3a5a8c", "species": "Striped bass & smallmouth"},
    {"id": "stones",     "name": "Stones River","emoji": "🪨", "file": "stones.html",
     "on_bg": "#eef0ec", "on_fg": "#5a6b52", "species": "White bass, trout & panfish"},
    {"id": "duck",       "name": "Duck River",  "emoji": "🐟", "file": "duck.html",
     "on_bg": "#eafaf0", "on_fg": "#1e7a45", "species": "Smallmouth"},
    {"id": "elktn",      "name": "Elk · Tims Ford", "emoji": "🐠", "file": "elktn.html",
     "on_bg": "#e7f3fb", "on_fg": "#1e7ac2", "species": "Tailwater trout (Tims Ford)"},
    {"id": "cumberland", "name": "Cumberland KY","emoji": "🟤", "file": "cumberland.html",
     "on_bg": "#efeafc", "on_fg": "#5b3ec2", "species": "Trophy trout (tailwater)"},
    {"id": "elk",        "name": "Elk River",   "emoji": "🦌", "file": "elk.html",
     "on_bg": "#fbeee0", "on_fg": "#b5651d", "species": "Smallmouth (Wheeler)"},
]

# ── the canonical declarative per-river config (single source of truth) ──────
# Consumed by the Atlas Generator (atlas_generator.py) AND, increasingly, by the page generators
# (Elk reads its zones + gauge here). Add a river → add an entry here + its generator.
# Schema: name, sub, species, vessel, base, lat, lon, model, gauge{type,site|lid,label},
# bands[[name,range,note]], trend_rule, zones[[letter,label,desc]], launch{name,desc},
# access[[name,desc]], hazards[str], flies[[name,job]], regs.
RIVER_CONFIG = {
 "elk": {
   "name":"Elk River","sub":"Wheeler Lake to the Tennessee Line","species":"Summer smallmouth",
   "vessel":"StealthCraft 1654 · 60/40 jet","base":"Joe Wheeler State Park, Rogersville AL",
   "lat":34.902,"lon":-87.078,"model":"warmwater smallmouth, flow-band",
   "gauge":{"type":"usgs","site":"03584600","label":"Elk River at Prospect, TN"},
   "bands":[["Very low","under 300 cfs","concentrated & spooky — riffle heads & shade hold everything"],
            ["Low & clear","300–700","holding well but easily pushed off — stealth, trolling motor"],
            ["Prime","700–1,800","spread across every seam & boulder — the day the boat earns its keep"],
            ["High & stained","1,800–3,500","pushed to banks & flooded wood — often excellent, bigger flies"],
            ["Blown out","over 3,500","scattered & hard to reach — structure or clean tributary inflows"]],
   "trend_rule":"Falling water beats level; rising is the worst. Prime or high-and-stained AND falling → turn UPSTREAM to the shoals (Zones C/D). Very-low, blown, or rising → turn DOWNSTREAM to the backwater structure (Zones B/A). No reading → downstream, because that plan works in everything.",
   "zones":[["A","Mouth · 0–5 mi","deep embayment, bluff walls & riprap — fish it like a lake: depth & shade"],
            ["B","Backwater · 5–12 mi","wood, docks, feeder creeks; current only when Wheeler generates"],
            ["C","Transition · 12–20 mi","first gravel bars & current seams — the most conditions-sensitive water"],
            ["D","River · 20 mi +","shoal-and-boulder smallmouth, jet water; TN license above the state line"]],
   "launch":{"name":"Hatchery Rd ramp (Buck Island)","desc":"AL-99 north bank, Limestone Co (~RM 21). Single lane, ~20 unpaved spaces, no facilities. Puts you straight into the transition water — Zone D up, Zone B down. Scout in daylight; assume no cell service."},
   "access":[["Joe Wheeler State Park","base — lodging & fuel; 9–10 mi open water to the mouth"],
             ["Elk River US-72","Zone B backwater, nearest ramp to the mouth (~RM 6)"],
             ["Sportsman's Park","Zone C transition, Elk River Mills Rd (~RM 15)"],
             ["Hatchery Rd (Buck Island)","PRIMARY LAUNCH — Zone C/D (~RM 21)"],
             ["Easter Ferry","Zone D shoals, near the AL/TN line (~RM 26)"],
             ["Maples Bridge","Zone D, upper river, TN side (~RM 30)"],
             ["Veto Access","Zone D, at the Prospect gauge (~RM 36); TN license"]],
   "hazards":["Floating & submerged wood after any rise — idle unfamiliar shoals before running them on plane.",
              "Sudden stage change when TVA starts/stops generating in the lake zones.",
              "Barge & rec traffic on the Tennessee main channel at the mouth — cross it, don't linger.",
              "Heat is the real emergency, not the boat — a gallon of water per person, hard stop when anyone stops sweating."],
   "flies":[["Deer-hair diver, black & olive","first-light fly — long pauses over seams & shade"],
            ["Boogle Bug popper","loud & durable — default when the water has color"],
            ["Sneaky Pete slider","clear-water topwater, won't alarm fish in gin"],
            ["Clouser Minnow","the workhorse once the sun is up — vary eye weight, not pattern"],
            ["Game Changer","big-fish fly for stained water & low light"],
            ["Crayfish, rust & olive","bottom fly for gravel-to-rock, eat on the pause"]],
   "regs":"Alabama license (Sep 1–Aug 31); Tennessee license above the state line. Wheeler: 10 black bass aggregate, no more than 5 smallmouth, 15\" smallmouth minimum. Midsummer: land fast, keep wet, release everything.",
 },
 "duck": {
   "name":"Duck River","sub":"Columbia to Centerville — middle Duck","species":"Summer smallmouth",
   "vessel":"jet boat / kayak","base":"—","lat":35.80,"lon":-87.37,"model":"warmwater smallmouth, flow-forecast",
   "gauge":{"type":"nwps","lid":"CNVT1","label":"Duck River at Centerville (NWS CNVT1)"},
   "bands":[["Low","under 0.9k cfs","skinny & clear — small water, light tackle, dawn/dusk topwater"],
            ["Prime","0.9–2.5k","dropping & clearing — ideal; wade the shoals, crawfish & topwater"],
            ["High","2.5–4.5k","up & off-color — work the banks, eddies & creek mouths"],
            ["Blown","over 4.5k","high & muddy — sit it out or fish a feeder creek"]],
   "trend_rule":"Falling & clearing water is prime for smallmouth; rising & off-color is tough. The river runs skinnier up top (Columbia) and fuller down low (Centerville).",
   "zones":[],
   "launch":{"name":"Chickasaw Trace or Shady Grove","desc":"Real motorized ramps; pick the reach that floats at the day's level. Low-head dam in downtown Columbia — put in below it and float downstream only."},
   "access":[["Chickasaw Trace","Maury Co motorized ramp — best upper put-in (RM 127)"],
             ["Williamsport","TWRA ramp, Hwy 50 bridge (RM 114)"],
             ["Leatherwood Bridge","motorized ramp near Shady Grove (RM 95)"],
             ["Littlelot","TWRA ramp, Hwy 230 (RM 89)"],
             ["River Park Centerville","town ramp, Hwy 100, near the gauge (RM 74)"]],
   "hazards":["Low-head dam in downtown Columbia — never approach from upstream; put in below it.",
              "Strainers, logjams & deadfall on the bends, worst after high water.",
              "Wear a PFD, scout blind bends, confirm the level before you shuttle."],
   "flies":[["Crawfish / craw #4–8","dead-drift on the bottom along rock & ledges"],
            ["Clouser Minnow","olive/white & chartreuse/white — the workhorse"],
            ["Popper / walking bug","dawn & the last hour over shoals"],
            ["Murdich / Game Changer","push water when it's up & stained"]],
   "regs":"Tennessee license. Check current TWRA black-bass limits. Catch-and-release keeps the smallmouth fishery strong.",
 },
 "caney": {
   "name":"Caney Fork","sub":"Center Hill Dam to Carthage","species":"Tailwater trout","file":"caney.html",
   "vessel":"60/40 power-drifter","base":"Long Branch (at the dam)","lat":36.10,"lon":-85.83,
   "model":"cold tailwater, dam-generation-driven",
   "gauge":{"type":"usgs","site":"03424860","label":"Caney Fork at Stonewall (USGS)"},
   "bands":[["Minimum flow","~250–400 cfs","wadeable — sight-fish the flats, midges & sowbugs"],
            ["Edge / rising","1,000–3,000","the sweet spot — work the leading edge as the release arrives"],
            ["1 unit","~3,900","boat water — drift & swing"],
            ["2–3 units","6,500–11,000+","high & fast — streamers on the bank, stay in the boat"]],
   "trend_rule":"Generation drives everything — water is cold year-round. Backtested at the Stonewall gauge (90 days, 80 releases): the generating bump travels ~2.5 mph, so it reaches Happy Hollow (6 mi) ~2½h after release, Betty's Island (9 mi) ~3½h, and Stonewall (15 mi) ~6h. Fish the minimum-flow flats early, be off before the bump is due, then ride the rise downstream from the boat. Verify the Center Hill schedule against TVA.",
   "zones":[],
   "launch":{"name":"Long Branch","desc":"Boat ramp & campground at the base of Center Hill Dam. Be off the wadeable flats before the water arrives."},
   "access":[["Long Branch","at the dam — ramp & wade"],["Betty's Island","the flats (~RM 15)"],
             ["Happy Hollow","off I-40 (~RM 19)"],["Stonewall","Gordonsville gauge (~RM 10)"],["Carthage","Cumberland mouth"]],
   "hazards":["The bump comes FAST when they generate — watch the schedule, give yourself a big margin, be off the shoals early.",
              "Cold water year-round — dress for it. Wading gets dangerous as the release arrives."],
   "flies":[["Zebra midge #18–22","the everyday staple, under an indicator"],["Sowbug / scud #14–18","year-round bottom bug"],
            ["Sulphur #16–18","late spring & summer"],["Sculpin / streamer","browns on the rise & generation"]],
   "regs":"Tennessee license & trout permit. Check TWRA Caney Fork trout regulations (slot/creel).",
 },
 "cumberland": {
   "name":"Cumberland KY","sub":"Wolf Creek Dam to Burkesville","species":"Trophy tailwater trout",
   "vessel":"drift / jon boat","base":"Kendall (below the dam)","lat":36.87,"lon":-85.14,
   "model":"cold tailwater, dam-generation-driven",
   "gauge":{"type":"usgs","site":"03414100","label":"Cumberland at Burkesville (USGS)"},
   "bands":[["Wadeable (off)","under 1,500 cfs","water off — wade the shoals; midge rig & sight-fishing"],
            ["Generating","1,500–8,000","boat & streamers — trophy browns eat on the rise"],
            ["High","8,000+","big water — heavy streamers, stay in the boat"]],
   "trend_rule":"Wolf Creek generation governs it. Water off → wade the shoals below the dam. Generating → get in the boat and throw meat; the rise is when the trophy browns hunt. Downstream routing is weak, so trust the release schedule & at-dam wade windows.",
   "zones":[],
   "launch":{"name":"Kendall Recreation Area","desc":"USACE ramp off US 127, just below Wolf Creek Dam. Main put-in; wade Boyd's Bar when the water's off."},
   "access":[["Kendall Rec Area","below the dam (~0.5 mi)"],["Helm's Landing","KY 379 (~4.5 mi)"],
             ["Winfrey's Ferry","cable takeout (~16 mi)"],["Burkesville City Ramp","near the gauge (~33 mi)"]],
   "hazards":["Be OFF the wadeable shoals before they generate — the bump comes fast on this river.",
              "Watch the horn/schedule and give yourself a big margin. Cold water year-round."],
   "flies":[["Zebra midge #18–22","tandem rig under an indicator when off"],["Sowbug / scud #14–18","the staple"],
            ["Sculpin / articulated streamer","browns on the generation rise"],["Y2K / egg","a little color when up"]],
   "regs":"Kentucky license & trout permit. Cumberland tailwater has special trout regs (brown-trout slot) — check KY F&W.",
 },
 "elktn": {
   "name":"Elk River · Tims Ford","sub":"Tims Ford Dam tailwater, TN — put-and-take trout","species":"Tailwater trout",
   "vessel":"wade / kayak","base":"Below Tims Ford Dam (Hwy 50)","lat":35.19,"lon":-86.28,
   "model":"cold tailwater, TVA-generation-driven",
   "gauge":{"type":"usgs","site":"03582000","label":"Elk River above Fayetteville (USGS — ~30 mi downstream, a lagging indicator)"},
   "bands":[["Low / likely off","under ~450 cfs","near baseflow — Tims Ford probably off; wade the shoals with midges & scuds"],
            ["Up — check TVA","~450–1,200","elevated (generation or rain) — could be rising & dangerous; confirm the schedule"],
            ["High","over ~1,200","big water — don't wade; heavy streamers from the bank or sit it out"]],
   "trend_rule":"TVA Tims Ford generation governs it — cold put-and-take trout for ~12 mi from the dam to Beans Creek. Water off → wade the shoals with midges & scuds and sight-fish. Generating → the river rises fast and is DANGEROUS to wade; fish streamers from the bank. The only live USGS gauge is ~30 mi downstream at Fayetteville and lags the release, so ALWAYS check the TVA Tims Ford generation schedule before you get in the water.",
   "zones":[],
   "launch":{"name":"Below the dam (Hwy 50)","desc":"TVA tailwater access just below Tims Ford Dam off Hwy 50 — the top of the trout water and the best wade shoals when the water's off. Know the generation schedule and be out before it starts."},
   "access":[["Below the dam (Hwy 50)","top of the trout water, at the dam"],
             ["Farris Creek Bridge","TVA river access, mid-tailwater (~6 river mi)"],
             ["Old Dam Ford","lower end of the stocked trout zone (~12 mi, Beans Creek)"]],
   "hazards":["TVA generation makes the river rise fast and DANGEROUS to wade or paddle — check the Tims Ford schedule and be out before it starts. Little warning once it's moving.",
              "Cold water year-round — dress for it. The downstream Fayetteville gauge lags the real release, so it is only a rough indicator."],
   "flies":[["Zebra midge #18–22","the everyday staple under an indicator"],
            ["Sowbug / scud #14–18","year-round bottom bug — sight-fish the shoals when off"],
            ["Pheasant Tail / BWO #16–20","spring & fall mayfly water"],
            ["Sculpin / Woolly Bugger","browns on the rise & generation"]],
   "regs":"Tennessee license & trout permit. Elk River tailwater creel: 7 trout in combination; only 2 brown trout kept per day Mar 1–Sep 30. TWRA-stocked rainbow & brown (recently cutthroat), monthly Mar–Dec.",
 },
 "cumbnash": {
   "name":"Cumberland · Nashville","sub":"Old Hickory Dam to Cheatham — the metro reach","species":"Striped bass, smallmouth & panfish",
   "vessel":"60/40 power-drifter","base":"Shelby Bottoms ramp","lat":36.17,"lon":-86.74,
   "model":"warmwater big-river, generation-driven current",
   "gauge":{"type":"usgs","site":"03431500","label":"Cumberland River at Nashville (USGS)"},
   "bands":[["Slack / no gen","under ~7,000 cfs","Old Hickory idle — little current; work the ledges, wing dams & structure slow & deep"],
            ["Generating","~7,000–30,000","current on — stripers & smallmouth feed; swing streamers through the tailrace"],
            ["High / heavy","over ~30,000","strong, stained flow — fish eddies, creek mouths & slack behind the wing dams"]],
   "trend_rule":"Depth is stable — this is a navigable impoundment (Cheatham pool), so you never ground out. CURRENT is the variable, and current is Old Hickory generation. Dam idle → slack, slow deep streamer fishing. When they generate, the current turns on and the striped bass & smallmouth feed hard on the ledges and in the tailrace — swing a big streamer, and a rising generation pulse is prime. Check the USACE Nashville District release before you launch.",
   "zones":[],
   "launch":{"name":"Shelby Bottoms / Shelby Park","desc":"Metro concrete ramp just east of downtown — closest to town and mid-reach. Run up toward Pennington Bend or down through the city; big water, so mind barge traffic and wakes."},
   "access":[["Old Hickory Dam Tailwater","USACE ramp just below the dam — the striper & smallmouth tailrace (~RM 216)"],
             ["Peeler Park","Metro ramp, Neely's Bend (~RM 205)"],
             ["Lock Two","Metro ramp, Pennington Bend (~RM 201)"],
             ["Shelby Bottoms","Metro ramp, closest to downtown (~RM 193)"],
             ["Cleeces Ferry","TWRA ramp, West Nashville (~RM 185)"]],
   "hazards":["Generation turns the current on fast — the tailrace below Old Hickory gets strong; stay off the dam and respect the pull.",
              "Commercial barge traffic runs the navigation channel — cross it, don't linger, and take big wakes at an angle.",
              "Submerged wing dams & rock ledges — idle unfamiliar water; they're all through the metro reach."],
   "flies":[["Baitfish streamer (Clouser / Deceiver)","the striper & white-bass standard — swing & strip it through the tailrace when they generate"],
            ["Articulated streamer","big water & low light — meat for the biggest stripers along the wing dams"],
            ["Clouser Minnow, deep","down on the ledges on a sink-tip — smallmouth & white bass"],
            ["Crawfish / Woolly Bugger","bottom fly along the rock ledges & wing dams for smallmouth"],
            ["Popper / bream bug","topwater smallmouth & panfish in the slack water & backwaters"]],
   "regs":"Tennessee license. Old Hickory/Cheatham: striped & hybrid bass 15\" min, 2/day combined; black bass per TWRA limits. Verify current TWRA Region 2 regs.",
 },
 "stones": {
   "name":"Stones River","sub":"below J. Percy Priest Dam to the Cumberland","species":"White bass, striper, trout & panfish",
   "vessel":"power-drifter (lower reach) / kayak","base":"Heartland Park ramp","lat":36.185,"lon":-86.665,
   "model":"peaking tailwater — lower reach floats, upper is generation-dependent",
   "gauge":{"type":"usgs","site":"03430200","label":"Stones River at US-70 near Donelson (USGS)"},
   "bands":[["Off / minimum","under ~200 cfs","Priest idle — the upper reach is skinny & wadeable; power-drift only the lower slackwater near the Cumberland"],
            ["Generating","~200–4,000","turbine running — current & bite on; white bass & stripers stack in the tailrace"],
            ["High","over ~4,000","heavy release — strong current below the dam; fish the eddies & creek mouths"]],
   "trend_rule":"A peaking tailwater: Percy Priest runs one turbine, so it sits near-zero between generation pulses. The LOWER reach (Heartland ramp → Cumberland confluence) stays floatable because the Cumberland (Cheatham pool) backs it up — that's your reliable power-drifter water. The upper tailwater below the dam is skinny and wadeable when the dam's off and runs only during generation. Tie plans to the USGS flow AND the USACE Percy Priest generation status.",
   "zones":[],
   "launch":{"name":"Heartland Park ramp","desc":"TWRA/Metro concrete ramp in Donelson near the Cumberland confluence — the reliable power-drifter launch. The lower reach here is deep slackwater backed up by the Cumberland regardless of generation."},
   "access":[["Heartland Park","concrete ramp near the confluence (~RM 0.5) — the power-drifter launch"],
             ["Percy Priest Tailwater","USACE day-use below the dam — wade & bank access, not a trailer ramp"],
             ["Kohl's / Lebanon Pike","kayak hand-launch on the greenway — no trailer ramp"]],
   "hazards":["Peaking generation — the river below the dam rises fast from near-zero; watch the horn/schedule and stay aware.",
              "The upper reach is rocky & skinny when the dam's off — don't run a power-drifter up there on minimum flow.",
              "Call TVA 1-800-238-2264 or read the USACE Percy Priest release before wading the tailwater."],
   "flies":[["Chartreuse Clouser #4–6","the white-bass run on a fly rod — swing it through the tailrace current"],
            ["Woolly Bugger #6","swung on the current — white bass, hybrids & smallmouth"],
            ["Baitfish streamer (Clouser / Deceiver)","striper & white bass chasing shad in the current"],
            ["Popper / bream bug","panfish & bluegill in the slack water & backwaters"],
            ["Midge / small nymph","stocked rainbows below the dam, winter (Dec–Feb), under an indicator"]],
   "regs":"Tennessee license (+ trout permit for winter trout). White bass 15/day; striped/hybrid 15\" 2/day; winter rainbow trout stocked (Dale Hollow NFH) Dec–Feb. Verify current TWRA Region 2 regs.",
 },
}

# The switcher block ALSO carries the shared design-polish rules (a /design-review pass): because
# __SWITCH_CSS__ is injected into every page's <style> AFTER its own :root, the overrides here win
# the cascade and reach all 8 pages from one place — real display typeface, WCAG-passing greys, 44px
# touch targets. Paired with BASE_HEAD (font <link>) injected by render().
SWITCH_CSS = (
    ".switch{display:inline-flex;max-width:100%;border:1px solid var(--line);border-radius:11px;"
    "overflow-x:auto;overflow-y:hidden;margin-bottom:14px;font-size:13px;font-weight:650;"
    "-webkit-overflow-scrolling:touch;scrollbar-width:none}"
    ".switch::-webkit-scrollbar{display:none}"
    ".switch a{flex:none;padding:8px 15px;color:var(--muted);text-decoration:none;background:#fff;white-space:nowrap}"
    ".switch a.on{font-weight:750}"
    "@media(max-width:560px){.switch a{padding:12px 12px;font-size:12px}}"
    # ── shared polish ──
    "h1,.eyebrow,.sec{font-family:'Space Grotesk',ui-sans-serif,-apple-system,system-ui,sans-serif}"
    ":root{--faint:#616e7b;--muted:#566270;--blue:#0068d6}"   # contrast: 2.6/3.7:1 → >=4.5:1 on the page/card bg
    "@media(max-width:560px){.sp a{padding:9px 13px}.wd{min-height:44px}.crafttog a{padding:9px 12px}}"
)

# Injected into every page's <head> by render() — one real typeface for display/headings, so the UI
# stops leaning on the system stack (the design-review "gave up on typography" flag). Body/data stays
# on the fast native stack by intent.
BASE_HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">'
)

CREDIT = ("Public data only · USACE CWMS · USGS · NOAA/NWS · Open-Meteo · OpenStreetMap. "
          "Estimates — tune from the water. Built for personal use.")

# ── shared JS: access-point popups with Google Maps links (all rivers) ───────
# accessPopup(p) builds a rich popup from a point {name, lat, lon, types?, info?, note?, rm?}.
# gmapsUrl drops a pin at the exact access coordinates. Pages also wire hover-to-open.
POPUP_JS = r"""
window.gmapsUrl=function(lat,lon){return 'https://www.google.com/maps/search/?api=1&query='+lat+','+lon;};
window.accessPopup=function(p){
 var ic={wade:'\u{1F97E}',paddle:'\u{1F6F6}',ramp:'\u{1F6A4}'};
 var t=(p.types||[]).map(function(k){return ic[k]||'';}).join(' ');
 var info=p.info||[p.note,(p.rm!=null?'river mile '+p.rm:'')].filter(Boolean).join(' · ');
 var h='<div style="font:650 14px/1.3 -apple-system,BlinkMacSystemFont,sans-serif;color:#16202b">'+(t?t+' ':'')+p.name+'</div>';
 if(info)h+='<div style="font:400 12px/1.45 -apple-system,sans-serif;color:#66788a;margin-top:3px;max-width:214px">'+info+'</div>';
 h+='<a href="'+gmapsUrl(p.lat,p.lon)+'" target="_blank" rel="noopener" style="display:inline-block;margin-top:8px;font:600 12px -apple-system,sans-serif;color:#0a84ff;text-decoration:none">\u{1F4CD} Open in Google Maps →</a>';
 return h;};
window.wireHover=function(mk){mk.on('mouseover',function(){this.openPopup();});return mk;};
"""

# ── shared JS: simple satellite river map (Duck, Cumberland; Caney is bespoke) ─
MAP_JS = r"""
window.buildRiverMap=function(D,color,zoneSegs){
 if(typeof L==='undefined')return;
 var map=L.map('lmap',{scrollWheelZoom:false});
 L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:18,attribution:'Esri'}).addTo(map);
 if(zoneSegs&&zoneSegs.length){
  // draw the channel colored by zone; today's target zones drawn bolder so the guidance is visible on the water
  zoneSegs.forEach(function(s){L.polyline(s.poly,{color:s.color,weight:s.target?6:3.5,opacity:s.target?.95:.7}).addTo(map);});
 }else{
  L.polyline(D.poly,{color:'#8fd6ff',weight:3,opacity:.85}).addTo(map);
 }
 D.points.forEach(function(p,i){
  var mk=L.marker([p.lat,p.lon],{icon:L.divIcon({className:'',iconSize:[26,26],iconAnchor:[13,13],
   html:'<div style="width:26px;height:26px;border-radius:50%;background:'+color+';border:2.5px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.6);color:#fff;font:700 12px/23px sans-serif;text-align:center">'+(i+1)+'</div>'})}).addTo(map);
  mk.bindPopup(accessPopup(p)); wireHover(mk);
 });
 map.fitBounds(D.poly,{padding:[26,26]});};
"""

# ── shared solunar panel (feature #8) — renders DATA.solunar into an element ──
SOLUNAR_CSS = (
    ".sol{padding:14px 16px}"
    ".solrow{display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap}"
    ".solstars{color:#f0a52b;font-size:18px;letter-spacing:2px}"
    ".solmoon{color:var(--muted);font-size:13px}"
    ".solw{font-size:13px;color:var(--muted);margin-top:3px}.solw b{color:var(--ink);font-weight:650;margin-right:5px}"
    ".solnote{font-size:12px;color:var(--faint);margin-top:9px;line-height:1.5}"
)
SOLUNAR_JS = r"""
window.renderSolunar=function(elId,s,tie){var el=document.getElementById(elId);
 if(!el)return; if(!s){el.style.display='none';return;}
 var r=s.rating||0,stars='★★★★★'.slice(0,r)+'☆☆☆☆☆'.slice(0,5-r);
 var maj=(s.major||[]).map(function(w){return w[0]+'–'+w[1];}).join('  ·  ');
 var min=(s.minor||[]).map(function(w){return w[0]+'–'+w[1];}).join('  ·  ');
 el.innerHTML='<div class="solrow"><div class="solstars">'+stars+'</div><div class="solmoon">\u{1F319} '+s.moon+' · <b>'+r+'/5</b> feed</div></div>'
  +'<div class="solw"><b>Majors</b> (peak) '+maj+'</div>'
  +'<div class="solw"><b>Minors</b> '+min+'</div>'
  +'<div class="solnote">'+(tie||'Best when a major window lines up with moving water. Computed from moon phase &amp; sun times (approx).')+'</div>';};
"""

# ── shared FLY-SELECTION MATRIX (clarity × light) ────────────────────────────
# buildFlyMatrix(containerId, F). F = {matrix:{clarityKey:{label, <lightKey>:fly}}, order:[clarityKeys],
#   lights:[[key,label]], boxinv:[[name,sizes,job]], now:{clarity,light,fly}, rig?, sources?[[name,url]]}.
# Highlights the current clarity×light cell (green). Clarity comes from the river's flow band; light
# from light_now(hour,cloud,wind).
def light_now(hour, cloud, wind):
    """dawn / low / bright / wind — the fly-matrix light column for the current moment."""
    if (wind or 0) >= 13: return "wind"
    if 5 <= hour < 8:      return "dawn"
    if 8 <= hour < 18:     return "bright" if (cloud or 0) < 45 else "low"
    return "low"

FLYMATRIX_CSS = (
    ".fm{padding:14px 16px 6px}.fmnow{font-size:13px;color:var(--muted);margin-bottom:10px}.fmnow b{color:var(--ink)}"
    ".fmg{display:grid;grid-template-columns:78px repeat(4,1fr);gap:5px;font-size:11px}"
    ".fmg .hh{font-size:10px;font-weight:700;color:var(--faint);text-align:center;align-self:end;padding-bottom:3px}"
    ".fmg .rl{font-size:10.5px;font-weight:700;color:var(--muted);align-self:center}"
    ".fmg .cell{background:#f4f7f9;border-radius:7px;padding:6px 5px;text-align:center;line-height:1.25;color:#2b4a63;min-height:38px;display:flex;align-items:center;justify-content:center}"
    ".fmg .cell.on{background:#e7f6ee;outline:2px solid #28c76f;font-weight:700;color:#1a7d47}"
    ".box{padding:6px 16px 12px;border-top:1px solid var(--line);margin-top:6px}"
    ".bx{display:flex;gap:11px;padding:10px 0;border-bottom:1px solid var(--line)}.bx:last-child{border-bottom:0}"
    ".bx .bn{flex:none;width:172px;font-size:12.5px;font-weight:600}.bx .bn span{display:block;color:var(--faint);font-weight:400;font-size:11px}"
    ".bx .bj{font-size:12.5px;color:var(--muted);line-height:1.45}"
    ".fmrig{padding:2px 16px 12px;font-size:13px;color:var(--muted);line-height:1.5}.fmrig b{color:var(--ink)}"
    ".fmsrc{padding:0 16px 14px;font-size:11.5px;color:var(--faint)}.fmsrc a{color:#2f6d94}"
    "@media(max-width:680px){.bx .bn{width:118px}.fmg{font-size:10px;grid-template-columns:56px repeat(4,1fr)}}"
)
FLYMATRIX_JS = r"""
window.buildFlyMatrix=function(cid,F){
 var el=document.getElementById(cid); if(!el||!F||!F.matrix)return;
 var M=F.matrix, now=F.now||{}, LL={dawn:'first light',low:'low light',bright:'bright sun',wind:'wind / chop'};
 var clab=(M[now.clarity]&&M[now.clarity].label)?M[now.clarity].label.split(' · ')[0].toLowerCase():'';
 var h='<div class="fm">';
 if(now.fly)h+='<div class="fmnow">On the water <b>now</b> — '+clab+' water, '+(LL[now.light]||'')+': <b>'+now.fly+'</b></div>';
 h+='<div class="fmg"><div class="hh"></div>';
 F.lights.forEach(function(l){h+='<div class="hh">'+l[1]+'</div>';});
 F.order.forEach(function(ck){h+='<div class="rl">'+M[ck].label+'</div>';
  F.lights.forEach(function(l){var on=(ck===now.clarity&&l[0]===now.light);h+='<div class="cell'+(on?' on':'')+'">'+M[ck][l[0]]+'</div>';});});
 h+='</div></div><div class="box">';
 (F.boxinv||[]).forEach(function(b){h+='<div class="bx"><div class="bn">'+b[0]+'<span>'+b[1]+'</span></div><div class="bj">'+b[2]+'</div></div>';});
 h+='</div>';
 if(F.rig)h+='<div class="fmrig"><b>Rig.</b> '+F.rig+'</div>';
 if(F.sources&&F.sources.length)h+='<div class="fmsrc">Patterns cross-checked with '+F.sources.map(function(s){return '<a href="'+s[1]+'" target=_blank rel=noopener>'+s[0]+'</a>';}).join(' · ')+' — verify current shop reports.</div>';
 el.innerHTML=h;
};
"""

# ── shared GENERATION SCHEDULE (dam tailwaters: per-day release windows + arrival timing) ──
# buildGenSchedule(containerId, days, hint, legend, opts). days=[{label,date,windows:[{units,span}],
#   spark:[24 unit counts], arr:[[ramp,time]]|null}]. opts={minLabel, arrLabel}. Now-marker on today.
GENSCHED_CSS = (
    ".gen{padding:12px 16px 14px}"
    ".ghint{font-size:12px;color:var(--muted);margin-bottom:10px;line-height:1.55}.ghint b{color:var(--ink)}"
    ".gday{padding:11px 0;border-top:1px solid var(--line)}.gday:first-of-type{border-top:0}"
    ".gtoday{background:#f5faff;border:1px solid #e0edfb;border-radius:12px;margin:2px 0;padding:11px 12px}"
    ".ghdr{display:flex;align-items:baseline;gap:7px;margin-bottom:8px;flex-wrap:wrap}"
    ".ghdr b{font-size:15px}.ghdr>span{font-size:12px;color:var(--muted)}"
    ".gtag{font-size:9px;font-weight:800;color:#fff;background:#0a84ff;border-radius:5px;padding:1px 6px;letter-spacing:.05em}"
    ".gwins{margin-left:auto;display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}"
    ".gwin{font-size:11px;font-weight:700;border-radius:6px;padding:2px 7px}"
    ".gw1{color:#2b6491;background:#eaf3fb;border:1px solid #d6e6f5}.gw2{color:#1e5f96;background:#deeeff;border:1px solid #c3ddf3}.gw3{color:#453fb0;background:#eae9fb;border:1px solid #d7d4f2}"
    ".gmin{font-size:11.5px;color:var(--faint);font-weight:600}"
    ".gbars{position:relative;display:flex;align-items:flex-end;gap:1.5px;height:34px}"
    ".gbars i{flex:1;border-radius:2px 2px 0 0;min-height:3px;display:block}"
    ".gnow{position:absolute;top:-3px;bottom:0;width:2px;background:#16202b;border-radius:1px}"
    ".gnow::after{content:'now';position:absolute;top:-12px;left:50%;transform:translateX(-50%);font-size:8px;font-weight:800;color:#16202b}"
    ".gaxis{display:flex;justify-content:space-between;font-size:9px;color:var(--faint);margin-top:3px;letter-spacing:.02em}"
    ".garr{margin-top:9px;font-size:12px;color:var(--muted);background:#eef6ff;border-radius:8px;padding:6px 10px;line-height:1.5}.garr b{color:#16202b;font-weight:650}"
    ".glegend{margin-top:12px;padding-top:10px;border-top:1px solid var(--line);font-size:10.5px;color:var(--faint);display:flex;gap:13px;flex-wrap:wrap;align-items:center}"
    ".glegend i{display:inline-block;width:12px;height:8px;border-radius:2px;margin-right:4px;vertical-align:0}"
)
GENSCHED_JS = r"""
window.buildGenSchedule=function(cid,days,hint,legend,opts){
 var el=document.getElementById(cid); if(!el||!days)return; opts=opts||{};
 var ucol=function(u){return u>=3?'#5e5ce6':u>=2?'#2f92d4':u>=1?'#7db8e0':'#e7edf3';};
 var maxU=3; days.forEach(function(g){(g.spark||[]).forEach(function(u){if(u>maxU)maxU=u;});});
 var nd=new Date(),nowHr=nd.getHours()+nd.getMinutes()/60;
 var h='<div class="ghint">'+(hint||'')+'</div>';
 days.forEach(function(g,di){var today=di===0,bars='';
  for(var hr=0;hr<24;hr++){var u=g.spark[hr]||0,ht=u?4+Math.round(u/maxU*28):3;bars+='<i style="height:'+ht+'px;background:'+ucol(u)+'" title="'+((hr%12)||12)+(hr<12?'am':'pm')+' · '+(u?u+'U':'off')+'"></i>';}
  var now=today?'<span class="gnow" style="left:'+(nowHr/24*100).toFixed(1)+'%"></span>':'';
  var wins=(g.windows&&g.windows.length)?g.windows.map(function(w){return '<span class="gwin gw'+Math.min(3,w.units)+'">'+w.units+'U '+w.span+'</span>';}).join(''):'<span class="gmin">'+(opts.minLabel||'minimum flow')+'</span>';
  var arr=g.arr?'<div class="garr">🌊 '+(opts.arrLabel||'bump reaches')+' '+g.arr.map(function(a){return '<b>'+a[0]+'</b> ~'+a[1];}).join(' · ')+'</div>':'';
  h+='<div class="gday'+(today?' gtoday':'')+'"><div class="ghdr"><b>'+g.label+'</b> <span>'+g.date+'</span>'+(today?'<span class="gtag">today</span>':'')+'<div class="gwins">'+wins+'</div></div>'
    +'<div class="gbars">'+bars+now+'</div><div class="gaxis"><span>12a</span><span>6a</span><span>noon</span><span>6p</span><span>12a</span></div>'+arr+'</div>';});
 h+='<div class="glegend">'+(legend||'')+'</div>'; el.innerHTML=h;};
"""

# ── shared FLOW-TIMER river diagram (scrub time → watch flow move down the river) ──
# buildFlowTimer(containerId, T). T = {times[], nowFrame, unit, refIdx, refName, bands[[max,color,label]],
#   front:bool, frontThresh, srcLabel, mouthLabel, points:[{name, series:[flow/frame]}] (top→bottom)}.
# Tailwaters pass per-point series lagged by travel time (+front:true) so dots light up downstream in
# sequence; flow rivers pass ~uniform series so the whole river changes together as you scrub.
FLOWTIMER_CSS = (
    ".ft{padding:14px 16px}"
    ".ftread{display:flex;align-items:baseline;gap:12px;margin-bottom:10px;flex-wrap:wrap}"
    ".ftt{font-size:16px;font-weight:750}.ftc{font-size:13px;color:var(--muted)}"
    ".ftstrip{position:relative;padding-left:24px;margin:6px 0 8px}"
    ".ftline{position:absolute;left:9px;top:8px;bottom:8px;width:5px;border-radius:3px;background:#d3e0ec}"
    ".ftrow{position:relative;display:flex;align-items:center;gap:10px;height:30px}"
    ".ftrow i{position:absolute;left:-19px;width:13px;height:13px;border-radius:50%;background:#9db0be;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.25)}"
    ".ftrow .nm{font-size:12.5px;font-weight:600}.ftrow .fv{margin-left:auto;font-size:11.5px;color:var(--muted);white-space:nowrap}"
    ".ftgraph{margin:6px 0 10px}"
    ".ftctl{display:flex;align-items:center;gap:12px}"
    ".ftplay{flex:none;width:36px;height:36px;border-radius:50%;border:1px solid var(--line);background:#fff;font-size:14px;cursor:pointer;color:var(--ink)}"
    ".ftslider{flex:1}"
    ".ftlab{flex:none;font-size:11px;color:var(--faint);min-width:64px;text-align:right}"
)
FLOWTIMER_JS = r"""
window.buildFlowTimer=function(cid,T){
 var el=document.getElementById(cid); if(!el||!T||!T.points||!T.points.length)return;
 var N=T.times.length, ri=T.refIdx||0;
 function band(v){for(var i=0;i<T.bands.length;i++){if(v<=T.bands[i][0])return T.bands[i];}return T.bands[T.bands.length-1];}
 function fmtv(v){return T.dec?(+v).toFixed(T.dec):Math.round(v).toLocaleString();}
 var rows=T.points.map(function(p,i){return '<div class="ftrow"><i data-i="'+i+'"></i><span class="nm">'+p.name+'</span><span class="fv" data-i="'+i+'"></span></div>';}).join('');
 el.innerHTML='<div class="ftread"><div class="ftt" id="'+cid+'_t"></div><div class="ftc" id="'+cid+'_c"></div></div>'
  +'<div class="ftstrip"><div class="ftline" id="'+cid+'_line"></div>'+rows+'</div>'
  +'<div class="ftgraph" id="'+cid+'_g"></div>'
  +'<div class="ftctl"><button class="ftplay" id="'+cid+'_play">▶</button>'
  +'<input type="range" class="ftslider" id="'+cid+'_sl" min="0" max="'+(N-1)+'" value="'+(T.nowFrame||0)+'"><div class="ftlab" id="'+cid+'_lab"></div></div>';
 // reference hydrograph
 var ref=T.points[ri].series, W=560,H=88,pad=4;
 var fmax=Math.max(1,Math.max.apply(null,ref))*1.12;
 function x(i){return pad+i*(W-2*pad)/(N-1);} function y(v){return H-8-v/fmax*(H-16);}
 var bg='',lo=0;T.bands.forEach(function(b){var hi=Math.min(b[0],fmax);if(hi>lo){bg+='<rect x="'+pad+'" y="'+y(hi).toFixed(1)+'" width="'+(W-2*pad)+'" height="'+(y(lo)-y(hi)).toFixed(1)+'" fill="'+b[1]+'" opacity=".15"/>';}lo=b[0];});
 var path='';ref.forEach(function(v,i){path+=(path?' L':'M')+x(i).toFixed(0)+','+y(v).toFixed(1);});
 var nx=x(T.nowFrame||0);
 document.getElementById(cid+'_g').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" width="100%">'+bg
  +'<line x1="'+nx+'" y1="4" x2="'+nx+'" y2="'+(H-4)+'" stroke="#93a3b3" stroke-width="1" stroke-dasharray="3 3"/>'
  +'<path d="'+path+'" fill="none" stroke="#16202b" stroke-width="1.8" opacity=".55"/>'
  +'<line id="'+cid+'_cur" x1="'+nx+'" y1="4" x2="'+nx+'" y2="'+(H-4)+'" stroke="#0a84ff" stroke-width="1.6"/></svg>';
 var strip=el.querySelector('.ftstrip'), tEl=document.getElementById(cid+'_t'), cEl=document.getElementById(cid+'_c'),
     cur=document.getElementById(cid+'_cur'), line=document.getElementById(cid+'_line'), lab=document.getElementById(cid+'_lab');
 function frame(f){f=Math.max(0,Math.min(N-1,f));
  tEl.textContent=T.times[f]+(f===T.nowFrame?' · now':'');
  var frontFrac=-1;
  T.points.forEach(function(p,i){var v=p.series[f],b=band(v);
   var d=strip.querySelector('.ftrow i[data-i="'+i+'"]'); if(d)d.style.background=b[1];
   var fv=strip.querySelector('.ftrow .fv[data-i="'+i+'"]'); if(fv)fv.textContent=fmtv(v)+' '+T.unit;
   if(T.front&&v>T.frontThresh)frontFrac=Math.max(frontFrac,(i+0.5)/T.points.length);});
  var rv=ref[f],rb=band(rv);
  cEl.innerHTML='<span style="color:'+rb[1]+';font-weight:700">'+rb[2]+'</span> · '+fmtv(rv)+' '+T.unit+(T.refName?' at '+T.refName:'');
  cur.setAttribute('x1',x(f));cur.setAttribute('x2',x(f));
  lab.textContent=(f===T.nowFrame?'now':(f<T.nowFrame?'−':'+')+Math.abs(f-T.nowFrame));
  if(T.front){var pct=frontFrac<0?0:frontFrac*100;line.style.background='linear-gradient(180deg,#3a7bb8 '+pct+'%,#d3e0ec '+pct+'%)';}
 }
 var sl=document.getElementById(cid+'_sl'); sl.oninput=function(){frame(+sl.value);};
 var pl=document.getElementById(cid+'_play'),tm=null;
 pl.onclick=function(){if(tm){clearInterval(tm);tm=null;pl.textContent='▶';return;}pl.textContent='⏸';
  tm=setInterval(function(){var f=+sl.value+1;if(f>=N)f=0;sl.value=f;frame(f);},220);};
 frame(T.nowFrame||0);
};
"""

# ── shared TRIP LOG (localStorage) — the start of the "learn from your trips" loop ──
# buildLog(containerId, storageKey, spots[], sumElId?) builds the whole form+list into a div.
LOG_CSS = (
    ".logc{padding:14px 16px}"
    ".logform{display:flex;flex-direction:column;gap:9px;margin-bottom:6px}"
    ".logrow{display:flex;gap:8px}.logrow select,.logrow input{flex:1;min-width:0}"
    ".logform select,.logform input,.logform textarea{border:1px solid var(--line);border-radius:10px;padding:9px 11px;font-size:13.5px;font-family:inherit;background:#fff;color:var(--ink);-webkit-appearance:none}"
    ".logform textarea{resize:vertical}"
    ".logstars{font-size:23px;color:#f0a52b;cursor:pointer;letter-spacing:4px;user-select:none;width:fit-content}"
    ".logbtn{border:0;background:var(--blue,#0a84ff);color:#fff;border-radius:10px;padding:11px;font-size:14px;font-weight:650;cursor:pointer;font-family:inherit}"
    ".logempty{font-size:13px;color:var(--muted);text-align:center;padding:12px 4px}"
    ".logitem{border-top:1px solid var(--line);padding:10px 0}"
    ".logmeta{font-size:14px;color:var(--ink)}.logmeta b{font-weight:700}"
    ".logdel{float:right;color:var(--faint);cursor:pointer;font-size:12px;padding:0 4px}"
    ".logfly{font-size:13px;color:#255074;margin-top:3px}.lognote{font-size:13px;color:var(--muted);margin-top:3px;line-height:1.4}"
)
LOG_JS = r"""
window.buildLog=function(cid,key,spots,sumId,legacyKey){
 var el=document.getElementById(cid); if(!el)return;
 var LOG=[]; try{LOG=JSON.parse(localStorage.getItem(key)||'[]');}catch(e){}
 if(!LOG.length&&legacyKey){try{var lg=JSON.parse(localStorage.getItem(legacyKey)||'[]');if(lg.length){LOG=lg;localStorage.setItem(key,JSON.stringify(LOG));}}catch(e){}}
 var rating=0;
 function esc(s){return (s==null?'':(''+s)).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
 var opts=(spots||[]).map(function(s){return '<option>'+esc(s)+'</option>';}).join('');
 el.innerHTML='<div class="logform"><div class="logrow"><select id="'+cid+'_spot">'+opts+'</select>'
   +'<input id="'+cid+'_fly" placeholder="flies that worked (e.g. #4 olive Clouser)"></div>'
   +'<div class="logstars" id="'+cid+'_stars"></div>'
   +'<textarea id="'+cid+'_note" placeholder="notes — water level, weather, what worked / what didn’t" rows="2"></textarea>'
   +'<button class="logbtn" id="'+cid+'_add">Log this trip</button></div><div id="'+cid+'_list"></div>';
 function $(s){return document.getElementById(cid+'_'+s);}
 var st=$('stars');
 for(var i=1;i<=5;i++){(function(i){var s=document.createElement('span');s.textContent='☆';
   s.onclick=function(){rating=i;[].forEach.call(st.children,function(c,j){c.textContent=j<i?'★':'☆';});};st.appendChild(s);})(i);}
 function save(){try{localStorage.setItem(key,JSON.stringify(LOG));}catch(e){}}
 function render(){var list=$('list');
  if(sumId){var su=document.getElementById(sumId);if(su)su.textContent=LOG.length?LOG.length+' trip'+(LOG.length>1?'s':''):'0 trips';}
  if(!LOG.length){list.innerHTML='<div class="logempty">No trips logged yet. After a day out, jot the spot, flies and how it fished — it builds your own playbook (and helps tune the model).</div>';return;}
  var h='';LOG.slice().reverse().forEach(function(e){var idx=LOG.indexOf(e);
   h+='<div class="logitem"><div class="logmeta"><b>'+esc(e.spot)+'</b> · '+esc(e.date)+' · <span style="color:#f0a52b">'+'★'.repeat(e.stars||0)+'</span><span style="color:#d5dce4">'+'☆'.repeat(5-(e.stars||0))+'</span><span class="logdel" data-i="'+idx+'">✕ delete</span></div>'
    +(e.fly?'<div class="logfly">🪰 '+esc(e.fly)+'</div>':'')+(e.note?'<div class="lognote">'+esc(e.note)+'</div>':'')+'</div>';});
  list.innerHTML=h;
  list.querySelectorAll('.logdel').forEach(function(d){d.onclick=function(){LOG.splice(+d.dataset.i,1);save();render();};});}
 $('add').onclick=function(){var spot=$('spot').value,fly=$('fly').value.trim(),note=$('note').value.trim();
  if(!fly&&!note&&!rating)return;
  var d=new Date();LOG.push({date:(d.getMonth()+1)+'/'+d.getDate(),spot:spot,fly:fly,note:note,stars:rating,ts:d.getTime()});
  save();$('fly').value='';$('note').value='';rating=0;[].forEach.call(st.children,function(c){c.textContent='☆';});render();};
 render();
};
"""

# ── shared seasonal HATCH CALENDAR (per-river data in the generator) ─────────
# DATA.hatch = {"rows":[{name,icon,pattern,m:[12 ints 0..3]}...]}; month = 1..12.
# Intensity: 0 none · 1 light · 2 active · 3 peak. Current month column highlighted.
HATCH_CSS = (
    ".hatch{padding:14px 16px}"
    ".hmh,.hhr{display:grid;grid-template-columns:104px repeat(12,1fr);align-items:center}"
    ".hml{font-size:9px;color:var(--faint);text-align:center;padding:0 1px;letter-spacing:-.02em;min-width:0;overflow:hidden}"
    ".hml.on{color:#0a5ec2;font-weight:800}"
    ".hhr{padding:3px 0}"
    ".hhn{font-size:11.5px;font-weight:600;line-height:1.2;padding-right:8px}"   # wraps — no truncation
    ".hcell{height:17px;border-right:2px solid #fff;border-radius:1px}"
    ".hcell.on{outline:2px solid #16202b;outline-offset:-1px;border-radius:2px;position:relative;z-index:1}"
    ".hnow{margin-top:12px;font-size:12.5px;color:var(--muted);line-height:1.55;border-top:1px solid var(--line);padding-top:11px}.hnow b{color:var(--ink)}"
    ".hlg{font-size:11px;color:var(--faint);margin-top:9px;display:flex;gap:13px;flex-wrap:wrap;align-items:center}"
    ".hlg i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:4px;vertical-align:-1px}"
    "@media(max-width:680px){.hmh,.hhr{grid-template-columns:66px repeat(12,1fr)}.hml{font-size:7.5px;letter-spacing:-.04em}.hhn{font-size:10px}}"
)
HATCH_JS = r"""
window.renderHatch=function(elId,H,month){var el=document.getElementById(elId);
 if(!el)return; if(!H||!H.rows){el.style.display='none';return;}
 var M=['J','F','M','A','M','J','J','A','S','O','N','D'],
     MN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
     COL=['#eef2f4','#cfe9d9','#83d6a3','#28c76f'],mi=(month||1)-1;
 var h='<div class="hmh"><div></div>';
 for(var k=0;k<12;k++)h+='<div class="hml'+(k===mi?' on':'')+'">'+MN[k]+'</div>';
 h+='</div>';
 H.rows.forEach(function(r){h+='<div class="hhr"><div class="hhn">'+(r.icon?r.icon+' ':'')+r.name+'</div>';
  for(var k=0;k<12;k++){var v=r.m[k]||0;h+='<div class="hcell'+(k===mi?' on':'')+'" style="background:'+COL[v]+'" title="'+r.name+'"></div>';}
  h+='</div>';});
 var now=H.rows.filter(function(r){return (r.m[mi]||0)>=2;}).sort(function(a,b){return b.m[mi]-a.m[mi];});
 var txt=now.map(function(r){return '<b>'+r.name+'</b>'+(r.pattern?' — '+r.pattern:'');}).join(' · ');
 h+='<div class="hnow"><b>On the water in '+MN[mi]+':</b> '+(txt||'quiet — fish the year-round staples')+'.</div>';
 h+='<div class="hlg"><span><i style="background:#28c76f"></i>peak</span><span><i style="background:#83d6a3"></i>active</span><span><i style="background:#cfe9d9"></i>light</span><span>&#9633; this month</span></div>';
 el.innerHTML=h;};
"""

# ── shared "River chatter" — recent Reddit intel (from reddit_intel.py) ──────
# Section hides itself when there's no fresh data, so it's invisible until reddit_intel.py runs.
def load_intel(river_id):
    """Return {'updated','posts':[...]} for this river from out/intel/reddit.json, or None."""
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "intel", "reddit.json")
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p))
    except Exception:
        return None
    r = (d.get("rivers") or {}).get(river_id)
    if not r or not r.get("posts"):
        return None
    return {"updated": d.get("updated"), "posts": r["posts"]}

CHATTER_CSS = (
    ".chatter{padding:6px}"
    ".ch{display:block;padding:11px 12px;border-bottom:1px solid var(--line);text-decoration:none;color:inherit}"
    ".ch:last-of-type{border-bottom:0}.ch:hover{background:#f7fafc}"
    ".chtop{display:flex;align-items:center;gap:8px;margin-bottom:3px}"
    ".chsub{font-size:11.5px;font-weight:700;color:#5a86a8}"
    ".chnew{font-size:9.5px;font-weight:800;color:#fff;background:#28c76f;border-radius:5px;padding:1px 5px;letter-spacing:.03em}"
    ".chmeta{margin-left:auto;font-size:11px;color:var(--faint)}"
    ".chttl{font-size:14px;font-weight:600;line-height:1.35}"
    ".chsnip{font-size:12.5px;color:var(--muted);margin-top:3px;line-height:1.45}"
    ".chfoot{font-size:11px;color:var(--faint);padding:9px 12px 3px}"
)
CHATTER_JS = r"""
window.renderChatter=function(elId,data,wrapId){
 var el=document.getElementById(elId),wrap=wrapId?document.getElementById(wrapId):el;
 if(!el)return;
 function esc(s){return (s==null?'':(''+s)).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
 var posts=(data&&data.posts)||[];
 if(!posts.length){if(wrap)wrap.style.display='none';return;}
 if(wrap)wrap.style.display='';
 var h='';
 posts.slice(0,8).forEach(function(p){
  h+='<a class="ch" href="'+esc(p.url)+'" target="_blank" rel="noopener">'
   +'<div class="chtop"><span class="chsub">r/'+esc(p.sub)+'</span>'+(p.new?'<span class="chnew">NEW</span>':'')
   +'<span class="chmeta">'+esc(p.date)+' · ▲'+(p.score|0)+' · 💬'+(p.comments|0)+'</span></div>'
   +'<div class="chttl">'+esc(p.title)+'</div>'
   +(p.snippet?'<div class="chsnip">'+esc(p.snippet)+'</div>':'')+'</a>';
 });
 h+='<div class="chfoot">Public Reddit posts via the official API'+(data.updated?' · updated '+esc(data.updated):'')+' · tap to open the thread</div>';
 el.innerHTML=h;
};
"""

# ── shared MONTHLY MOON & FEEDING CALENDAR (client-side solunar for any month) ──
# buildMoonCal(containerId, lat, lon): color-coded month grid, hover for detail, prev/next + dropdowns.
# Moon phase/feeding is pure moon-age math; sun times are computed astronomically (approx, browser TZ).
MOONCAL_CSS = (
    ".mcal{padding:14px 16px}"
    ".mcalhdr{display:flex;align-items:center;gap:8px;margin-bottom:12px}"
    ".mcalhdr button{border:1px solid var(--line);background:#fff;border-radius:9px;width:32px;height:32px;font-size:17px;line-height:1;cursor:pointer;color:var(--muted)}"
    ".mcalhdr select{border:1px solid var(--line);border-radius:9px;padding:6px 8px;font-size:14px;font-family:inherit;background:#fff;color:var(--ink);font-weight:650}"
    ".mcalhdr .sp{flex:1}"
    ".mcalwk{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-bottom:4px}"
    ".mcalwk div{text-align:center;font-size:10px;font-weight:700;color:var(--faint);letter-spacing:.06em}"
    ".mcalgrid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}"
    ".mcell{aspect-ratio:1;border-radius:9px;padding:5px 6px;cursor:pointer;display:flex;flex-direction:column;justify-content:space-between;border:1.5px solid transparent}"
    ".mcell.today{border-color:#16202b}.mcell.sel{outline:2px solid #0a84ff;outline-offset:-2px}"
    ".mcell .dn{font-size:12px;font-weight:700;color:#16202b}.mcell .mi{font-size:13px;align-self:flex-end;line-height:1}"
    ".mcell.blank{cursor:default}"
    ".mcaldet{margin-top:12px;border-top:1px solid var(--line);padding-top:11px;font-size:12.5px;color:var(--muted);line-height:1.7;min-height:56px}"
    ".mcaldet b{color:var(--ink)}.mcaldet .stars{color:#f0a52b;letter-spacing:1px}"
    ".mcalleg{margin-top:9px;font-size:11px;color:var(--faint);display:flex;align-items:center;gap:5px;flex-wrap:wrap}"
    ".mcalleg i{width:16px;height:11px;border-radius:2px;display:inline-block}"
)
MOONCAL_JS = r"""
window.buildMoonCal=function(cid,lat,lon){
 var el=document.getElementById(cid); if(!el)return;
 var rad=Math.PI/180, SYN=29.530588853, REF=Date.UTC(2000,0,6,18,14)/86400000+2440587.5;
 var COL=['#f4f7f9','#e0efe6','#c1e4d0','#8ed6ab','#54c78c','#28c76f'];
 var MON=['January','February','March','April','May','June','July','August','September','October','November','December'];
 var now=new Date(), Y=now.getFullYear(), M=now.getMonth();
 function localMin(jd){var dt=new Date((jd-2440587.5)*86400000);return dt.getHours()*60+dt.getMinutes();}
 function fmt(m){m=((Math.round(m)%1440)+1440)%1440;var h=Math.floor(m/60),ap=h<12?'a':'p',hh=(h%12)||12,mm=(''+(m%60)).padStart(2,'0');return hh+':'+mm+ap;}
 function sun(y,mo,d){
  var jday=Date.UTC(y,mo,d)/86400000+2440587.5, nn=Math.round(jday-2451545.0), lw=lon, Js=nn+0.0009-lw/360;
  var Mn=((357.5291+0.98560028*Js)%360+360)%360;
  var C=1.9148*Math.sin(Mn*rad)+0.02*Math.sin(2*Mn*rad)+0.0003*Math.sin(3*Mn*rad);
  var lam=((Mn+C+180+102.9372)%360+360)%360;
  var Jt=2451545.0+Js+0.0053*Math.sin(Mn*rad)-0.0069*Math.sin(2*lam*rad);
  var dec=Math.asin(Math.sin(lam*rad)*Math.sin(23.4397*rad));
  var cw=(Math.sin(-0.833*rad)-Math.sin(lat*rad)*Math.sin(dec))/(Math.cos(lat*rad)*Math.cos(dec));
  var noon=localMin(Jt),rise=null,set=null;
  if(cw>=-1&&cw<=1){var w=Math.acos(cw)/rad;rise=localMin(Jt-w/360);set=localMin(Jt+w/360);}
  return {noon:noon,rise:rise,set:set};
 }
 function moon(y,mo,d){
  var jd=Date.UTC(y,mo,d,12)/86400000+2440587.5, age=(((jd-REF)%SYN)+SYN)%SYN, frac=age/SYN;
  var illum=Math.round((1-Math.cos(2*Math.PI*frac))/2*100);
  var N=[[.02,'New','🌑'],[.24,'Waxing crescent','🌒'],[.28,'First quarter','🌓'],[.47,'Waxing gibbous','🌔'],[.53,'Full','🌕'],[.72,'Waning gibbous','🌖'],[.78,'Last quarter','🌗'],[.98,'Waning crescent','🌘'],[2,'New','🌑']];
  var nm=N.filter(function(x){return frac<=x[0];})[0];
  var dd=Math.min(frac,Math.abs(frac-.5),Math.abs(frac-1));
  return {illum:illum,name:nm[1],icon:nm[2],rating:Math.max(1,Math.min(5,Math.round(1+(1-dd/0.25)*4))),age:age};
 }
 function sol(y,mo,d){var mn=moon(y,mo,d),sn=sun(y,mo,d);
  var ut=((sn.noon+mn.age*48.8)%1440+1440)%1440, lt=(ut+720)%1440;
  return {icon:mn.icon,name:mn.name,illum:mn.illum,rating:mn.rating,rise:sn.rise,set:sn.set,
   major:[[fmt(ut-60),fmt(ut+60)],[fmt(lt-60),fmt(lt+60)]],minor:[[fmt(ut-368),fmt(ut-308)],[fmt(ut+308),fmt(ut+368)]]};}
 function render(){
  var startDow=new Date(Y,M,1).getDay(), days=new Date(Y,M+1,0).getDate();
  var tY=now.getFullYear(),tM=now.getMonth(),tD=now.getDate();
  var mopts=MON.map(function(n,i){return '<option value="'+i+'"'+(i===M?' selected':'')+'>'+n+'</option>';}).join('');
  var yopts='';for(var yy=tY-3;yy<=tY+3;yy++)yopts+='<option value="'+yy+'"'+(yy===Y?' selected':'')+'>'+yy+'</option>';
  var h='<div class="mcalhdr"><button data-nav="-1">‹</button><select id="'+cid+'_mo">'+mopts+'</select>'
   +'<select id="'+cid+'_yr">'+yopts+'</select><span class="sp"></span><button data-nav="1">›</button></div>'
   +'<div class="mcalwk"><div>S</div><div>M</div><div>T</div><div>W</div><div>T</div><div>F</div><div>S</div></div><div class="mcalgrid">';
  for(var b=0;b<startDow;b++)h+='<div class="mcell blank"></div>';
  for(var d=1;d<=days;d++){var s=sol(Y,M,d),tdy=(Y===tY&&M===tM&&d===tD);
   h+='<div class="mcell'+(tdy?' today':'')+'" data-d="'+d+'" style="background:'+COL[s.rating]+'"><div class="dn">'+d+'</div><div class="mi">'+s.icon+'</div></div>';}
  h+='</div><div class="mcaldet" id="'+cid+'_det"></div>'
   +'<div class="mcalleg">Feeding strength <i style="background:'+COL[1]+'"></i><i style="background:'+COL[2]+'"></i><i style="background:'+COL[3]+'"></i><i style="background:'+COL[4]+'"></i><i style="background:'+COL[5]+'"></i> — new &amp; full moons peak · tap/hover a day</div>';
  el.innerHTML=h;
  el.querySelectorAll('[data-nav]').forEach(function(bt){bt.onclick=function(){M+=+bt.dataset.nav;if(M<0){M=11;Y--;}if(M>11){M=0;Y++;}render();};});
  document.getElementById(cid+'_mo').onchange=function(){M=+this.value;render();};
  document.getElementById(cid+'_yr').onchange=function(){Y=+this.value;render();};
  var det=document.getElementById(cid+'_det');
  function show(d){var s=sol(Y,M,d),dt=new Date(Y,M,d);
   det.innerHTML='<b>'+dt.toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric'})+'</b> · '+s.icon+' '+s.name+' · '+s.illum+'% lit · <span class="stars">'+'★'.repeat(s.rating)+'☆'.repeat(5-s.rating)+'</span> feed<br>'
    +'<b>Majors</b> (peak) '+s.major.map(function(w){return w[0]+'–'+w[1];}).join('  ·  ')+'<br>'
    +'<b>Minors</b> '+s.minor.map(function(w){return w[0]+'–'+w[1];}).join('  ·  ')
    +(s.rise!=null?'<br><span style="color:var(--faint)">Sun '+fmt(s.rise)+'–'+fmt(s.set)+' · times approx</span>':'');}
  el.querySelectorAll('.mcell[data-d]').forEach(function(c){
   function pick(){el.querySelectorAll('.mcell.sel').forEach(function(x){x.classList.remove('sel');});c.classList.add('sel');show(+c.dataset.d);}
   c.onmouseover=pick; c.onclick=pick;});
  var dd=(Y===tY&&M===tM)?tD:1; show(dd);
  var dc=el.querySelector('.mcell[data-d="'+dd+'"]'); if(dc)dc.classList.add('sel');
 }
 render();
};
"""

def solunar(day, sunrise_hm, sunset_hm, tz):
    """Local solunar estimate: moon age + sun times → feeding rating + major/minor windows.
    day=date, sunrise_hm/sunset_hm='HH:MM' local, tz=ZoneInfo. Mirrors the proven Caney calc."""
    if not (sunrise_hm and sunset_hm):
        return None
    def _m(hm):
        h, mn = map(int, hm.split(":")); return h*60 + mn
    def _fmt(m):
        m = int(round(m)) % 1440; h = m // 60
        return "%d:%02d%s" % ((h % 12) or 12, m % 60, "am" if h < 12 else "pm")
    noon = (_m(sunrise_hm) + _m(sunset_hm)) / 2.0
    ref = _dt.datetime(2000, 1, 6, 18, 14, tzinfo=_dt.timezone.utc).timestamp()
    syn = 29.530588853
    tnoon = _dt.datetime(day.year, day.month, day.day, 12, 0, tzinfo=tz).timestamp()
    age = ((tnoon - ref) / 86400.0) % syn; frac = age / syn
    illum = round((1 - math.cos(2*math.pi*frac)) / 2 * 100)
    moon = next(n for f, n in [(.02, "New"), (.24, "Waxing crescent"), (.28, "First quarter"),
                (.47, "Waxing gibbous"), (.53, "Full"), (.72, "Waning gibbous"),
                (.78, "Last quarter"), (.98, "Waning crescent"), (2, "New")] if frac <= f)
    ut = (noon + age*48.8) % 1440; lt = (ut + 720) % 1440
    d = min(frac, abs(frac-.5), abs(frac-1.0)); rating = max(1, min(5, round(1 + (1 - d/0.25)*4)))
    return {"rating": rating, "moon": "%s · %d%% lit" % (moon, illum), "approx": True,
            "major": [[_fmt(ut-60), _fmt(ut+60)], [_fmt(lt-60), _fmt(lt+60)]],
            "minor": [[_fmt(ut-368), _fmt(ut-308)], [_fmt(ut+308), _fmt(ut+368)]]}

def switcher(cur):
    # HQ home link first, then every river. cur="hq" highlights the HQ tab.
    if cur == "hq":
        parts = ['<a class="on" style="background:#1c2b3a;color:#fff">🏠 HQ</a>']
    else:
        parts = ['<a href="index.html">🏠 HQ</a>']
    for r in RIVERS:
        if r["id"] == cur:
            parts.append('<a class="on" style="background:%s;color:%s">%s %s</a>'
                         % (r["on_bg"], r["on_fg"], r["emoji"], r["name"]))
        else:
            parts.append('<a href="%s">%s %s</a>' % (r["file"], r["emoji"], r["name"]))
    return '<div class="switch">' + "".join(parts) + "</div>"

def render(html, river_id):
    """Fill every shared token for this river. Unknown/unused tokens stay blank-safe."""
    return (html
            .replace("<head>", "<head>" + BASE_HEAD, 1)
            .replace("__SWITCH_CSS__", SWITCH_CSS)
            .replace("__SWITCHER__", switcher(river_id))
            .replace("__CREDIT__", CREDIT)
            .replace("__POPUP_JS__", POPUP_JS)
            .replace("__MAP_JS__", MAP_JS)
            .replace("__SOLUNAR_CSS__", SOLUNAR_CSS)
            .replace("__SOLUNAR_JS__", SOLUNAR_JS)
            .replace("__HATCH_CSS__", HATCH_CSS)
            .replace("__HATCH_JS__", HATCH_JS)
            .replace("__CHATTER_CSS__", CHATTER_CSS)
            .replace("__CHATTER_JS__", CHATTER_JS)
            .replace("__LOG_CSS__", LOG_CSS)
            .replace("__LOG_JS__", LOG_JS)
            .replace("__MOONCAL_CSS__", MOONCAL_CSS)
            .replace("__MOONCAL_JS__", MOONCAL_JS)
            .replace("__FLOWTIMER_CSS__", FLOWTIMER_CSS)
            .replace("__FLOWTIMER_JS__", FLOWTIMER_JS)
            .replace("__FLYMATRIX_CSS__", FLYMATRIX_CSS)
            .replace("__FLYMATRIX_JS__", FLYMATRIX_JS)
            .replace("__GENSCHED_CSS__", GENSCHED_CSS)
            .replace("__GENSCHED_JS__", GENSCHED_JS))

# ── shared utilities every float/tailwater page can reuse ────────────────────
_UA = {"User-Agent": "riverlib/1.0"}
def get(u, h=None, timeout=60):
    with urllib.request.urlopen(
            urllib.request.Request(u, headers={**_UA, **(h or {})}), timeout=timeout) as r:
        return json.load(r)

def haversine(a, b):
    """Straight-line miles between (lat,lon) points."""
    R = 3958.8
    la1, lo1 = map(math.radians, a); la2, lo2 = map(math.radians, b)
    dla, dlo = la2 - la1, lo2 - lo1
    h = math.sin(dla/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(dlo/2)**2
    return 2 * R * math.asin(math.sqrt(h))

def shuttle_miles(a, b, road_factor=1.35):
    """Estimated ROAD shuttle miles between two accesses (straight-line × sinuosity)."""
    return round(haversine(a, b) * road_factor, 1)

# ── River Monitor HQ: shared status contract every generator emits ───────────
# Each page writes out/status/<id>.json so the homepage (index.html) can aggregate
# ALL rivers into one week-ahead board (filter by species, sort by best water).
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

def write_status(river_id, status):
    d = os.path.join(OUT, "status"); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, river_id + ".json"), "w") as f:
        json.dump(status, f)

# grade label → 0..3 base water score (how the current condition seeds the week)
GRADE_SCORE = {"Prime": 3.0, "Good": 2.3, "Fair": 1.3, "Slow": 0.8, "Tough": 0.6,
               "Blown": 0.3, "High": 1.0, "Up": 1.4, "Low": 1.8, "—": 1.3}

def _grade_from_score(s):
    if s >= 2.5: return ("Prime", "#28c76f")
    if s >= 1.7: return ("Good",  "#7db85a")
    if s >= 0.9: return ("Fair",  "#f2a832")
    return ("Slow", "#8b6cef")

def build_week(wx, base, tz, per_date_note=None):
    """7-day conditions projection blending the river's current water state (base: a 0..3
    score, or a per-day list) with weather (rain/temps) and moon feeding (solunar rating).
    Honest by design — most of these rivers have no true multi-day FLOW forecast, so the
    baseline is 'today's water persists' nudged by weather & moon. wx=Open-Meteo (needs
    daily temperature_2m_max/min, precipitation_probability_max, sunrise, sunset, 7 days)."""
    if not wx or "daily" not in wx: return []
    D = wx["daily"]; out = []
    pp_all = D.get("precipitation_probability_max", [0] * 9)
    H = wx.get("hourly", {}); hcloud = H.get("cloud_cover", [])
    hidx = {t: i for i, t in enumerate(H.get("time", []))}
    for i, ds in enumerate(D["time"][:7]):
        d = _dt.date.fromisoformat(ds)
        sr = D["sunrise"][i][11:16] if i < len(D.get("sunrise", [])) else None
        ss = D["sunset"][i][11:16] if i < len(D.get("sunset", [])) else None
        sol = solunar(d, sr, ss, tz)
        rating = sol["rating"] if sol else 3
        pop = pp_all[i] or 0
        hi = round(D["temperature_2m_max"][i]); lo = round(D["temperature_2m_min"][i])
        b = base[i] if isinstance(base, (list, tuple)) else base
        score = b + (0.5 if rating >= 4 else 0.2 if rating >= 3 else 0.0) \
                  - (1.0 if pop >= 70 else 0.5 if pop >= 50 else 0.0)
        score = max(0.0, min(3.0, score))
        grade, col = _grade_from_score(score)
        feed = "strong" if rating >= 4 else "fair" if rating >= 3 else "slow"
        note = "%d°/%d° · %d%% rain · %s feed" % (hi, lo, pop, feed)
        if per_date_note and ds in per_date_note:
            note = per_date_note[ds] + " · " + note
        cc = hcloud[hidx[ds + "T13:00"]] if (ds + "T13:00") in hidx else None
        ico = ("🌧️" if pop >= 45 else "☀️" if (cc is not None and cc < 25)
               else "☁️" if (cc is not None and cc >= 65) else "⛅")
        out.append({"date": d.strftime("%-m/%-d"),
                    "label": ("Today" if i == 0 else d.strftime("%a")),
                    "grade": grade, "col": col, "note": note, "ico": ico,
                    "pop": pop, "hi": hi, "lo": lo, "rating": rating})
    return out

def today_wx(wx, tz):
    """Compact today weather for the HQ card line: icon, hi/lo, rain %, wind (midday snapshot)."""
    if not wx or "daily" not in wx:
        return None
    D = wx["daily"]
    hi = round(D["temperature_2m_max"][0]); lo = round(D["temperature_2m_min"][0])
    pop = (D.get("precipitation_probability_max", [0]) or [0])[0] or 0
    ico, wind, sky = "⛅", None, "partly cloudy"
    H = wx.get("hourly")
    if H and "time" in H:
        d = _dt.datetime.now(tz).date()
        key = _dt.datetime(d.year, d.month, d.day, 13).strftime("%Y-%m-%dT%H:00")
        if key in H["time"]:
            i = H["time"].index(key)
            cc = H["cloud_cover"][i] or 0; wind = round(H["wind_speed_10m"][i] or 0)
            ico = "☀️" if cc < 25 else "⛅" if cc < 65 else "☁️"
            sky = "clear" if cc < 25 else "partly cloudy" if cc < 65 else "overcast"
            if pop >= 45: ico = "🌧️"
    return {"ico": ico, "hi": hi, "lo": lo, "pop": pop, "wind": wind, "sky": sky}

def emit_status(river_id, now, wx, base_score, tz, species, kind, drive, per_date_note=None):
    """Build the week outlook and write the HQ status card for this river in one call."""
    r = next((x for x in RIVERS if x["id"] == river_id), {})
    status = {"id": river_id, "name": r.get("name"), "emoji": r.get("emoji"),
              "file": r.get("file"), "on_bg": r.get("on_bg"), "on_fg": r.get("on_fg"),
              "species": species, "kind": kind, "drive": drive,
              "now": now, "wx": today_wx(wx, tz),
              "week": build_week(wx, base_score, tz, per_date_note)}
    write_status(river_id, status)
    return status
