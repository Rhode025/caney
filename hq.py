#!/usr/bin/env python3
"""
River Monitor HQ — the homepage (out/index.html).
Aggregates every river's status card (out/status/<id>.json, written by each generator) into one
week-ahead board: current condition + a 7-day conditions projection per river, filterable by
target species and sortable by best water / soonest / drive time. Build the rivers first, then
this. Sources roll up from each river page. Personal use.
"""
import json,os,sys,datetime,glob
from zoneinfo import ZoneInfo
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import riverlib
CT=ZoneInfo("America/Chicago")
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"out")
now_ct=datetime.datetime.now(CT)

# ---- load every river's status card, ordered by the RIVERS registry ----
order={r["id"]:i for i,r in enumerate(riverlib.RIVERS)}
CARDS=[]
for f in glob.glob(os.path.join(OUT,"status","*.json")):
    try: CARDS.append(json.load(open(f)))
    except Exception as e: print("skip",f,e)
CARDS.sort(key=lambda c:order.get(c["id"],99))
# union of species for the filter chips (stable, by first appearance)
SPECIES=[]
for c in CARDS:
    for s in c.get("species",[]):
        if s not in SPECIES: SPECIES.append(s)

DATA={"cards":CARDS,"species":SPECIES,"updated":now_ct.strftime("%A, %b %-d · %-I:%M %p"),"count":len(CARDS)}

TEMPLATE=r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>River Monitor HQ</title>
<style>
:root{--ink:#16202b;--muted:#66788a;--faint:#93a3b3;--line:#e6ecf2;--card:#fff}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,sans-serif;
 background:radial-gradient(1100px 720px at 80% -8%,#e9eef5 0,transparent 60%),linear-gradient(180deg,#eef2f6,#e5ebf1);min-height:100vh}
.app{max-width:960px;margin:0 auto;padding:30px 22px 80px}
__SWITCH_CSS__
.eyebrow{font-size:12px;letter-spacing:.26em;text-transform:uppercase;color:var(--faint);font-weight:600}
h1{margin:6px 0 4px;font-size:34px;font-weight:800;letter-spacing:-.7px}
.cap{color:var(--muted);font-size:14.5px}
.ctrl{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;margin:18px 0 6px}
.sp{display:flex;flex-wrap:wrap;gap:6px}
.sp a{font-size:12px;font-weight:650;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;color:var(--muted);cursor:pointer;user-select:none}
.sp a.on{background:#1c2b3a;color:#fff;border-color:#1c2b3a}
.sortw{font-size:12.5px;color:var(--muted);display:flex;align-items:center;gap:7px}
.sortw select{font:inherit;font-size:12.5px;padding:5px 8px;border-radius:9px;border:1px solid var(--line);background:#fff;color:var(--ink)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--muted);margin:4px 2px 14px}
.legend i{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:5px;vertical-align:-1px}
.rc{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:18px;
 box-shadow:0 8px 26px rgba(20,50,80,.06);padding:16px 18px;margin-bottom:14px;transition:box-shadow .15s,transform .15s}
.rc:hover{box-shadow:0 12px 32px rgba(20,50,80,.12);transform:translateY(-1px)}
.rc-h{display:flex;align-items:center;gap:13px}
.rc-h .em{font-size:26px;flex:none}
.rc-t{flex:1;min-width:0}
.rc-t .nm{font-size:18px;font-weight:750;letter-spacing:-.2px}
.rc-t .kd{font-size:12px;color:var(--faint);margin-top:1px}
.rc-now{flex:none;text-align:right;display:flex;align-items:center;gap:10px}
.rc-now .badge{color:#fff;font-weight:800;font-size:12px;padding:7px 12px;border-radius:11px;white-space:nowrap}
.rc-now .sub{font-size:12px;color:var(--muted);max-width:150px;text-align:right;line-height:1.35}
.rc-now .sub b{color:var(--ink);display:block;font-size:12.5px}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin:11px 0 4px}
.tags span{font-size:10.5px;font-weight:650;color:#4a5a6a;background:#f0f3f7;border-radius:999px;padding:3px 9px}
.wk{display:flex;gap:5px;margin-top:5px}
.wxrow{display:flex;gap:5px;margin-top:11px}
.wxc{flex:1;min-width:0;text-align:center;display:flex;flex-direction:column;align-items:center;gap:1px}
.wxc .wi{font-size:15px;line-height:1.15}
.wxc .wt{font-size:11px;font-weight:700;color:var(--ink)}
.wxc .wr{font-size:9px;font-weight:600;color:#2f6d94}
.wxc .wr.dry{color:var(--faint);font-weight:400}
.wd{flex:1;min-width:0;border-radius:9px;padding:7px 3px 8px;text-align:center;color:#fff;position:relative}
.wd .dl{display:block;font-size:10.5px;font-weight:700;opacity:.92}
.wd .dd{display:block;font-size:9.5px;opacity:.82;margin-top:1px}
.wd .dg{display:block;font-size:10px;font-weight:750;margin-top:4px}
.wd.best::after{content:"★";position:absolute;top:2px;right:4px;font-size:9px;opacity:.9}
.wxline{margin-top:9px;font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px}
.wxline .lbl{color:var(--faint);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;font-weight:600}
.wd{cursor:pointer}
.wknote{margin-top:8px;font-size:12px;color:var(--muted);background:#f5f7fa;border:1px solid var(--line);border-radius:9px;padding:8px 11px;line-height:1.4}
.rc-ft{font-size:11.5px;color:var(--faint);margin-top:9px}
.viewsel{display:inline-flex;background:#e7edf3;border-radius:12px;padding:3px;gap:2px}
.viewsel button{font:inherit;font-size:13px;font-weight:700;border:0;background:transparent;color:var(--muted);
 padding:8px 16px;border-radius:9px;cursor:pointer;min-height:40px}
.viewsel button.on{background:#fff;color:var(--ink);box-shadow:0 1px 3px rgba(20,50,80,.14)}
.dayhead{font-size:15px;font-weight:750;margin:14px 2px 2px;letter-spacing:-.2px}
.daysub{font-size:12px;color:var(--faint);margin:0 2px 12px}
.hl{font-size:15px;font-weight:700;margin:12px 0 2px;letter-spacing:-.2px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:9px 0 2px}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:700;border-radius:999px;
 padding:5px 11px;color:#fff;white-space:nowrap}
.chip.ghost{background:#f0f3f7;color:#4a5a6a}
.chip .cw{font-weight:500;opacity:.92}
.curve{margin-top:12px;position:relative}
.curve svg{display:block;width:100%;height:44px;overflow:visible}
.curve .clab{display:flex;justify-content:space-between;font-size:9.5px;color:var(--faint);margin-top:3px;font-weight:600}
.curve .ctitle{font-size:10.5px;color:var(--faint);letter-spacing:.07em;text-transform:uppercase;font-weight:700;margin-bottom:4px}
.curve .ctitle .obs{color:#b3703a}
.nocurve{margin-top:12px;font-size:12px;color:var(--muted);background:#f5f7fa;border:1px dashed #d6dee7;
 border-radius:10px;padding:10px 12px;line-height:1.45}
.winbar{display:flex;gap:4px;margin-top:9px}
.winbar span{flex:1;text-align:center;font-size:10.5px;font-weight:700;color:#fff;border-radius:7px;padding:5px 4px}
.empty{text-align:center;color:var(--muted);padding:40px;font-size:14px}
.note{font-size:11.5px;color:var(--faint);line-height:1.6;margin:2px 2px 0}
.foot{text-align:center;color:var(--faint);font-size:11.5px;margin-top:24px;line-height:1.6}
@media(max-width:620px){.app{padding:22px 14px 60px}h1{font-size:28px}.viewsel{width:100%}.viewsel button{flex:1;padding:9px 6px}.chip{font-size:11.5px}.rc-now .sub{display:none}.wd .dg{display:none}.wd .dd{display:none}}
</style></head><body><div class="app">
 __SWITCHER__
 <div class="eyebrow">River Monitor · Middle Tennessee</div>
 <h1>River Monitor HQ</h1>
 <div class="cap" id="cap"></div>
 <div class="ctrl">
   <div class="viewsel" id="viewsel">
     <button data-v="today">Today</button><button data-v="tomorrow">Tomorrow</button><button data-v="week">Week</button>
   </div>
 </div>
 <div class="dayhead" id="dayhead"></div><div class="daysub" id="daysub"></div>
 <div class="ctrl">
   <div class="sp" id="spf"></div>
   <div class="sortw">Sort <select id="sort">
     <option value="week">Best this week</option>
     <option value="now">Fishing now</option>
     <option value="drive">Nearest drive</option>
     <option value="name">Name</option>
   </select></div>
 </div>
 <div class="legend" id="legend"></div>
 <div id="board"></div>
 <div class="note">Next-week projection blends each river's current water state with weather &amp; moon feeding — most of these rivers have no true multi-day flow forecast, so treat it as a planning lean, not a promise. Open a river for the live gauge, generation and the full read.</div>
 <div class="foot" id="foot"></div>
</div>
<script>
const D=__DATA__;
const GW={Prime:3,Great:3,Good:2,Gen:2,Fair:1,Up:1,Low:1,High:1,Off:1,Slow:0,Slack:0,Tough:0,"—":1};
function weekScore(c){return (c.week||[]).reduce((a,w)=>a+(GW[w.grade]||0),0);}
function nowScore(c){return GW[c.now.grade]||0;}
function driveMin(c){var m=(c.drive||'').match(/([\d.]+)\s*(hr|min)/);if(!m)return 999;return Math.round(parseFloat(m[1])*(m[2]==='hr'?60:1));}
let filter=new Set(); let sortBy='week';
// Default view: Today before noon, Tomorrow after. Past midday you are almost always
// planning the next trip rather than deciding whether to go right now.
let view = (new Date().getHours() < 12) ? 'today' : 'tomorrow';

function fmtHour(h){return (h%12||12)+(h<12?'a':'p');}

// Inline SVG area chart of the day's flow. Gaps (null hours) break the path rather than
// interpolating across them, so an observed-only curve visibly stops where the data does.
function sparkline(cv, col, isToday){
  if(!cv || !cv.vals) return '';
  const v=cv.vals, W=300, H=40, PAD=3;
  const known=v.map((x,i)=>[i,x]).filter(p=>p[1]!=null);
  if(!known.length) return '';
  let max=Math.max(...known.map(p=>p[1])), min=Math.min(...known.map(p=>p[1]));
  if(max===min){max=min+1;}
  const X=i=>PAD+(i/23)*(W-PAD*2), Y=x=>H-PAD-((x-min)/(max-min))*(H-PAD*2);
  let segs=[],cur=[];
  v.forEach((x,i)=>{ if(x==null){ if(cur.length>1)segs.push(cur); cur=[]; } else cur.push([i,x]); });
  if(cur.length>1)segs.push(cur);
  let paths='';
  segs.forEach(sg=>{
    const line=sg.map((p,k)=>(k?'L':'M')+X(p[0]).toFixed(1)+' '+Y(p[1]).toFixed(1)).join(' ');
    const area=line+' L'+X(sg[sg.length-1][0]).toFixed(1)+' '+(H-PAD)+' L'+X(sg[0][0]).toFixed(1)+' '+(H-PAD)+' Z';
    paths+='<path d="'+area+'" fill="'+col+'" opacity=".16"/>'
          +'<path d="'+line+'" fill="none" stroke="'+col+'" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
  });
  let nowmark='';
  if(isToday){ const nh=new Date().getHours()+new Date().getMinutes()/60;
    nowmark='<line x1="'+X(nh).toFixed(1)+'" y1="0" x2="'+X(nh).toFixed(1)+'" y2="'+H+'" stroke="#16202b" stroke-width="1" opacity=".38" stroke-dasharray="2 2"/>'; }
  const src=cv.src==='observed'
    ? '<span class="obs">Observed only · no forecast</span>' : (cv.label||'');
  const rng=(cv.min===cv.peak) ? Math.round(cv.peak).toLocaleString()+' '+cv.unit
        : Math.round(cv.min).toLocaleString()+'–'+Math.round(cv.peak).toLocaleString()+' '+cv.unit;
  return '<div class="curve"><div class="ctitle">'+src+' · '+rng+'</div>'
    +'<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">'+paths+nowmark+'</svg>'
    +'<div class="clab"><span>12a</span><span>6a</span><span>noon</span><span>6p</span><span>12a</span></div></div>';
}

function dayCard(c){
  const d=(c.days||{})[view];
  if(!d) return '<div class="nocurve">This river does not report a day read yet.</div>';
  let h='';
  if(d.headline) h+='<div class="hl">'+d.headline+'</div>';
  h+='<div class="chips">';
  if(d.vessel && d.vessel.kind!=='na')
    h+='<span class="chip" style="background:'+d.vessel.col+'">'+d.vessel.ico+' '+d.vessel.label+'</span>';
  if(d.level && d.level.kind!=='unknown')
    h+='<span class="chip" style="background:'+d.level.col+'">'+d.level.label
      +(d.level.detail?'<span class="cw">'+d.level.detail+'</span>':'')+'</span>';
  if(d.clarity && d.clarity.kind!=='unknown')
    h+='<span class="chip" style="background:'+d.clarity.col+'">● '+d.clarity.label+'</span>';
  h+='</div>';
  if(d.vessel && d.vessel.why) h+='<div class="rc-ft">'+d.vessel.why+'</div>';
  const sp=sparkline(d.curve, (d.level&&d.level.col)||'#2f92d4', view==='today');
  h+= sp || '<div class="nocurve">No flow curve for this day — this river has no forward flow forecast.</div>';
  if((d.windows||[]).length){
    h+='<div class="winbar">';
    d.windows.forEach(w=>{const col=w.kind==='wade'?'#20b2aa':'#2f92d4';
      h+='<span style="background:'+col+'">'+(w.kind==='wade'?'🥾':'🚤')+' '+w.from+'–'+w.to+'</span>';});
    h+='</div>';
  }
  return h;
}
document.getElementById('cap').textContent=D.count+' rivers within range · updated '+D.updated;
// species filter chips
(function(){let h='<a data-s="" class="on">All species</a>';D.species.forEach(s=>h+='<a data-s="'+s+'">'+s+'</a>');
 const el=document.getElementById('spf');el.innerHTML=h;
 el.querySelectorAll('a').forEach(a=>a.onclick=()=>{const s=a.dataset.s;
  if(!s){filter.clear();}else{if(filter.has(s))filter.delete(s);else filter.add(s);}
  el.querySelectorAll('a').forEach(z=>z.classList.toggle('on',z.dataset.s? filter.has(z.dataset.s):filter.size===0));
  render();});})();
document.getElementById('sort').onchange=e=>{sortBy=e.target.value;render();};
function bestIdx(c){let bi=-1,bs=-1;(c.week||[]).forEach((w,i)=>{const s=GW[w.grade]||0;if(s>bs){bs=s;bi=i;}});return bi;}
function render(){
 let list=D.cards.slice();
 if(filter.size)list=list.filter(c=>(c.species||[]).some(s=>filter.has(s)));
 const cmp={week:(a,b)=>weekScore(b)-weekScore(a)||nowScore(b)-nowScore(a),
            now:(a,b)=>nowScore(b)-nowScore(a)||weekScore(b)-weekScore(a),
            drive:(a,b)=>driveMin(a)-driveMin(b),
            name:(a,b)=>a.name.localeCompare(b.name)}[sortBy];
 list.sort(cmp);
 const bd=document.getElementById('board');
 if(!list.length){bd.innerHTML='<div class="empty">No rivers match that species filter.</div>';return;}
 let h='';list.forEach(c=>{const n=c.now,bi=bestIdx(c);
  h+='<a class="rc" href="'+c.file+'">'
   +'<div class="rc-h"><span class="em">'+c.emoji+'</span>'
   +'<div class="rc-t"><div class="nm">'+c.name+'</div><div class="kd">'+(c.kind||'')+' · '+(c.drive||'')+'</div></div>'
   // The badge is the LIVE grade, which is always today. On a Tomorrow or Week view that
   // sat unlabelled next to a headline about another day — a Prime badge above "no
   // generation - slack water". Say which day the badge belongs to.
   +'<div class="rc-now"><div class="sub"><b>'+n.cond+'</b>'+(n.detail||'')+'</div>'
   +'<div class="badge" style="background:'+n.col+'">'+n.grade
     +(view==='today'?'':'<small style="display:block;font-size:9px;opacity:.85;font-weight:600">now</small>')
     +'</div></div></div>';
  if(view==='week'){
    h+='<div class="wxrow">';(c.week||[]).forEach(w=>{
     h+='<div class="wxc"><span class="wi">'+(w.ico||'')+'</span><span class="wt">'+w.hi+'°</span>'
       +(w.pop?'<span class="wr">☔'+w.pop+'%</span>':'<span class="wr dry">·</span>')+'</div>';});
    h+='</div>';
    h+='<div class="wk">';(c.week||[]).forEach((w,i)=>{
     const nt=(w.label+' '+w.date+' — '+w.grade+': '+(w.note||'')).replace(/"/g,'&quot;');
     h+='<div class="wd'+(i===bi?' best':'')+'" style="background:'+w.col+'" title="'+nt+'" data-note="'+nt+'">'
      +'<span class="dl">'+(w.label==='Today'?'Today':w.label)+'</span><span class="dd">'+w.date+'</span><span class="dg">'+w.grade+'</span></div>';});
    h+='</div><div class="wknote" hidden></div>';
    h+='<div class="rc-ft">now: '+(n.detail||'—')+(n.asof?' · as of '+n.asof:'')+' → open for the live read</div>';
  } else {
    h+=dayCard(c);
    const wi=(view==='tomorrow')?1:0, w=(c.week||[])[wi];
    if(w) h+='<div class="rc-ft">weather: '+(w.ico||'')+' '+w.hi+'°/'+w.lo+'° · '+(w.pop||0)+'% rain → open for the full read</div>';
  }
  if((c.species||[]).length){h+='<div class="tags">';c.species.forEach(s=>h+='<span>'+s+'</span>');h+='</div>';}
  h+='</a>';});
 bd.innerHTML=h;
}
function paintView(){
  document.querySelectorAll('#viewsel button').forEach(b=>b.classList.toggle('on',b.dataset.v===view));
  const d=new Date(); if(view==='tomorrow') d.setDate(d.getDate()+1);
  const nice=d.toLocaleDateString([], {weekday:'long', month:'short', day:'numeric'});
  const hd=document.getElementById('dayhead'), sb=document.getElementById('daysub');
  if(view==='week'){ hd.textContent='Next 7 days';
    sb.textContent='Planning lean from current water + weather + moon — not a flow forecast.'; }
  else { hd.textContent=(view==='today'?'Today · ':'Tomorrow · ')+nice;
    sb.textContent=(view==='today'
      ? 'What the water is doing right now, hour by hour.'
      : 'What the water is forecast to do. Rivers without a flow forecast say so.'); }
  document.getElementById('legend').innerHTML = (view==='week')
    ? '<span><i style="background:#28c76f"></i>Prime</span><span><i style="background:#7db85a"></i>Good</span>'
      +'<span><i style="background:#f2a832"></i>Fair</span><span><i style="background:#8b6cef"></i>Slow</span>'
      +'<span>· ★ = best day · tap a day for detail</span>'
    : '<span><i style="background:#20b2aa"></i>🥾 wade</span><span><i style="background:#2f92d4"></i>🚤 boat</span>'
      +'<span><i style="background:#28c76f"></i>prime</span><span><i style="background:#f2a832"></i>high</span>'
      +'<span><i style="background:#8b6cef"></i>blown</span>'
      +(view==='today'?'<span>· dashed line = now</span>':'');
  render();
}
document.getElementById('viewsel').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b)return; view=b.dataset.v; paintView();});
paintView();
// tap a day → reveal its note inline (and DON'T navigate); tapping anywhere else on the card opens the river
document.getElementById('board').addEventListener('click',function(e){
  const wd=e.target.closest('.wd'); if(!wd)return;
  e.preventDefault();
  const note=wd.closest('.rc').querySelector('.wknote');
  if(note.dataset.for===wd.dataset.note){note.hidden=true;note.dataset.for='';}   // tap again to dismiss
  else{note.textContent=wd.dataset.note;note.hidden=false;note.dataset.for=wd.dataset.note;}
});
document.getElementById('foot').textContent='Aggregated from each river\'s live status card · public data only (USGS · USACE · NOAA/NWS · Open-Meteo · OpenStreetMap) · projections are estimates, tune from the water · built for personal use.';
</script></body></html>"""
html=riverlib.render(TEMPLATE,"hq").replace("__DATA__",json.dumps(DATA))
open(os.path.join(OUT,"index.html"),"w").write(html)
print("wrote out/index.html (River Monitor HQ) | %d rivers | species: %s"%(len(CARDS),", ".join(SPECIES)))
