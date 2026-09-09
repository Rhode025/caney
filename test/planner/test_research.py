"""§15-§21 — the research layer, and that the product works without it."""
import os
import time

from harness import check, eq, raises, section

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
