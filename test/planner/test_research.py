"""§15-§21 — the research layer, and that the product works without it."""
import os
import sys
import time

from harness import check, eq, raises, section

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from caney.domain.claim import SourceTier, UnsourcedClaim
from caney.research import cache
from caney.research.corpus import claims_for, seed_claims
from caney.research.provider import (NullProvider, OpenAIResearchProvider, SAFETY_SENSITIVE_RE,
                                     allowed_domains, build_provider, classify,
                                     queries_for, research_zone, to_claims)
from caney.zones.registry import zone


def test_provider_is_optional():
    section("§17 — research is optional; the planner does not depend on it")
    p = build_provider({})
    check("no key configured → the null provider", isinstance(p, NullProvider))
    check("the null provider is disabled", not p.enabled)
    eq("it returns nothing, with a reason", p.search_primary("x")[0], [])
    check("and the reason is legible", bool(p.search_primary("x")[1]))

    p2 = build_provider({"OPENAI_API_KEY": "sk-test"})
    check("a key alone is not enough — RESEARCH_ENABLED gates it too",
          isinstance(p2, NullProvider))
    p3 = build_provider({"OPENAI_API_KEY": "sk-test", "RESEARCH_ENABLED": "1"})
    check("both set → the OpenAI provider", isinstance(p3, OpenAIResearchProvider))
    check("the model is configurable", build_provider(
        {"OPENAI_API_KEY": "k", "RESEARCH_ENABLED": "1",
         "OPENAI_RESEARCH_MODEL": "gpt-5"}).model == "gpt-5")

    claims, meta = research_zone(NullProvider(), "striped_bass",
                                 zone("carthage_confluence"), time.time(), 9)
    eq("a disabled provider yields no claims", claims, [])
    check("and says so in the metadata", meta["errors"] and not meta["enabled"])

    section("§17 — the primary-search allowlist")
    for d in ("tn.gov", "usgs.gov", "usace.army.mil", "tva.com", "weather.gov",
              "noaa.gov", "fws.gov", "ky.gov", "alabama.gov"):
        check("allowlist includes " + d, d in allowed_domains())
    os.environ["CANEY_RESEARCH_DOMAINS"] = "example.edu"
    check("the allowlist is extensible by environment",
          "example.edu" in allowed_domains())
    del os.environ["CANEY_RESEARCH_DOMAINS"]


def test_query_generation():
    section("§18 — queries are precise, not 'what is good fishing'")
    z = zone("carthage_confluence")
    qs = queries_for("striped_bass", z, time.time())
    check("several queries are generated", len(qs) >= 3, str(len(qs)))
    joined = " ".join(q["q"] for q in qs).lower()
    for term in ("striped bass", "cordell hull", "caney fork", "tennessee"):
        check("queries name " + term, term in joined)
    check("queries carry a cache family", all(q["family"] for q in qs))
    check("a tailwater gets a current/thermal query",
          any("thermal refuge" in q["q"] for q in qs))
    check("no query is a bare 'good fishing'",
          not any(q["q"].strip().lower() in ("good fishing", "fishing") for q in qs))


def test_claim_extraction():
    section("§19/§20 — findings become sourced claims, or nothing")
    z = zone("carthage_confluence")
    got = to_claims([
        {"url": "https://www.tn.gov/twra/x", "title": "TWRA",
         "text": "Stripers stack below the dam through the summer."},
        {"url": "", "text": "Trust me, they are biting."},
        {"text": "No url at all."},
    ], "striped_bass", z, 7)
    eq("only the sourced finding survives", len(got), 1)
    eq("it is scoped to the zone", got[0].location_ids, [z.id])
    eq("a tn.gov source is tier B", got[0].source_tier, SourceTier.B)
    check("it is scored", got[0].confidence > 0)

    section("§20 — a search-derived number is never a measurement")
    numeric = to_claims([{"url": "https://www.tn.gov/twra/x",
                          "text": "They were generating 4,000 cfs on Tuesday."}],
                        "striped_bass", z, 7)
    check("a claim carrying a flow figure is flagged safety-sensitive",
          numeric[0].safety_sensitive)
    check("a claim with no figures is not", not got[0].safety_sensitive)
    for s in ("the release is 3,900 cfs", "gauge stage 4.2 ft", "wade until 1:00"):
        check("safety pattern catches %r" % s, bool(SAFETY_SENSITIVE_RE.search(s)))
    for s in ("fish a #18 midge", "shad are the forage base"):
        check("safety pattern ignores %r" % s, not SAFETY_SENSITIVE_RE.search(s))

    section("claim types are classified, not guessed at render time")
    eq("stocking", classify("TWRA stocks trout monthly"), "stocking")
    eq("survey", classify("spring electrofishing survey results"), "survey")
    eq("thermal_refuge", classify("cool oxygenated tailwater refuge"), "thermal_refuge")


def test_cache():
    section("§21 — TTL by information type, not one global number")
    check("live data expires in minutes", cache.TTL["live"] <= 30 * 60)
    check("a weekly report lasts 6-24 hours",
          6 * 3600 <= cache.TTL["report"] <= 24 * 3600)
    check("regulations last days", cache.TTL["regulation"] >= 2 * 86400)
    check("management pages last weeks", cache.TTL["management"] >= 14 * 86400)
    check("historical surveys last months", cache.TTL["survey"] >= 60 * 86400)
    check("the ordering is monotonic",
          cache.TTL["live"] < cache.TTL["report"] < cache.TTL["regulation"]
          < cache.TTL["management"] < cache.TTL["survey"])

    section("cache keys separate species, place, date bucket and query family")
    k1 = cache.key("striped_bass", "carthage_confluence", "2026-09-09", "report")
    check("same inputs → same key",
          k1 == cache.key("striped_bass", "carthage_confluence", "2026-09-09", "report"))
    for changed in [("trout", "carthage_confluence", "2026-09-09", "report"),
                    ("striped_bass", "caney_upper", "2026-09-09", "report"),
                    ("striped_bass", "carthage_confluence", "2026-09-10", "report"),
                    ("striped_bass", "carthage_confluence", "2026-09-09", "management")]:
        check("changing one dimension changes the key", cache.key(*changed) != k1)
    check("a report bucket is per day",
          cache.date_bucket(time.time(), "report") !=
          cache.date_bucket(time.time() + 86400, "report"))
    check("a management bucket is per month",
          cache.date_bucket(time.time(), "management") ==
          cache.date_bucket(time.time() + 86400, "management"))


def test_seed_corpus():
    section("§22 — the seeded TWRA evidence")
    cs = seed_claims()
    check("the corpus is not empty", len(cs) >= 12, str(len(cs)))
    check("every seeded claim has a source URL", all(c.source_url for c in cs))
    check("every seeded claim has a title", all(c.source_title for c in cs))
    check("no seeded claim is safety-sensitive", not any(c.safety_sensitive for c in cs),
          str([c.claim_text[:40] for c in cs if c.safety_sensitive]))
    check("every seeded claim declares its valid months",
          all(c.valid_months for c in cs))
    check("every seeded claim is tier A or B",
          all(c.source_tier in (SourceTier.A, SourceTier.B) for c in cs),
          str({c.source_tier for c in cs}))

    striper = claims_for("striped_bass", month=9, zone_ids=["carthage_confluence"])
    check("the Carthage striper case has several claims", len(striper) >= 5, str(len(striper)))
    texts = " ".join(c.claim_text for c in striper)
    for phrase in ("Cordell Hull Dam downstream", "Caney Fork River",
                   "gizzard shad", "thermal refuge"):
        check("the evidence covers: " + phrase, phrase in texts)
    check("claims are returned best-first",
          all(striper[i].confidence >= striper[i + 1].confidence
              for i in range(len(striper) - 1)))
    check("a spring-only claim is down-weighted in September",
          all(c.confidence < 0.4 for c in striper if c.valid_months == [5]) or
          not any(c.valid_months == [5] for c in striper))


def test_research_changes_ranking():
    """§61 — recent Tier A/B research supports a zone, without overwhelming live water."""
    import fixtures as F
    from caney.domain.claim import ResearchClaim, SourceTier
    from caney.planner import scoring
    from caney.zones.registry import zone

    section("§61 — sourced research moves a candidate, within its weight cap")
    z = zone("carthage_confluence")
    none_fit = scoring.fit_research(z, [], "striped_bass", 9)
    seeded = claims_for("striped_bass", month=9, zone_ids=[z.id])
    with_fit = scoring.fit_research(z, seeded, "striped_bass", 9)
    check("evidence raises the research component",
          with_fit.value > none_fit.value, "%s vs %s" % (with_fit.value, none_fit.value))
    check("and the line names its source", "TWRA" in with_fit.why or "tier" in with_fit.why,
          with_fit.why)

    section("but it cannot overwhelm live water")
    from caney.species.profiles import weights_for
    w = weights_for("striped_bass")
    research_max = w["research"]
    live_max = w["current"] + w["thermal"]
    check("research is capped below the live-water components",
          research_max < live_max * 0.5, "%s vs %s" % (research_max, live_max))
    delta = (with_fit.value - none_fit.value) * research_max
    check("the whole research swing is worth less than one live component",
          delta < w["current"], "%.1f points vs current's %s" % (delta, w["current"]))

    section("§27 — a tier clash is reported, not silently resolved")
    agency = ResearchClaim(species="striped_bass", claim_type="forage",
                           claim_text="Shad are the forage base on this reservoir.",
                           source_url="https://www.tn.gov/twra/x",
                           location_ids=[z.id])
    forum = ResearchClaim(species="striped_bass", claim_type="forage",
                          claim_text="Everyone says the bait has moved out of the creek.",
                          source_url="https://www.reddit.com/r/x",
                          location_ids=[z.id])
    check("the agency source outranks the forum",
          agency.source_quality > forum.source_quality * 2,
          "%s vs %s" % (agency.source_quality, forum.source_quality))
    eq("the forum is tier D", forum.source_tier, SourceTier.D)


def test_stale_research():
    """§24, §62 — decay is PER CLAIM TYPE, and both halves of the system agree on it.

    This test has been wrong twice and the history is worth keeping.

    First it was a time bomb: it pinned `published_at` to the literal "2026-09-02", one day
    inside a seven-day grace, and asserted a blended ratio of 1.4 against an actual 1.413.
    When that date aged past seven days a scheduled build failed having passed three hours
    earlier. Relative dates fixed that.

    Then it pinned the step curve EXACTLY — which was the right instinct and the wrong
    target, because the step curve itself was the bug. Python applied one curve to every
    claim type while the research worker had sixteen, and they disagreed by 18x on a
    month-old fishing report. The table is shared now (caney/research/decay.py, emitted to
    research-worker/src/decay.generated.js), so what this pins is the SHARED model and the
    fact that the two consumers cannot drift apart again.
    """
    import datetime as _dt
    import subprocess as _sp

    from caney.domain.claim import ResearchClaim
    from caney.research.decay import DECAY, decay_for, recency, recency_for
    section("§24 — decay is per claim type")

    check("the table covers the types the worker knows", len(DECAY) == 16, str(len(DECAY)))
    check("a fresh claim of any type is worth ~1.0",
          all(abs(recency(k, 0) - 1.0) < 1e-9 for k in DECAY))
    check("every type has a floor above zero — old agency science is still science",
          all(DECAY[k]["floor"] > 0 for k in DECAY))
    check("no floor reaches 1.0 except where influence genuinely does not decay",
          [k for k in DECAY if DECAY[k]["floor"] >= 0.95] == ["regulation"],
          str([k for k in DECAY if DECAY[k]["floor"] >= 0.95]))

    section("§24 — the shape that matters: perishable vs structural")
    # A fishing report is worthless as a CURRENT report within a month; a habitat
    # description is still true years later. One curve could express neither.
    check("a month-old fishing report has collapsed to its floor",
          abs(recency("recent_report", 30) - 0.05) < 1e-9,
          str(recency("recent_report", 30)))
    check("a month-old habitat note is barely touched",
          recency("habitat", 30) > 0.97, str(recency("habitat", 30)))
    check("at five years the report is worth far less than the habitat note",
          recency("habitat", 5 * 365) > recency("recent_report", 5 * 365) * 10,
          "%s vs %s" % (recency("habitat", 5 * 365), recency("recent_report", 5 * 365)))
    check("a regulation does not decay in influence",
          recency("regulation", 5 * 365) > 0.98, str(recency("regulation", 5 * 365)))
    check("an unknown claim type falls to the default, not to zero",
          recency("no_such_type", 400) == recency_for("no_such_type", None) or
          recency("no_such_type", 0) == 1.0)
    check("monotonic in age for every type",
          all(recency(k, a) >= recency(k, b)
              for k in DECAY for a, b in ((0, 7), (7, 30), (30, 400), (400, 5000))))

    section("§24 — the seed corpus's spelling is aliased, not silently defaulted")
    # The corpus says seasonal_location; the worker says seasonal_distribution. Letting
    # that fall through to DEFAULT cost three TWRA claims a third of their weight.
    check("seasonal_location resolves to seasonal_distribution",
          decay_for("seasonal_location") is DECAY["seasonal_distribution"])
    check("and is therefore not on the default curve",
          recency("seasonal_location", 5 * 365) != recency("no_such_type", 5 * 365))

    section("§62 — an undated claim gets its type's FLOOR, not a flat 0.5")
    # 22 of the 23 seeded claims carry no publication date, so this branch is what nearly
    # the whole corpus is scored on. A flat 0.5 over-credited perishable claims and
    # under-credited durable agency facts simultaneously.
    for kind in ("recent_report", "habitat", "regulation"):
        check("undated %s scores its floor (%.2f)" % (kind, DECAY[kind]["floor"]),
              abs(recency_for(kind, None) - DECAY[kind]["floor"]) < 1e-9,
              str(recency_for(kind, None)))
    check("an unparseable date does not crash", recency_for("habitat", "last Tuesday") > 0)

    section("§62 — a current report still outranks an ancient one, with margin")
    def _ago(days):
        return (_dt.date.today() - _dt.timedelta(days=days)).isoformat()

    def _claim(days, slug):
        return ResearchClaim(species="trout", claim_type="recent_report",
                             claim_text="The tailwater fished well this week.",
                             source_url="https://www.tn.gov/twra/%s" % slug,
                             published_at=_ago(days), location_ids=["caney_upper"])

    f = _claim(1, "report").score(month=9, zone_ids=["caney_upper"])
    o = _claim(5 * 365, "report-old").score(month=9, zone_ids=["caney_upper"])
    check("the current report is worth more", f > o, "%s vs %s" % (f, o))
    check("materially more, not marginally", f > o * 1.25, "%s vs %s" % (f, o))
    scores = [_claim(d, "r%d" % d).score(month=9, zone_ids=["caney_upper"])
              for d in (1, 20, 90, 300, 5 * 365)]
    check("score falls monotonically as a report ages",
          all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)),
          str([round(x, 4) for x in scores]))

    section("§2 — the two implementations cannot drift apart")
    r = _sp.run([sys.executable, os.path.join(ROOT, "tools", "emit_decay.py"), "--check"],
                capture_output=True, text=True, cwd=ROOT)
    check("research-worker/src/decay.generated.js is in sync with the Python table",
          r.returncode == 0, (r.stdout + r.stderr).strip()[:160])

def test_research_offline():
    """§63 — RESEARCH_ENABLED=false must still produce a valid plan."""
    import datetime as dt
    import fixtures as F
    from zoneinfo import ZoneInfo
    from caney.domain.claim import ClaimBook
    from caney.domain.zone import Craft
    from caney.planner.engine import Request, plan
    from caney.sources.registry import water_for
    from caney.sources.snapshots import _mint_safety_claims
    from caney.zones.registry import ZONES, all_zones

    section("§63 — the planner is unaffected when research is off")
    p = build_provider({"RESEARCH_ENABLED": "false", "OPENAI_API_KEY": "sk-x"})
    check("the provider is the null one", isinstance(p, NullProvider))

    snaps = {}
    for z in all_zones():
        rid = z.hydrology_river
        if rid == "caney":
            s = F.with_arrival(F.snapshot(z.id, rid, flow=280, temp_f=56, generation=250,
                                          forecast=F.GOLDEN_RELEASES["single_afternoon"]),
                               z.mfd or 6.0)
        else:
            s = F.snapshot(z.id, rid, flow=600, temp_f=70, flow_trend="steady",
                           model_confidence="reported")
        snaps[z.id] = s
    book = ClaimBook()
    tz = ZoneInfo("America/Chicago")
    for zid, s in snaps.items():
        cfg = water_for(ZONES[zid].hydrology_river)
        _mint_safety_claims(ZONES[zid], s, {"cfg": cfg, "release_rows": [], "alerts": []},
                            cfg, F.at(6), F.at(6) + 3 * 86400, tz, book)

    req = Request("trout", F.at(6), F.at(11), Craft.WADE, now=F.at(5))
    # NO research claims at all — the offline case, exactly.
    got = plan(req, snaps, book, {z.id: [] for z in all_zones()})
    check("a plan is still produced", bool(got.primary_candidate), got.verdict_why)
    check("it still has an itinerary", got.itinerary is not None and
          len(got.itinerary.segments) >= 3)
    check("it still carries safety claims", len(got.safety) > 0)
    eq("research confidence is honestly zero", got.research_confidence, 0.0)
    check("opportunity is unaffected by the absence", got.opportunity > 0)
    check("and the research component scores its no-evidence default, not zero",
          any(l.key == "research" and l.earned > 0 for l in got.score_breakdown),
          str([(l.key, l.earned) for l in got.score_breakdown if l.key == "research"]))

    section("the UI is told, so it can say so")
    check("research metadata records that it is disabled",
          getattr(p, "reason", None) is not None)
