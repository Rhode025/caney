#!/usr/bin/env python3
"""
Build a MEASURED depth + wadeability model per river from USGS field measurements.

USGS crews physically measure each gauging: channel width, cross-sectional area, and
HOW they made the measurement (wading vs from a boat/bridge/cableway). That gives two
things no amount of forum reading can:

  mean depth = channel_area / channel_width      -> absolute depth at a known discharge
  measurement_type == "Wading"                   -> a professional stood in it at that flow

So the wade threshold is not inferred from anecdote; it is the flow above which USGS
stops wading and starts working from a boat. Depth is not inferred from a rise curve
plus a guessed reference; it is area over width.

    python3 analysis/channel_geom.py
"""
import json, urllib.request, math, os, statistics, sys

API = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/channel-measurements/items"
UA = {"User-Agent": "caney-geom/1.0"}
SITES = {
    "caney":      ("03424860", "Caney Fork at Stonewall"),
    "cumberland": ("03414100", "Cumberland at Burkesville"),
    "cumbnash":   ("03431500", "Cumberland at Nashville"),
    "stones":     ("03430200", "Stones River at US-70"),
    "elktn":      ("03582000", "Elk River above Fayetteville"),
    "elk":        ("03584600", "Elk River at Prospect"),
    "duck":       ("03599500", "Duck River (USGS)"),
}

def fetch(site):
    rows, offset = [], 0
    while True:
        u = "%s?monitoring_location_id=USGS-%s&limit=500&offset=%d&f=json" % (API, site, offset)
        d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=180))
        fs = d.get("features", [])
        for f in fs:
            p = f.get("properties", {})
            try:
                q = float(p["channel_flow"]); w = float(p["channel_width"]); a = float(p["channel_area"])
            except (KeyError, TypeError, ValueError):
                continue
            if q <= 0 or w <= 0 or a <= 0:
                continue
            rows.append({"q": q, "w": w, "a": a, "d": a / w,
                         "how": (p.get("measurement_type") or "").strip(),
                         "mat": (p.get("channel_material") or "").strip(),
                         "t": p.get("time", "")[:10]})
        if len(fs) < 500: break
        offset += 500
    return rows

def powerfit(xs, ys):
    """log-log least squares: d = c * q^f"""
    lx = [math.log(x) for x in xs]; ly = [math.log(y) for y in ys]
    n = len(lx); mx = sum(lx)/n; my = sum(ly)/n
    sxx = sum((x-mx)**2 for x in lx); sxy = sum((x-mx)*(y-my) for x, y in zip(lx, ly))
    f = sxy/sxx; lc = my - f*mx
    ssr = sum((y-(lc+f*x))**2 for x, y in zip(lx, ly)); sst = sum((y-my)**2 for y in ly)
    return f, math.exp(lc), (1 - ssr/sst if sst else 0.0)

def crossover(rows, nbins=12):
    """Flow at which P(wading) crosses 50%, plus the per-bin table.

    max(waded) is one bold crew on one day. This is the behavioural threshold: below it
    crews nearly always wade, above it they nearly always take a boat.

    CAVEAT, and it matters: measurement_type also reflects how the SITE is equipped.
    A cableway or bridge station gets boat-type measurements at any flow, so a low
    crossover there means "they have a cableway", not "you cannot wade it". Check
    waded_frac_table before trusting a crossover.
    """
    typed = [r for r in rows if r["how"]]
    if len(typed) < 20: return None, []
    qs = sorted(r["q"] for r in typed)
    lo, hi = max(qs[0], 1.0), qs[-1]
    edges = [lo * (hi/lo) ** (i/nbins) for i in range(nbins+1)]
    table, cross = [], None
    for a, b in zip(edges, edges[1:]):
        g = [r for r in typed if a <= r["q"] < b]
        if len(g) < 4: continue
        frac = sum(1 for r in g if r["how"].lower().startswith("wad")) / len(g)
        table.append([round(a), len(g), round(frac, 2)])
        if cross is None and frac < 0.5: cross = round(a)
    return cross, table

out = {}
for rid, (site, label) in SITES.items():
    try:
        rows = fetch(site)
    except Exception as e:
        print("%-11s FETCH FAILED %s" % (rid, str(e)[:60])); continue
    if len(rows) < 12:
        print("%-11s only %d usable measurements" % (rid, len(rows))); continue
    f, c, r2 = powerfit([r["q"] for r in rows], [r["d"] for r in rows])
    waded = [r["q"] for r in rows if r["how"].lower().startswith("wad")]
    boated = [r["q"] for r in rows if r["how"] and not r["how"].lower().startswith("wad")]
    mats = {}
    for r in rows: mats[r["mat"]] = mats.get(r["mat"], 0) + 1
    rec = {
        "site": site, "label": label, "n": len(rows),
        "q_range": [round(min(r["q"] for r in rows)), round(max(r["q"] for r in rows))],
        "depth_exp": round(f, 3), "depth_coef": round(c, 4), "r2": round(r2, 3),
        "depth_at": {str(q): round(c * q**f, 2) for q in (100, 250, 500, 1000, 2000, 5000, 10000)},
        "waded_n": len(waded), "boated_n": len(boated),
        "waded_max_q": (round(max(waded)) if waded else None),
        "waded_p90_q": (round(sorted(waded)[int(len(waded)*0.9)]) if len(waded) >= 5 else None),
        "boated_min_q": (round(min(boated)) if boated else None),
        "substrate": sorted(mats.items(), key=lambda x: -x[1])[:3],
    }
    _cross, _tab = crossover(rows)
    rec["wade_crossover_q"] = _cross
    rec["waded_frac_table"] = _tab      # [[flow_bin_start, n, fraction_waded], ...]
    rec["wade_crossover_depth"] = (round(c * _cross**f, 2) if _cross else None)
    # Is the crossover a real signal or just the site's equipment? If crews NEVER wade a
    # majority even at the lowest measured flows, this is a cableway/bridge station and the
    # crossover says nothing about whether YOU can wade it. Four of seven sites fail this.
    _peak_waded = max((row[2] for row in _tab), default=0.0)
    rec["crossover_trustworthy"] = bool(_peak_waded >= 0.5)
    rec["crossover_caveat"] = ("" if _peak_waded >= 0.5 else
        "Crews never wade a majority at any measured flow — cableway/bridge station. "
        "This crossover reflects site equipment, not wadeability. Use a reported source instead.")
    out[rid] = rec
    print("%-11s n=%-4d Q %5d-%-7d  d=%.3f·Q^%.3f (R2 %.2f)  cross@%s  boat>=%s  %s"
          % (rid, rec["n"], rec["q_range"][0], rec["q_range"][1], c, f, r2,
             (rec["wade_crossover_q"] if rec["crossover_trustworthy"] else "n/a"),
             rec["boated_min_q"],
             ("" if rec["crossover_trustworthy"] else "[cableway] ") +
             (rec["substrate"][0][0] if rec["substrate"] else "?")))
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "channel_geom.json")
json.dump(out, open(p, "w"), indent=1)
print("\nwrote", p)

