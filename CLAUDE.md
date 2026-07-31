# Caney — agent orientation

Personal river-fishing tool: per-river planning pages built by Python generators, plus an
HQ that ranks the rivers. Not a product (but see `PRODUCT_STRATEGY.md`).

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
| `briefing.py` | Caney Fork — the deepest page (dam routing, generation timing) |
| `duck.py` `elk.py` `elktn.py` `stones.py` `cumberland.py` | the other single-river pages |
| `cumbnash.py` `cheatham.py` `cordell.py` | the three Cumberland mainstem tailraces |
| `riverlib.py` | shared components — the parity rule below lives or dies here |
| `hq.py` | cross-river ranking page |
| `analysis/` | one-off calibration and backtest scripts (not part of the build) |
| `test/` | QA suite — see `test/README.md` |
| `out/` | generated HTML, **gitignored**, rebuilt from the generators |
| `RIVER_SPEC.md` | the canonical feature spec every river page targets |
| `docs/JOURNAL.md` | session memory: state, decisions, open threads |

## Build & check

```bash
./build.sh                   # regenerate every river + HQ into out/ (~30s, stdlib only)
python3 briefing.py          # or duck.py, elk.py, … — one river at a time
./test/run.sh                # build, then static + runtime checks
python3 test/verify.py       # static only, instant, no deps
```

`build.sh` is the single source of the generator list and order. `hq.py` runs last because it
aggregates every `out/status/<id>.json` into `index.html`. There are **no third-party Python
dependencies** anywhere in this repo; keep it that way.

Install the pre-commit gate once: `ln -sf ../../test/hooks/pre-commit .git/hooks/pre-commit`

## Deploy

`.github/workflows/deploy.yml` builds and publishes to Cloudflare Pages on push to master,
every 3 hours, and on manual dispatch. Static QA gates the deploy: a build that fails
`verify.py` is never published.

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
