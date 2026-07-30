#!/usr/bin/env python3
"""
Atlas Generator — web UI.  Run it, open the page, pick a river + dates, get a PDF.

    python3 atlas_server.py           # → http://127.0.0.1:8899

Pure standard library (no deps). Generation is synchronous (~30–60s while the LLM writes),
so the page shows a spinner and streams the finished PDF back as a download.
"""
import os, sys, json, traceback, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import atlas_generator as ag

def options():
    o = ""
    for rid, c in ag.ATLAS.items():
        o += '<option value="%s">%s — %s</option>' % (rid, c["name"], c["species"])
    return o

def form_html():
    today = datetime.date.today(); tom = today + datetime.timedelta(days=1)
    return """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Atlas Generator</title><style>
:root{--ink:#16202b;--muted:#66788a;--faint:#93a3b3;--line:#e6ecf2;--amber:#b5651d}
*{box-sizing:border-box}body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,sans-serif;
 background:radial-gradient(1000px 700px at 82% -6%,#f7efe4 0,transparent 60%),linear-gradient(180deg,#f6f2ec,#efe9e0);min-height:100vh}
.app{max-width:620px;margin:0 auto;padding:44px 22px 80px}
.eyebrow{font-size:12px;letter-spacing:.26em;text-transform:uppercase;color:var(--faint);font-weight:600}
h1{margin:6px 0 6px;font-size:34px;font-weight:800;letter-spacing:-.8px}
.cap{color:var(--muted);font-size:14.5px;line-height:1.6;max-width:34em}
.card{background:#fff;border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 26px rgba(20,50,80,.06);padding:22px;margin-top:24px}
label{display:block;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);font-weight:700;margin:14px 0 6px}
select,input{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:11px;font-size:15px;font-family:inherit;background:#fff;color:var(--ink)}
.row{display:flex;gap:14px}.row>div{flex:1}
button{margin-top:22px;width:100%;padding:14px;border:0;border-radius:12px;background:linear-gradient(135deg,#b5651d,#8a4e16);color:#fff;font-size:15px;font-weight:700;cursor:pointer}
button:disabled{opacity:.6;cursor:default}
.msg{margin-top:16px;font-size:13.5px;color:var(--muted);min-height:20px;line-height:1.5}
.msg.ok{color:#2a8a52}.msg.err{color:#b3392f}
.spin{display:inline-block;width:14px;height:14px;border:2px solid #d9c3a8;border-top-color:#b5651d;border-radius:50%;animation:sp .8s linear infinite;vertical-align:-2px;margin-right:7px}
@keyframes sp{to{transform:rotate(360deg)}}
.note{margin-top:20px;font-size:11.5px;color:var(--faint);line-height:1.6}
.rivers{margin-top:8px;font-size:12px;color:var(--faint)}.rivers a{color:#5a86a8}
</style></head><body><div class="app">
<div class="eyebrow">Field Atlas · Generator</div>
<h1>Atlas Generator</h1>
<div class="cap">Pick a river and the dates you're planning to fish. It pulls the live gauge, the day-by-day
weather &amp; moon, and has an LLM write you a downloadable field-atlas PDF — ground truth, flow doctrine,
a plan for each day, flies, and the honest call — in the same format as the Elk River atlas.</div>
<div class="card">
 <label>River</label><select id="river">__OPTS__</select>
 <div class="row"><div><label>Start date</label><input type="date" id="start" value="__TODAY__"></div>
 <div><label>End date</label><input type="date" id="end" value="__TOM__"></div></div>
 <button id="go" onclick="gen()">Generate atlas PDF</button>
 <div class="msg" id="msg"></div>
</div>
<div class="note">Runs the <code>claude</code> CLI locally to write the prose (no API key needed) and headless Chrome to render the PDF.
A planning document — verify ramps, flows &amp; regulations before you launch. Dates within the ~16-day weather forecast window get the richest per-day plans.</div>
<div class="rivers">Live pages: <a href="/../index.html">Caney</a> · <a href="/../duck.html">Duck</a> · <a href="/../cumberland.html">Cumberland</a> · <a href="/../elk.html">Elk</a></div>
<script>
const msg=document.getElementById('msg'),go=document.getElementById('go');
function say(t,c){msg.className='msg'+(c?' '+c:'');msg.innerHTML=t;}
async function gen(){
 const river=document.getElementById('river').value,start=document.getElementById('start').value,end=document.getElementById('end').value;
 if(!start||!end){say('Pick both dates.','err');return;}
 go.disabled=true;say('<span class="spin"></span>Generating — the LLM is writing your atlas and rendering the PDF (~30–60s)…');
 try{
  const r=await fetch('/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({river,start,end})});
  if(!r.ok){const e=await r.json().catch(()=>({error:'generation failed'}));say('⚠ '+(e.error||'failed'),'err');go.disabled=false;return;}
  const cd=r.headers.get('Content-Disposition')||'';const m=cd.match(/filename="([^"]+)"/);const name=m?m[1]:'atlas.pdf';
  const src=r.headers.get('X-Atlas-Source');
  const blob=await r.blob();const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();
  say('✓ Atlas generated ('+(src==='llm'?'LLM-written':'template fallback')+') — <a href="'+url+'" download="'+name+'">download</a> if it didn\'t start.','ok');
 }catch(e){say('⚠ '+e,'err');}
 go.disabled=false;
}
</script></div></body></html>""".replace("__OPTS__", options()).replace("__TODAY__", today.isoformat()).replace("__TOM__", tom.isoformat())

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, ctype, body, extra=None):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, "text/html; charset=utf-8", form_html().encode())
        else:
            self._send(404, "text/plain", b"not found")
    def do_POST(self):
        if self.path != "/generate":
            self._send(404, "text/plain", b"not found"); return
        try:
            n = int(self.headers.get("Content-Length", 0)); req = json.loads(self.rfile.read(n) or b"{}")
            print("generating: %s %s→%s" % (req.get("river"), req.get("start"), req.get("end")))
            path, used = ag.generate_atlas(req["river"], req["start"], req["end"])
            pdf = open(path, "rb").read(); fn = os.path.basename(path)
            self._send(200, "application/pdf", pdf, {
                "Content-Disposition": 'attachment; filename="%s"' % fn,
                "X-Atlas-Source": "llm" if used else "template"})
            print("  → sent %s (%s, %d KB)" % (fn, "llm" if used else "template", len(pdf)//1024))
        except Exception as e:
            traceback.print_exc()
            self._send(500, "application/json", json.dumps({"error": str(e)}).encode())

if __name__ == "__main__":
    port = int(os.environ.get("ATLAS_PORT", "8899"))
    print("Atlas Generator → http://127.0.0.1:%d  (Ctrl-C to stop)" % port)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
