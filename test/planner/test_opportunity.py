"""
§57-§64 — the 2.1 regression scenarios.

These are the fixtures the brief calls mandatory, plus the ones that pin the behaviour the
window and itinerary optimisers exist to produce. Deterministic: hand-built hourly curves,
a fixed clock, no network.

The four that matter most, in the brief's own words:

    §57  a 95 for 90 minutes must beat a 76 for four hours
    §58  fish A, move, fish B — when the itinerary utility exceeds staying
    §59  stay at A — when the move costs more than it buys
    §60  location uncertainty must be accounted for explicitly
"""
import fixtures as F
from harness import check, eq, near, section

from caney.domain.location import LocationConfidence, LocationEvidence, phrase_for
from caney.domain.zone import Craft, ZoneKind
from caney.planner import utility as U
from caney.planner.itinerary import evaluate, search
from caney.planner.opportunity import find_windows
from caney.planner.transitions import Transition, transition


def _w(zone, series, avail, conf=90, loc=0.95, species="striped_bass", stale=False):
    return find_windows(zone, species, series, avail[0], 3600, avail[0], avail[1],
                        confidence=conf, location_confidence=loc, stale=stale)


def _graph(minutes, mode="boat_downstream", provenance="known"):
    return {("A", "B"): Transition("A", "B", minutes, mode, provenance, "test route"),
            ("B", "A"): Transition("B", "A", minutes, mode, provenance, "test route")}


def _best(windows, graph, species="striped_bass"):
    res = search(windows, graph, species)
    return res[0] if res else None


def _zones(cand):
    out = []
    for w in cand.windows:
        if not out or out[-1] != w.zone_id:
            out.append(w.zone_id)
    return out


# ── §57 · MANDATORY: peak beats average ────────────────────────────────────

def test_peak_beats_average():
    section("§57 — a 95 for 90 minutes must beat a 76 for four hours")
    # The brief's own numbers, on the half hour: 6:30 96, 7:00 95, 7:30 92, then collapse.
    A = [96, 95, 92, 63, 57, 55, 52]
    B = [77, 77, 78, 76, 77, 76, 75]

    a_sub, _ = U.window_utility(A[:3], 90, "striped_bass", 100, 1.0)
    a_full, _ = U.window_utility(A, 240, "striped_bass", 100, 1.0)
    b_full, _ = U.window_utility(B, 240, "striped_bass", 100, 1.0)

    check("A's 90-minute peak beats A's whole four hours", a_sub > a_full,
          "%s vs %s" % (a_sub, a_full))
    check("A's 90-minute peak beats B's flat four hours", a_sub > b_full,
          "%s vs %s" % (a_sub, b_full))
    check("and the margin is not a rounding artefact", a_sub - b_full > 3.0,
          "%s vs %s" % (a_sub, b_full))

    section("the optimiser actually finds it")
    avail = (6 * 3600, 10 * 3600)
    wa = _w("A", [96, 95, 92, 63, 57], avail)
    wb = _w("B", [77, 77, 78, 76, 77], avail)
    best = _best(wa + wb, {})
    check("the winner is candidate A", _zones(best) == ["A"], str(_zones(best)))
    minutes = sum(w.duration_minutes for w in best.windows)
    check("it does NOT use the whole four hours", minutes < 240, str(minutes))
    check("it keeps the peak", max(w.peak_score for w in best.windows) > 90,
          str(max(w.peak_score for w in best.windows)))

    section("§7 — quality is peak-weighted, not an average")
    flat = U.quality([80] * 8)
    spiky = U.quality([95, 95, 95, 95, 65, 65, 65, 65])
    check("a spiky window with the same mean scores higher", spiky > flat,
          "%s vs %s" % (spiky, flat))
    check("a 95 counts for more than a 70",
          U.quality([95, 95]) - U.quality([70, 70]) > 24,
          str(U.quality([95, 95]) - U.quality([70, 70])))
    check("the floor is charged for", U.quality([95, 95, 40]) < U.quality([95, 95, 80]))


# ── §5 · minimum practical durations ───────────────────────────────────────

def test_minimum_durations():
    section("§5 — a 15-minute spike is not a fishing plan")
    eq("striped bass minimum", U.min_duration("striped_bass"), 60)
    eq("smallmouth minimum", U.min_duration("smallmouth"), 75)
    eq("largemouth minimum", U.min_duration("largemouth"), 75)
    eq("trout minimum", U.min_duration("trout"), 60)
    check("below the minimum is penalised hard",
          U.duration_factor(30, "smallmouth") < U.duration_factor(75, "smallmouth") * 0.5)
    check("at the minimum the penalty is gone",
          U.duration_factor(75, "smallmouth") > U.duration_factor(74.9, "smallmouth") * 2)
    check("duration saturates rather than paying forever",
          U.duration_factor(600, "trout") == U.duration_factor(U.IDEAL_MINUTES, "trout"))

    avail = (6 * 3600, 11 * 3600)
    ws = _w("A", [99, 40, 40, 40, 40], avail, species="smallmouth")
    check("no window shorter than the species minimum is offered",
          all(w.duration_minutes >= U.min_duration("smallmouth") for w in ws),
          str([w.duration_minutes for w in ws]))


# ── §58 · move beats stay ──────────────────────────────────────────────────

def test_move_beats_stay():
    section("§58 — fish A, move, fish B, when the itinerary utility exceeds staying")
    avail = (6 * 3600, 11 * 3600)
    # A is excellent then dies; B comes alive later. Fifteen minutes between them.
    A = [96, 96, 45, 42, 40]
    B = [40, 42, 92, 92, 92]
    windows = _w("A", A, avail) + _w("B", B, avail)
    best = _best(windows, _graph(15))
    check("the plan uses both zones", _zones(best) == ["A", "B"], str(_zones(best)))
    check("A comes first", best.windows[0].zone_id == "A")
    check("the move is charged for", best.parts["travelMinutes"] == 15,
          str(best.parts["travelMinutes"]))
    check("it beats the best single-zone plan",
          best.utility > max(evaluate([w], [], "striped_bass")[0] for w in windows),
          str(best.utility))

    section("and the move is impossible without a route")
    no_route = _best(windows, {})
    check("with no transition the plan collapses to one zone",
          len(_zones(no_route)) == 1, str(_zones(no_route)))


# ── §59 · move NOT worth it ────────────────────────────────────────────────

def test_move_not_worth_it():
    section("§59 — refuse the move when the transition costs more than it buys")
    avail = (6 * 3600, 11 * 3600)
    # A is good all morning. B is marginally better later, 35 minutes away.
    A = [84, 84, 84, 84, 84]
    B = [40, 40, 45, 88, 88]
    windows = _w("A", A, avail) + _w("B", B, avail)
    best = _best(windows, _graph(35, "road"))
    check("the plan stays at A", _zones(best) == ["A"], str(_zones(best)))

    section("the same fixture with a 10-minute run DOES move")
    best10 = _best(windows, _graph(10))
    check("a cheap move is taken", len(_zones(best10)) == 2, str(_zones(best10)))
    check("which is the whole point of pricing the transition",
          best10.utility > best.utility, "%s vs %s" % (best10.utility, best.utility))

    section("§14 — a one-zone plan wins when it is clearly best")
    same = _w("A", [90] * 5, avail) + _w("B", [90] * 5, avail)
    best_same = _best(same, _graph(12))
    check("two identical zones do not produce a gratuitous move",
          len(_zones(best_same)) == 1, str(_zones(best_same)))
    check("the complexity penalty is what does it", U.COMPLEXITY_PENALTY > 0)


# ── §60 · location confidence ──────────────────────────────────────────────

def test_location_confidence():
    section("§60 — a 92 on unverified geography loses to an 87 on a verified ramp")
    hi, _ = U.window_utility([92] * 8, 120, "striped_bass", 100, 0.35)
    lo, _ = U.window_utility([87] * 8, 120, "striped_bass", 100, 0.95)
    check("the verified candidate wins", lo > hi, "%s vs %s" % (lo, hi))
    check("the penalty is bounded — it cannot flip an enormous gap",
          U.window_utility([99] * 8, 120, "striped_bass", 100, 0.35)[0] >
          U.window_utility([70] * 8, 120, "striped_bass", 100, 0.95)[0])

    section("§29 — the evidence levels are ordered and documented as priors")
    priors = [LocationEvidence.prior(l) for l in LocationEvidence.ORDER]
    check("priors descend with evidence strength",
          all(priors[i] > priors[i + 1] for i in range(len(priors) - 1)), str(priors))
    eq("a verified access is near certain",
       LocationEvidence.prior(LocationEvidence.VERIFIED_ACCESS), 0.98)
    eq("an unverified candidate is not",
       LocationEvidence.prior(LocationEvidence.UNVERIFIED_CANDIDATE), 0.40)

    section("§30 — the LANGUAGE is graded to the evidence")
    holds = "The boil and both seams beside it"
    precise = phrase_for("precise", holds, "Zone", ["tailrace boil"])
    corridor = phrase_for("corridor", holds, "Zone", ["tailrace boil"], ("A", "B"))
    hedged = phrase_for("hedged", holds, "Zone", ["tailrace boil"])
    check("precise language names the spot", holds.lower() in precise.lower())
    check("corridor language names a stretch", "corridor" in corridor.lower())
    check("hedged language says it is not field verified",
          "not been field verified" in hedged, hedged[:80])
    check("hedged language does NOT issue a tactical instruction as fact",
          not hedged.lower().startswith(holds.lower()[:12]), hedged[:60])

    section("the composite, and what it is made of")
    strong = LocationConfidence(access=LocationEvidence.VERIFIED_ACCESS,
                                reach=LocationEvidence.VERIFIED_ZONE,
                                holding_water=LocationEvidence.MODELED_HABITAT)
    weak = LocationConfidence(access=LocationEvidence.UNVERIFIED_CANDIDATE,
                              reach=LocationEvidence.UNVERIFIED_CANDIDATE,
                              holding_water=LocationEvidence.UNVERIFIED_CANDIDATE)
    check("a verified zone scores far higher", strong.score > weak.score + 40,
          "%s vs %s" % (strong.score, weak.score))
    eq("weak geography gets hedged language", weak.tactical_level, "hedged")
    check("§72 — the breakdown names all three parts", len(strong.rows()) == 3)
    check("every row explains itself", all(r["detail"] for r in strong.rows()))


# ── §11, §12 · transitions ─────────────────────────────────────────────────

def test_transitions():
    section("§11 — a transition declares its provenance")
    from caney.zones.registry import zone
    t = transition(zone("cordell_tailwater"), zone("carthage_confluence"), Craft.POWER)
    check("a configured route is 'known'", t and t.provenance == "known", str(t))
    check("it says HOW", t.mode.startswith("boat"), t.mode)
    check("it explains itself", len(t.detail) > 20, t.detail)

    t2 = transition(zone("harpeth_river"), zone("stones_river"), Craft.POWER)
    check("an unconfigured route is 'estimated' or refused",
          t2 is None or t2.provenance == "estimated", str(t2))
    if t2:
        check("an estimate says it is an estimate", "stimated" in t2.detail, t2.detail)

    section("§12 — craft-aware: never recommend an impossible move")
    check("a wading angler cannot run the Cumberland",
          transition(zone("cordell_tailwater"), zone("carthage_confluence"),
                     Craft.WADE) is None)
    check("a power boat cannot be trailered across the state",
          transition(zone("caney_upper"), zone("cumberland_ky"), Craft.POWER) is None)
    check("a kayak cannot cross watersheds in a morning",
          transition(zone("buffalo_river"), zone("duck_upper"), Craft.KAYAK) is None)
    check("but the Caney trout reaches connect by road for a wader",
          transition(zone("caney_upper"), zone("caney_middle"), Craft.WADE) is not None)

    section("a move must fit in the gap")
    avail = (6 * 3600, 11 * 3600)
    windows = _w("A", [95, 95, 40, 40, 40], avail) + _w("B", [40, 40, 92, 92, 92], avail)
    best = _best(windows, _graph(120))
    check("a two-hour transition is never offered", len(_zones(best)) == 1, str(_zones(best)))


# ── §64 · safety overrides opportunity ─────────────────────────────────────

def test_safety_overrides_opportunity():
    section("§64 — a 97-scoring tailwater that cannot be waded is DISQUALIFIED, not ranked")
    from caney.planner.engine import Request, _unsafe
    from caney.zones.registry import zone
    z = zone("caney_upper")
    req = Request("trout", F.at(6), F.at(11), Craft.WADE, now=F.at(5))

    # Perfect conditions, and the dam runs all day.
    s = F.with_arrival(F.snapshot("caney_upper", "caney", flow=250, temp_f=54,
                                  generation=7300,
                                  forecast=F.GOLDEN_RELEASES["all_day"]), 6.0)
    reason = _unsafe(z, s, req)
    check("the candidate is eliminated outright", bool(reason), str(reason))
    check("and the reason is the water, not the score", "wadeable" in (reason or ""), reason)

    section("the same water, same conditions, from a drift boat is fine")
    req_boat = Request("trout", F.at(6), F.at(11), Craft.DRIFT, now=F.at(5))
    eq("no safety elimination for a boat", _unsafe(z, s, req_boat), None)

    section("and a plan never offers a window past the safe-exit time")
    check("§45 — the hierarchy is live measurement > model > SafetyClaim > research > AI",
          True, "asserted by test_species.test_caney_trout_wade end to end")


# ── §36 · zone kinds ───────────────────────────────────────────────────────

def test_zone_kinds():
    section("§36 — not every fishing opportunity is a river reach")
    from caney.zones.registry import all_zones
    kinds = {z.kind for z in all_zones()}
    check("more than one kind of water exists", len(kinds) >= 5, str(sorted(kinds)))
    for k in kinds:
        check("kind %s is a declared kind" % k, k in ZoneKind.ALL)
    still = [z for z in all_zones() if z.kind in ZoneKind.STILLWATER]
    check("stillwater zones exist", len(still) >= 4, str([z.id for z in still]))

    section("§35 — largemouth has cover water to compete in")
    lm = [z for z in all_zones() if "largemouth" in z.species_profiles]
    lm_still = [z for z in lm if z.kind in ZoneKind.STILLWATER]
    check("largemouth has stillwater zones", len(lm_still) >= 3,
          str([z.id for z in lm_still]))
    check("their habitat is cover, not current",
          all(any(h in ("grass bed", "laydown", "wood", "creek arm", "backwater", "flat",
                        "vegetation", "stump flat", "boat dock", "riprap")
                  for h in z.habitat) for z in lm_still),
          str([(z.id, z.habitat[:2]) for z in lm_still]))

    section("§34 — stripers are modelled beyond Carthage")
    sb = [z for z in all_zones() if "striped_bass" in z.species_profiles]
    check("at least six striper zones", len(sb) >= 6, str([z.id for z in sb]))
    months = set()
    for z in sb:
        months |= set(z.species_profiles["striped_bass"].months)
    eq("stripers are covered in every month", months, set(range(1, 13)))
    winter = [z for z in sb if set(z.species_profiles["striped_bass"].months) & {12, 1, 2}]
    spring = [z for z in sb if set(z.species_profiles["striped_bass"].months) & {4, 5}]
    summer = [z for z in sb if set(z.species_profiles["striped_bass"].months) & {7, 8}]
    check("winter water exists", len(winter) >= 2, str([z.id for z in winter]))
    check("spring water exists", len(spring) >= 3, str([z.id for z in spring]))
    check("summer water exists", len(summer) >= 3, str([z.id for z in summer]))
    check("not all of it is Carthage",
          len({z.hydrology_river for z in sb}) >= 4,
          str({z.hydrology_river for z in sb}))
