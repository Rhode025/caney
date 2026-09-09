# Research Intelligence worker

A Cloudflare Worker that turns web search into **sourced, normalised `ResearchClaim`s** and
stores them so the planner can read them without ever holding an API key.

It does not answer fishing questions. It returns evidence.

## Why a worker at all

Three reasons, in order of importance:

1. **The key never reaches a browser** (§18, §44). `OPENAI_API_KEY` is a Worker secret. The
   site is static; anything client-side that searched would have to ship a credential.
2. **Research must be refreshable independently of the build** (§16, §42). The hourly site
   build is not a research schedule. The worker owns its own cache and TTLs and can be
   asked for fresh evidence between builds.
3. **Cost and abuse control live in one place** (§43, §44). Rate limits, per-day query
   caps, query-scope validation and the audit trail are all here rather than duplicated in
   every caller.

## Storage: D1, with KV in front

**D1** (SQLite) holds the claims and the audit trail. Research claims need *queryable
metadata* — "every striped-bass claim for these zone ids, valid this month, above this
tier, not stale" is a `WHERE` clause, and in KV it would be a manually maintained index
that goes wrong the first time a write fails halfway. Dedupe (§78) is a natural key. The
audit trail (§77) is append-only rows.

**KV** holds only the hot response cache, keyed by the query hash, because KV's native TTL
and edge reads are exactly right for "same question, same day, don't pay again" and nothing
about that needs querying.

Trip outcomes, when they move off-device, belong in D1 for the same reason: the scoreboard
asks `species × zone × season × conditions → outcome`, which is a query.

## Endpoints

```
GET  /health                 status, counts, cache hit rate, spend so far today
POST /research               {species, zone_ids[], date, context{}} -> {claims[], meta}
POST /refresh                force a refresh for one (species, zone) — rate limited harder
GET  /claims?species=&zone=  read stored claims without triggering a search
```

`POST /research` never fetches a URL the caller supplies. The only outbound request it can
make is to the configured model provider, with a query IT built from a validated species
and a validated zone id (§44).

## Configuration

```
wrangler secret put OPENAI_API_KEY
```

```toml
[vars]
OPENAI_RESEARCH_MODEL = "gpt-4.1-mini"
RESEARCH_ENABLED = "1"
MAX_QUERIES_PER_DAY = "400"
MAX_QUERIES_PER_ZONE_DAY = "12"
```

Bindings: `DB` (D1), `CACHE` (KV).

## Local development

```bash
cd research-worker
npx wrangler d1 create caney-research         # once; put the id in wrangler.toml
npx wrangler d1 execute caney-research --local --file=./schema.sql
npx wrangler dev
node test.mjs                                  # pure-function tests, no network
```

## Failure behaviour

**Research failure must not break the planner** (§43, §58, §63). Every endpoint returns
`200` with `{claims: [], meta: {error, degraded: true}}` rather than an error status, and
`caney/research/provider.py::HttpResearchProvider` treats any failure as "no claims" — the
deterministic planner is unaffected and the UI says research is unavailable.
