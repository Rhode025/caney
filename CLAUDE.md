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
| `duck.py` `elk.py` `elktn.py` `stones.py` `cumberland.py` `cumbnash.py` | the other six rivers |
| `riverlib.py` | shared components — the parity rule below lives or dies here |
| `hq.py` | cross-river ranking page |
| `analysis/` | one-off calibration and backtest scripts (not part of the build) |
| `test/` | QA suite — see `test/README.md` |
| `out/` | generated HTML, **gitignored**, rebuilt from the generators |
| `RIVER_SPEC.md` | the canonical feature spec every river page targets |
| `docs/JOURNAL.md` | session memory: state, decisions, open threads |

## Build & check

```bash
python3 briefing.py          # or duck.py, elk.py, … — each writes its page into out/
./test/run.sh                # regenerate, then static + runtime checks
python3 test/verify.py       # static only, instant, no deps
```

Install the pre-commit gate once: `ln -sf ../../test/hooks/pre-commit .git/hooks/pre-commit`

## Invariants

- **Parity rule** (`RIVER_SPEC.md` §0) — a user-facing feature ships on *every* river in the
  same change, or gets an explicit `—` with a reason in the §3 matrix. No "I'll add it later."
- **Fly-only content** — no lures/gear terms, no catfish/sauger/crappie. `verify.py` enforces it.
- **Calibration constants carry their provenance in the comment above them.** When you change
  one, rewrite the comment to say what evidence moved it, and update any user-facing copy that
  quotes the old number. `2c2bc2c` is the worked example: one constant, nine call sites of prose.
- **Never hardcode a calibrated number in the page JS** — pass it through `DATA` so Python stays
  the single source. (`DATA.mph` exists because a hardcoded `3` got missed once.)
