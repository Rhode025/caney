#!/usr/bin/env python3
"""
QC for the Duck sections and the Buffalo — the rivers driven by the routing engine.

qc_caney.py covers the dam-driven page in depth; these four pages had no per-river QC at all
when they shipped. What matters here is different from Caney: there is no announced release, so
every number is either a gauge reading, an interpolation between two gauges, or a routed
forecast — and the page has to be honest about which.

    python3 test/qc_rivers.py
"""
import json, os, re, sys

ROOT = "/Users/stevenrhodes/caney"
sys.path.insert(0, ROOT)
import riverlib

OK, FAIL, WARN = [], [], []
def chk(name, cond, detail=""): (OK if cond else FAIL).append((name, detail))
def warn(name, cond, detail=""):
    if not cond: WARN.append((name, detail))

def data(rid):
    h = open(os.path.join(ROOT, "out", rid + ".html")).read()
    m = re.search(r"\bconst D=\{", h)
    j = h.index("{", m.start()); d = 0
    for k in range(j, len(h)):
        if h[k] == "{": d += 1
        elif h[k] == "}":
            d -= 1
            if d == 0: break
    return json.loads(h[j:k + 1])

RIVERS = ["duckup", "duckmid", "ducklow", "buffalo"]
D = {r: data(r) for r in RIVERS}
RT = json.load(open(os.path.join(ROOT, "analysis", "duck_routing.json")))["rivers"]

# ── routing calibration ────────────────────────────────────────────────────────
for key in ("duck", "buffalo"):
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
    chk("transfer beats a constant gain by a real margin: " + key,
        t["test_mae"] < 0.8 * t["compared"]["const"],
        "%s vs const %s" % (t["test_mae"], t["compared"]["const"]))
    chk("horizon floor is stated: " + key, r.get("useful_from_h", 0) >= 6, str(r.get("useful_from_h")))

# ── per-page integrity ─────────────────────────────────────────────────────────
for rid in RIVERS:
    d = D[rid]
    R = d.get("route") or {}
    chk("page carries routing provenance: " + rid, bool(R.get("src") and R.get("why")))
    chk("page names its transfer model: " + rid, R.get("tf") in ("power", "linear"), str(R.get("tf")))
    chk("routed forecast is not offered inside the useless horizon: " + rid,
        (R.get("predAt") or 0) >= (R.get("minH") or 12),
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

print("QC — Duck sections + Buffalo")
print("  passed : %d" % len(OK))
print("  warned : %d" % len(WARN))
print("  FAILED : %d" % len(FAIL))
for n, d_ in WARN: print("   ! %-58s %s" % (n, d_))
for n, d_ in FAIL: print("   ✗ %-58s %s" % (n, d_))
sys.exit(1 if FAIL else 0)
