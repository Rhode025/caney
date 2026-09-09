# Local development, testing and deployment

## Start every session from the repo root

```bash
cd ~/caney && claude
```

Session history is filed under the directory you launch from. The real memory is
`docs/JOURNAL.md` — read it at the start of a session, append to it at the end.

## Build

```bash
./build.sh              # every river + the board + the planner + the bot corpus (~60 s)
python3 planner.py      # JUST the planner and its dataset (~2 s warm, ~8 s cold)
python3 briefing.py     # one river
```

No third-party Python dependencies anywhere. Keep it that way.

Source responses are cached on disk under `.cache/` (gitignored) with per-kind TTLs, so a
second `planner.py` inside the TTL makes no network calls at all. `CANEY_CACHE_DIR` moves
it.

## Serve

```bash
cd out && python3 -m http.server 8919
```

Then <http://127.0.0.1:8919/>. Everything works from a plain static server — that is the
deployment target too.

The service worker caches aggressively. While iterating on `web/`, use a hard reload or
DevTools → Application → Service Workers → *Update on reload*.

## Frontend

There is no build step. The files in `web/` are copied verbatim to `out/assets/` and are
the files the browser runs, so the debugger shows the source you edited.

```
web/assets/app.css        the one stylesheet — tokens, components, dark mode, a11y
web/planner/model.js      candidate ranking, gates, the plan pipeline
web/planner/utility.js    the window utility function — a mirror of utility.py
web/planner/opportunity.js window discovery — a mirror of opportunity.py
web/planner/itin.js       the itinerary beam search — a mirror of itinerary.py
web/planner/segments.js   segment assembly — a mirror of segments.py
web/planner/timeline.js   the .ics alarm export
web/planner/ui.js         rendering
web/planner/app.js        state, persistence, events, offline
web/planner/map.js        Leaflet, from the local bundle
web/planner/trip.js       trip log + model scoreboard
web/planner/format.js     epochs → the reader's clock
```

To iterate without a full rebuild: `cp web/planner/*.js web/assets/*.css out/assets/…`, or
just run `python3 planner.py`, which copies them.

## Tests

```bash
./test/run.sh                  # everything, rebuilding first
./test/run.sh --no-build       # everything, against the current out/

python3 test/planner/run.py    # unit + fixtures. no network, fixed clock, instant.
python3 test/verify.py         # static QA over the built site
node test/planner/test_parity.mjs   # Python↔browser scoring parity
cd riverguide && node test.mjs      # slicer, access, fail-closed guard, itinerary
cd research-worker && node test.mjs # tiering, decay, normalisation, dedupe — no network
cd test && node planner.mjs         # browser + axe accessibility
cd test && node browser.mjs         # the river pages
node test/planner-smoke.mjs https://caney.pages.dev    # post-deploy
```

`test/planner/run.py` is the one to run while working. It touches no network and pins its
clock at `2026-09-09`, so a failure means the code changed, never that the river did.

Install the pre-commit gate once:

```bash
ln -sf ../../test/hooks/pre-commit .git/hooks/pre-commit
```

## Research (optional)

Preferred — the Research Intelligence worker holds the key, the cache, the decay curves and
the spend cap:

```bash
export RESEARCH_ENABLED=1
export CANEY_RESEARCH_ENDPOINT=https://caney-research.<subdomain>.workers.dev
python3 planner.py
```

Direct, for a local run with the secret to hand:

```bash
export RESEARCH_ENABLED=1
export OPENAI_API_KEY=…
export OPENAI_RESEARCH_MODEL=gpt-4.1-mini    # optional
python3 planner.py
```

Without either, the planner is fully deterministic and every test still passes. Set
`CANEY_PLANNER_FAST=1` to skip live research even when a key is present.

### Deploying the research worker

Independent of the static site (§75):

```bash
cd research-worker
npx wrangler d1 create caney-research           # once — put the id in wrangler.toml
npx wrangler kv namespace create CACHE          # once — put the id in wrangler.toml
npx wrangler d1 execute caney-research --remote --file=./schema.sql
npx wrangler secret put OPENAI_API_KEY
npx wrangler deploy
curl https://caney-research.<subdomain>.workers.dev/health
```

Then set the `CANEY_RESEARCH_ENDPOINT` repository **variable** so CI builds use it. Nothing
about the site build depends on the worker existing.

## Deployment

`.github/workflows/deploy.yml` → Cloudflare Pages, on push to `master`, hourly, and on
manual dispatch. **The live site is <https://caney.pages.dev>** — not the
`master.caney.pages.dev` branch alias, which is permanently stale.

Gates, in order, all of which must pass before `pages deploy`:

1. planner unit tests + golden model fixtures + species regressions
2. secret scan
3. build
4. `verify.py` static QA + river QC
5. Python↔browser scoring parity
6. RiverGuide tests
7. browser QA — river pages
8. browser QA — planner, the six §62 scenarios, axe accessibility
9. …deploy…
10. post-deploy smoke + freshness against the live site

The `cache_dam.json` + `.cache` restore/save steps are load-bearing, not an optimisation:
`briefing.py` falls back to a last-good Center Hill forecast when CWMS is thin, and the file
is gitignored, so a cold runner would build an empty forecast during an outage.

Secrets are repository secrets (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`,
`OPENAI_API_KEY`) and variables (`RESEARCH_ENABLED`, `OPENAI_RESEARCH_MODEL`). Nothing is
committed; `test_architecture.py::test_repo_hygiene` and the CI secret scan both check.

## RiverGuide (the Telegram bot)

```bash
cd riverguide
node test.mjs
npx wrangler deploy
```

It answers from `out/bot.json`, which now embeds the planner's claim book and zone model,
and from `out/plan/featured/*.json` for planning questions.

## Adding a fishing zone

1. Add a `FishingZone` to `caney/zones/registry.py`. Give it real coordinates from a
   verified source, or a corridor between verified endpoints — never a pin derived from
   prose.
2. Point `hydrology_river` at whichever generator owns the water numbers, and add that
   river to `caney/sources/registry.py::WATER` if it is not already there.
3. Attach one `SpeciesProfileRef` per species, with months, pattern, holds, `move_to` and
   `evidence` claim ids.
4. If it introduces new evidence, add the claims to `caney/research/corpus.py` with their
   URLs.
5. `python3 test/planner/run.py` — `test_zones` will tell you what you left out.

## Adding a species

1. Add the key and `DISPLAY` entry in `caney/species/profiles.py`.
2. Add a `SpeciesProfile` with every rule classified `SOURCED` or `HEURISTIC`.
3. Add a `WEIGHTS` column summing to 100, using only components that have fit functions.
4. Pin it in `test/planner/test_domain.py::test_weights`.
5. Attach it to zones. `validate()` fails if a species has nowhere to fish.


## Adding a transition route

`caney/planner/transitions.py::KNOWN_ROUTES`, keyed `(from_zone, to_zone)` and asymmetric
where the water is:

```python
("cordell_tailwater", "carthage_confluence"): (12.0, "boat_downstream",
    "8 river miles of continuously navigable Cumberland, running downstream."),
("carthage_confluence", "cordell_tailwater"): (16.0, "boat_upstream",
    "8 river miles back up to the dam, against the release."),
```

Minutes are the whole move including overhead. Without an entry the model estimates from
straight-line distance and labels the estimate as one; if no mode the craft has can make
the move, `transition()` returns `None` and the move is never offered.

## Bumping a model version

`caney/version.py`. Bump the relevant one whenever you change the utility function or the
searches (`PLANNER_VERSION`), the weights or a species rule (`SPECIES_MODEL_VERSION`), the
zone registry or location confidence (`ZONE_MODEL_VERSION`), or the corpus, tiers or decay
curves (`RESEARCH_VERSION`). The trip log freezes all four, and the scoreboard groups by
`planner` — a calibration figure that silently spans a model change is worse than none.
