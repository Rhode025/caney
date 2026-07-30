#!/usr/bin/env python3
"""
Atlas Generator — turn a river + a date range into a downloadable, LLM-written FIELD ATLAS PDF
in the same format as the Elk River Field Atlas.

Pipeline:  river config + live gauge + per-date weather/solunar  ->  a structured "brief"  ->
the `claude` CLI writes the conditions-specific prose (ground truth, day-by-day plan, reading
the water)  ->  styled multi-sheet HTML  ->  headless Chrome print-to-PDF.

LLM: shells out to the `claude` CLI (already authenticated — no API key to set up). If `claude`
isn't found it falls back to template prose so you still get a PDF.

CLI:
    python3 atlas_generator.py --river elk --start 2026-08-01 --end 2026-08-02 [--out atlas.pdf]

Also importable:  generate_atlas(river_id, start, end, out=None) -> pdf_path
"""
import json, os, sys, subprocess, datetime, urllib.request, urllib.parse, argparse, html, shutil
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import riverlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "out", "atlas"); os.makedirs(OUTDIR, exist_ok=True)
CT = ZoneInfo("America/Chicago"); UA = {"User-Agent": "atlas-generator/1.0"}
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def _get(u, h=None):
    with urllib.request.urlopen(urllib.request.Request(u, headers={**UA, **(h or {})}), timeout=60) as r:
        return json.load(r)

# ── per-river atlas config (facts for the LLM + the structural sheets) ───────
ATLAS = riverlib.RIVER_CONFIG   # single source of truth (declarative per-river facts)

# ── flow ─────────────────────────────────────────────────────────────────────
def fetch_flow(cfg):
    g = cfg["gauge"]
    try:
        if g["type"] == "usgs":
            d = _get("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=%s&period=P2D&parameterCd=00060" % g["site"])
            vals = d["value"]["timeSeries"][0]["values"][0]["value"]
            pts = [(datetime.datetime.fromisoformat(p["dateTime"]), float(p["value"])) for p in vals if p["value"] not in ("", "-999999")]
            unit = "cfs"
        else:  # nwps
            sf = _get("https://api.water.noaa.gov/nwps/v1/gauges/%s/stageflow" % g["lid"])
            pts = [(datetime.datetime.fromisoformat(p["validTime"].replace("Z", "+00:00")), p["secondary"]) for p in sf.get("observed", {}).get("data", [])]
            unit = "kcfs"
        pts.sort()
        cur = pts[-1][1]
        ref = next((v for t, v in reversed(pts) if (pts[-1][0] - t).total_seconds() >= 6 * 3600), pts[0][1])
        dv = cur - ref; thr = max(0.03 * abs(cur), (30 if unit == "cfs" else 0.15))
        trend = "rising" if dv > thr else "falling" if dv < -thr else "steady"
        return {"cur": round(cur, 1), "unit": unit, "trend": trend}
    except Exception as e:
        print("flow warn:", e); return None

# ── weather + solunar per date ───────────────────────────────────────────────
def fetch_days(cfg, dates):
    lat, lon = cfg["lat"], cfg["lon"]; out = []
    wx = None
    try:
        s, e = dates[0].isoformat(), dates[-1].isoformat()
        wx = _get("https://api.open-meteo.com/v1/forecast?latitude=%.3f&longitude=%.3f"
                  "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,cloud_cover_mean,wind_speed_10m_max,sunrise,sunset"
                  "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%%2FChicago&start_date=%s&end_date=%s" % (lat, lon, s, e))
    except Exception as ex:
        print("wx warn:", ex)
    D = (wx or {}).get("daily", {})
    tidx = {t: i for i, t in enumerate(D.get("time", []))}
    for d in dates:
        ds = d.isoformat(); i = tidx.get(ds)
        row = {"date": d.strftime("%a %b %-d")}
        if i is not None:
            row.update({"hi": round(D["temperature_2m_max"][i]), "lo": round(D["temperature_2m_min"][i]),
                        "pop": D["precipitation_probability_max"][i], "cloud": round(D["cloud_cover_mean"][i]),
                        "wind": round(D["wind_speed_10m_max"][i]),
                        "sunrise": D["sunrise"][i][11:16], "sunset": D["sunset"][i][11:16]})
            s = riverlib.solunar(d, row["sunrise"], row["sunset"], CT)
            if s: row["moon"] = s["moon"]; row["feed"] = s["rating"]; row["major"] = s["major"]
        out.append(row)
    return out

# ── LLM (claude CLI) ─────────────────────────────────────────────────────────
def llm_atlas(cfg, flow, days, start, end):
    have = shutil.which("claude")
    brief = {
        "river": cfg["name"], "species": cfg["species"], "model": cfg["model"],
        "dates": "%s to %s" % (start.strftime("%b %-d"), end.strftime("%b %-d, %Y")),
        "current_flow": flow, "flow_bands": cfg["bands"], "trend_rule": cfg["trend_rule"],
        "launch": cfg["launch"], "zones": cfg["zones"], "hazards": cfg["hazards"], "days": days,
    }
    prompt = (
        "You are writing a terse, authoritative fly-fishing FIELD ATLAS for one angler, in the voice of a "
        "20-year guide. Plain, confident, specific. No hype, no hedging filler. It is a PLANNING document.\n\n"
        "Here is the brief (real data):\n" + json.dumps(brief, indent=1) + "\n\n"
        "Return ONLY a compact JSON object (no markdown fence, no preamble) with EXACTLY these keys:\n"
        '  "ground_truth": a 3-4 sentence paragraph on what this water actually is for these dates and this flow, and how the fish are behaving.\n'
        '  "prime_window": 1-2 sentences on when to fish and when to quit, given the season and the daily light.\n'
        '  "days": an array, one object per date, each {"date": <the date string>, "read": a 2-3 sentence plan for THAT day using its weather, moon/feed and the flow trend, "fly": one concrete fly + how to fish it}.\n'
        '  "reading_water": an array of 4-6 short strings, the highest-value lies/targets to fish in priority order.\n'
        '  "go_no_go": 1-2 sentences — the honest call on whether these are good dates and what would change it.\n'
        "Ground every day in its actual forecast numbers. If flow is unknown, say so and plan around structure. Be concrete about location types for THIS river."
    )
    if have:
        # Run the claude CLI as a pure text endpoint: JSON envelope, no tools, strict system prompt,
        # and a clean cwd OUTSIDE the project so it doesn't load CLAUDE.md/project context and start
        # behaving like an agent (that was the bug — it added tool-approval commentary).
        cwd = "/tmp/atlas_llm_cwd"; os.makedirs(cwd, exist_ok=True)
        try:
            r = subprocess.run([have, "-p", prompt, "--output-format", "json",
                                "--disallowed-tools", "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task",
                                "--append-system-prompt",
                                "You are a text-generation endpoint. Output only the exact JSON object requested — no tools, no commentary, no preamble."],
                               capture_output=True, text=True, timeout=240, cwd=cwd)
            env = json.loads(r.stdout)
            res = env.get("result", "")
            data = json.loads(res[res.find("{"):res.rfind("}") + 1])
            if data.get("ground_truth") and data.get("days"):
                return data, True
            print("llm warn: incomplete JSON, using template")
        except Exception as e:
            print("llm warn (falling back to template):", e)
    # template fallback
    return {
        "ground_truth": "%s — %s. This atlas plans %s. %s" % (cfg["name"], cfg["species"].lower(), brief["dates"], cfg["trend_rule"]),
        "prime_window": "Fish the first two to three hours hard around first light; these are conditions animals and the bite falls off as the sun climbs.",
        "days": [{"date": d["date"], "read": "Hi %s° / Lo %s°, %s%% rain, moon %s. Be on the water at first light." % (d.get("hi","–"), d.get("lo","–"), d.get("pop","–"), d.get("moon","–")), "fly": cfg["flies"][0][0]} for d in days],
        "reading_water": [f[0] + " — " + f[1] for f in cfg["flies"][:5]],
        "go_no_go": "A planning estimate. Verify flow, ramp status and regulations before you launch.",
    }, False

# ── render styled multi-sheet atlas HTML ─────────────────────────────────────
def esc(s): return html.escape(str(s), quote=True)

def render_html(cfg, flow, days, L, start, end, llm_used):
    fu = flow["unit"] if flow else ""
    flow_now = ("%s %s · %s" % (flow["cur"], fu, flow["trend"])) if flow else "gauge unavailable"
    compiled = datetime.datetime.now(CT).strftime("%B %-d, %Y")
    span = "%s – %s" % (start.strftime("%b %-d"), end.strftime("%b %-d, %Y"))
    sheets = []
    # cover
    sheets.append("""<div class="sheet cover"><div class="topline"><span>FIELD ATLAS · GENERATED EDITION</span><span>%s</span></div>
      <div class="covermid"><div class="eyebrow">%s</div><h1>%s</h1><div class="sub">%s</div>
      <p class="lede">A conditions-specific operating guide for %s, %s. Compiled %s.</p></div>
      <div class="coverfoot"><div><span>DATES</span><b>%s</b></div><div><span>VESSEL</span><b>%s</b></div>
      <div><span>FLOW NOW</span><b>%s</b></div><div><span>STATUS</span><b>Planning · verify before launch</b></div></div></div>""" % (
        esc(compiled.upper()), esc(cfg["species"].upper()), esc(cfg["name"]), esc(cfg["sub"]),
        esc(cfg["species"].lower()), esc(span), esc(compiled), esc(span), esc(cfg.get("vessel","—")), esc(flow_now)))
    # ground truth
    gt = "".join("<p>%s</p>" % esc(p) for p in [L["ground_truth"]])
    zrows = "".join('<tr><td class="zc">%s</td><td><b>%s</b><br><span>%s</span></td></tr>' % (esc(z[0]), esc(z[1]), esc(z[2])) for z in cfg["zones"])
    zblock = ('<div class="subh">Zones</div><table class="z">%s</table>' % zrows) if zrows else ""
    sheets.append(sheet("01", "GROUND TRUTH", "what this water is", gt + zblock, cfg))
    # the launch + access
    arows = "".join('<tr><td><b>%s</b></td><td>%s</td></tr>' % (esc(a[0]), esc(a[1])) for a in cfg["access"])
    launch = '<div class="callout"><b>Primary launch — %s.</b> %s</div>' % (esc(cfg["launch"]["name"]), esc(cfg["launch"]["desc"]))
    sheets.append(sheet("02", "THE LAUNCH & ACCESS", "where to put the boat in", launch + '<div class="subh">Ramps</div><table class="a">%s</table>' % arows, cfg))
    # flow doctrine
    brows = "".join('<tr><td><b>%s</b></td><td class="cfs">%s</td><td>%s</td></tr>' % (esc(b[0]), esc(b[1]), esc(b[2])) for b in cfg["bands"])
    doctrine = ('<div class="callout"><b>Now: %s.</b> %s</div>' % (esc(flow_now), esc(cfg["gauge"]["label"])) +
                '<table class="b"><tr><th>Band</th><th>Reading</th><th>What the fish do</th></tr>%s</table>' % brows +
                '<div class="rule"><b>Trend rule.</b> %s</div>' % esc(cfg["trend_rule"]))
    sheets.append(sheet("03", "FLOW DOCTRINE", "which number governs the day", doctrine, cfg))
    # prime window + reading the water
    lies = "".join("<li>%s</li>" % esc(x) for x in L.get("reading_water", []))
    rw = '<div class="callout">%s</div><div class="subh">Highest-value water, in order</div><ol class="lies">%s</ol>' % (esc(L.get("prime_window","")), lies)
    sheets.append(sheet("04", "READING THE WATER", "when to fish, what to fish first", rw, cfg))
    # day-by-day (may span multiple sheets — 3 days per sheet)
    dmap = {d["date"]: d for d in days}
    dayblocks = []
    for ld in L.get("days", []):
        wd = dmap.get(ld.get("date"), {})
        meta = " · ".join(x for x in [
            ("%s°/%s°" % (wd.get("hi"), wd.get("lo"))) if wd.get("hi") is not None else "",
            ("%s%% rain" % wd["pop"]) if wd.get("pop") is not None else "",
            ("%s mph" % wd["wind"]) if wd.get("wind") is not None else "",
            ("dawn %s" % wd["sunrise"]) if wd.get("sunrise") else "",
            ("moon %s · feed %s/5" % (wd.get("moon","–"), wd.get("feed","–"))) if wd.get("moon") else "",
        ] if x)
        dayblocks.append('<div class="day"><div class="dh"><b>%s</b><span>%s</span></div><p>%s</p><div class="fly">🪶 %s</div></div>' % (
            esc(ld.get("date","")), esc(meta), esc(ld.get("read","")), esc(ld.get("fly",""))))
    for i in range(0, len(dayblocks), 3):
        chunk = "".join(dayblocks[i:i+3])
        sheets.append(sheet("05" if i == 0 else "05·%d" % (i//3+1), "THE SCHEDULE", "day by day, on the clock", chunk, cfg))
    # flies
    frows = "".join('<tr><td><b>%s</b></td><td>%s</td></tr>' % (esc(f[0]), esc(f[1])) for f in cfg["flies"])
    sheets.append(sheet("06", "FLY SELECTION", "what to tie on", '<table class="a">%s</table>' % frows, cfg))
    # hazards + rules + go/no-go
    hz = "".join("<li>%s</li>" % esc(x) for x in cfg["hazards"])
    haz = ('<div class="callout warn"><b>The honest call.</b> %s</div>' % esc(L.get("go_no_go","")) +
           '<div class="subh">Hazards</div><ul class="hz">%s</ul>' % hz +
           '<div class="rule"><b>Rules & licenses.</b> %s</div>' % esc(cfg["regs"]) +
           '<div class="pre">PRE-LAUNCH: Plug in · Lanyard on · PFDs on · Fuel confirmed · Float plan sent · Water aboard · Turn-around time agreed.</div>')
    sheets.append(sheet("07", "HAZARDS, RULES & THE CALL", "how not to lose a day", haz, cfg))

    src = "LLM-written (claude) + live data" if llm_used else "template + live data"
    return TEMPLATE.replace("__SHEETS__", "".join(sheets)).replace("__SRC__", esc(src)).replace("__RIVER__", esc(cfg["name"]))

def sheet(no, title, kicker, body, cfg):
    return ('<div class="sheet"><div class="sh"><span class="tag">SHEET %s</span><span class="ti">%s</span>'
            '<span class="ki">%s</span></div><div class="body">%s</div>'
            '<div class="foot"><span>%s · FIELD ATLAS</span><span>SCHEMATIC & PLANNING USE — NOT FOR NAVIGATION</span></div></div>') % (
        esc(no), esc(title), esc(kicker), body, esc(cfg["name"].upper()))

TEMPLATE = r"""<!doctype html><html><head><meta charset=utf-8><style>
@page{size:letter;margin:0}
*{box-sizing:border-box}
body{margin:0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;color:#16202b;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.sheet{width:8.5in;height:11in;padding:.72in .8in .7in;position:relative;page-break-after:always;overflow:hidden}
.eyebrow{font-size:10px;letter-spacing:.3em;text-transform:uppercase;color:#9aa7b4;font-weight:700}
.topline{display:flex;justify-content:space-between;font-size:8.5px;letter-spacing:.22em;color:#9aa7b4;text-transform:uppercase;font-weight:600}
.cover{display:flex;flex-direction:column}.covermid{margin-top:1.7in;flex:1}
h1{font-size:60px;font-weight:800;letter-spacing:-1.5px;margin:.06in 0 0;line-height:.98}
.sub{font-size:13px;letter-spacing:.2em;text-transform:uppercase;color:#66788a;margin-top:.14in}
.lede{max-width:5in;color:#66788a;font-size:12.5px;line-height:1.7;margin-top:.34in}
.coverfoot{display:flex;gap:.34in;border-top:1px solid #e6ecf2;padding-top:12px}
.coverfoot span{display:block;font-size:8px;letter-spacing:.16em;text-transform:uppercase;color:#9aa7b4;font-weight:700}
.coverfoot b{font-size:11.5px;font-weight:600}
.sh{border-bottom:1.5px solid #16202b;padding-bottom:9px;display:flex;align-items:baseline;gap:12px}
.tag{background:#16202b;color:#fff;padding:3px 9px;font-size:10px;letter-spacing:.12em;font-weight:800}
.ti{font-size:19px;font-weight:800;letter-spacing:-.3px}
.ki{margin-left:auto;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#9aa7b4;font-weight:600}
.body{margin-top:.28in;font-size:12px;line-height:1.68;color:#33414f}
.body p{margin:0 0 .16in}
.subh{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#b5651d;font-weight:700;margin:.24in 0 .1in}
.callout{background:#f7f3ee;border-left:3px solid #b5651d;padding:11px 13px;font-size:12px;line-height:1.6;margin-bottom:.16in}
.callout.warn{background:#fdf3f2;border-left-color:#c0453a}.callout b{color:#16202b}
.rule{border-top:1px solid #e6ecf2;margin-top:.2in;padding-top:11px;font-size:11.5px;color:#66788a;line-height:1.6}.rule b{color:#16202b}
table{width:100%;border-collapse:collapse;font-size:11.5px}
table th{text-align:left;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:#9aa7b4;border-bottom:1px solid #e6ecf2;padding:6px 8px 6px 0}
table td{padding:8px 8px 8px 0;border-bottom:1px solid #eef2f6;vertical-align:top}
table td span{color:#8a97a4;font-size:10.5px}
td.zc{width:26px;font-weight:800;color:#b5651d}.cfs{color:#66788a;white-space:nowrap;width:1.1in}
.lies{margin:.06in 0 0;padding-left:1.1em}.lies li{margin-bottom:7px}
.day{border-top:1px solid #eef2f6;padding:12px 0}.day:first-child{border-top:0}
.dh{display:flex;align-items:baseline;gap:10px}.dh b{font-size:14px}.dh span{font-size:10.5px;color:#8a97a4}
.day p{margin:6px 0}.fly{font-size:11px;color:#b5651d;font-weight:600}
.hz{margin:.06in 0 0;padding-left:1.1em}.hz li{margin-bottom:6px}
.pre{margin-top:.2in;background:#16202b;color:#fff;padding:9px 12px;font-size:10px;letter-spacing:.04em;border-radius:4px}
.foot{position:absolute;bottom:.5in;left:.8in;right:.8in;border-top:1px solid #e6ecf2;padding-top:8px;font-size:8px;letter-spacing:.1em;color:#aab4be;text-transform:uppercase;display:flex;justify-content:space-between}
</style></head><body>__SHEETS__</body></html>"""

def to_pdf(html_str, out):
    tmp = os.path.join(OUTDIR, "_atlas_tmp.html"); open(tmp, "w").write(html_str)
    if not os.path.exists(CHROME):
        raise RuntimeError("Chrome not found for PDF rendering: " + CHROME)
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    "--print-to-pdf=" + out, "file://" + tmp], capture_output=True, timeout=120)
    return out

def generate_atlas(river_id, start, end, out=None):
    cfg = ATLAS.get(river_id)
    if not cfg: raise ValueError("unknown river '%s' (have: %s)" % (river_id, ", ".join(ATLAS)))
    if isinstance(start, str): start = datetime.date.fromisoformat(start)
    if isinstance(end, str): end = datetime.date.fromisoformat(end)
    if end < start: start, end = end, start
    dates = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)][:8]
    flow = fetch_flow(cfg)
    days = fetch_days(cfg, dates)
    L, used = llm_atlas(cfg, flow, days, start, end)
    doc = render_html(cfg, flow, days, L, start, end, used)
    if not out:
        out = os.path.join(OUTDIR, "atlas_%s_%s_%s.pdf" % (river_id, start.isoformat(), end.isoformat()))
    to_pdf(doc, out)
    return out, used

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate a field-atlas PDF for a river + date range.")
    ap.add_argument("--river", required=True, choices=list(ATLAS))
    ap.add_argument("--start", required=True); ap.add_argument("--end", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    path, used = generate_atlas(a.river, a.start, a.end, a.out)
    print("wrote %s  (%s)" % (path, "LLM-written" if used else "template fallback"))
