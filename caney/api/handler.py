"""
The API. §7, §11, §74, §75, §76.

Runtime-independent by construction: it takes a body and a context and returns
`(status, dict)`. The Cloudflare Worker, the local dev server and the tests all call these
three functions, which is what makes "one canonical planner implementation" (§2) true
rather than aspirational — there is no second code path that could answer differently.

§74 SHAPES THE ORDER OF WORK HERE. The deterministic plan comes first and is returned
whether or not research is available; research enriches a plan that already exists. A
search that is slow, rate-limited or down must never be the reason somebody's morning is
still loading, so the research step is bounded and its failure is a `research_status`, not
an exception.
"""
import time

from ..domain.planning import (Confidence, PlanEnvelope, PlanningSnapshot,
                               ResearchStatus, SCHEMA_VERSION)
from ..domain.session import PlanSession, PlanState
from ..version import versions
from . import contract
from .contract import BadRequest, error


class Context:
    """Everything a request needs that is not the request.

    Assembled by the host — the Worker builds one per request from its bindings; the dev
    server builds one at startup and reuses it. The planner never reaches for a global.
    """

    def __init__(self, snapshots=None, book=None, claims_by_zone=None, store=None,
                 research_status=ResearchStatus.DISABLED, source_stats=None,
                 now=None, tz_name="America/Chicago", build_snapshots=None):
        self.snapshots = snapshots or {}
        self.book = book
        self.claims_by_zone = claims_by_zone or {}
        from .storage import NullStore
        self.store = store if store is not None else NullStore()
        self.research_status = research_status
        self.source_stats = source_stats or {}
        self.now = now or time.time()
        self.tz_name = tz_name
        #: Optional callable(species, window) -> (snapshots, book, claims). Lets a host
        #: fetch lazily and per-request (§31, §32) instead of holding the world.
        self.build_snapshots = build_snapshots


def health(ctx):
    """§76 — may stay externally reachable, and is the only thing that should."""
    from ..tz import backend as tz_backend
    from ..sources.http import current as source_runtime
    return 200, {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "versions": versions(),
        "tz_backend": tz_backend(),
        "source_runtime": source_runtime().name,
        "zones": len(ctx.snapshots),
        "research_status": ctx.research_status,
        "storage": ctx.store.stats().get("backend", "unknown"),
        "now": round(ctx.now),
    }


def plan(body, ctx):
    """POST /api/v3/plan → PlanEnvelope. §7."""
    t0 = time.time()
    try:
        req = contract.parse(body, now=ctx.now, tz_name=ctx.tz_name)
    except BadRequest as e:
        return error(400, e.message, e.field)

    snaps, book, claims = ctx.snapshots, ctx.book, ctx.claims_by_zone
    if ctx.build_snapshots is not None:
        snaps, book, claims = ctx.build_snapshots(req)
    if not snaps:
        # Not a client error and not a bug: the source layer has nothing. Say which.
        return error(503, "no water data is available to plan from", "", "no_sources")

    t_plan = time.time()
    from ..planner.engine import plan as run_plan
    cbz = {zid: (claims.get((zid, req.species)) or claims.get(zid) or [])
           for zid in snaps}
    try:
        p = run_plan(req, snaps, book, cbz)
    except Exception as e:                      # noqa: BLE001
        # §76 — a programming error is a 500 and says so. Dressing it as a degraded 200
        # is how a bug survives to production looking like a data problem.
        return error(500, "the planner failed: %s: %s" % (type(e).__name__, e))
    plan_ms = (time.time() - t_plan) * 1000.0

    snapshot = _snapshot_for(p, snaps, ctx)
    env = _envelope(p, req, snapshot, ctx)
    env.timings = {"total_ms": round((time.time() - t0) * 1000.0, 1),
                   "plan_ms": round(plan_ms, 1),
                   "sources": dict(ctx.source_stats)}

    ctx.store.put("snapshot", snapshot.id, snapshot.to_json())
    from .storage import redact_origin
    ctx.store.put("plan", env.plan_id, redact_origin(env.to_json()))
    return 200, env.to_json()


def refresh(plan_id, body, ctx):
    """POST /api/v3/plans/{plan_id}/refresh → UNCHANGED or MATERIAL_CHANGE. §11.

    The BROWSER DOES NOT DECIDE (§11). It gets a verdict, a structured delta and the
    thresholds that produced them; it may explain the answer and may not reach a
    different one.
    """
    stored = ctx.store.get("plan", plan_id)
    if not stored:
        return error(404, "no plan with id %r — it may have expired" % plan_id, "plan_id")
    old_snap = ctx.store.get("snapshot", stored.get("snapshot_id") or "") or {}

    # Re-plan from the ORIGINAL request. Re-parsing the stored request rather than
    # accepting a new body is deliberate: a refresh must answer "has my plan changed",
    # and letting the client vary the request would answer a different question with the
    # same word.
    req_body = dict(stored.get("request") or {})
    if body and isinstance(body, dict) and body.get("origin"):
        # §16 — the client keeps the origin and sends it per request. The stored plan
        # deliberately does not retain it.
        req_body["origin"] = body["origin"]
    elif stored.get("request", {}).get("door_to_door"):
        # Refusing is the only honest option. Re-planning without the origin would
        # silently produce a WINDOW-ONLY plan — no drive, no leave-by, a different
        # itinerary — and return it as though it were a comparison against the original.
        # A delta computed across that difference would be pure noise.
        return error(400,
                     "this plan was planned door to door, so re-checking it needs the "
                     "origin again. It is not stored (§16) — send it with the refresh.",
                     "origin", "origin_required")
    try:
        req = contract.parse(req_body, now=ctx.now, tz_name=ctx.tz_name)
    except BadRequest as e:
        return error(500, "the stored request no longer parses: %s" % e.message)

    snaps, book, claims = ctx.snapshots, ctx.book, ctx.claims_by_zone
    if ctx.build_snapshots is not None:
        snaps, book, claims = ctx.build_snapshots(req)
    if not snaps:
        return error(503, "no water data is available to re-check against", "",
                     "no_sources")

    from ..planner.engine import plan as run_plan
    cbz = {zid: (claims.get((zid, req.species)) or claims.get(zid) or [])
           for zid in snaps}
    p = run_plan(req, snaps, book, cbz)
    new_snapshot = _snapshot_for(p, snaps, ctx)
    new_env = _envelope(p, req, new_snapshot, ctx)

    from ..planner import delta as delta_mod
    from ..tz import zone as tzf
    d = delta_mod.compute(old_snap, new_snapshot.to_json(),
                          stored.get("recommendation"), new_env.recommendation,
                          tz=tzf(ctx.tz_name))

    ctx.store.put("snapshot", new_snapshot.id, new_snapshot.to_json())
    from .storage import redact_origin
    if d.material:
        ctx.store.put("plan", new_env.plan_id, redact_origin(new_env.to_json()))

    return 200, {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "checked_at": round(ctx.now),
        "delta": d.to_json(),
        # The replacement plan is only included when it is actually different. Sending it
        # every time would make every poll look like a change to any client that
        # re-rendered on receipt.
        "plan": new_env.to_json() if d.material else None,
    }


def session(body, ctx, session_id=None):
    """Create or advance a PlanSession. §9."""
    if not isinstance(body, dict):
        return error(400, "the request body must be a JSON object")
    if session_id:
        raw = ctx.store.get("session", session_id)
        if not raw:
            return error(404, "no session %r" % session_id, "session_id")
        s = PlanSession.from_json(raw)
        to = body.get("state")
        if to:
            if to not in PlanState.ALL:
                return error(400, "unknown state %r" % to, "state")
            try:
                s.transition(to, body.get("reason", ""), at=ctx.now)
            except ValueError as e:
                # A refused transition is the CLIENT asking for something impossible.
                return error(409, str(e), "state", "illegal_transition")
        if body.get("outcome") is not None:
            s.outcome = body["outcome"]
            s.updated_at = ctx.now
        ctx.store.put("session", s.id, s.to_json())
        return 200, {"schema_version": SCHEMA_VERSION, "session": s.to_json()}

    plan_id = body.get("plan_id")
    if not plan_id:
        return error(400, "plan_id is required to start a session", "plan_id")
    stored = ctx.store.get("plan", plan_id)
    if not stored:
        return error(404, "no plan with id %r" % plan_id, "plan_id")
    s = PlanSession(plan_id=plan_id, snapshot_id=stored.get("snapshot_id", ""),
                    created_at=ctx.now, updated_at=ctx.now)
    s.transition(PlanState.READY, "plan accepted", at=ctx.now)
    ctx.store.put("session", s.id, s.to_json())
    return 201, {"schema_version": SCHEMA_VERSION, "session": s.to_json()}


# ── assembly ────────────────────────────────────────────────────────────────

def _score(pj, key):
    """A score off a serialised plan, refusing to invent one.

    `pj.get(key) or 0.0` would have done, and it is the exact shape §3.4 exists to
    forbid: a genuine 0.0 (a SKIP plan really does have zero opportunity) and a missing
    field would become the same number, and the confidence grade downstream reads that
    number to decide whether to tell somebody the plan is trustworthy. FishingPlan.to_json
    always emits these, so an absent one is a bug in the serialiser — which is worth a
    loud failure rather than a quiet zero.
    """
    v = pj.get(key)
    if v is None:
        raise KeyError("plan is missing %r — the serialiser did not emit it" % key)
    return float(v)



def _snapshot_for(p, snaps, ctx):
    """Freeze the inputs this plan used — and only those. §8, §32."""
    used = list(((p.itinerary.zone_sequence if p.itinerary else None) or
                 ([p.primary_candidate] if p.primary_candidate else [])))
    for a in p.alternatives[:4]:
        if a.get("zone_id") and a["zone_id"] not in used:
            used.append(a["zone_id"])
    zones, release, weather = {}, {}, {}
    for zid in used:
        s = snaps.get(zid)
        if s is None:
            continue
        zones[zid] = s.to_json()
        rid = s.river_id
        if rid and rid not in release and s.generation_forecast.ok:
            release[rid] = s.generation_forecast.value
        if rid and rid not in weather:
            weather[rid] = s.weather_hours
    snap = PlanningSnapshot(
        created_at=ctx.now, zones=zones, release_series=release,
        weather_series=weather,
        research_claim_ids=[c.get("id") for c in p.evidence if c.get("id")],
        safety_claim_ids=[c.get("id") for c in p.safety if c.get("id")],
        routing=((p.logistics or {}).get("routing") or {}),
        freshness={zid: (snaps[zid].freshness() if zid in snaps else [])
                   for zid in used},
        model_versions=versions(), source_stats=dict(ctx.source_stats))
    return snap.seal()


def _envelope(p, req, snapshot, ctx):
    pj = p.to_json()
    env = PlanEnvelope(
        created_at=ctx.now,
        request=req.to_json(),
        recommendation=pj,
        itinerary=pj.get("itinerary"),
        alternatives=pj.get("alternatives") or [],
        snapshot_id=snapshot.id,
        opportunity=_score(pj, "opportunity"),
        forecast_confidence=_score(pj, "confidence"),
        location_confidence=_score(pj, "location_confidence"),
        research_confidence=_score(pj, "research_confidence"),
        freshness=pj.get("data_freshness") or [],
        safety=pj.get("safety") or [],
        research_status=ctx.research_status,
        model_versions=versions(),
        logistics=pj.get("logistics"),
        limitations=pj.get("limitations") or [])
    env.grade()
    return env
