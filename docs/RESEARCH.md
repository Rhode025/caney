# The research layer

> **2.1.** The seeded corpus below is still the offline floor. What is new is the
> **Research Intelligence worker** (`research-worker/`) — a Cloudflare Worker that holds
> the key, does the searching, normalises findings into claims, decays them by type,
> dedupes them and keeps an audit trail. Sections 1–8 describe the model; section 9
> describes the service.

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


---

## 9. The Research Intelligence worker (§16, §17, §44)

`research-worker/`. A Cloudflare Worker, deployed independently of the static site.

### Why a service rather than a library call

1. **The key never reaches a browser.** `OPENAI_API_KEY` is a Worker secret.
2. **Research refreshes independently of the build.** The hourly site build is not a
   research schedule; the worker owns its own cache and TTLs.
3. **Cost and abuse control live in one place** — rate limits, per-zone-per-day caps, a
   global daily cap, query-scope validation and the audit trail.

### Endpoints

```
GET  /health                 status, claim count, cache hit rate, spend today
POST /research               {species, zone_ids[], date, context{}} -> {claims[], disagreements[], meta}
POST /refresh                force a refresh (rate-limited harder)
GET  /claims?species=&zone=  read stored claims without triggering a search
```

**It never fetches a URL a caller supplies.** The only outbound request is to the model
provider, with a query the worker built from a validated species key (one of four) and
validated zone ids (`^[a-z0-9_]{3,48}$`, at most six).

### Storage: D1, with KV in front (§76)

**D1** holds claims and the audit trail. Every question we ask of this data is a query —
"every striped-bass claim for these zones, valid this month, above this tier, not stale" is
a `WHERE` clause, and in KV it would be a hand-maintained index that goes wrong the first
time a write fails halfway. Dedupe is a natural unique index; the audit trail is
append-only rows.

**KV** holds only the hot response cache, keyed by query hash, because KV's native TTL and
edge reads are exactly right for "same question, same day, don't pay again" and nothing
about that needs querying.

Trip outcomes, when they move off-device, belong in D1 for the same reason: the scoreboard
asks `species × zone × season × conditions → outcome`.

### Decay by claim type (§24)

`research-worker/src/claims.js::DECAY`. `ttlSeconds` is when we go looking again;
`halfLifeDays` is how fast influence decays meanwhile; `floor` is what it is always worth.

| claim type | TTL | half-life | floor |
|---|---|---|---|
| `recent_report` | 12 h | 5 d | 0.05 |
| `stocking` | 14 d | 500 d | 0.35 |
| `regulation` | **7 d** | — | **0.95** |
| `current_response`, `thermal_refuge`, `seasonal_distribution`, `migration` | 28 d | ~1200 d | 0.65 |
| `forage` | 45 d | 1100 d | 0.55 |
| `habitat`, `species_presence` | 90 d | 2200 d | 0.70 |
| `survey` | 180 d | 1800 d | 0.45 |

Regulations are the interesting case: they do **not** decay in influence — a regulation is
either current or it is wrong — but they must be rechecked, so the TTL is short and the
floor is high.

§62 falls out of this: a five-year-old field report is worth `0.05`; a current one `>0.85`.

### Refresh policy (§42)

The worker searches only when: no claims are held, the held claims are stale for their
type, the date or season has materially changed, a new candidate zone enters the ranking,
or the user explicitly refreshes. Otherwise it answers from the store, and the response
says `source: "store"`.

### Cost controls (§43)

Tracked per UTC day in `budget`: queries, tokens in/out, cache hits. Capped by
`MAX_QUERIES_PER_DAY` (default 400) and `MAX_QUERIES_PER_ZONE_DAY` (default 12). Over cap,
the worker returns what it holds with `degraded: true` — it does not fail.

### Audit trail (§77)

Every search cycle records the query, the provider and model, latency, the source URLs
returned, how many claims were accepted, how many rejected **and why**, and tokens spent.
It does **not** retain copies of the pages — normalised claims and source metadata only.

### Disagreement (§27)

`disagreements()` reports when sources of different authority make claims of the same type
about the same water. It never silently picks one. The plan surfaces it:

> *Research confidence reduced: sources of different authority disagree about forage on
> this water. The agency source is weighted higher.*

### Failure behaviour (§43, §58, §63)

Every endpoint answers **200** with `{claims: [], meta: {degraded: true, error}}` rather
than an error status, and `HttpResearchProvider` treats any failure as "no claims". Research
going down must never take the planner with it —
`test_research.test_research_offline` runs the whole pipeline with zero claims and asserts
a valid plan comes out.

### Configuring the planner to use it

```bash
export RESEARCH_ENABLED=1
export CANEY_RESEARCH_ENDPOINT=https://caney-research.<subdomain>.workers.dev
python3 planner.py
```

Order of preference in `build_provider()`: the worker, then a direct OpenAI call if only
`OPENAI_API_KEY` is set, then `NullProvider` — and the planner is completely unaffected.
