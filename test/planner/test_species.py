"""
§51 — species regression fixtures, and §22's Carthage striper case.

These run the FULL pipeline — candidate generation, eligibility gates, scoring, confidence,
ranking, plan assembly — against hand-built snapshots. No network, fixed clock.

The Carthage case is the one that proves the architecture. `cordell.py`'s species line
reads "Smallmouth, white bass & panfish", so under the old river.species[] model a
striped-bass request could never reach the Cordell Hull tailwater. TWRA manages that exact
reach as the striped-bass concentration for the system. The test asserts the candidate
appears, ranks strongly, and carries its sourced evidence.
"""
import fixtures as F
from harness import check, eq, section

from caney.domain.zone import Craft
from caney.planner.engine import Request, candidates, plan
from caney.research.corpus import claims_for
from caney.zones.registry import ZONES, all_zones


def _book():
    from caney.domain.claim import ClaimBook
    return ClaimBook()


def _mint(book, snaps):
    """Run the same claim minting the live builder does, over fixture snapshots."""
    from zoneinfo import ZoneInfo
    from caney.sources.registry import water_for
    from caney.sources.snapshots import _mint_safety_claims
    tz = ZoneInfo("America/Chicago")
    for zid, s in snaps.items():
        z = ZONES[zid]
        cfg = water_for(z.hydrology_river)
        _mint_safety_claims(z, s, {"cfg": cfg, "release_rows": [], "alerts": []},
                            cfg, F.at(6), F.at(6) + 3 * 86400, tz, book)


def _claims(species, month):
    return {z.id: claims_for(species, month=month, zone_ids=[z.id]) for z in all_zones()}


def _run(species, craft, h0, h1, snaps, day=0):
    book = _book()
    _mint(book, snaps)
    req = Request(species, F.at(h0, day), F.at(h1, day), craft, now=F.at(5))
    return plan(req, snaps, book, _claims(species, req.month)), book


# ── the shared world these fixtures fish in ────────────────────────────────
def _late_summer_world(*, cordell_running=True, cheatham_running=False,
                       centerhill="single_afternoon"):
    """Every zone gets a snapshot; only the ones a test cares about are interesting."""
    snaps = {}
    for z in all_zones():
        rid = z.hydrology_river
        if rid == "caney":
            s = F.snapshot(z.id, rid, flow=280, stage=2.1, temp_f=56, generation=250,
                           forecast=F.GOLDEN_RELEASES[centerhill], flow_trend="steady")
            F.with_arrival(s, z.mfd or 6.0)
        elif rid == "cordell":
            s = F.snapshot(z.id, rid, temp_f=71,
                           generation=16000 if cordell_running else 0,
                           forecast=(F.GOLDEN_RELEASES["all_day"] if cordell_running
                                     else F.GOLDEN_RELEASES["no_generation"]),
                           flow_trend="steady", clarity="stained")
            F.with_arrival(s, z.mfd or 1.0, "Cordell Hull Dam")
        elif rid == "cheatham":
            s = F.snapshot(z.id, rid, temp_f=78,
                           generation=18000 if cheatham_running else 0,
                           forecast=(F.GOLDEN_RELEASES["all_day"] if cheatham_running
                                     else F.GOLDEN_RELEASES["no_generation"]))
            F.with_arrival(s, z.mfd or 0.5, "Cheatham Dam")
        elif rid == "cumbnash":
            s = F.snapshot(z.id, rid, flow=12000, temp_f=79, generation=0,
                           forecast=F.GOLDEN_RELEASES["no_generation"])
        elif rid in ("duckup", "duckmid", "ducklow", "buffalo", "harpeth", "elk"):
            import riverlib
            m = riverlib.WATER_MODEL.get(rid) or {"wade_ok": 500, "wade_marginal": 800,
                                                  "no_wade": 1100}
            s = F.snapshot(z.id, rid, flow=F.warmwater_flow(m, "prime"), temp_f=74,
                           flow_trend="steady", clarity="clear",
                           model_confidence="reported")
        elif rid == "stones":
            s = F.snapshot(z.id, rid, flow=300, temp_f=80, generation=0,
                           forecast=F.GOLDEN_RELEASES["no_generation"],
                           flow_trend="steady", model_confidence="reported")
        elif rid == "elktn":
            s = F.snapshot(z.id, rid, flow=400, temp_f=62, model_confidence="reported")
        elif rid == "cumberland":
            s = F.snapshot(z.id, rid, flow=1800, temp_f=52, generation=1000,
                           forecast=F.GOLDEN_RELEASES["no_generation"],
                           model_confidence="reported")
            F.with_arrival(s, z.mfd or 3.0, "Wolf Creek Dam")
        else:
            s = F.snapshot(z.id, rid, model_confidence="unknown")
        snaps[z.id] = s
    return snaps


def test_carthage_stripers():
    section("§22/§51 — Carthage stripers, late summer, Cordell running, early morning")
    snaps = _late_summer_world(cordell_running=True)
    p, book = _run("striped_bass", Craft.POWER, 6, 10, snaps)

    scored, rejected = candidates(
        Request("striped_bass", F.at(6), F.at(10), Craft.POWER, now=F.at(5)),
        snaps, book, _claims("striped_bass", 9))
    ids = [c["zone"].id for c in scored]

    check("the Carthage confluence complex is a CANDIDATE at all",
          "carthage_confluence" in ids, ",".join(ids))
    check("so is the Cordell Hull tailrace", "cordell_tailwater" in ids, ",".join(ids))
    check("and the lower Caney, which is the same confluence from the other side",
          "caney_lower" in ids, ",".join(ids))

    top3 = ids[:3]
    check("the confluence complex ranks in the top three",
          "carthage_confluence" in top3, ",".join(top3))
    check("every one of the top three is confluence water",
          set(top3) <= {"carthage_confluence", "cordell_tailwater", "caney_lower"},
          ",".join(top3))

    # The page-level species tag must take no part.
    import riverlib
    cordell_page_species = riverlib.RIVER_CONFIG["cordell"]["species"]
    check("the cordell PAGE still does not list striped bass — and it does not matter",
          "trip" not in cordell_page_species.lower() and
          "striped" not in cordell_page_species.lower(), cordell_page_species)

    cc = next(c for c in scored if c["zone"].id == "carthage_confluence")
    ev = [c for c in cc["claims"] if "carthage_confluence" in c.location_ids]
    check("the candidate carries sourced TWRA evidence", len(ev) >= 3, "%d claims" % len(ev))
    check("every claim has a source URL", all(c.source_url for c in ev))
    check("the evidence names the reach TWRA describes",
          any("Cordell Hull Dam downstream" in c.claim_text for c in ev),
          "; ".join(c.claim_text[:40] for c in ev[:2]))
    research_line = next(l for l in cc["lines"] if l.key == "research")
    check("research evidence actually moves the score",
          research_line.earned > research_line.possible * 0.6,
          "%s / %s" % (research_line.earned, research_line.possible))

    section("the plan itself")
    check("a plan is produced", bool(p.primary_candidate), p.verdict_why)
    check("the winner is confluence water",
          p.primary_candidate in ("carthage_confluence", "cordell_tailwater", "caney_lower"),
          p.primary_candidate)
    check("it names a launch", bool((p.access.get("launch") or {}).get("name")),
          str(p.access.get("launch")))
    check("it has a timeline", len(p.timeline) >= 4, str(len(p.timeline)))
    check("it says what to tie on", bool(p.technique and p.technique.primary_fly))
    check("current is the biggest single component for stripers",
          max(p.score_breakdown, key=lambda l: l.possible).key == "current")

    section("§3.2 — the same water, a different fishery, out of season")
    p_winter, _ = _run("striped_bass", Craft.POWER, 6, 10, snaps)
    check("the confluence is a year-round striper zone", 
          ZONES["carthage_confluence"].supports_species("striped_bass", 1))
    check("the lower Caney striper pattern is SEASONAL, not year-round",
          not ZONES["caney_lower"].supports_species("striped_bass", 1) and
          ZONES["caney_lower"].supports_species("striped_bass", 7))
    check("and the same zone also holds trout, in the opposite months",
          ZONES["caney_lower"].supports_species("trout", 1) and
          not ZONES["caney_lower"].supports_species("trout", 7))


def test_caney_trout_wade():
    section("§51 — Caney trout, wading, morning, with an afternoon release")
    snaps = _late_summer_world(centerhill="single_afternoon")
    p, book = _run("trout", Craft.WADE, 6, 12, snaps)

    check("an upper or middle Caney reach wins",
          p.primary_candidate in ("caney_upper", "caney_middle"), p.primary_candidate)
    check("the verdict is not a SKIP", p.verdict != "SKIP", p.verdict_why)

    exits = [c for c in p.safety if c["kind"] == "safe_exit"]
    check("the plan carries a safe-exit claim", bool(exits), str([c["kind"] for c in p.safety]))
    check("the safe exit uses the EARLIEST arrival bound, not the typical one",
          all(c["bound"] == "earliest" for c in exits),
          str([c["bound"] for c in exits]))

    arr = [c for c in p.safety if c["kind"] == "release_arrival"]
    check("arrival is stated as a distribution, not a single time",
          arr and all(isinstance(c["value"], list) and len(c["value"]) == 3 for c in arr),
          str([c.get("value") for c in arr]))
    if arr:
        e, m, l = arr[0]["value"]
        check("earliest < typical < latest", e < m < l, "%s %s %s" % (e, m, l))
        ex = [c for c in p.safety if c["kind"] == "safe_exit"]
        if ex:
            check("the exit time is BEFORE the earliest possible arrival",
                  ex[0]["value"] < e, "%s vs %s" % (ex[0]["value"], e))

    # The invariant that matters is not "there is a safety step" — it is that the plan
    # never leaves you in the water past the exit time. On this fixture the window is
    # chosen so it closes hours before the release even leaves the dam, which is the
    # system working; the exit claim is still on the plan for the reader to see.
    ex = [c for c in p.safety if c["kind"] == "safe_exit"]
    if ex:
        exit_at = min(c["value"] for c in ex)
        check("the plan never has you in the water past the safe-exit time",
              p.best_window["end"] <= exit_at,
              "window ends %s, exit %s" % (p.best_window["end"], exit_at))
        inside = [s for s in p.timeline if s.kind == "safety"]
        check("a safe exit inside the window is a hard step in the itinerary",
              (exit_at > p.best_window["end"] + 5400) or bool(inside),
              str([s.kind for s in p.timeline]))
    check("generation is the biggest component for trout",
          max(p.score_breakdown, key=lambda l: l.possible).key == "generation")

    section("§51 — the same request with no release forecast at all")
    snaps2 = _late_summer_world()
    for zid in ("caney_upper", "caney_middle", "caney_lower"):
        snaps2[zid] = F.with_arrival(
            F.snapshot(zid, "caney", flow=280, temp_f=56, generation=250), ZONES[zid].mfd or 6)
    p2, _ = _run("trout", Craft.WADE, 6, 12, snaps2)
    check("no Caney reach is offered for wading without a release forecast",
          p2.primary_candidate not in ("caney_upper", "caney_middle"), p2.primary_candidate)
    outs = [a for a in p2.alternatives if a.get("eliminated")]
    check("and the reason is stated to the reader",
          any("release forecast" in (a.get("reason") or "") for a in outs),
          str([a.get("reason") for a in outs][:2]))


def test_trout_power_boat():
    section("§62 — trout from a power boat: the Caney reaches must be GATED OUT")
    snaps = _late_summer_world()
    p, _ = _run("trout", Craft.POWER, 13, 18, snaps)
    outs = {a["name"]: a.get("reason") for a in p.alternatives if a.get("eliminated")}
    check("upper Caney is eliminated for a power boat",
          any("Upper Caney" in n for n in outs), ",".join(outs))
    check("the elimination names craft, not a low score",
          any("Power boat" in (r or "") for r in outs.values()), str(outs))
    check("something is still offered, or the refusal is explicit",
          p.primary_candidate or p.verdict == "SKIP", p.verdict_why)


def test_smallmouth_bands():
    section("§51 — Buffalo smallmouth across low / prime / high")
    import riverlib
    m = riverlib.WATER_MODEL["buffalo"]
    scores = {}
    for band in ("very_low", "prime", "high", "blown"):
        snaps = _late_summer_world()
        snaps["buffalo_river"] = F.snapshot(
            "buffalo_river", "buffalo", flow=F.warmwater_flow(m, band), temp_f=74,
            flow_trend="steady", clarity="clear", model_confidence="reported")
        # Score the zone directly rather than reading it off the winner's alternatives
        # list, which is truncated to three and silently reports None for a zone that
        # ranked fourth — an assertion that then passes for the wrong reason.
        book = _book()
        _mint(book, snaps)
        req = Request("smallmouth", F.at(6), F.at(11), Craft.KAYAK, now=F.at(5))
        scored, _rej = candidates(req, snaps, book, _claims("smallmouth", req.month))
        hit = next((c for c in scored if c["zone"].id == "buffalo_river"), None)
        scores[band] = hit["score"] if hit else None
    check("prime beats very low", scores["prime"] > scores["very_low"], str(scores))
    check("prime beats high", scores["prime"] > scores["high"], str(scores))
    check("every band produced a score", all(v is not None for v in scores.values()),
          str(scores))
    check("blown out is the worst of the four", scores["blown"] == min(
        v for v in scores.values() if v is not None), str(scores))


def test_largemouth_can_win():
    section("§51 — largemouth cover water must be able to outrank current water")
    # Hot late summer, no generation anywhere: the current-oriented zones have no seam,
    # and the vegetation/wood/backwater zones should come out on top for largemouth.
    snaps = _late_summer_world(cordell_running=False, cheatham_running=False)
    p, _ = _run("largemouth", Craft.ANY, 17, 21, snaps)
    z = p.primary_candidate
    check("a cover/backwater zone wins for largemouth",
          z in ("cordell_creek_arms", "stones_river", "cheatham_tailrace",
                "oldhickory_tailrace", "duck_lower", "elk_alabama", "harpeth_river"), z)
    check("habitat and temperature are the two biggest components for largemouth",
          {l.key for l in sorted(p.score_breakdown, key=lambda x: -x.possible)[:2]}
          == {"thermal", "habitat"},
          str([l.key for l in p.score_breakdown[:3]]))

    section("and the SAME conditions rank smallmouth somewhere different")
    p_smb, _ = _run("smallmouth", Craft.ANY, 17, 21, snaps)
    check("the two species do not simply return the same water",
          p_smb.primary_candidate != p.primary_candidate,
          "%s vs %s" % (p_smb.primary_candidate, p.primary_candidate))


def test_confidence_beats_score():
    section("§31 — a fully observed candidate can beat a better-looking unobserved one")
    from caney.planner.confidence import rank_key
    check("89 at 42 confidence loses to 84 at 93",
          rank_key(89, 42) < rank_key(84, 93),
          "%.1f vs %.1f" % (rank_key(89, 42), rank_key(84, 93)))
    check("at equal confidence the higher score still wins",
          rank_key(89, 80) > rank_key(84, 80))

    # And end to end: strip the live water off the best striper zone and watch it drop.
    snaps = _late_summer_world(cordell_running=True)
    before, book = _run("striped_bass", Craft.POWER, 6, 10, snaps)
    blind = dict(snaps)
    blind["carthage_confluence"] = F.snapshot("carthage_confluence", "cordell")
    after, _ = _run("striped_bass", Craft.POWER, 6, 10, blind)
    cc_after = next((a for a in after.alternatives
                     if a.get("name") == "Carthage Confluence Complex"), None)
    if after.primary_candidate == "carthage_confluence":
        check("removing every live reading lowers confidence",
              after.confidence < before.confidence,
              "%s vs %s" % (after.confidence, before.confidence))
    else:
        check("removing every live reading costs it the win", True,
              "now %s" % after.primary_candidate)
        if cc_after:
            check("and the alternative says confidence is why",
                  "confidence" in (cc_after.get("what_would_flip_it") or "").lower() or
                  bool(cc_after.get("lost_on")), str(cc_after)[:160])
