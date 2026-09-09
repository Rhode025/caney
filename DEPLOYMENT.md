# Deployment

Three things ship, on two platforms.

| What | Where | Live |
|---|---|---|
| Static site + app | Cloudflare Pages | https://caney.pages.dev · app at `/app/` |
| Planner API | Cloudflare Worker (Python) | https://caney-api.steven-b9c.workers.dev |
| Research service | Cloudflare Worker | https://caney-research.steven-b9c.workers.dev |

## How to deploy

Cloudflare credentials live as **GitHub repository secrets** and are not on any developer
machine. That is why deployment is a workflow rather than a script:

```bash
gh workflow run workers.yml -f action=probe            # what can the token do?
gh workflow run workers.yml -f action=bootstrap        # create KV, attempt D1
gh workflow run workers.yml -f action=deploy-research
gh workflow run workers.yml -f action=deploy-api
gh workflow run workers.yml -f action=deploy-all
```

Pages deploys on push to master, hourly, and on manual dispatch (`deploy.yml`).

## Token capability, measured

`workers.yml -f action=probe` asks the Cloudflare API directly. As of the last run:

| Resource | Result |
|---|---|
| `workers/scripts` | **200** — Workers can be deployed |
| `storage/kv/namespaces` | **200** — KV can be created |
| `pages/projects` | **200** — Pages deploys |
| `d1/database` | **401** — *Authentication error* |

D1 is a **permission limit, not a design choice**. The token is a User API Token whose role
carries no D1 privilege; Cloudflare's own message is *"Contact account super admin to
change your permissions."*

---

# Machine-readable deployment checklist

Everything that is not done, why, and exactly what unblocks it.

```yaml
deployed:
  - id: PAGES
    what: static site, river pages, roadmap, and the v3 app at /app/
    url: https://caney.pages.dev
    status: live

  - id: RESEARCH_WORKER
    what: Research Intelligence service (§34, §97)
    url: https://caney-research.steven-b9c.workers.dev
    status: live
    bindings: { CACHE: kv/afe6706a296e4b0181fc170688ade2d9 }
    degraded:
      - reason: no OPENAI_API_KEY secret is set
        effect: health reports enabled=false; no live search runs
        fix: gh secret set OPENAI_API_KEY   # then wrangler secret put, see below
      - reason: no D1 binding
        effect: claim history and exact budget counting unavailable
        mitigation: daily and per-zone caps fall back to KV counters

  - id: API_WORKER
    what: the canonical planner (§4, §98)
    url: https://caney-api.steven-b9c.workers.dev
    status: live
    bindings: { PLANS: kv/d8101bfcb97f423d83e9ada04c66061e }
    verified:
      - POST /api/v3/plan returns a PlanEnvelope for all four species
      - all 77 upstream sources fetch with zero failures across three shards
      - warm latency 0.92s median, 1.39s p95
      - GET  /health reports tz_backend=builtin-us-rule (Pyodide has no tz database)
      - plans, snapshots and sessions persist to KV
      - stored plans contain no origin coordinates, only an ~11 km cell

blocked:
  - id: RES-02
    what: D1 for the research worker and for plan history
    blocked_by: the deploy token's role has no D1 privilege (401)
    unblock:
      - who: the Cloudflare account super admin
      - action: add "D1:Edit" to the token behind CLOUDFLARE_API_TOKEN,
                or issue a new token with Account / D1 / Edit
      - then: gh workflow run workers.yml -f action=bootstrap
      - then: uncomment the [[d1_databases]] block in research-worker/wrangler.toml
              and caney-api/wrangler.toml, insert the printed database_id, and
              apply research-worker/schema.sql
    impact_while_blocked: low. Caps are enforced from KV; plans and sessions are
      addressed by id, which KV serves. What is missing is QUERIES — "my last ten
      trips" — and exact counting under concurrency.

  - id: RES-03
    what: live primary-source research
    blocked_by: no OPENAI_API_KEY
    unblock:
      - npx wrangler secret put OPENAI_API_KEY --name caney-research
      - gh variable set RESEARCH_ENABLED --body 1     # for the Pages build
      - gh secret set OPENAI_API_KEY                  # for the Pages build
    impact_while_blocked: none for correctness. The planner is fully deterministic
      without it and every gate passes; the seeded TWRA/TDEC corpus still applies.
      research_status reports "disabled" rather than pretending.

  - id: API-02
    what: bind the research worker to the API privately (§35)
    blocked_by: nothing technical — waiting on RES-03 so the binding does something
    unblock:
      - uncomment the [[services]] block in caney-api/wrangler.toml
      - gh workflow run workers.yml -f action=deploy-api

  - id: API-03
    what: keeping the snapshot shards fresh
    status: RESOLVED, by three paths, because no single one is reliable
    the_bug: the Worker's own cron looked dead — wrangler printed
      `schedule: */5 * * * *` on every deploy and bundle age grew 865s, 966s, 1067s with
      no error anywhere. The build markers settled it: build_bundle writes
      build:last_start before doing anything else, and EVERY marker ever written said
      why="self". No "cron" marker had ever existed, which rules out "invoked and threw
      inside the body" and leaves "invoked with an arity the signature refused" — a
      TypeError at the call boundary leaves no marker, no log, no trace. Both handlers
      now take *args/**kwargs and find env by looking for an object carrying bindings.
      A why=cron marker appeared within two minutes.
    the_residual: it fires INTERMITTENTLY. Observed one landed build in seventeen
      minutes where three were due; the missing fires never reached build_bundle at all.
      Separately, GitHub's schedule trigger on refresh.yml had still not fired an hour
      after the workflow was added, which matches CLAUDE.md's existing note about
      scheduled runs here arriving 40-100 minutes late or never.
    so: three independent paths, and the reliable one is the third.
      1. the Worker cron, every 5 min, one shard per bucket — intermittent
      2. .github/workflows/refresh.yml, every 10 min, all three shards — unproven
      3. .github/workflows/deploy.yml, hourly and on every push — RELIABLE, it has been
         running all along
      Worst case is therefore an hour of staleness, and the freshness strip reports every
      signal's real age rather than assuming. A release forecast revises far more slowly.
    manual: python3 tools/refresh_api.py

  - id: API-04
    what: 28 of 74 upstream sources failed from inside the Worker
    status: RESOLVED
    detail: Cloudflare allows 50 subrequests per invocation and a full build asked for 74.
      Because 1101/1102 are returned as plain text with no CORS headers, the browser
      reported this as a CORS failure — a symptom two layers from the cause.
    resolution: the build is sharded by hydrology river, one shard per invocation, and
      KV operations were accounted for in the same budget. Now 30 ok / 0 failed,
      23 ok / 0 failed, 24 ok / 0 failed — 77 of 77 sources, zero failures.

  - id: API-05
    what: cold Python isolates intermittently return 1101/1102
    status: MITIGATED, not eliminated
    detail: a cold isolate cannot always import the 65-module package and rehydrate the
      state bundle inside its CPU budget. Measured: warm requests ~0.9s median, 1.4s p95,
      and reliable; cold ones 2.6-4s and failing roughly one in four.
    mitigation: the app retries 5xx and network errors twice with backoff, and the refresh
      script retries too. The retry lands on the isolate the first attempt warmed, so it
      is a fix for a transient rather than a paper-over. Browser QA passes 94 of 95 checks
      across all four §94 flows with the retry in place.
    unblock: a Workers Paid plan raises the CPU limit substantially; alternatively, trim
      the import surface further (features are already lazy) or split the package.

  - id: CUSTOM_DOMAIN
    what: api.caney… rather than *.workers.dev (§96)
    blocked_by: no zone is attached to this account for a caney domain
    unblock: add the domain to Cloudflare, then a [[routes]] block in
      caney-api/wrangler.toml
    note: cosmetic. workers.dev is a working production URL.
```

## Configuration reference

```bash
# Pages build (GitHub)
gh variable set RESEARCH_ENABLED --body 1
gh variable set CANEY_RESEARCH_ENDPOINT --body https://caney-research.steven-b9c.workers.dev
gh secret   set OPENAI_API_KEY

# Workers
npx wrangler secret put OPENAI_API_KEY --name caney-research

# The app's API base (build time, defaults to the deployed Worker)
VITE_CANEY_API=https://caney-api.steven-b9c.workers.dev
```

## Rollback

The 2.1 planner is still built and served at `/` and `/plan.html`; the 3.0 app is at
`/app/`. Nothing was deleted, so rollback is a link change rather than a redeploy.
