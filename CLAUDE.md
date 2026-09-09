# Caney — agent orientation

Personal river-fishing tool. **A fishing-day oracle** (`out/index.html`): you pick a
species, a time window and a craft, and it runs your day — the best contiguous window
inside your availability, the zone or zones to fish, when to move and why, what to tie on
at each stretch, the conditions that would change the plan, and the evidence behind all of
it. Behind that sit the original per-river planning pages built by Python generators, and
the board that ranks them (`out/rivers.html`). Not a product (but see
`PRODUCT_STRATEGY.md`).

**The central idea:** your availability is a CONSTRAINT, not an instruction to fish every
minute of it. A 95 for ninety minutes beats a 76 for four hours, and the plan says so.

**Read `docs/ARCHITECTURE.md` before changing anything in `caney/` or `web/`.**

## Start every session from this directory

```bash
cd /Users/stevenrhodes/caney && claude
```

Claude Code files session history under the directory you launch from, so launching from
`out/` (or anywhere else) strands that conversation in a separate history that `claude -c`
and `claude --resume` will never show you. **Repo root, always.** Resume with `claude -c`
(last session) or `claude -r` (pick from a list).

Session logs are a convenience, not the memory. The memory is `docs/JOURNAL.md` — read it
at the start of a session, append to it at the end. It is git-tracked and survives anything
that happens to `~/.claude`.

## Layout

| Path | What |
|---|---|
| `caney/` | the planner package — domain, species, zones, research, sources, planner, render |
| `research-worker/` | Cloudflare Worker: web search → sourced ResearchClaims, D1 + KV |
| `planner.py` | builds the species-first homepage + `out/plan/*` (runs after `hq.py`) |
| `web/` | the shared frontend — one stylesheet, ES modules, no build step |
| `docs/ARCHITECTURE.md` | how the two halves fit together. Start here. |
| `docs/PLANNER.md` | the window utility function and the itinerary search |
| `briefing.py` | Caney Fork — the deepest page (dam routing, generation timing) |
| `duck.py` `elk.py` `elktn.py` `stones.py` `cumberland.py` | the other single-river pages |
| `cumbnash.py` `cheatham.py` `cordell.py` | the three Cumberland mainstem tailraces |
| `riverlib.py` | shared components — the parity rule below lives or dies here |
| `hq.py` | cross-river ranking board → `out/rivers.html` (no longer the homepage) |
| `analysis/` | one-off calibration and backtest scripts (not part of the build) |
| `test/` | QA suite — see `test/README.md` |
| `out/` | generated HTML, **gitignored**, rebuilt from the generators |
| `RIVER_SPEC.md` | the canonical feature spec every river page targets (the drill-down layer) |
| `docs/JOURNAL.md` | session memory: state, decisions, open threads |

## Build & check

```bash
./build.sh                   # every river + board + planner + bot corpus (~60s, stdlib only)
python3 planner.py           # JUST the planner and its dataset (~2s warm)
python3 briefing.py          # or duck.py, elk.py, … — one river at a time
./test/run.sh                # build, then every check we have
python3 test/planner/run.py  # planner unit + fixtures — no network, fixed clock, instant
python3 test/verify.py       # static only, instant, no deps
```

`planner.py` runs **after** `hq.py` (it links the river pages as the drill-down layer) and
**before** `bot.py` (the bot corpus embeds the planner's safety claim book).

`build.sh` is the single source of the generator list and order. `hq.py` runs after the
river generators because it aggregates every `out/status/<id>.json` into `rivers.html`;
`planner.py` then builds the homepage, and `bot.py` runs last of all. There are **no
third-party Python dependencies** anywhere in this repo; keep it that way.

Install the pre-commit gate once: `ln -sf ../../test/hooks/pre-commit .git/hooks/pre-commit`

## Deploy

`.github/workflows/deploy.yml` builds and publishes to Cloudflare Pages on push to master,
**hourly**, and on manual dispatch. **The live site is https://caney.pages.dev** — not the
`master.caney.pages.dev` branch alias, which stopped being repointed after the first few
deploys and is now permanently stale.

Hourly rather than 3-hourly because GitHub delays scheduled workflows under load and drops
them when backed up (observed: 18:00 ran at 19:44, 21:00 ran at 22:11, 00:00 never fired).
Asking hourly makes a skipped run cost ~1 h of staleness instead of 6+.

**Every suite gates the deploy, not just `verify.py`** (2.0, §49): planner unit tests and
model fixtures → secret scan → build → static QA + river QC → Python↔browser scoring parity
→ RiverGuide → browser QA for the river pages → browser QA for the planner including axe
accessibility → deploy → post-deploy smoke and freshness against the live site.

Research is optional in CI: set the `RESEARCH_ENABLED` variable and the `OPENAI_API_KEY`
secret to turn it on. Without them the build is fully deterministic and every gate passes.

The cache step in that workflow is load-bearing, not an optimisation. `briefing.py:80-89`
keeps a last-good Center Hill release forecast in `cache_dam.json` and falls back to it when
USACE CWMS is thin or down. That file is gitignored, so without the persisted cache a runner
would build an empty forecast during an outage and the "USING CACHED release data" path would
never fire. Do not remove it.

## Invariants

- **Parity rule** (`RIVER_SPEC.md` §0) — a user-facing feature ships on *every* river in the
  same change, or gets an explicit `—` with a reason in the §3 matrix. No "I'll add it later."
- **Fly-only content** — no lures/gear terms, no catfish/sauger/crappie. `verify.py` enforces it.
- **Calibration constants carry their provenance in the comment above them.** When you change
  one, rewrite the comment to say what evidence moved it, and update any user-facing copy that
  quotes the old number. `2c2bc2c` is the worked example: one constant, nine call sites of prose.
- **Never hardcode a calibrated number in the page JS** — pass it through `DATA` so Python stays
  the single source. (`DATA.mph` exists because a hardcoded `3` got missed once.)
- **Unknown is never zero.** `value or 0` is how a missing release forecast becomes
  "0 cfs" becomes "wade all day". Every planner value is an `Observation` with a
  `known/stale/unknown/error` state; `test_architecture.py` greps for bare `or 0` and fails
  the build unless the line is marked `# not a measurement`.
- **Safety numbers are minted once.** `caney/sources/snapshots.py::_mint_safety_claims` is
  the only place a `SafetyClaim` is created. Anything generative may quote a claim and may
  never restate one; `riverguide/src/guard.js` verifies per zone and **fails closed** —
  an unverifiable safety sentence is deleted, not annotated. `docs/SAFETY.md`.
- **Safety uses the earliest bound, fishing uses the typical one.** `arrival_window()`
  returns `(earliest, typical, latest)`; safe-exit claims are always `bound="earliest"`.
- **Species live in zones, not on pages.** A page's `species` line is a description. The
  model is `caney/zones/registry.py`, and a zone may span pages.
- **Weights are config.** `caney/species/profiles.py::WEIGHTS`, pinned by a test. Never put
  a threshold in `caney/planner/scoring.py` — and never anywhere in `web/planner/`, which
  assembles and does not model. `test/planner/test_parity.mjs` replays Python's own answers
  at four layers (component scores, window utilities, best-subwindow sets and whole
  itineraries) through the browser engine; a leaked constant makes one of them disagree.
- **Never optimise the mean.** A window's score is peak-weighted with an explicit floor
  term (`caney/planner/utility.py`), and the duration factor SATURATES — both exist to stop
  the optimiser padding a peak with dead hours. `docs/PLANNER.md` §2.
- **Every constant in the utility function is published to the browser** in `data.utility`,
  for the same reason `DATA.mph` exists.
- **A move must be paid for, and must be possible.** `caney/planner/transitions.py` returns
  `None` when a craft cannot make a move — which removes it from the search rather than
  pricing it — and every offered move declares whether its cost is `known`, `estimated` or
  `unknown`.
- **Geography has confidence, and it costs.** `caney/domain/location.py`. Weak geography
  loses real utility AND gets hedged language: a zone whose tactical level is `hedged` must
  never emit precise tactical prose, which `verify.py` checks structurally.
- **Model versions are frozen into every plan** (`caney/version.py`). Bump the relevant one
  when you change the utility function, the weights, the zone registry or the corpus — the
  scoreboard groups by version, and a calibration figure spanning a model change is worse
  than none.
- **No build-time relative time** (`RIVER_SPEC.md` §0) — every day row ships `iso`, every page
  ships `todayIso`, and `Today`/`Tomorrow` are stamped client-side from the reader's clock by
  `riverlib.DAYLABEL_JS`. Never select a day by index (`week[0]`, `di===0`); select by `isToday`.
  A stale build must degrade to "Fri · 2d ago", never claim an old day is today.
