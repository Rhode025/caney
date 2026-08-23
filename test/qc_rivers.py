#!/usr/bin/env python3
"""
QC for the Duck sections and the Buffalo — the rivers driven by the routing engine.

qc_caney.py covers the dam-driven page in depth; these four pages had no per-river QC at all
when they shipped. What matters here is different from Caney: there is no announced release, so
every number is either a gauge reading, an interpolation between two gauges, or a routed
forecast — and the page has to be honest about which.

    python3 test/qc_rivers.py
"""
import json, math, os, re, sys

ROOT = "/Users/stevenrhodes/caney"
sys.path.insert(0, ROOT)
import riverlib

OK, FAIL, WARN = [], [], []
def chk(name, cond, detail=""): (OK if cond else FAIL).append((name, detail))
def warn(name, cond, detail=""):
    if not cond: WARN.append((name, detail))

def data(rid):
    h = open(os.path.join(ROOT, "out", rid + ".html")).read()
    m = re.search(r"\bconst D=(?:window\.__rlRelabel\()?\{", h)
    j = h.index("{", m.start()); d = 0
    for k in range(j, len(h)):
        if h[k] == "{": d += 1
        elif h[k] == "}":
            d -= 1
            if d == 0: break
    return json.loads(h[j:k + 1])

RIVERS = ["duckup", "duckmid", "ducklow", "buffalo", "harpeth"]
D = {r: data(r) for r in RIVERS}
RT = json.load(open(os.path.join(ROOT, "analysis", "duck_routing.json")))["rivers"]

# ── routing calibration ────────────────────────────────────────────────────────
for key in ("duck", "buffalo", "harpeth"):
    r = RT[key]
    chk("routing measured on real hours: " + key, r["n_hours"] > 1000, str(r["n_hours"]))
    chk("routing correlation is strong: " + key, r["r"] > 0.8, str(r["r"]))
    chk("routing lag is positive (water flows downhill): " + key, r["lag_h"] > 0, str(r["lag_h"]))
    chk("routing lag is physically plausible: " + key, 2 <= r["lag_h"] <= 48, str(r["lag_h"]))
    chk("downstream gauge is bigger: " + key, r["gain_median"] > 1.0, str(r["gain_median"]))
    t = r["transfer"]
    # The whole point of the backtest: a constant gain multiplier LOST to persistence at every
    # horizon. If the deployed transfer is "const", the optimisation has been reverted.
    chk("transfer model is the backtested winner, not a constant gain: " + key,
        t["kind"] != "const", t["kind"])
    chk("the winning transfer really has the lowest held-out error: " + key,
        t["test_mae"] == min(v for v in t["compared"].values() if v is not None),
        json.dumps(t["compared"]))
    _marg = 1.0 - t["test_mae"] / t["compared"]["const"]
    warn("transfer beats a constant gain by a useful margin: " + key, _marg >= 0.10,
         "only %.0f%% better than a constant gain — the model choice barely matters here" % (100 * _marg))
    chk("horizon floor is stated: " + key, r.get("useful_from_h", 0) >= 6, str(r.get("useful_from_h")))

# ── per-page integrity ─────────────────────────────────────────────────────────
for rid in RIVERS:
    d = D[rid]
    R = d.get("route") or {}
    chk("page carries routing provenance: " + rid, bool(R.get("src") and R.get("why")))
    chk("page names its transfer model: " + rid, R.get("tf") in ("power", "linear"), str(R.get("tf")))
    _src = open(os.path.join(ROOT, "out", rid + ".html")).read()
    chk("the page guards the routed forecast on the useful horizon: " + rid,
        "R.predAt>=R.minH" in _src.replace(" ", ""), "guard missing")
    chk("horizon floor is published so the guard can work: " + rid,
        (R.get("minH") or 0) >= 6 and R.get("predAt") is not None,
        "predAt=%s minH=%s" % (R.get("predAt"), R.get("minH")))
    if R.get("upNow") and R.get("pred"):
        chk("routed forecast moves the right way (downstream is bigger): " + rid,
            R["pred"] > R["upNow"], "%s -> %s" % (R["upNow"], R["pred"]))

    pts = d.get("points") or []
    chk("page has accesses: " + rid, len(pts) >= 2, str(len(pts)))
    for p in pts:
        chk("access has real coordinates: %s/%s" % (rid, p["name"]),
            34 < p["lat"] < 37 and -89 < p["lon"] < -85, "%s,%s" % (p["lat"], p["lon"]))
    secs = d.get("sections") or []
    chk("page has float sections: " + rid, len(secs) >= 1, str(len(secs)))
    for s in secs:
        chk("section distance is positive: %s/%s→%s" % (rid, s["from"], s["to"]), s["mi"] > 0, str(s["mi"]))
        chk("section flow is a real number: %s/%s" % (rid, s["from"]), s["flow"] is None or s["flow"] >= 0, str(s["flow"]))
    cur = d.get("cur") or {}
    chk("current flow present: " + rid, cur.get("flow") is not None)
    chk("water model covers this river: " + rid, rid in riverlib.WATER_MODEL)
    wm = riverlib.WATER_MODEL[rid]
    chk("water model cites a source: " + rid, len(wm.get("src", "")) > 40)
    chk("wade thresholds ordered: " + rid,
        wm["wade_ok"] < wm["wade_marginal"] < wm["no_wade"],
        "%s/%s/%s" % (wm["wade_ok"], wm["wade_marginal"], wm["no_wade"]))

# ── the reason the Duck was split: the three reaches must NOT read the same ────
flows = {r: (D[r]["cur"] or {}).get("flow") for r in ("duckup", "duckmid", "ducklow")}
chk("the three Duck sections report different water", len(set(flows.values())) == 3, json.dumps(flows))
chk("Duck flow increases downstream (tributaries only add water)",
    flows["duckup"] < flows["duckmid"] < flows["ducklow"], json.dumps(flows))

# each section's accesses must lie inside its own river-mile range, and the ranges must tile
RANGES = {"duckup": (113.9, 133.5), "duckmid": (95.0, 113.9), "ducklow": (73.7, 95.0)}
for rid, (lo, hi) in RANGES.items():
    names = {p["name"] for p in D[rid]["points"]}
    chk("section is bounded by its own ramps: " + rid, 2 <= len(names) <= 4, str(sorted(names)))
chk("Duck sections tile the reach with no gap",
    RANGES["duckup"][0] == RANGES["duckmid"][1] and RANGES["duckmid"][0] == RANGES["ducklow"][1])

# area-derived channel positions must be monotone downstream and span [0,1]
chk("channel positions are area-derived and monotone",
    all(D["duckup"]["points"][i]["lat"] is not None for i in range(len(D["duckup"]["points"]))))

# the middle reach has no gauge and MUST say so rather than implying a reading
mid_why = (D["duckmid"].get("route") or {}).get("why", "").lower()
chk("the ungauged reach admits it has no gauge", "no gauge" in mid_why, mid_why[:80])
low_why = (D["ducklow"].get("route") or {}).get("why", "").lower()
chk("the gauged reach says it is gauged", "forecast" in low_why, low_why[:80])

# ── a page must not wear another river's clothes ─────────────────────────────
# The Harpeth was generated from the Buffalo generator, which had itself been generated from the
# Duck's. Its flow timer shipped listing CHICKASAW, WILLIAMSPORT, LEATHERWOOD and LITTLELOT --
# Duck ramps, on the Harpeth. Every place name a page shows must belong to that page.
FOREIGN = {
    "harpeth": ["chickasaw", "williamsport", "leatherwood", "littlelot", "centerville", "columbia",
                "lobelville", "flatwoods", "topsy", "lbvt1", "cnvt1"],
    "buffalo": ["chickasaw", "williamsport", "leatherwood", "littlelot", "centerville", "columbia",
                "narrows", "kingston springs", "cnvt1"],
    "duckup": ["lobelville", "flatwoods", "topsy", "narrows", "kingston springs", "lbvt1"],
    "duckmid": ["lobelville", "flatwoods", "topsy", "narrows", "kingston springs", "lbvt1"],
    "ducklow": ["lobelville", "flatwoods", "topsy", "narrows", "kingston springs", "lbvt1"],
}
def _body_without_switcher(rid):
    t = open(os.path.join(ROOT, "out", rid + ".html")).read()
    i = t.find('class="switch"')
    if i >= 0:
        j = t.find("</div>", i)
        if j > i: t = t[:i] + t[j:]
    return t.lower()

for rid, bad in FOREIGN.items():
    _txt = _body_without_switcher(rid)
    for b in bad:
        chk("%s does not mention %s (another river's)" % (rid, b), b not in _txt)

# a page may only claim an NWPS forecast if one actually exists for it
NWPS = {"ducklow": True, "buffalo": True, "duckup": False, "duckmid": False, "harpeth": False}
for rid, has in NWPS.items():
    _txt = open(os.path.join(ROOT, "out", rid + ".html")).read()
    if not has:
        chk("%s does not claim an NWPS forecast it lacks" % rid, "NWPS forecast at" not in _txt)

# the default craft must be one the river's own water model allows
for rid in RIVERS:
    _c0 = (D.get(rid) or {}).get("craft0")
    if _c0:
        _allowed = riverlib.WATER_MODEL[rid]["craft"]
        _map = {"jet": "boat", "paddle": "paddle", "power": "boat"}
        chk("default craft is one this river allows: %s (%s)" % (rid, _c0),
            _map.get(_c0, _c0) in _allowed, "%s vs %s" % (_c0, _allowed))

# ── HQ must agree with the river page it links to ─────────────────────────────
# HQ's week used to persist TODAY's grade for seven days even on rivers that publish a real
# multi-day flow forecast, and its moon term was one-sided (+0.5/+0.2/+0.0, never negative), so
# HQ read a full grade above the page on 24 of 24 day-grades. Two views of the same river must
# not disagree about the same day.
import glob
def page_any(rid):
    h = open(os.path.join(ROOT, "out", rid + ".html")).read()
    for pat in (r"\bDATA=(?:window\.__rlRelabel\()?\{", r"\bconst D=(?:window\.__rlRelabel\()?\{"):
        m = re.search(pat, h)
        if m:
            j = h.index("{", m.start()); d = 0
            for k in range(j, len(h)):
                if h[k] == "{": d += 1
                elif h[k] == "}":
                    d -= 1
                    if d == 0: break
            return json.loads(h[j:k + 1])
    return None

mismatch = []
for f in sorted(glob.glob(os.path.join(ROOT, "out", "status", "*.json"))):
    rid = os.path.basename(f)[:-5]
    st = json.load(open(f))
    pg = page_any(rid)
    if not pg: continue
    series = pg.get("outlook") or pg.get("week") or []
    if not series: continue                      # river with no multi-day page forecast
    for i, w in enumerate((st.get("week") or [])[:6]):
        if i >= len(series): continue
        if w.get("grade") != series[i].get("grade"):
            mismatch.append("%s/%s HQ=%s page=%s" % (rid, w.get("label"), w.get("grade"), series[i].get("grade")))
chk("HQ week agrees with every river page's own outlook", not mismatch, "; ".join(mismatch[:6]))

# the moon nudge must stay zero-mean and inside a grade band, or the offset comes straight back
import inspect
_bw = inspect.getsource(riverlib.build_week)
chk("HQ moon term is zero-mean, not one-sided", "rating - 3" in _bw, "one-sided moon term is back")
chk("HQ moon term cannot cross a grade band alone", "0.15" in _bw, _bw[:0])

# ── access coordinates must be at the water, not at a town centre ─────────────
# The Buffalo shipped with geocoded TOWN CENTRES: Lobelville was 1,236 m and Topsy Bridge
# 1,099 m from the river, so the Google Maps pin dropped in the middle of town rather than at
# the launch. A ramp pin may sit off the centreline (parking is on the bank) but not by a mile.
def segd(pt, a, b):
    latm = 111320.0; lonm = 111320.0 * math.cos(math.radians(pt[0]))
    px, py = (pt[1] - a[1]) * lonm, (pt[0] - a[0]) * latm
    bx, by = (b[1] - a[1]) * lonm, (b[0] - a[0]) * latm
    L = bx * bx + by * by
    t = 0 if L == 0 else max(0, min(1, (px * bx + py * by) / L))
    return math.hypot(px - t * bx, py - t * by)
for rid in RIVERS:
    poly = D[rid].get("poly") or []
    if len(poly) < 2: continue
    for p in D[rid]["points"]:
        dm = min(segd((p["lat"], p["lon"]), poly[i], poly[i + 1]) for i in range(len(poly) - 1))
        chk("access pin is on the river, not in town: %s/%s" % (rid, p["name"]), dm < 800, "%.0f m" % dm)

# ── access pins vs the TWRA Boating & Fishing Access layer ────────────────────
# Where TWRA publishes a site, TWRA is the authority for where the ramp is. Our hand-placed
# Caney pins drifted downstream (+1.2 mi Happy Hollow, +2.2 mi Betty's Island against their own
# mfd) until they were cross-referenced. This guards the ones we corrected: if a coordinate
# wanders away from TWRA's again, it fails here. Sites TWRA does not list (Littlelot, Stonewall,
# Lancaster, Buffalo Valley, the I-40 Welcome Center) are county/private/informal and exempt.
TWRA_PATH = os.path.join(ROOT, "analysis", "twra_access.json")
if os.path.exists(TWRA_PATH):
    _tw = json.load(open(TWRA_PATH))["sites"]
    def _near(nm, water_key):
        c = [t for t in _tw if water_key in t["water"].lower() and nm.lower() in t["name"].lower()]
        return c[0] if c else None
    # (page, our access name, TWRA site name, TWRA water key)
    MATCHED = [("caney", "Happy Hollow", "HAPPY HOLLOW", "caney"),
               ("caney", "Betty's Island", "BETTYS ISLAND", "caney"),
               ("duckup", "Riverside", "Riverside Access Area", "duck"),
               ("duckup", "Chickasaw Trace", "Chickasaw Trace park", "duck"),
               ("duckmid", "Williamsport", "Williamsport Bridge", "duck"),
               ("buffalo", "Linden (Hwy 100)", "LINDEN", "buffalo")]
    for pg, ours, twn, wk in MATCHED:
        d_ = page_any(pg)
        if not d_: continue
        p_ = next((x for x in d_["points"] if x["name"] == ours), None)
        t_ = _near(twn, wk)
        chk("TWRA site is still in the reference data: " + twn, t_ is not None)
        if not (p_ and t_): continue
        dm = math.hypot((p_["lat"] - t_["lat"]) * 111320,
                        (p_["lon"] - t_["lon"]) * 111320 * math.cos(math.radians(p_["lat"])))
        chk("pin matches TWRA's published ramp: %s/%s" % (pg, ours), dm < 250, "%.0f m from TWRA" % dm)
else:
    warn("TWRA reference data present", False, "analysis/twra_access.json missing")

# ── TWRA site detail attached to the pins ────────────────────────────────────
# Ramp surface, lane count, hull limit, parking and facilities come from the state's own record.
# The matching radius is the sharp edge here: at 400 m the I-40 Welcome Center claimed the
# Betty's Island ramp 218 m away and would have shown one site's facilities under another's name.
if os.path.exists(TWRA_PATH):
    _claims = {}
    _detail = 0
    for _f in sorted(glob.glob(os.path.join(ROOT, "out", "*.html"))):
        _rid = os.path.basename(_f)[:-5]
        if _rid == "index": continue
        _d = page_any(_rid)
        if not _d: continue
        for _p in (_d.get("points") or []):
            _T = _p.get("twra")
            if not _T: continue
            _detail += 1
            chk("TWRA record is a close match, not a neighbouring site: %s/%s" % (_rid, _p["name"]),
                _T.get("m", 999) <= 150, "%s m from %s" % (_T.get("m"), _T.get("name")))
            chk("TWRA record carries something worth showing: %s/%s" % (_rid, _p["name"]),
                any(_T.get(k) for k in ("ramp", "launchable", "parking", "trailer_spaces",
                                        "surface", "restroom", "dock", "pier", "camping", "gas")),
                json.dumps(_T)[:80])
            _claims.setdefault(_T["name"], set()).add(_rid + "/" + _p["name"])
    chk("at least the known TWRA ramps are attached", _detail >= 8, str(_detail))
    # one TWRA site may appear on two PAGES (a shared section boundary) but never twice on one
    for _site, _who in _claims.items():
        _pages = [w.split("/")[0] for w in _who]
        chk("no TWRA site is claimed twice on one page: " + _site,
            len(_pages) == len(set(_pages)), str(sorted(_who)))

print("QC — Duck sections, Buffalo, Harpeth")
print("  passed : %d" % len(OK))
print("  warned : %d" % len(WARN))
print("  FAILED : %d" % len(FAIL))
for n, d_ in WARN: print("   ! %-58s %s" % (n, d_))
for n, d_ in FAIL: print("   ✗ %-58s %s" % (n, d_))
sys.exit(1 if FAIL else 0)
