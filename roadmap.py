#!/usr/bin/env python3
"""
roadmap.py -> out/roadmap.html — the QC & UX audit and the sprint board, on the live site.

Single source of truth is roadmap.json, which also feeds the GitHub issues (one per
ticket, created by tools/make_issues.py). The issue is the system of record: this page
LINKS to it rather than duplicating its state, so there is only ever one place that
says whether a ticket is done.

No network, no live data — the only generator in the build that touches neither.
"""
import json, os, html as _h
import riverlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

R = json.load(open(os.path.join(HERE, "roadmap.json")))
REPO = R.get("repo", "Rhode025/caney")

LANES = [("now", "Now"), ("next", "Next"), ("later", "Later")]
DATA = {
    "tickets": R["tickets"],
    "findings": R["findings"],
    "method": R["method"],
    "generated": R["generated"],
    "repo": REPO,
    "issuesUrl": "https://github.com/%s/issues" % REPO,
    "counts": {
        "tickets": len(R["tickets"]),
        "fail": sum(1 for f in R["findings"] if f[3] == "fail"),
        "warn": sum(1 for f in R["findings"] if f[3] == "warn"),
        "ok": sum(1 for f in R["findings"] if f[3] == "ok"),
    },
}

TEMPLATE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Roadmap · River Monitor</title>
<meta name="description" content="QC and UX audit of the river tool, and the 38 sprint tickets that come out of it.">
<style>
:root{--ink:#16202b;--muted:#5d6f80;--faint:#6b7b8a;--line:#e2e9ef;--line2:#eef3f7;
 --card:#fff;--card2:#fafcfd;--ground:#f4f7f9;--accent:#0a5ec2;
 --p0f:#a62b17;--p0b:#fdeceb;--p1f:#8a5a10;--p1b:#fdf3e3;
 --p2f:#145d99;--p2b:#eaf3fb;--p3f:#55636f;--p3b:#eef1f4;
 --ok:#1c7a4a;--okb:#e8f6ee;
 --mono:ui-monospace,SFMono-Regular,Menlo,'SF Mono',monospace}
*{box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{margin:0;background:var(--ground);color:var(--ink);
 font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Roboto,sans-serif;
 font-size:15px;line-height:1.55}
__SWITCH_CSS__
.wrap{max-width:1140px;margin:0 auto;padding:0 20px 80px}
.head{padding:34px 0 26px;border-bottom:1px solid var(--line)}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;
 color:var(--accent)}
h1{font-size:clamp(29px,4.6vw,44px);line-height:1.06;letter-spacing:-.02em;margin:12px 0 0}
.method{margin:13px 0 0;max-width:66ch;color:var(--muted);font-size:15px}
.tally{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 0}
.tally a,.tally span{font-family:var(--mono);font-size:11.5px;padding:5px 11px;border-radius:20px;
 border:1px solid var(--line);background:var(--card);color:var(--muted);text-decoration:none}
.tally a:hover{border-color:var(--accent);color:var(--accent)}
.tally .crit{background:var(--p0b);color:var(--p0f);border-color:transparent}
.tally .ser{background:var(--p1b);color:var(--p1f);border-color:transparent}
.tally .pass{background:var(--okb);color:var(--ok);border-color:transparent}
section{padding-top:44px}
h2{font-size:21px;letter-spacing:-.01em;margin:0 0 5px;display:flex;gap:11px;align-items:baseline;flex-wrap:wrap}
h2 i{font-style:normal;font-family:var(--mono);font-size:11.5px;color:var(--faint);letter-spacing:.07em}
.lede{color:var(--muted);margin:0 0 20px;max-width:72ch;font-size:14.5px}
code{font-family:var(--mono);font-size:12.5px;background:var(--card2);border:1px solid var(--line);
 border-radius:4px;padding:1px 5px}
/* findings */
.meas{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.mh,.mr{display:grid;grid-template-columns:minmax(190px,1.4fr) 118px 1fr 84px;gap:15px;
 padding:11px 17px;align-items:baseline}
.mh{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;
 color:var(--faint);background:var(--card2);border-bottom:1px solid var(--line)}
.mr{border-top:1px solid var(--line2);font-size:14px}
.mr:first-of-type{border-top:none}
.mr b{font-weight:600}
.mr .v{font-family:var(--mono);font-size:13px;font-variant-numeric:tabular-nums}
.mr .n{color:var(--muted);font-size:13.5px}
.vd{font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.05em;padding:3px 8px;
 border-radius:5px;justify-self:start;white-space:nowrap}
.vd.fail{background:var(--p0b);color:var(--p0f)}
.vd.warn{background:var(--p1b);color:var(--p1f)}
.vd.ok{background:var(--okb);color:var(--ok)}
/* board */
.board{display:grid;grid-template-columns:repeat(3,1fr);gap:13px;align-items:start}
.lane{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:11px}
.lane.now{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
.lh{display:flex;justify-content:space-between;align-items:center;padding:2px 3px 10px;
 border-bottom:1px solid var(--line);margin-bottom:10px}
.lh b{font-size:13.5px}.lane.now .lh b{color:var(--accent)}
.lh span{font-family:var(--mono);font-size:10.5px;color:var(--faint);background:var(--card);
 border:1px solid var(--line);border-radius:20px;padding:1px 8px}
.mini{display:block;background:var(--card);border:1px solid var(--line);border-left:3px solid var(--line);
 border-radius:8px;padding:9px 11px;margin-bottom:7px;text-decoration:none;color:inherit}
.mini:hover{border-color:var(--accent);border-left-color:var(--accent)}
.mini.P0{border-left-color:var(--p0f)}.mini.P1{border-left-color:var(--p1f)}
.mini.P2{border-left-color:var(--p2f)}.mini.P3{border-left-color:var(--p3f)}
.mini .k{display:block;font-family:var(--mono);font-size:10px;color:var(--faint);letter-spacing:.05em}
.mini .t{display:block;font-size:12.5px;line-height:1.35;font-weight:500;margin-top:3px}
/* controls + tickets */
.ctl{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin:0 0 16px;padding:12px 14px;
 background:var(--card);border:1px solid var(--line);border-radius:11px}
.cg{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.cg .lb{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
 color:var(--faint);margin-right:2px}
.chip{font-family:var(--mono);font-size:11px;padding:5px 10px;border-radius:20px;cursor:pointer;
 border:1px solid var(--line);background:var(--card2);color:var(--muted);min-height:30px}
.chip:hover{border-color:var(--accent);color:var(--accent)}
.chip[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff}
#q{flex:1;min-width:170px;font:inherit;font-size:14px;padding:8px 12px;border:1px solid var(--line);
 border-radius:8px;background:var(--card2);color:var(--ink)}
.tks{display:flex;flex-direction:column;gap:8px}
.tk{background:var(--card);border:1px solid var(--line);border-radius:11px;overflow:hidden}
.tk>summary{display:grid;grid-template-columns:56px 50px 1fr auto;gap:13px;align-items:center;
 padding:12px 16px;cursor:pointer;list-style:none}
.tk>summary::-webkit-details-marker{display:none}
.tk>summary:hover{background:var(--card2)}
.sp{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--accent)}
.sp em{display:block;font-style:normal;font-size:9px;color:var(--faint);letter-spacing:.08em;font-weight:400}
.pr{font-family:var(--mono);font-size:10px;font-weight:700;padding:3px 7px;border-radius:5px;text-align:center}
.pr.P0{background:var(--p0b);color:var(--p0f)}.pr.P1{background:var(--p1b);color:var(--p1f)}
.pr.P2{background:var(--p2b);color:var(--p2f)}.pr.P3{background:var(--p3b);color:var(--p3f)}
.tt{font-weight:500;font-size:14.5px;line-height:1.35}
.tt .kk{display:block;font-family:var(--mono);font-size:10px;color:var(--faint);letter-spacing:.07em;
 text-transform:uppercase;margin-bottom:2px}
.gh{font-family:var(--mono);font-size:11px;color:var(--faint);text-decoration:none;white-space:nowrap}
.gh:hover{color:var(--accent)}
.tb{padding:0 16px 17px;border-top:1px solid var(--line2)}
.tb h4{font-family:var(--mono);font-size:9.5px;letter-spacing:.11em;text-transform:uppercase;
 color:var(--faint);margin:14px 0 6px;font-weight:600}
.tb p{margin:0;color:var(--muted);font-size:14px;max-width:78ch}
.tb ul{margin:0;padding-left:18px;color:var(--muted);font-size:14px;max-width:78ch}
.tb li{margin:3px 0}
.ev{border-left:2px solid var(--accent);padding-left:12px}
.empty{padding:32px;text-align:center;color:var(--faint);background:var(--card);
 border:1px dashed var(--line);border-radius:11px}
.foot{margin-top:50px;padding-top:20px;border-top:1px solid var(--line);color:var(--faint);
 font-size:12.5px;max-width:78ch}
:where(a,button,summary,input):focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
@media(max-width:900px){.board{grid-template-columns:1fr}
 .mh,.mr{grid-template-columns:1fr 104px 78px}.mh .n,.mr .n{display:none}}
@media(max-width:620px){.wrap{padding:0 14px 60px}
 .tk>summary{grid-template-columns:48px 46px 1fr;gap:10px;padding:11px 13px}.gh{display:none}
 .mh,.mr{grid-template-columns:1fr 92px;gap:10px;padding:10px 13px}
 .mh .vh{display:none}.mr .vd{grid-column:1/-1;justify-self:start;margin-top:2px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body>
__SWITCHER__
<div class="wrap">
<div class="head">
  <div class="eyebrow">River Monitor · engineering</div>
  <h1>QC &amp; UX audit, then 38 sprints</h1>
  <p class="method" id="method"></p>
  <div class="tally" id="tally"></div>
</div>

<section>
  <h2>What the audit found <i id="fcount"></i></h2>
  <p class="lede">Only measurements — each row is a number that can be reproduced, the threshold it
  is judged against, and the consequence if it stays.</p>
  <div class="meas" id="meas"></div>
</section>

<section>
  <h2>The board <i>3 lanes · live state lives on GitHub</i></h2>
  <p class="lede">Lane placement is the plan; whether a ticket is <em>done</em> is answered by its
  GitHub issue, not by this page. Click a card to open the ticket below.</p>
  <div class="board" id="board"></div>
</section>

<section>
  <h2>Sprint roadmap <i>S1 → S38</i></h2>
  <p class="lede">One ticket per sprint, ordered by consequence: what puts you on the wrong water
  before what makes the codebase nicer. Every ticket carries the measurement that justifies it.</p>
  <div class="ctl">
    <div class="cg" id="fe"><span class="lb">Epic</span></div>
    <div class="cg" id="fp"><span class="lb">Priority</span></div>
    <input id="q" type="search" placeholder="Search tickets, files, evidence…" aria-label="Search tickets">
  </div>
  <div class="tks" id="list"></div>
</section>

<p class="foot" id="foot"></p>
</div>
<script>
const D=__DATA__;
const T=D.tickets, esc=s=>String(s).replace(/&(?![a-z]+;|#)/g,'&amp;').replace(/</g,'&lt;');
document.getElementById('method').innerHTML=D.method;
document.getElementById('fcount').textContent=
  '14 pages · '+D.counts.fail+' critical · '+D.counts.warn+' serious · '+D.counts.ok+' pass';
document.getElementById('tally').innerHTML=
  '<span class="crit">'+D.counts.fail+' critical</span>'
 +'<span class="ser">'+D.counts.warn+' serious</span>'
 +'<span class="pass">'+D.counts.ok+' pass</span>'
 +'<a href="'+D.issuesUrl+'" target="_blank" rel="noopener">'+D.counts.tickets+' tickets on GitHub →</a>'
 +'<a href="index.html">← River Monitor HQ</a>';
document.getElementById('foot').innerHTML=
  'Source of truth is <code>roadmap.json</code> in the repo; every ticket has a GitHub issue and the '
 +'issue decides whether it is done. Effort is nominal — S under a session, M one session, L more than one. '
 +'Epics are labelled rather than colour-coded on purpose: seven categorical hues failed colour-vision '
 +'separation, so colour here is reserved for priority and always ships its label. Audited '+D.generated+'.';

document.getElementById('meas').innerHTML=
  '<div class="mh"><div>Measurement</div><div>Result</div><div class="n">Threshold &amp; consequence</div><div class="vh">Verdict</div></div>'
 +D.findings.map(f=>'<div class="mr"><b>'+esc(f[0])+'</b><div class="v">'+esc(f[1])+'</div>'
   +'<div class="n">'+f[2]+'</div><div class="vd '+f[3]+'">'
   +({fail:'Critical',warn:'Serious',ok:'Pass'})[f[3]]+'</div></div>').join('');

const LANES=[['now','Now'],['next','Next'],['later','Later']];
document.getElementById('board').innerHTML=LANES.map(([id,label])=>{
  const it=T.filter(t=>t.lane===id);
  return '<div class="lane'+(id==='now'?' now':'')+'"><div class="lh"><b>'+label+'</b><span>'+it.length+'</span></div>'
   +it.map(t=>'<a class="mini '+t.priority+'" href="#tk'+t.sprint+'" data-s="'+t.sprint+'">'
     +'<span class="k">S'+t.sprint+' · '+t.key+'</span><span class="t">'+esc(t.title)+'</span></a>').join('')
   +'</div>';}).join('');
document.getElementById('board').addEventListener('click',e=>{
  const a=e.target.closest('.mini'); if(!a)return;
  const d=document.getElementById('tk'+a.dataset.s); if(d){d.open=true;}});

const EP=[...new Set(T.map(t=>t.epic))];
let fE='all',fP='all',fQ='';
try{const s=JSON.parse(localStorage.getItem('rm.road')||'{}');fE=s.e||'all';fP=s.p||'all';}catch(e){}
const save=()=>{try{localStorage.setItem('rm.road',JSON.stringify({e:fE,p:fP}));}catch(e){}};

function chips(host,items,cur,on){
  host.querySelectorAll('.chip').forEach(c=>c.remove());
  items.forEach(([v,l])=>{const b=document.createElement('button');
    b.className='chip';b.type='button';b.textContent=l;b.setAttribute('aria-pressed',String(v===cur));
    b.onclick=()=>on(v);host.appendChild(b);});
}
function renderList(){
  const el=document.getElementById('list'),q=fQ.trim().toLowerCase();
  const rows=T.filter(t=>(fE==='all'||t.epic===fE)&&(fP==='all'||t.priority===fP)
    &&(!q||(t.title+' '+t.key+' '+t.epic+' '+t.evidence+' '+t.done.join(' ')).toLowerCase().includes(q)));
  if(!rows.length){el.innerHTML='<div class="empty">No tickets match that filter.</div>';return;}
  el.innerHTML=rows.map(t=>
    '<details class="tk" id="tk'+t.sprint+'"><summary>'
   +'<span class="sp">S'+t.sprint+'<em>SPRINT</em></span>'
   +'<span class="pr '+t.priority+'">'+t.priority+'</span>'
   +'<span class="tt"><span class="kk">'+esc(t.epic)+' · '+t.key+'</span>'+esc(t.title)+'</span>'
   +(t.issue_url?'<a class="gh" href="'+t.issue_url+'" target="_blank" rel="noopener">#'+t.issue+' ↗</a>':'<span class="gh">'+t.effort+'</span>')
   +'</summary><div class="tb">'
   +'<h4>Evidence</h4><div class="ev"><p>'+t.evidence+'</p></div>'
   +'<h4>Done means</h4><ul>'+t.done.map(a=>'<li>'+a+'</li>').join('')+'</ul>'
   +'</div></details>').join('');
}
function render(){
  chips(document.getElementById('fe'),
    [['all','All '+T.length],...EP.map(e=>[e,e+' '+T.filter(t=>t.epic===e).length])],
    fE,v=>{fE=v;save();render();});
  chips(document.getElementById('fp'),
    [['all','Any'],...['P0','P1','P2','P3'].map(p=>[p,p+' '+T.filter(t=>t.priority===p).length])],
    fP,v=>{fP=v;save();render();});
  renderList();
}
document.getElementById('q').addEventListener('input',e=>{fQ=e.target.value;renderList();});
render();
if(location.hash.startsWith('#tk')){const d=document.getElementById(location.hash.slice(1));if(d)d.open=true;}
</script>
</body></html>"""

html = riverlib.render(TEMPLATE, "roadmap").replace("__DATA__", json.dumps(DATA))
with open(os.path.join(OUT, "roadmap.html"), "w") as f:
    f.write(html)
print("wrote", os.path.join(OUT, "roadmap.html"),
      "| %d tickets, %d findings, issues #%s-#%s"
      % (len(R["tickets"]), len(R["findings"]),
         R["tickets"][0].get("issue"), R["tickets"][-1].get("issue")))
