/**
 * The Python↔browser parity gate. §47, and the contract in web/planner/model.js.
 *
 * planner.py writes out/plan/parity.json — Python's OWN score for a sampled set of
 * (zone, species, window) cases, computed by caney/planner/scoring.py. This replays every
 * case through the browser engine and fails if any disagrees by more than 0.05 points.
 *
 * That is what keeps "the browser only assembles" true. If someone puts a threshold in
 * model.js, this test is what notices.
 */
import { readFileSync } from "node:fs";
import { score } from "../../web/planner/model.js";

const root = new URL("../../", import.meta.url).pathname;
const data = JSON.parse(readFileSync(root + "out/plan/data.json", "utf8"));
const parity = JSON.parse(readFileSync(root + "out/plan/parity.json", "utf8"));

let bad = 0, n = 0, worst = 0, worstCase = null;
for (const c of parity.cases) {
  const got = score(data, c.zone, c.species, c.craft, c.start, c.end);
  n++;
  if (!got) {
    console.error("  ✗ no score for", c.zone, c.species);
    bad++;
    continue;
  }
  const d = Math.abs(got.score - c.score);
  if (d > worst) { worst = d; worstCase = c; }
  if (d > 0.05) {
    bad++;
    console.error(`  ✗ ${c.zone}|${c.species} ${new Date(c.start * 1000).toISOString()}: ` +
                  `python ${c.score} vs js ${got.score} (Δ${d.toFixed(3)})`);
  }
}

console.log(`  parity: ${n - bad}/${n} cases match (worst Δ ${worst.toFixed(4)}` +
            (worstCase ? ` on ${worstCase.zone}|${worstCase.species}` : "") + ")");
if (bad) {
  console.error("\n  Python and the browser engine disagree. Either a threshold leaked " +
                "into web/planner/model.js, or caney/planner/scoring.py changed without " +
                "the aggregation contract being updated.");
  process.exit(1);
}
