"""Domain invariants: unknown is not zero, claims are sourced, weights are the spec."""
from harness import check, eq, near, raises, section

from caney.domain.claim import (ClaimBook, ResearchClaim, SafetyKind, SourceTier,
                                UnsourcedClaim, claim_numbers, tier_for_domain)
from caney.domain.observation import DataState, Observation, UnknownValue, budget_for
from caney.species.profiles import (COMPONENT_LABEL, SPECIES, WEIGHTS, validate,
                                    weights_for)


def test_observations():
    section("§3.4 — unknown never equals zero")
    u = Observation.unknown("cfs", "USACE")
    check("an unknown observation is not ok", not u.ok)
    eq("an unknown observation has no value", u.value, None)
    eq("or_else forces the caller to name the fallback", u.or_else(-1), -1)
    eq("a known observation returns its value", Observation.known(0, "cfs").or_else(-1), 0)
    check("a REAL zero is a real reading",
          Observation.known(0, "cfs").ok and Observation.known(0, "cfs").value == 0)
    eq("age_label refuses to age a value that does not exist", u.age_label(), "unknown")
    raises("require() on an unknown raises rather than substituting", UnknownValue,
           u.require, "wade window")

    section("freshness budgets demote rather than delete")
    old = Observation.known(3900, "cfs", observed_at=0)
    eq("a value past its budget becomes stale", old.with_staleness(3600).state, DataState.STALE)
    check("a stale value keeps its number", old.with_staleness(3600).value == 3900)
    check("a stale value loses confidence",
          old.with_staleness(3600).confidence < old.confidence)
    eq("epoch 0 is a time, not an absence",
       Observation.known(1, "cfs", observed_at=0).age_s(3600), 3600)
    check("release forecasts get a longer budget than flow",
          budget_for("release_forecast") > budget_for("flow"))

    section("Observation.known(None) refuses to invent")
    eq("known(None) degrades to unknown", Observation.known(None, "cfs").state,
       DataState.UNKNOWN)


def test_claims():
    section("§3.3 — safety claims are immutable and scoped")
    b = ClaimBook()
    c = b.add(SafetyKind.SAFE_EXIT, "caney_upper",
              "Be out of the water at Upper Caney Fork by 1:45 PM.", bound="earliest")
    eq("a claim licenses exactly the numbers it asserts", c.numbers, ("1:45",))
    check("a claim id is stable across builds",
          b.add(SafetyKind.SAFE_EXIT, "caney_upper",
                "Be out of the water at Upper Caney Fork by 1:45 PM.").id == c.id)
    b.add(SafetyKind.FLOW, "cheatham_tailrace", "Flow is 9,000 cfs.")
    eq("licensed numbers are per zone", b.allowed_numbers("caney_upper"), {"1:45"})
    check("another zone's numbers do not leak in",
          "9000" not in b.allowed_numbers("caney_upper"))
    raises("an unknown safety kind is refused", ValueError,
           b.add, "vibes", "caney_upper", "It feels fine.")
    eq("explicit numbers override text extraction",
       b.add(SafetyKind.FLOW, "z", "Flow at USGS 03424860 is 1,500 cfs (50 min ago).",
             numbers=("1500",)).numbers, ("1500",))
    eq("thousands separators normalise", claim_numbers("3,982 cfs"), ("3982",))
    eq("a sentence-ending period is punctuation", claim_numbers("Try a #18."), ("18",))

    section("§20 — no source, no claim")
    raises("a research claim with no source cannot be constructed", UnsourcedClaim,
           ResearchClaim, species="trout", claim_text="they are biting", source_url="")
    rc = ResearchClaim(species="striped_bass", claim_type="seasonal_location",
                       claim_text="x", source_url="https://www.tn.gov/twra/x",
                       location_ids=["carthage_confluence"])
    eq("an agency domain resolves to tier B", rc.source_tier, SourceTier.B)
    eq("usgs.gov is tier A", tier_for_domain("waterservices.usgs.gov"), SourceTier.A)
    eq("a forum is tier D", tier_for_domain("reddit.com"), SourceTier.D)
    check("tier A outranks tier D",
          SourceTier.ORDER[SourceTier.A] > SourceTier.ORDER[SourceTier.D])
    on = rc.score(month=7, zone_ids=["carthage_confluence"])
    off = ResearchClaim(species="striped_bass", claim_type="seasonal_location",
                        claim_text="x", source_url="https://www.tn.gov/twra/x",
                        location_ids=["carthage_confluence"], valid_months=[1]
                        ).score(month=7, zone_ids=["carthage_confluence"])
    check("an out-of-season claim scores far lower", off < on * 0.3, "%s vs %s" % (off, on))
    elsewhere = ResearchClaim(species="striped_bass", claim_type="seasonal_location",
                              claim_text="x", source_url="https://www.tn.gov/twra/x",
                              location_ids=["duck_upper"]
                              ).score(month=7, zone_ids=["carthage_confluence"])
    check("a claim about other water scores lower", elsewhere < on, "%s vs %s" % (elsewhere, on))


def test_weights():
    section("§13 — the published weight table, pinned exactly")
    eq("issues found by validate()", validate(), [])
    SPEC = {
        "striped_bass": {"current": 25, "thermal": 20, "seasonal": 15, "research": 15,
                         "forage": 10, "light": 7, "weather": 5, "moon": 3},
        "smallmouth": {"flow": 20, "thermal": 15, "clarity": 15, "habitat": 15,
                       "weather": 10, "research": 10, "current": 7, "access": 5, "moon": 3},
        "largemouth": {"thermal": 20, "habitat": 20, "level": 15, "weather": 15,
                       "forage": 15, "light": 7, "current": 5, "moon": 3},
        "trout": {"generation": 30, "thermal": 20, "hatch": 15, "clarity": 10,
                  "weather": 8, "research": 7, "access": 7, "moon": 3},
    }
    for sp, want in SPEC.items():
        eq("weights match the spec: " + sp, weights_for(sp), want)
        eq("weights sum to 100: " + sp, sum(want.values()), 100)
    eq("exactly four species", set(SPECIES), set(SPEC))

    section("§14 — the moon is capped, structurally")
    for sp in SPECIES:
        check("moon is 3 points or fewer: " + sp, WEIGHTS[sp]["moon"] <= 3)
        others = 100 - WEIGHTS[sp]["moon"]
        check("a perfect moon cannot outweigh everything else: " + sp,
              WEIGHTS[sp]["moon"] < others * 0.05)
    for sp, w in WEIGHTS.items():
        for k in w:
            check("every weighted component has a label: %s.%s" % (sp, k),
                  k in COMPONENT_LABEL)
