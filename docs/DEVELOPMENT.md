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
web/planner/model.js      scoring assembly, gates, window search, ranking
web/planner/timeline.js   itinerary assembly + .ics export
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
cd riverguide && node test.mjs      # slicer, access, fail-closed guard
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

```bash
export RESEARCH_ENABLED=1
export OPENAI_API_KEY=…
export OPENAI_RESEARCH_MODEL=gpt-4.1-mini    # optional
python3 planner.py
```

Without these the planner is fully deterministic and every test still passes. Set
`CANEY_PLANNER_FAST=1` to skip live research even when a key is present.

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
