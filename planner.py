#!/usr/bin/env python3
"""
planner.py — build the species-first planner (out/index.html + out/plan/*).

Runs AFTER the river generators in build.sh, because it reuses their calibrated hydrology
through caney/sources and links to their pages as the drill-down layer (§48).

Emits:
    out/plan/data.json      the planner dataset the browser runs on (§24, §27)
    out/plan/parity.json    Python's own scores for sampled windows — the JS engine is
                            tested against this file (test/planner/test_parity.mjs)
    out/plan/featured/*.json  fully-assembled FishingPlans from the Python engine, one per
                            (species × craft × preset), for RiverGuide and the bot
    out/index.html          the species-first homepage
    out/plan.html           the result view (the same page; kept as a stable deep link)
    out/assets/*            shared CSS/JS, copied from web/ — NOT inlined (§47)

Environment:
    RESEARCH_ENABLED=1 OPENAI_API_KEY=… OPENAI_RESEARCH_MODEL=…   optional (§17)
    CANEY_PLANNER_FAST=1                                          skip live research
"""
import datetime as dt
import json
import os
import shutil
import sys
import time
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from caney.domain.zone import Craft                       # noqa: E402
from caney.planner.engine import Request, plan            # noqa: E402
from caney.render.dataset import build as build_dataset   # noqa: E402
from caney.research.corpus import claims_for              # noqa: E402
from caney.research.provider import build_provider, research_zone  # noqa: E402
from caney.research import cache as research_cache        # noqa: E402
from caney.sources.http import stats as http_stats        # noqa: E402
from caney.sources.snapshots import build_all             # noqa: E402
from caney.species.profiles import SPECIES                # noqa: E402
from caney.zones.registry import all_zones                # noqa: E402

CT = ZoneInfo("America/Chicago")
OUT = os.path.join(HERE, "out")
WEB = os.path.join(HERE, "web")

# The presets the homepage offers (§5). Featured plans are precomputed for these so the
# bot and RiverGuide can answer from a real FishingPlan without running Python.
PRESETS = [
    ("dawn",      5, 9),
    ("morning",   6, 11),
    ("midday",   10, 15),
    ("afternoon", 13, 18),
    ("evening",  16, 21),
]


def log(*a):
    print("   ", *a)


def main():
    t_start = time.time()
    now = time.time()
    os.makedirs(os.path.join(OUT, "plan", "featured"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)

    log("building snapshots…")
    snaps, book = build_all(now=now, horizon_days=3)
    log("%d zones, %d safety claims" % (len(snaps), len(book)))

    # ── research (§15-21). Optional: with no key the planner is unaffected. ──
    provider = build_provider()
    research_meta = {"provider": provider.name, "enabled": provider.enabled,
                     "queries": 0, "fetched": 0, "cached": 0, "errors": [],
                     "latencySeconds": 0.0, "claims": 0}
    live_claims = {}
    if provider.enabled and not os.environ.get("CANEY_PLANNER_FAST"):
        month = dt.datetime.fromtimestamp(now, CT).month
        for z in all_zones():
            for sp in z.species_profiles:
                cs, meta = research_zone(provider, sp, z, now, month, snaps.get(z.id))
                live_claims[(z.id, sp)] = cs
                research_meta["queries"] += len(meta["queries"])
                research_meta["fetched"] += meta["fetched"]
                research_meta["cached"] += meta["cached"]
                research_meta["latencySeconds"] += meta["latency_s"]
                research_meta["errors"].extend(meta["errors"][:1])
                research_meta["claims"] += len(cs)
        log("research: %d queries, %d fetched, %d cached, %d claims"
            % (research_meta["queries"], research_meta["fetched"],
               research_meta["cached"], research_meta["claims"]))
    else:
        research_meta["errors"].append(getattr(provider, "reason", "research disabled"))
        log("research: %s (deterministic planner unaffected)" % provider.name)
    refreshed, n_cached = research_cache.last_refreshed()
    research_meta["refreshedAt"] = refreshed
    research_meta["cacheEntries"] = n_cached

    month = dt.datetime.fromtimestamp(now, CT).month
    claims_by_zs = {}
    for z in all_zones():
        for sp in z.species_profiles:
            claims_by_zs[(z.id, sp)] = claims_for(
                sp, month=month, zone_ids=[z.id], extra=live_claims.get((z.id, sp), ()))

    today = dt.datetime.fromtimestamp(now, CT).date()
    log("emitting dataset…")
    data = build_dataset(snaps, book, claims_by_zs, now=now, research_meta=research_meta)
    _write(os.path.join(OUT, "plan", "data.json"), data)

    # ── featured plans from the authoritative Python engine ─────────────────
    featured, index = {}, []
    for sp in SPECIES:
        for craft in Craft.ALL:
            for day in (0, 1):
                d = today + dt.timedelta(days=day)
                for name, h0, h1 in PRESETS:
                    req = Request(sp, _ep(d, h0), _ep(d, h1), craft, now=now)
                    cbz = {z.id: claims_by_zs.get((z.id, sp), []) for z in all_zones()}
                    p = plan(req, snaps, book, cbz)
                    key = "%s-%s-d%d-%s" % (sp, craft, day, name)
                    featured[key] = p.to_json()
                    index.append({"key": key, "species": sp, "craft": craft, "day": day,
                                  "preset": name, "verdict": p.verdict, "score": p.score,
                                  "confidence": p.confidence, "zone": p.primary_candidate})
    # One file per plan, not one 4 MB blob: a consumer (RiverGuide, the bot, a phone)
    # fetches exactly the plan it was asked about.
    for key, pj in featured.items():
        _write(os.path.join(OUT, "plan", "featured", key + ".json"), pj)
    _write(os.path.join(OUT, "plan", "featured", "index.json"),
           {"built": round(now), "plans": index})
    log("featured plans: %d" % len(featured))

    # ── the parity fixture the browser engine is tested against ─────────────
    _write(os.path.join(OUT, "plan", "parity.json"), _parity(data, now, today))

    # ── shared frontend assets, copied not inlined (§47) ────────────────────
    _copy_assets()

    # ── pages ───────────────────────────────────────────────────────────────
    from caney.render.pages import write_pages
    write_pages(OUT, data, now)

    _write(os.path.join(OUT, "plan", "build.json"), {
        "built": round(now), "durationSeconds": round(time.time() - t_start, 2),
        "zones": len(snaps), "safetyClaims": len(book),
        "featuredPlans": len(featured),
        "http": http_stats(), "research": research_meta,
        "datasetBytes": os.path.getsize(os.path.join(OUT, "plan", "data.json")),
    })
    log("planner built in %.1fs (dataset %.0f KB)"
        % (time.time() - t_start,
           os.path.getsize(os.path.join(OUT, "plan", "data.json")) / 1024.0))


def _parity(data, now, today):
    """Sampled (zone, species, window) → Python's score, computed FROM THE EMITTED DATASET.

    Scoring through the same arrays the browser downloads is the point: if this fixture
    were built from a separately computed series, a divergence between what Python scores
    and what it ships would pass the test.
    """
    from caney.planner import scoring
    from caney.render.dataset import rehydrate
    cases = []
    for zid, z in data["zones"].items():
        for sp in list(z["species_profiles"])[:2]:
            key = zid + "|" + sp
            if key not in data["series"]:
                continue
            ser, statics = rehydrate(data, zid, sp, Craft.ANY)
            zone = _zone(zid)
            snap_stub = None
            for day, h0, h1 in ((0, 6, 10), (1, 13, 18), (1, 5, 9)):
                d = today + dt.timedelta(days=day)
                a, b = _ep(d, h0), _ep(d, h1)
                v, _lines, _fits = scoring.score(sp, zone, snap_stub, [], (a, b), Craft.ANY,
                                                 d.month, {}, None, False,
                                                 series=ser, statics=statics)
                cases.append({"zone": zid, "species": sp, "start": round(a),
                              "end": round(b), "craft": Craft.ANY, "score": v})
    return {"built": round(now), "cases": cases}


def _zone(zid):
    from caney.zones.registry import zone
    return zone(zid)


def _copy_assets():
    for name in sorted(os.listdir(os.path.join(WEB, "assets"))):
        shutil.copyfile(os.path.join(WEB, "assets", name),
                        os.path.join(OUT, "assets", name))
    dst = os.path.join(OUT, "assets", "planner")
    os.makedirs(dst, exist_ok=True)
    for name in sorted(os.listdir(os.path.join(WEB, "planner"))):
        if name.endswith(".js"):
            shutil.copyfile(os.path.join(WEB, "planner", name), os.path.join(dst, name))
    for name in ("manifest.webmanifest", "sw.js", "offline.html"):
        p = os.path.join(WEB, name)
        if os.path.exists(p):
            shutil.copyfile(p, os.path.join(OUT, name))


def _ep(d, hour):
    return dt.datetime(d.year, d.month, d.day, int(hour), tzinfo=CT).timestamp()


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"), ensure_ascii=False, default=_default)
    os.replace(tmp, path)


def _default(o):
    if hasattr(o, "to_json"):
        return o.to_json()
    raise TypeError("not JSON serialisable: %r" % (type(o),))


if __name__ == "__main__":
    main()
