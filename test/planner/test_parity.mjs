/**
 * The Python↔browser parity gate. §55, §56.
 *
 * planner.py writes out/plan/parity.json — Python's OWN answers, computed from the emitted
 * dataset — at four layers:
 *
 *     cases        component-weighted window score      (the 2.0 contract, still pinned)
 *     windows      window utility over the hourly series
 *     subwindows   the best-window SET the optimiser finds inside an availability
 *     itineraries  the winning sequence: zones, times and utility
 *
 * Every one is replayed through web/planner/*.js. This is what keeps "the browser selects
 * among precomputed opportunities, it does not model" true: if a threshold, a curve or a
 * coefficient leaks into the browser, one of these four disagrees.
 */
import { readFileSync } from "node:fs";
import { score } from "../../web/planner/model.js";
import { sampleSeries, windowUtility } from "../../web/planner/utility.js";
import { findWindows } from "../../web/planner/opportunity.js";
import { search } from "../../web/planner/itin.js";

const root = new URL("../../", import.meta.url).pathname;
const data = JSON.parse(readFileSync(root + "out/plan/data.json", "utf8"));
const parity = JSON.parse(readFileSync(root + "out/plan/parity.json", "utf8"));

let fails = 0, checked = 0;
const TOL = 0.05;
const near = (a, b) => Math.abs(a - b) <= TOL;
function bad(msg) { fails++; console.error("  \x1b[31m✗\x1b[0m " + msg); }

// ── 1. component-weighted window scores ────────────────────────────────────
let worst = 0;
for (const c of parity.cases) {
  checked++;
  const got = score(data, c.zone, c.species, c.craft, c.start, c.end);
  if (!got) { bad(`no score for ${c.zone}|${c.species}`); continue; }
  const d = Math.abs(got.score - c.score);
  if (d > worst) worst = d;
  if (d > TOL) bad(`score ${c.zone}|${c.species}: python ${c.score} vs js ${got.score}`);
}
console.log(`  scores:      ${parity.cases.length} cases (worst Δ ${worst.toFixed(4)})`);

// ── 2. window utility ──────────────────────────────────────────────────────
worst = 0;
for (const w of parity.windows) {
  checked++;
  const h = data.hourly[w.zone + "|" + w.species];
  const samples = sampleSeries(data.utility, h.values, h.t0, h.step, w.start, w.end);
  const got = windowUtility(data.utility, samples, (w.end - w.start) / 60, w.species,
                            w.confidence, w.locationConfidence);
  const d = Math.abs(got.utility - w.utility);
  const dq = Math.abs(got.parts.quality - w.quality);
  if (d > worst) worst = d;
  if (d > TOL) bad(`utility ${w.zone}|${w.species}: python ${w.utility} vs js ${got.utility}`);
  if (dq > TOL) bad(`quality ${w.zone}|${w.species}: python ${w.quality} vs js ${got.parts.quality}`);
}
console.log(`  utility:     ${parity.windows.length} windows (worst Δ ${worst.toFixed(4)})`);

// ── 3. best-subwindow discovery ────────────────────────────────────────────
let subFails = 0;
for (const s of parity.subwindows) {
  checked++;
  const got = findWindows(data, s.zone, s.species, s.availStart, s.availEnd, {
    confidence: s.confidence, locationConfidence: s.locationConfidence,
  });
  if (got.length !== s.windows.length) {
    subFails++;
    bad(`subwindow count ${s.zone}|${s.species}: python ${s.windows.length} vs js ${got.length}`);
    continue;
  }
  for (let i = 0; i < got.length; i++) {
    const a = s.windows[i], b = got[i];
    if (Math.round(a.start) !== Math.round(b.start) ||
        Math.round(a.end) !== Math.round(b.end) ||
        !near(a.utility, b.utility)) {
      subFails++;
      bad(`subwindow ${i} ${s.zone}|${s.species}: python ` +
          `${a.start}-${a.end}@${a.utility} vs js ${b.start}-${b.end}@${b.utility}`);
      break;
    }
  }
}
console.log(`  subwindows:  ${parity.subwindows.length} availabilities ` +
            `(${parity.subwindows.length - subFails} exact)`);

// ── 4. whole itineraries ───────────────────────────────────────────────────
let itFails = 0;
for (const it of parity.itineraries) {
  checked++;
  const month = new Date(it.start * 1000).getMonth() + 1;
  let allWindows = [];
  for (const [zid, z] of Object.entries(data.zones)) {
    if (!(z.species_profiles || {})[it.species]) continue;
    const g = data.gates[zid] || {};
    if (it.craft !== "any" && !(g.craft || []).includes(it.craft)) continue;
    const months = (g.seasons || {})[it.species];
    if (months && !months.includes(month)) continue;
    if (!data.hourly[zid + "|" + it.species]) continue;
    const conf = (data.confidence[zid + "|" + it.species] || {}).value || 0;
    const loc = (z.location_confidence || {}).value || 0;
    const stale = ["flow", "generation"].some(
      (k) => ((z.water || {})[k] || {}).state === "stale");
    allWindows = allWindows.concat(findWindows(data, zid, it.species, it.start, it.end,
      { confidence: conf, locationConfidence: loc, stale }));
  }
  const seqs = search(data, allWindows, it.craft, it.species);
  if (!seqs.length) { itFails++; bad(`no itinerary for ${it.species}/${it.craft}`); continue; }
  const got = seqs[0];
  const gotZones = got.windows.map((w) => w.zone_id);
  if (JSON.stringify(gotZones) !== JSON.stringify(it.zones)) {
    itFails++;
    bad(`itinerary zones ${it.species}/${it.craft}: python ${it.zones} vs js ${gotZones}`);
    continue;
  }
  if (!near(got.utility, it.utility)) {
    itFails++;
    bad(`itinerary utility ${it.species}/${it.craft}: python ${it.utility} vs js ${got.utility}`);
    continue;
  }
  for (let i = 0; i < it.windows.length; i++) {
    if (Math.round(got.windows[i].start) !== it.windows[i].start ||
        Math.round(got.windows[i].end) !== it.windows[i].end) {
      itFails++;
      bad(`itinerary times ${it.species}/${it.craft} window ${i}`);
      break;
    }
  }
}
console.log(`  itineraries: ${parity.itineraries.length} requests ` +
            `(${parity.itineraries.length - itFails} exact)`);

console.log(`  ${checked} parity checks across four layers.`);
if (fails) {
  console.error("\n  Python and the browser engine disagree. Either a constant leaked into " +
                "web/planner/, or the Python side changed without the emitted dataset " +
                "following it.");
  process.exit(1);
}
