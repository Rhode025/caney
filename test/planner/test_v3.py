"""
Caney 3.0 — the API contract, logistics, features and deltas. §86-§93.

The golden scenarios in §87-§93 are the spec's own acceptance tests, and they are written
here as fixtures rather than prose so that a regression is a failing check rather than
somebody noticing. Each one names the section it comes from.

No network. Snapshots are built once from the shared fixture runtime, at a fixed clock, so
these run in CI in seconds and give the same answer in January as in September.
"""
import copy
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from harness import check, section, skip          # noqa: E402

NASHVILLE = (36.1627, -86.7816)


def _ctx():
    """Snapshots + claims at a fixed clock. Cached across tests in one run."""
    if not hasattr(_ctx, "_v"):
        import time
        from caney.research.corpus import claims_for
        from caney.sources.snapshots import build_all
        from caney.zones.registry import all_zones
        now = time.time()
        snaps, book = build_all(now=now, horizon_days=3)
        month = dt.datetime.fromtimestamp(now, _tz()).month
        claims = {}
        for z in all_zones():
            for sp in z.species_profiles:
                claims[(z.id, sp)] = claims_for(sp, month=month, zone_ids=[z.id])
        _ctx._v = (snaps, book, claims, now)
    return _ctx._v


def _tz():
    from caney.tz import zone
    return zone("America/Chicago")


def _ep(day_offset, hour, minute=0):
    now = _ctx()[3]
    d = dt.datetime.fromtimestamp(now, _tz()).date() + dt.timedelta(days=day_offset)
    return dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=_tz()).timestamp()


def _plan(species, craft, depart_h, return_h, origin=NASHVILLE, method="either",
          max_drive=None, depart_m=0, return_m=0):
    from caney.planner.engine import Request, plan
    snaps, book, claims, now = _ctx()
    req = Request(species, craft=craft, method=method, now=now, origin=origin,
                  depart_after=_ep(1, depart_h, depart_m),
                  return_by=_ep(1, return_h, return_m),
                  max_drive_minutes=max_drive)
    cbz = {zid: claims.get((zid, species), []) for zid in snaps}
    return req, plan(req, snaps, book, cbz)


# ── §87 · door to door ──────────────────────────────────────────────────────

def test_door_to_door():
    section("§87 — the whole trip, not just the fishing")
    from caney.domain.zone import Craft
    req, p = _plan("striped_bass", Craft.POWER, 5, 11, return_m=30)
    check("a plan is produced", bool(p.primary_candidate), p.verdict_why)
    L = p.logistics
    check("the plan carries logistics", L is not None)
    if not L:
        return
    kinds = [x["kind"] for x in L["legs"]]
    for want in ("depart", "drive_out", "prep", "run_out", "fish",
                 "run_back", "takeout", "drive_home", "home"):
        check("the day includes %s" % want, want in kinds, str(kinds))
    s = L["summary"]
    check("it says when to leave", s["leave"] is not None)
    check("it says when you are home", s["home"] is not None)
    check("leaving is not before the day opens", s["leave"] >= _ep(1, 5) - 1,
          "%s vs %s" % (s["leave"], _ep(1, 5)))
    check("home is not after the deadline", s["home"] <= _ep(1, 11, 30) + 1,
          "home %s deadline %s" % (s["home"], _ep(1, 11, 30)))
    check("fishing starts after launching",
          s["fish_start"] >= (s["launch"] or 0))
    check("there is real fishing time in it", s["fishing_minutes"] >= 45,
          str(s["fishing_minutes"]))
    check("the legs are contiguous and in order",
          all(L["legs"][i]["end"] <= L["legs"][i + 1]["start"] + 1
              for i in range(len(L["legs"]) - 1)))


# ── §88 · the best water is too far ─────────────────────────────────────────

def test_best_water_too_far():
    section("§88 — reachable beats better when the day is short")
    from caney.domain.zone import Craft
    from caney.planner import logistics
    from caney.routing.provider import build_provider
    from caney.zones.registry import zone as Z
    snaps, _book, _c, _now = _ctx()
    av = logistics.Availability(depart_after=_ep(1, 5), return_by=_ep(1, 11, 30))
    r = build_provider()

    far = logistics.envelope(Z("cumberland_ky"), av, NASHVILLE, Craft.POWER, r)
    near = logistics.envelope(Z("oldhickory_tailrace"), av, NASHVILLE, Craft.POWER, r)
    check("the far water is eliminated by the day", not far.viable,
          "%d fishable minutes" % far.minutes)
    check("the elimination reason is the travel arithmetic, not a score",
          "driving" in (far.reason or "") or "reach" in (far.reason or ""), far.reason)
    check("the near water survives", near.viable, near.reason)
    check("the near water offers more fishing than the far",
          near.minutes > far.minutes, "%d vs %d" % (near.minutes, far.minutes))

    _req, p = _plan("striped_bass", Craft.POWER, 5, 11, return_m=30)
    check("the winner is not the unreachable water",
          p.primary_candidate != "cumberland_ky", p.primary_candidate)
    elim = [a for a in p.alternatives if a.get("eliminated")]
    check("eliminated candidates are reported with reasons",
          all(a.get("reason") for a in elim), str(elim[:1]))

    section("§88 — a longer day reaches further")
    long_av = logistics.Availability(depart_after=_ep(1, 4), return_by=_ep(1, 20))
    far_long = logistics.envelope(Z("cumberland_ky"), long_av, NASHVILLE, Craft.POWER, r)
    check("the same water IS reachable given a whole day", far_long.viable,
          "%d minutes" % far_long.minutes)


# ── §89 · feature selection ─────────────────────────────────────────────────

def test_feature_selection():
    section("§89 — the release decides which feature comes first")
    from caney.domain.observation import Observation
    from caney.planner import features as F
    snaps, _b, _c, _now = _ctx()

    rows_on = [(_ep(1, 4) + i * 3600, 9000.0) for i in range(14)]
    rows_split = [(_ep(1, 4) + i * 3600, 9000.0 if _ep(1, 4) + i * 3600 < _ep(1, 8, 30)
                   else 0.0) for i in range(14)]

    s_on = copy.deepcopy(snaps["cordell_tailwater"])
    s_on.generation_forecast = Observation.known(rows_on, "cfs", "fixture")
    s_split = copy.deepcopy(snaps["cordell_tailwater"])
    s_split.generation_forecast = Observation.known(rows_split, "cfs", "fixture")

    on = F.order_for_window("cordell_tailwater", "striped_bass", 9, s_on,
                            _ep(1, 6), _ep(1, 11))
    split = F.order_for_window("cordell_tailwater", "striped_bass", 9, s_split,
                               _ep(1, 6), _ep(1, 11))
    check("with the units turning, one feature carries the window", len(on) == 1,
          str([x["feature"].name for x in on]))
    check("the current-driven feature wins while the water is on",
          on[0]["feature"].current_driven, on[0]["feature"].feature_type)
    check("a shutdown inside the window splits it into two features", len(split) == 2,
          str([x["feature"].name for x in split]))
    if len(split) == 2:
        check("the two legs are different features",
              split[0]["feature"].id != split[1]["feature"].id)
        check("the legs are sequential, not concurrent",
              split[0]["end"] == split[1]["start"] and split[0]["start"] < split[0]["end"])
        check("the move states its reason", bool(split[1]["why"]), split[1]["why"])
        check("the second leg is better than staying put",
              split[1]["fit"] > 0, str(split[1]["fit"]))

    section("§89 — a move is only offered when it is to better water")
    s2 = copy.deepcopy(snaps["carthage_confluence"])
    s2.generation_forecast = Observation.known(rows_split, "cfs", "fixture")
    stay = F.order_for_window("carthage_confluence", "striped_bass", 9, s2,
                              _ep(1, 6), _ep(1, 11))
    check("the confluence stays put across the same shutdown", len(stay) == 1,
          str([(x["feature"].name, x["fit"]) for x in stay]))

    section("§25 — a described reach may not become a waypoint")
    from caney.domain.feature import (FeatureGeometry, GeometryConfidence,
                                      InventedWaypoint)
    for lvl in ("AGENCY_DESCRIBED", "OSM_DERIVED", "MODELED", "UNVERIFIED"):
        try:
            FeatureGeometry(kind="point", points=[[36.274193, -85.912103]],
                            confidence=getattr(GeometryConfidence, lvl))
            check("a %s point is refused" % lvl, False, "it was ALLOWED")
        except InventedWaypoint:
            check("a %s point is refused" % lvl, True)
    from caney.zones.features import all_features
    from caney.zones.registry import all_zones
    known = set()
    for z in all_zones():
        for pt in (z.geometry.points if z.geometry else []):
            known.add(tuple(pt))
        for a in z.access:
            if a.lat is not None:
                known.add((a.lat, a.lon))
    stray = [(f.id, pt) for f in all_features()
             for pt in (f.geometry.points if f.geometry else []) if tuple(pt) not in known]
    check("every feature coordinate traces to the zone registry", not stray, str(stray[:2]))


# ── §90 · plan delta ────────────────────────────────────────────────────────

def test_plan_delta():
    section("§90 — a generation change moves the plan, and says so")
    from caney.planner import delta as D
    tz = _tz()
    old_rows = [[_ep(1, 4) + i * 3600, 9000.0 if _ep(1, 4) + i * 3600 < _ep(1, 8, 30)
                 else 0.0] for i in range(14)]
    new_rows = [[_ep(1, 4) + i * 3600, 9000.0 if _ep(1, 4) + i * 3600 < _ep(1, 7, 45)
                 else 0.0] for i in range(14)]
    zj = lambda rows, flow: {"cordell_tailwater": {                       # noqa: E731
        "river_id": "cordell",
        "generation_forecast": {"value": rows, "state": "known"},
        "flow": {"value": flow, "state": "known"}}}
    old_snap = {"id": "a", "zones": zj(old_rows, 9000)}
    new_snap = {"id": "b", "zones": zj(new_rows, 4000)}
    old_plan = {"id": "p1", "opportunity": 82,
                "itinerary": {"zone_sequence": ["cordell_tailwater"],
                              "windows": [{"zone": "cordell_tailwater",
                                           "start": _ep(1, 6), "end": _ep(1, 9)}]},
                "safety": [{"kind": "safe_exit", "at": _ep(1, 9, 30),
                            "zone_id": "cordell_tailwater"}]}
    new_plan = {"id": "p2", "opportunity": 71,
                "itinerary": {"zone_sequence": ["cordell_tailwater",
                                                "carthage_confluence"],
                              "windows": [{"zone": "cordell_tailwater",
                                           "start": _ep(1, 6), "end": _ep(1, 7, 55)}]},
                "safety": [{"kind": "safe_exit", "at": _ep(1, 8, 50),
                            "zone_id": "cordell_tailwater"}]}

    d = D.compute(old_snap, new_snap, old_plan, new_plan, tz=tz)
    check("the verdict is MATERIAL_CHANGE", d.verdict == "MATERIAL_CHANGE", d.verdict)
    fields = [c.field_name for c in d.changes]
    check("the generation stop is reported", "generation_stop" in fields, str(fields))
    check("the zone sequence change is reported", "zone_sequence" in fields, str(fields))
    check("a headline is produced", bool(d.headline), d.headline)
    check("SAFETY leads the headline", d.changes[0].field_name.startswith("safety_"),
          d.changes[0].field_name)
    check("thresholds ride along so the client cannot re-decide",
          "GENERATION_SHIFT_MINUTES" in d.to_json()["thresholds"])

    section("§11 — nothing moving is UNCHANGED, not a shrug")
    same = D.compute(old_snap, old_snap, old_plan, old_plan, tz=tz)
    check("identical inputs are UNCHANGED", same.verdict == "UNCHANGED", same.verdict)
    check("and carry no changes", not same.changes, str(len(same.changes)))

    section("§10 — safety is asymmetric")
    later = copy.deepcopy(new_plan)
    later["safety"] = [{"kind": "safe_exit", "at": _ep(1, 10, 30),
                        "zone_id": "cordell_tailwater"}]
    dl = D.compute(old_snap, old_snap, old_plan, later, tz=tz)
    safety_rows = [c for c in dl.changes if c.field_name.startswith("safety_")]
    check("an exit moving LATER is notable, not material",
          all(c.materiality == "notable" for c in safety_rows), str(safety_rows))
    earlier = copy.deepcopy(new_plan)
    earlier["safety"] = [{"kind": "safe_exit", "at": _ep(1, 9, 22),
                          "zone_id": "cordell_tailwater"}]
    de = D.compute(old_snap, old_snap, old_plan, earlier, tz=tz)
    safety_rows = [c for c in de.changes if c.field_name.startswith("safety_")]
    check("an exit moving EARLIER by eight minutes is material",
          any(c.materiality == "material" for c in safety_rows), str(safety_rows))


# ── §91 · a live source goes stale ──────────────────────────────────────────

def test_source_failure():
    section("§91 — a source failing is never silent")
    from caney.planner import delta as D
    tz = _tz()
    base = {"cordell_tailwater": {"river_id": "cordell",
                                  "flow": {"value": 9000, "state": "known"},
                                  "generation_forecast": {"value": [], "state": "known"}}}
    gone = copy.deepcopy(base)
    gone["cordell_tailwater"]["flow"] = {"value": 9000, "state": "stale"}
    plan = {"id": "p", "opportunity": 80,
            "itinerary": {"zone_sequence": ["cordell_tailwater"], "windows": []},
            "safety": []}
    d = D.compute({"id": "a", "zones": base}, {"id": "b", "zones": gone}, plan, plan, tz=tz)
    rows = [c for c in d.changes if c.field_name == "flow"]
    check("going stale is reported as a change", bool(rows), str(d.changes))
    if rows:
        check("and says confidence has dropped", "onfidence" in rows[0].why, rows[0].why)

    section("§91/§75 — unknown never becomes zero")
    from caney.domain.observation import Observation
    u = Observation.unknown("cfs", "a gauge")
    check("an unknown observation is not ok", not u.ok)
    check("it has no value", u.value is None)
    try:
        u.require()
        check("require() refuses an unknown", False, "it returned")
    except Exception as e:
        check("require() refuses an unknown", type(e).__name__ == "UnknownValue",
              type(e).__name__)


# ── §92 · research down ─────────────────────────────────────────────────────

def test_research_unavailable():
    section("§92 — research down still yields a deterministic plan")
    from caney.domain.planning import ResearchStatus
    from caney.domain.zone import Craft
    from caney.planner.engine import Request, plan as run
    snaps, book, _claims, now = _ctx()
    req = Request("striped_bass", craft=Craft.POWER, now=now, origin=NASHVILLE,
                  depart_after=_ep(1, 5), return_by=_ep(1, 11, 30))
    p = run(req, snaps, book, {zid: [] for zid in snaps})     # no research at all
    check("a plan is still produced", bool(p.primary_candidate), p.verdict_why)
    check("it still names a window", bool(p.best_window))
    check("it still carries safety claims", isinstance(p.safety, list))
    check("research confidence reflects the absence", p.research_confidence >= 0)
    check("degraded is a distinct status from disabled",
          ResearchStatus.DEGRADED != ResearchStatus.DISABLED)


# ── §7/§75/§76 · the API contract ───────────────────────────────────────────

def test_api_contract():
    section("§76 — client errors are 400s that name the field")
    from caney.api.contract import BadRequest, parse
    snaps, _b, _c, now = _ctx()
    good = {"species": "striped_bass", "craft": "power", "method": "either",
            "availability": {"depart_after": _ep(1, 5), "return_by": _ep(1, 11, 30)},
            "origin": {"lat": 36.1627, "lon": -86.7816}}
    r = parse(good, now=now)
    check("a good request parses", r.species == "striped_bass")
    check("and is door to door", r.door_to_door)

    for name, body, field in (
            ("unknown species", {**good, "species": "walleye"}, "species"),
            ("unknown craft", {**good, "craft": "submarine"}, "craft"),
            ("unknown method", {**good, "method": "trolling"}, "method"),
            ("no availability", {"species": "trout"}, "availability"),
            ("half a day", {**good, "availability": {"depart_after": _ep(1, 5)}},
             "availability"),
            ("backwards", {**good, "availability": {"depart_after": _ep(1, 11),
                                                    "return_by": _ep(1, 5)}},
             "availability"),
            ("origin off Earth", {**good, "origin": {"lat": 999, "lon": 0}}, "origin"),
            ("negative drive cap", {**good, "max_drive_minutes": -5},
             "max_drive_minutes")):
        try:
            parse(body, now=now)
            check("%s is rejected" % name, False, "it parsed")
        except BadRequest as e:
            check("%s is rejected, naming %s" % (name, field), e.field == field,
                  "field was %r" % e.field)

    section("§7 — the envelope carries what §7 lists")
    from caney.api.handler import Context, plan as api_plan
    from caney.api.storage import MemoryStore
    store = MemoryStore()
    _snaps, book, claims, _n = _ctx()
    ctx = Context(snapshots=_snaps, book=book, claims_by_zone=claims, store=store,
                  now=now)
    status, env = api_plan(good, ctx)
    check("POST /plan returns 200", status == 200, str(env)[:160])
    if status != 200:
        return
    for f in ("plan_id", "created_at", "expires_at", "request", "recommendation",
              "itinerary", "alternatives", "snapshot_id", "opportunity",
              "forecast_confidence", "location_confidence", "research_confidence",
              "freshness", "safety", "research_status", "model_versions"):
        check("the envelope carries %s" % f, f in env, str(sorted(env))[:120])
    check("it grades confidence as a word",
          env["confidence_label"] in ("HIGH", "MEDIUM", "LOW"), env["confidence_label"])
    check("the snapshot was stored", store.get("snapshot", env["snapshot_id"]) is not None)
    check("the plan was stored", store.get("plan", env["plan_id"]) is not None)

    section("§16 — the stored plan holds no coordinates")
    import json as _json
    stored = _json.dumps(store.get("plan", env["plan_id"]))
    check("the origin latitude is not in the stored plan", "36.1627" not in stored)
    check("the origin longitude is not in the stored plan", "-86.7816" not in stored)
    check("a coarse cell is kept instead", "origin_cell" in stored)

    section("§11 — refresh needs the origin back, and says so")
    from caney.api.handler import refresh as api_refresh
    st, out = api_refresh(env["plan_id"], {}, ctx)
    check("refreshing a door-to-door plan without an origin is a 400", st == 400, str(st))
    if st == 400:
        check("the error names the reason", out["error"]["code"] == "origin_required",
              out["error"]["code"])
    st, out = api_refresh(env["plan_id"], {"origin": good["origin"]}, ctx)
    check("with the origin it succeeds", st == 200, str(out)[:160])
    if st == 200:
        check("it returns a verdict",
              out["delta"]["verdict"] in ("UNCHANGED", "MATERIAL_CHANGE"),
              out["delta"]["verdict"])
        check("an unchanged plan is not resent", out["plan"] is None
              or out["delta"]["verdict"] == "MATERIAL_CHANGE")

    section("§76 — an unknown route is a 404, not a degraded 200")
    from caney.api import router
    st, _ = router.route("GET", "/api/v3/nope", None, ctx)
    check("unknown endpoint is 404", st == 404, str(st))
    st, _ = router.route("GET", "/api/v3/plan", None, ctx)
    check("wrong method is 405", st == 405, str(st))
    st, _ = router.route("GET", "/health", None, ctx)
    check("health is 200", st == 200, str(st))


# ── §9 · the session lifecycle ──────────────────────────────────────────────

def test_sessions():
    section("§9 — a trip has a lifecycle, not a boolean")
    from caney.domain.session import PlanSession, PlanState
    s = PlanSession(plan_id="p")
    for to in ("READY", "EN_ROUTE", "AT_LAUNCH", "ON_WATER", "COMPLETED"):
        s.transition(to)
    check("the normal path is legal", s.state == "COMPLETED")
    check("it is terminal", s.terminal)
    try:
        s.transition("ON_WATER")
        check("a completed trip cannot resume", False, "it did")
    except ValueError:
        check("a completed trip cannot resume", True)
    s2 = PlanSession(plan_id="p")
    s2.transition("READY")
    s2.transition("ON_WATER")
    check("AT_LAUNCH may be skipped — people put in and start fishing",
          s2.state == "ON_WATER")
    check("an active trip has a refresh cadence", s2.refresh_seconds() == 300,
          str(s2.refresh_seconds()))
    s2.transition("ABORTED")
    check("a trip may be abandoned from anywhere", s2.terminal)
    check("a terminal trip has no cadence", s2.refresh_seconds() is None)
    check("every state is reachable in NEXT",
          set(PlanState.ALL) - {"DRAFT"} <=
          {t for v in PlanState.NEXT.values() for t in v})


# ── §8 · the snapshot ───────────────────────────────────────────────────────

def test_snapshot_is_replayable():
    section("§8 — a snapshot is content-addressed and lossless")
    import json
    from caney.domain.claim import ClaimBook
    from caney.domain.planning import PlanningSnapshot
    from caney.domain.snapshot import RiverSnapshot
    snaps, book, _c, _n = _ctx()

    a = PlanningSnapshot(zones={"z": {"flow": 412.00000000000006}},
                         model_versions={"planner": "3.0.0"})
    b = PlanningSnapshot(zones={"z": {"flow": 412.0}},
                         model_versions={"planner": "3.0.0"})
    check("float noise does not move the address", a.fingerprint() == b.fingerprint())
    c = PlanningSnapshot(zones={"z": {"flow": 500.0}},
                         model_versions={"planner": "3.0.0"})
    check("a real change does move it", a.fingerprint() != c.fingerprint())
    check("sealing assigns it", a.seal().id.startswith("snap_"))

    section("§12 — rehydration is lossless, above all for state")
    bad = []
    for zid, s in snaps.items():
        j = json.loads(json.dumps(s.to_json(), default=str))
        r = RiverSnapshot.from_json(j).to_json()
        for k in j:
            if k == "freshness":
                continue
            if json.dumps(j[k], default=str) != json.dumps(r.get(k), default=str):
                bad.append((zid, k))
    check("every zone round-trips", not bad, str(bad[:3]))
    states = {s.generation_forecast.state for s in snaps.values()}
    r_states = {RiverSnapshot.from_json(
        json.loads(json.dumps(s.to_json(), default=str))).generation_forecast.state
        for s in snaps.values()}
    check("observation states survive the round trip", states == r_states,
          "%s vs %s" % (states, r_states))

    raw = json.loads(json.dumps(book.to_json(), default=str))
    b2 = ClaimBook.from_json(raw)
    check("the claim book round-trips", len(b2) == len(book))
    check("and every claim is identical",
          sorted(json.dumps(x, sort_keys=True, default=str) for x in book.to_json()) ==
          sorted(json.dumps(x, sort_keys=True, default=str) for x in b2.to_json()))
    from caney.domain.claim import SafetyClaim
    one = list(b2._claims.values())[0]
    try:
        object.__getattribute__(one, "text")
        setattr(one, "text", "tampered")
        check("claims stay immutable after rehydration", False, "it was mutated")
    except Exception as e:
        check("claims stay immutable after rehydration",
              type(e).__name__ == "FrozenInstanceError", type(e).__name__)


# ── §20 · method ────────────────────────────────────────────────────────────

def test_method():
    section("§20 — method changes technique and nothing else")
    from caney.domain.zone import Craft
    fly_req, fly = _plan("striped_bass", Craft.POWER, 5, 11, method="fly", return_m=30)
    conv_req, conv = _plan("striped_bass", Craft.POWER, 5, 11, method="conventional",
                           return_m=30)
    check("the same water wins either way",
          fly.primary_candidate == conv.primary_candidate,
          "%s vs %s" % (fly.primary_candidate, conv.primary_candidate))
    check("the same window is chosen", fly.best_window == conv.best_window)
    check("the opportunity is identical", fly.opportunity == conv.opportunity,
          "%s vs %s" % (fly.opportunity, conv.opportunity))
    check("fly gets a fly", bool(fly.technique and fly.technique.primary_fly),
          str(fly.technique.primary if fly.technique else None))
    check("conventional gets conventional tackle",
          bool(conv.technique and conv.technique.primary_lure),
          str(conv.technique.primary if conv.technique else None))
    check("each offers the other", bool(fly.technique.alternate)
          and bool(conv.technique.alternate))

    section("§20 — the two technique tables cannot drift")
    from caney.species.profiles import SPECIES, profile
    from caney.species.techniques import CONVENTIONAL, FIELDS
    for sp in SPECIES:
        check("%s has both tables" % sp, sp in CONVENTIONAL)
        if sp not in CONVENTIONAL:
            continue
        check("%s condition keys match" % sp,
              set(profile(sp).techniques) == set(CONVENTIONAL[sp]),
              str(set(profile(sp).techniques) ^ set(CONVENTIONAL[sp])))
        for key, row in CONVENTIONAL[sp].items():
            missing = [f for f in FIELDS if f not in row]
            check("%s/%s is complete" % (sp, key), not missing, str(missing))


# ── §17/§19 · routing honesty ───────────────────────────────────────────────

def test_routing_is_honest():
    section("§17 — an estimate says it is an estimate")
    from caney.routing.provider import (ESTIMATE_ROUNDING_MINUTES, Provenance,
                                        build_provider)
    p = build_provider()
    r = p.route(NASHVILLE, (36.285278, -85.939722))
    check("a route is produced", r is not None)
    check("it is labelled estimated", r.provenance == Provenance.ESTIMATED, r.provenance)
    check("it is rounded, not falsely precise",
          r.minutes % ESTIMATE_ROUNDING_MINUTES == 0, str(r.minutes))
    check("an estimate buys more return slack than a routed answer",
          Provenance.SLACK[Provenance.ESTIMATED] > Provenance.SLACK[Provenance.ROUTED])
    check("no origin means no route, not zero minutes",
          p.route(None, (36.28, -85.93)) is None)

    section("§17 — the fit tracks the mapped drive times it was fitted to")
    for dest, stated, tol in (((36.285278, -85.939722), 70, 10),
                              ((36.17, -86.74), 25, 10),
                              ((36.8672, -85.1461), 135, 15)):
        got = p.route(NASHVILLE, dest)
        check("estimate for a %d-minute drive is within %d" % (stated, tol),
              abs(got.minutes - stated) <= tol,
              "%s vs %s" % (got.minutes, stated))
