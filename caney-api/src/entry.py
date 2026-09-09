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
BUNDLE_KEY = "bundle:latest"
BUNDLE_TTL_SECONDS = 3600.0
#: Reuse within one isolate, so a burst of requests shares one rehydrate.
ISOLATE_TTL_SECONDS = 240.0

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


async def build_bundle(env, now):
    """Fetch everything and serialise the snapshots. Called by the CRON, not by a request."""
    from caney.sources import runtime as rt
    from caney.sources.snapshots import build_all

    def build():
        return build_all(now=now, horizon_days=3)

    filled, stats = await prefetch(build, fetch)
    with rt.using(filled):
        snaps, book = build()

    bundle = {
        "built_at": now,
        "zones": {zid: s.to_json() for zid, s in snaps.items()},
        "book": book.to_json(),
        "prefetch": stats,
        "versions": __import__("caney.version", fromlist=["versions"]).versions(),
    }
    kv = getattr(env, "PLANS", None)
    if kv is not None:
        from js import Object
        from pyodide.ffi import to_js
        await kv.put(BUNDLE_KEY, json.dumps(bundle, default=str),
                     to_js({"expirationTtl": int(BUNDLE_TTL_SECONDS * 3)},
                           dict_converter=Object.fromEntries))
    return bundle, stats


def _rehydrate(bundle, now):
    from caney.domain.claim import ClaimBook
    from caney.domain.snapshot import RiverSnapshot
    snaps = {zid: RiverSnapshot.from_json(z)
             for zid, z in (bundle.get("zones") or {}).items()}
    book = ClaimBook.from_json(bundle.get("book") or [])
    return snaps, book, _claims_for_all(now)


async def _load(env, now):
    """Snapshots for this request: isolate cache, then KV, then a build as a last resort."""
    if _CACHE["snaps"] is not None and (now - _CACHE["at"]) < ISOLATE_TTL_SECONDS:
        return (_CACHE["snaps"], _CACHE["book"], _CACHE["claims"], _CACHE["stats"])

    kv = getattr(env, "PLANS", None)
    if kv is not None:
        raw = await kv.get(BUNDLE_KEY)
        if raw:
            bundle = json.loads(raw)
            age = now - float(bundle.get("built_at") or 0)
            if age < BUNDLE_TTL_SECONDS:
                snaps, book, claims = _rehydrate(bundle, now)
                _CACHE.update(snaps=snaps, book=book, claims=claims, at=now,
                              stats=dict(bundle.get("prefetch") or {},
                                         bundle_age_s=round(age, 1)),
                              built_at=bundle.get("built_at"), source="kv")
                return snaps, book, claims, _CACHE["stats"]

    # No bundle, or a stale one. Build inline — expensive, and the honest fallback for a
    # cold start before the first cron has run. The freshness strip reports the real ages
    # either way, so a request served this way is not silently different.
    bundle, stats = await build_bundle(env, now)
    snaps, book, claims = _rehydrate(bundle, now)
    _CACHE.update(snaps=snaps, book=book, claims=claims, at=now,
                  stats=dict(stats, built_inline=True),
                  built_at=now, source="inline")
    return snaps, book, claims, _CACHE["stats"]


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


async def handle(request, env):
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
            ctx = Context(snapshots=_CACHE["snaps"] or {}, book=_CACHE["book"],
                          claims_by_zone=_CACHE["claims"] or {}, store=store, now=now)
            status, obj = router.route(method, path, body, ctx)
            obj["snapshot_age_s"] = (round(now - float(_CACHE["built_at"]), 1)
                                     if _CACHE.get("built_at") else None)
            obj["prefetch"] = _CACHE.get("stats") or {}
            obj["bundle_source"] = _CACHE.get("source") or "none"
            return _json(status, obj, cors)

        snaps, book, claims, stats = await _load(env, now)
        ctx = Context(snapshots=snaps, book=book, claims_by_zone=claims, store=store,
                      research_status=_research_status(env),
                      source_stats=stats, now=now)
        status, obj = router.route(method, path, body, ctx)
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


async def on_fetch(request, env):
    return await handle(request, env)


async def on_scheduled(event, env, ctx):
    """The cron. §12, §37 — the system keeps conditions fresh, not the caller."""
    await build_bundle(env, time.time())


try:
    from workers import WorkerEntrypoint

    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            return await handle(request, self.env)

        async def scheduled(self, event):
            await build_bundle(self.env, time.time())
except ImportError:                                 # older runtime — on_fetch carries it
    pass
