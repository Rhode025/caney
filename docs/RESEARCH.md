# The research layer

Deterministic water and weather tell you *whether* it is fishable. They do not tell you
that TWRA manages the Cordell Hull tailwater as the striped-bass concentration for the
Cumberland system. That is what this layer is for.

**It is optional.** With no `OPENAI_API_KEY`, or with `RESEARCH_ENABLED` unset,
`build_provider()` returns `NullProvider` and the planner is unaffected — every test in
`test/planner/` runs that way, and the evidence drawer says *"research off"*.

---

## 1. Source tiers (§16)

| tier | what | weight | examples |
|---|---|---|---|
| **A** | direct official instrument / agency data | 1.00 | USGS, USACE CWMS, TVA, NOAA/NWS |
| **B** | primary fisheries research & management | 0.85 | TWRA species and Where-to-Fish pages, weekly reports, electrofishing and creel surveys, stocking reports, management plans, USFWS, university fisheries studies |
| **C** | recent local field intelligence | 0.50 | guides, fly shops, marinas, local outdoor publications |
| **D** | community intelligence | 0.25 | forums, Reddit, user trip logs |

Tier is **derived from the domain**, in `TIER_DOMAINS`, not asserted by whatever produced
the claim. Anything unrecognised is D. A lower tier may never override a higher one, and
nothing below A may ever supply an instrument reading.

## 2. No source, no claim (§20)

`ResearchClaim.__post_init__` raises `UnsourcedClaim` without a `source_url`. This is a
constructor invariant, not a review guideline: an unsourced claim is exactly what "the model
made it up" looks like in a dataclass, and it cannot be constructed.

A search-derived value may **never** become a canonical measurement.
`SAFETY_SENSITIVE_RE` marks any claim whose prose contains something shaped like a flow, a
stage, a generation time or a wade window; such a claim is kept for its language, flagged in
the evidence drawer, and **no code anywhere reads a number out of a `ResearchClaim`**.

## 3. Query generation (§18)

`queries_for(species, zone, when, snapshot)` builds several precise queries from the
species, the zone's own names, its dam, the state, the month and the season — plus a
temperature query when the water temperature is known. It never asks "what is good
fishing".

For `carthage_confluence` in September:

```
Striped bass Carthage Confluence Complex Cumberland River Caney Fork River
  Cordell Hull Dam Tennessee fisheries management habitat seasonal movement summer
Striped bass fishing report … Tennessee September 2026
Striped bass Cordell Hull Dam tailwater current generation thermal refuge Tennessee
Striped bass regulations creel limit length limit … Tennessee
```

## 4. Provider (§17)

```
ResearchProvider
  search_primary(query, domains, max_results)     Tier A/B — domain-filtered
  search_secondary(query, max_results)            everything else
```

`OpenAIResearchProvider` posts to the Responses API with the hosted `web_search` tool and
`filters.allowed_domains`. No SDK dependency — this repo is stdlib-only, so it posts JSON to
the REST endpoint. The system prompt requires an exact URL, a title and a close paraphrase
for every finding, and forbids restating a river flow, gauge stage, dam generation time or
wade window as fact.

Environment:

```
RESEARCH_ENABLED=1
OPENAI_API_KEY=…                 never written to disk, the cache, or any artefact
OPENAI_RESEARCH_MODEL=gpt-4.1-mini
CANEY_RESEARCH_DOMAINS=a.edu,b.gov      extends the allowlist
```

Default allowlist: `tn.gov tnwildlife.org usgs.gov usace.army.mil tva.com weather.gov
noaa.gov fws.gov ky.gov fw.ky.gov alabama.gov outdooralabama.com water.noaa.gov epa.gov`.

## 5. Caching (§21)

Keyed by `(species, geographic candidate, date bucket, query family)`, with a TTL chosen by
**information type**:

| family | TTL | date bucket |
|---|---|---|
| live instrument data | 15 min | per day |
| weekly fishing reports | 12 h | per day |
| regulations | 7 days | per ISO week |
| species management pages | 28 days | per month |
| historical surveys | 120 days | per month |

`cache.last_refreshed()` feeds the "research last refreshed" line in the evidence drawer.

## 6. The seeded corpus (§22)

`caney/research/corpus.py` ships 17 transcribed Tier-B claims so the Carthage case works
offline and can be a regression fixture. Every entry carries its URL, its title, its valid
months and the date it was retrieved; the scorer decays them and the live provider replaces
them with fresher claims of the same type when it runs.

The Carthage striper case, from TWRA:

* *"Striped bass are concentrated from Cordell Hull Dam downstream to the mouth of the
  Caney Fork River."*
* *"They are also abundant in the Caney Fork River and are usually found within 2 river
  miles from its confluence to the Cumberland River."*
* *"May is a great month to catch a trophy Striped Bass from the upper end of Old Hickory
  Reservoir near Carthage, Tennessee."*
* water temperature in the low-to-mid 60s, photoperiod and **water current** are the
  spawning cues.
* *"Great numbers of gizzard shad, threadfin shad, and skipjack herring continue to provide
  a forage base very conducive to a trophy-striped bass fishery."*
* TWRA stocks striped bass annually in Cordell Hull; the state record, 65 lb 6 oz, came
  from it in 2000.
* the Cordell Hull tailwater is a TN SWAP Conservation Opportunity Area for cold-tailwater
  habitat — the summer thermal refuge.

**Not one seeded claim carries a flow, a stage, a generation time or a wade cutoff.**
`test_research.py::test_seed_corpus` asserts that.

## 7. Extraction (§19)

Raw model prose never reaches the recommendation engine. `to_claims()` normalises each
finding into a `ResearchClaim`, classifies its `claim_type` by keyword, scopes it to the
zone that was searched, scores it, and drops anything without a usable source — including a
finding with no `url` key at all, which used to raise and would have taken a whole build
down on one malformed response.

## 8. How research reaches a score

`fit_research(zone, claims, species, month)` takes the top four claims that mention this
water, averages their confidence, and returns `0.35 + 0.9 × strength` capped at 1.0. It
contributes 15 points for stripers, 10 for smallmouth, 7 for trout, and 0 for largemouth
(whose column spends that weight on `forage / recent reports` instead). The breakdown line
names the count, the tiers and the best source — which is what appears under
**Recent research evidence** in the score breakdown, and links out from the evidence drawer.
