"""
The Caney API, as a Cloudflare Python Worker. §4, §5, §96, §98.

    POST /api/v3/plan                     a PlanEnvelope
    POST /api/v3/plans/{id}/refresh       UNCHANGED or MATERIAL_CHANGE
    GET  /api/v3/plans/{id}               a stored plan
    POST /api/v3/sessions                 start a PlanSession
    GET|POST /api/v3/sessions/{id}        read or advance one
    GET  /health                          liveness and versions

This file is PLUMBING ONLY. Every decision — what is a valid request, which water wins,
what counts as a material change — is made in caney/, which the build copies in beside
this file. §4 says not to create a second copy of the planner, and the way to keep that
true under a bundler is to make the copy a build artifact rather than a directory somebody
can edit.

WHAT PYODIDE MAKES AWKWARD, and how each is handled:

  * No tz database. `caney/tz.py` falls back to the US rule; `/health` reports which
    backend is live so a silent switch is visible.
  * No blocking sockets. `source_runtime.prefetch` discovers and fetches concurrently
    before the planner runs; the planner itself never awaits.
  * Async KV against a synchronous handler. Keys are preloaded before and flushed after,
    which works because every request addresses storage by an id it already knows.
"""
import json
import time

from js import Response, fetch

from caney.api import router
from caney.api.handler import Context
from caney.api.storage import NullStore
from caney.domain.planning import ResearchStatus

from source_runtime import prefetch
from storage import KVStore

#: SNAPSHOTS ARE NOT BUILT ON THE REQUEST PATH. Twenty-two zones of hydrology is far more
#: work than answering one question, and doing it per request is what the platform
#: rejected: the first plan succeeded in 4.3 s and the second returned 1102, resource
#: limits exceeded. A cron-triggered build writes the bundle to KV and requests rehydrate
#: it, which drops a request to parse, read, plan — the 40 ms the planner actually needs.
#:
#: This is also §12 done properly. Five minutes is the cadence a generation schedule
#: revises at, and it is now a property of the SYSTEM rather than of whoever happens to
#: call the API.
#: ONE KEY PER SHARD, not one bundle read-modify-written three times. The first version
#: had each shard load the whole 1 MB bundle, merge into it and write it back, which on a
#: cold start meant six snapshot builds plus three 1 MB reads and three 1 MB writes in a
#: single invocation — and that is what was returning 1102 (resource limits) and 1101
#: (worker threw). Those are PLATFORM errors, so they carry no CORS headers, and the
#: browser reported them as a CORS failure: a symptom two layers from the cause.
#:
#: Separate keys mean a build writes only its own third and reads nothing.
def _shard_key(n):
    return "bundle:shard:%d" % n

#: How old a bundle may be before a request triggers a background rebuild. Five minutes,
#: matching the cron.
BUNDLE_FRESH_SECONDS = 300.0
#: How old it may be before a request refuses to use it and rebuilds INLINE, blocking.
#: An hour is well past any generation forecast's usefulness.
BUNDLE_MAX_SECONDS = 3600.0
#: Reuse within one isolate, so a burst of requests shares one rehydrate.
ISOLATE_TTL_SECONDS = 120.0

#: CLOUDFLARE ALLOWS 50 SUBREQUESTS PER INVOCATION. A full build asks for 74, so 24-28 of
#: them were failing with "Too many subrequests by single Worker invocation" — which is
#: why the winning zone was quietly planning on unknown flow. The count is not a bug to
#: optimise away: 17 rivers x four or five sources each is what the model needs.
#:
#: So a build does a THIRD of the rivers and merges into the stored bundle. Sharding by
#: river is the natural split — a river is already the fetch-dedupe unit and its zones
#: share every source — and because each zone's snapshot carries its own timestamps, a
#: bundle assembled from shards refreshed at different moments still reports every zone's
#: real age rather than one blended lie. Three shards of 25-30 requests leaves margin;
#: two of 44 and 30 did not.
SHARDS = 3

_CACHE = {"snaps": None, "book": None, "claims": None, "at": 0.0, "stats": {},
          "built_at": None, "source": ""}


def _json(status, obj, headers=None):
    h = {"Content-Type": "application/json; charset=utf-8"}
    h.update(headers or {})
    from js import Object
    from pyodide.ffi import to_js
    return Response.new(json.dumps(obj, default=str),
                        status=status,
                        headers=to_js(h, dict_converter=Object.fromEntries))


def _origins(env):
    raw = getattr(env, "ALLOWED_ORIGINS", "") or ""
    return tuple(x.strip() for x in raw.split(",") if x.strip()) or router.DEFAULT_ORIGINS


def _claims_for_all(now):
    """The seeded research corpus, per (zone, species). Pure lookups over a static table."""
    import datetime as dt
    from caney.research.corpus import claims_for
    from caney.tz import zone as tzf
    from caney.zones.registry import all_zones
    month = dt.datetime.fromtimestamp(now, tzf()).month
    out = {}
    for z in all_zones():
        for sp in z.species_profiles:
            out[(z.id, sp)] = claims_for(sp, month=month, zone_ids=[z.id])
    return out


def _shard(n):
    """Rivers for shard `n`, round-robin so adjacent shards are not adjacent water."""
    from caney.sources.snapshots import rivers
    rs = rivers()
    return [r for i, r in enumerate(rs) if i % SHARDS == (n % SHARDS)]


async def build_bundle(env, now, why="unknown", shard=0):
    """Fetch everything and serialise the snapshots.

    Writes a MARKER before it starts and a result after it finishes, so /health can tell
    the three cases apart: never invoked, invoked and still running, invoked and threw.
    Without that the cron's silence and a crashing builder look identical from outside,
    which is exactly where an afternoon goes.
    """
    kv0 = getattr(env, "PLANS", None)
    if kv0 is not None:
        try:
            from js import Object as _O
            from pyodide.ffi import to_js as _tj
            await kv0.put("build:last_start",
                          json.dumps({"at": now, "why": why}),
                          _tj({"expirationTtl": 86400}, dict_converter=_O.fromEntries))
        except Exception:                           # noqa: BLE001
            pass
    from caney.sources import runtime as rt
    from caney.sources.snapshots import build_all

    kv_n = getattr(env, "PLANS", None)
    if shard is None:
        shard = 0
    n = int(shard) % SHARDS
    mine = _shard(n)

    def build():
        return build_all(now=now, horizon_days=3, only_rivers=mine)

    filled, stats = await prefetch(build, fetch)
    with rt.using(filled):
        snaps, book = build()

    # This shard's zones only. Merging happens at READ time, from separate keys — a
    # claim stays with the zone whose readings minted it, and every zone keeps its own
    # observed_at, so a set of shards refreshed at different moments still reports each
    # zone's real age rather than one blended timestamp wrong for all of them.
    bundle = {
        "built_at": now,
        "shard": n,
        "shard_rivers": mine,
        "zones": {zid: sn.to_json() for zid, sn in snaps.items()},
        "book": book.to_json(),
        "prefetch": dict(stats, shard=n, shard_rivers=len(mine),
                         zones_refreshed=len(snaps)),
        "versions": __import__("caney.version", fromlist=["versions"]).versions(),
    }

    kv = getattr(env, "PLANS", None)
    if kv is not None:
        from js import Object
        from pyodide.ffi import to_js
        await kv.put(_shard_key(n), json.dumps(bundle, default=str),
                     to_js({"expirationTtl": int(BUNDLE_MAX_SECONDS * 6)},
                           dict_converter=Object.fromEntries))
        try:
            await kv.put("build:last_ok",
                         json.dumps({"at": time.time(), "why": why,
                                     "ok": stats.get("ok"), "failed": stats.get("failed")}),
                         to_js({"expirationTtl": 86400},
                               dict_converter=Object.fromEntries))
        except Exception:                           # noqa: BLE001
            pass
    return bundle, stats


def _rehydrate(bundle, now):
    from caney.domain.claim import ClaimBook
    from caney.domain.snapshot import RiverSnapshot
    snaps = {zid: RiverSnapshot.from_json(z)
             for zid, z in (bundle.get("zones") or {}).items()}
    book = ClaimBook.from_json(bundle.get("book") or [])
    return snaps, book, _claims_for_all(now)


async def _read_shards(kv, now):
    """(zones, book, meta) merged from the shard keys, plus each shard's age."""
    zones, book, meta = {}, [], []
    for n in range(SHARDS):
        raw = None
        try:
            raw = await kv.get(_shard_key(n))
        except Exception:                           # noqa: BLE001
            raw = None
        if not raw:
            meta.append({"shard": n, "age_s": None, "present": False})
            continue
        b = json.loads(raw)
        zones.update(b.get("zones") or {})
        book.extend(b.get("book") or [])
        meta.append({"shard": n, "present": True,
                     "age_s": round(now - float(b.get("built_at") or now), 1),
                     "prefetch": b.get("prefetch") or {}})
    return zones, book, meta


async def _load(env, now, ctx=None):
    """Snapshots for this request, merged from the shards. Stale-while-revalidate.

    THE CRON IS NOT TRUSTED TO BE THE ONLY PATH. It is registered — wrangler reports
    `schedule: */5 * * * *` on every deploy — and the bundle's age was observed growing
    linearly at 865s, 966s, 1067s, which means the scheduled handler was not running and
    no error surfaced anywhere a deploy log would show it. Rather than keep guessing at
    handler shapes against a beta runtime, freshness is a property of TRAFFIC as well as
    of the clock.

    A request rebuilds at most ONE shard, and always the oldest. Building more than one
    per invocation is what produced 1102.
    """
    if _CACHE["snaps"] is not None and (now - _CACHE["at"]) < ISOLATE_TTL_SECONDS:
        return (_CACHE["snaps"], _CACHE["book"], _CACHE["claims"], _CACHE["stats"])

    kv = getattr(env, "PLANS", None)
    if kv is not None:
        zones, book, meta = await _read_shards(kv, now)
        present = [m for m in meta if m["present"]]
        if zones and len(present) == SHARDS:
            ages = [m["age_s"] for m in present]
            oldest = max(ages)
            snaps, bk, claims = _rehydrate({"zones": zones, "book": book}, now)
            stats = {"shards": meta, "oldest_shard_age_s": oldest,
                     "zones": len(zones)}
            _CACHE.update(snaps=snaps, book=bk, claims=claims, at=now, stats=stats,
                          built_at=now - oldest, source="kv")
            # NO REBUILD ON THE REQUEST PATH. Requests that also rebuilt a shard were
            # the ones returning 1102: read three shard keys, rehydrate 22 zones, plan,
            # then run two snapshot passes and ~28 more subrequests, all on one
            # invocation's budget. The ones that only read and planned took 1.0s and
            # always succeeded.
            #
            # This also reframes the cron. It looked dead — bundle age growing 865s, 966s,
            # 1067s with no error anywhere — and the likeliest explanation now is that it
            # WAS firing and dying on the same 74-subrequest build, leaving no trace I
            # could see. A cron tick is one shard now, which is the cheapest thing in the
            # system.
            #
            # Worst case is 15 minutes of staleness (three shards, one per five-minute
            # tick). The freshness strip reports every signal's real age, so that is
            # visible rather than assumed, and a generation forecast revises far more
            # slowly than it is fetched.
            if oldest >= BUNDLE_FRESH_SECONDS:
                stats["stale"] = True
                stats["stale_note"] = ("waiting on the scheduled build; requests do not "
                                       "rebuild")
            return snaps, bk, claims, stats

        # Some shards are missing. Build EXACTLY ONE, and never fan the rest out into
        # this same invocation.
        #
        # THE SUBREQUEST BUDGET IS PER INVOCATION AND KV COUNTS TOWARDS IT. The previous
        # version built one shard inline and handed two more to waitUntil, which put
        # roughly 72 fetches plus a handful of KV operations on one invocation against a
        # limit of 50 — so the two background shards came back half-fetched (8 ok / 15
        # failed, 12 ok / 12 failed) and the invocation returned 1102. waitUntil does not
        # buy a fresh budget; it only defers the work.
        #
        # So a cold system fills in over successive invocations — requests and cron ticks
        # alike, one shard each. The first plans are made from fewer zones, which is
        # stated in `limitations` rather than hidden, and it converges within a couple of
        # minutes.
        missing = [m["shard"] for m in meta if not m["present"]]
        stalest = missing[0] if missing else 0
        await build_bundle(env, now, "fill", stalest)
        zones, book, meta = await _read_shards(kv, now)
        snaps, bk, claims = _rehydrate({"zones": zones, "book": book}, now)
        still = [m["shard"] for m in meta if not m["present"]]
        stats = {"shards": meta, "zones": len(zones), "filling": True,
                 "built_shard": stalest, "pending_shards": still}
        _CACHE.update(snaps=snaps, book=bk, claims=claims, at=now, stats=stats,
                      built_at=now, source="filling")
        return snaps, bk, claims, stats

    # No KV at all. One shard's worth is all a single invocation can fetch.
    bundle, stats = await build_bundle(env, now, "no-kv", 0)
    snaps, bk, claims = _rehydrate(bundle, now)
    _CACHE.update(snaps=snaps, book=bk, claims=claims, at=now,
                  stats=dict(stats, no_storage=True), built_at=now, source="inline")
    return snaps, bk, claims, _CACHE["stats"]


async def _store_for(env, path, body):
    """A KVStore with the keys this request will read already loaded."""
    kv = getattr(env, "PLANS", None)
    if kv is None:
        return NullStore()
    store = KVStore(kv)
    wanted = []
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[-2:] == ["plans", ""]:
        pass
    for i, p in enumerate(parts):
        if p == "plans" and i + 1 < len(parts):
            wanted.append("plan:" + parts[i + 1])
        if p == "sessions" and i + 1 < len(parts):
            wanted.append("session:" + parts[i + 1])
    if isinstance(body, dict) and body.get("plan_id"):
        wanted.append("plan:" + str(body["plan_id"]))
    for k in wanted:
        raw = await kv.get(k)
        if raw is not None:
            store.preload(k, raw)
    # A refresh reads the plan's snapshot, whose id is only known once the plan is loaded.
    for k in list(wanted):
        if k.startswith("plan:"):
            row = store.get("plan", k.split(":", 1)[1])
            if row and row.get("snapshot_id"):
                sk = "snapshot:" + row["snapshot_id"]
                raw = await kv.get(sk)
                if raw is not None:
                    store.preload(sk, raw)
    return store


async def _flush(store):
    if not isinstance(store, KVStore):
        return
    for key, value, ttl in store.pending():
        try:
            if value is None:
                await store.kv.delete(key)
            else:
                from js import Object
                from pyodide.ffi import to_js
                await store.kv.put(key, value,
                                   to_js({"expirationTtl": int(ttl)},
                                         dict_converter=Object.fromEntries))
        except Exception:                           # noqa: BLE001
            # A storage failure must not fail a plan that is otherwise correct. The
            # client keeps a usable plan; it simply cannot refresh that one by id.
            pass
    store.clear_pending()


async def handle(request, env, ctx=None):
    t0 = time.time()
    url = str(request.url)
    path = "/" + url.split("://", 1)[-1].split("/", 1)[-1].split("?")[0] \
        if "://" in url else url
    path = path if path.startswith("/") else "/" + path
    method = str(request.method).upper()
    origin = request.headers.get("Origin") or ""
    cors = router.cors_headers(origin, _origins(env))

    if method == "OPTIONS":
        from js import Object
        from pyodide.ffi import to_js
        return Response.new(None, status=204,
                            headers=to_js(cors, dict_converter=Object.fromEntries))

    body = None
    if method in ("POST", "PATCH", "PUT"):
        try:
            raw = await request.text()
            body = json.loads(raw) if raw else {}
        except Exception as e:                      # noqa: BLE001
            return _json(400, {"error": {"message": "invalid JSON: %s" % e,
                                         "status": 400, "code": "bad_request"}}, cors)

    now = time.time()
    try:
        store = await _store_for(env, path, body)
        # /health must answer even when every upstream is down — it is how you find out.
        if path.rstrip("/") in ("/health", "/api/v3/health"):
            hctx = Context(snapshots=_CACHE["snaps"] or {}, book=_CACHE["book"],
                           claims_by_zone=_CACHE["claims"] or {}, store=store, now=now)
            status, obj = router.route(method, path, body, hctx)
            obj["snapshot_age_s"] = (round(now - float(_CACHE["built_at"]), 1)
                                     if _CACHE.get("built_at") else None)
            obj["prefetch"] = _CACHE.get("stats") or {}
            obj["bundle_source"] = _CACHE.get("source") or "none"
            # Health deliberately does not build, but it should not report "no bundle"
            # while one is sitting in KV — that reads as an outage. Peek at the metadata
            # without rehydrating 22 zones.
            kv = getattr(env, "PLANS", None)
            if kv is not None and obj["bundle_source"] == "none":
                zones, _bk, meta = await _read_shards(kv, now)
                if zones:
                    obj["bundle_source"] = "kv"
                    obj["zones"] = len(zones)
                    ages = [m["age_s"] for m in meta if m["present"]]
                    obj["snapshot_age_s"] = max(ages) if ages else None
                    obj["shards"] = meta
            if kv is not None:
                for k, label in (("build:last_start", "last_build_start"),
                                 ("build:last_ok", "last_build_ok")):
                    raw2 = await kv.get(k)
                    if raw2:
                        row = json.loads(raw2)
                        row["age_s"] = round(now - float(row.get("at") or now), 1)
                        obj[label] = row
            obj["ctx_available"] = ctx is not None and hasattr(ctx, "waitUntil")
            return _json(status, obj, cors)

        snaps, book, claims, stats = await _load(env, now, ctx)
        ctx = Context(snapshots=snaps, book=book, claims_by_zone=claims, store=store,
                      research_status=_research_status(env),
                      source_stats=stats, now=now)
        status, obj = router.route(method, path, body, ctx)
        # §75 — an incomplete world is a limitation, not a silent difference. A plan made
        # while shards are still filling had fewer candidates, and the reader is told.
        pending = (stats or {}).get("pending_shards")
        if status == 200 and pending and isinstance(obj, dict) and "limitations" in obj:
            obj["limitations"] = list(obj["limitations"]) + [
                "Conditions for some water were still loading when this plan was made, so "
                "%d of 22 zones were considered. Re-planning in a minute will use all of "
                "them." % (stats or {}).get("zones", 0)]
        await _flush(store)
        if isinstance(obj, dict) and "timings" in obj:
            obj["timings"]["worker_ms"] = round((time.time() - t0) * 1000.0, 1)
        return _json(status, obj, cors)
    except Exception as e:                          # noqa: BLE001
        import traceback
        return _json(500, {"error": {
            "message": "%s: %s" % (type(e).__name__, e), "status": 500,
            "code": "internal_error",
            "trace": traceback.format_exc()[-1200:] if _debug(env) else None}}, cors)


def _debug(env):
    return str(getattr(env, "DEBUG", "") or "") == "1"


def _research_status(env):
    """§35/§36 — research reaches us through a service binding, never from the browser."""
    if getattr(env, "RESEARCH", None) is None:
        return ResearchStatus.DISABLED
    return ResearchStatus.CACHED


# ── entry points ────────────────────────────────────────────────────────────
# Python Workers have had two handler shapes, and which one the platform looks for
# depends on the runtime behind your compatibility date. The module-level `on_fetch`
# came first; `WorkerEntrypoint.fetch` is current, and a deploy that registers neither
# is rejected with "The uploaded script has no registered event handlers" — which is
# what happened here on the first attempt, AFTER a clean 65-module bundle, so it reads
# like a code fault rather than a version mismatch.
#
# Both are exported. The class form is guarded because `workers` does not exist on older
# runtimes and an unguarded import would turn a version mismatch into an import crash,
# which is a strictly worse failure: it happens later and says less.


async def on_fetch(request, env, ctx=None):
    return await handle(request, env, ctx)


async def on_scheduled(event, env, ctx=None):
    """The cron. §12, §37 — the system keeps conditions fresh, not the caller.

    One shard per minute-bucket, so a cron invocation stays inside the subrequest limit
    the same way a request does.
    """
    n = int(time.time() // 300) % SHARDS
    await build_bundle(env, time.time(), "cron", n)


try:
    from workers import WorkerEntrypoint

    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            return await handle(request, self.env, getattr(self, "ctx", None))

        async def scheduled(self, _event=None):
            await build_bundle(self.env, time.time())
except ImportError:                                 # older runtime — on_fetch carries it
    pass
