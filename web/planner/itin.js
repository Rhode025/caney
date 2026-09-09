/**
 * Itinerary search in the browser. §9, §13, §55, §56.
 *
 * A mirror of caney/planner/itinerary.py: the same beam, the same feasibility rules, the
 * same objective. It runs over Python's opportunity windows and Python's transition graph,
 * with Python's constants — so it selects among precomputed opportunities rather than
 * modelling anything (§56).
 *
 * The objective evaluates a candidate day as ONE pseudo-window over its concatenated
 * samples, minus travel, minus idle, plus a breadth credit, minus a complexity penalty.
 * Summing per-window utilities would reward adding segments; averaging would reward
 * padding; this rewards a day whose fished time is uniformly good and charges for every
 * minute spent not fishing.
 */
import { windowUtility } from "./utility.js";

export function idleMinutes(windows, transitions) {
  let total = 0;
  for (let i = 0; i < transitions.length; i++) {
    const gap = (windows[i + 1].start - windows[i].end) / 60;
    total += Math.max(0, gap - transitions[i].minutes);
  }
  return total;
}

export function evaluate(data, windows, transitions, species) {
  const U = data.utility;
  let samples = [], minutes = 0;
  for (const w of windows) {
    samples = samples.concat(w.samples);
    minutes += w.duration_minutes;
  }
  if (!samples.length) return { utility: -1e9, parts: {} };

  const travel = transitions.reduce((a, t) => a + t.minutes, 0);
  const idle = idleMinutes(windows, transitions);
  const conf = Math.min(...windows.map((w) => w.confidence));
  const loc = Math.min(...windows.map((w) => w.location_confidence));
  const stale = windows.some((w) => w.stale);

  const { utility, parts } = windowUtility(
    U, samples, minutes, species, conf, loc, travel + U.idleCostFactor * idle, stale);

  const zones = new Set(windows.map((w) => w.zone_id));
  const complexity = U.complexityPenalty * Math.max(0, zones.size - 1);
  const meanQ = windows.reduce((a, w) => a + w.quality, 0) / windows.length;
  const breadth = U.breadthBonus * Math.max(0, windows.length - 1) * (meanQ / 100);
  const u = round4(utility + breadth - complexity);

  return {
    utility: u,
    parts: Object.assign({}, parts, {
      complexity: round4(complexity), breadth: round4(breadth),
      travelMinutes: round1(travel), idleMinutes: round1(idle),
      fishingMinutes: round1(minutes), zones: zones.size, utility: u,
    }),
  };
}

export function search(data, allWindows, craft, species) {
  const I = data.itinerary;
  const graph = data.transitions[craft] || {};
  if (!allWindows.length) return [];

  const ordered = allWindows.slice().sort((a, b) =>
    (a.start - b.start) || (b.utility - a.utility));

  let beams = ordered.map((w) => {
    const e = evaluate(data, [w], [], species);
    return { windows: [w], transitions: [], utility: e.utility, parts: e.parts };
  });
  beams.sort((a, b) => b.utility - a.utility);
  const best = beams.slice(0, I.beam);
  let frontier = beams.slice(0, I.beam);

  for (let depth = 1; depth < I.maxZones; depth++) {
    const grown = [];
    for (const cand of frontier) {
      const last = cand.windows[cand.windows.length - 1];
      const used = new Set(cand.windows.map((w) => w.zone_id));
      for (const w of ordered) {
        if (used.has(w.zone_id)) continue;
        const tr = graph[last.zone_id + "|" + w.zone_id];
        if (!tr) continue;
        const gap = (w.start - last.end) / 60;
        if (gap < tr.minutes - 1e-6) continue;
        if (gap - tr.minutes > I.maxIdleMinutes) continue;
        const seq = cand.windows.concat([w]);
        const trs = cand.transitions.concat([tr]);
        const e = evaluate(data, seq, trs, species);
        grown.push({ windows: seq, transitions: trs, utility: e.utility, parts: e.parts });
      }
    }
    if (!grown.length) break;
    grown.sort((a, b) => b.utility - a.utility);
    frontier = grown.slice(0, I.beam);
    best.push(...frontier);
  }

  best.sort((a, b) => b.utility - a.utility);
  const seen = new Set(), out = [];
  for (const c of best) {
    const key = zoneSeq(c).join(">") + "|" + c.windows.map((w) => Math.round(w.start)).join(",");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(c);
    if (out.length >= 12) break;
  }
  return out;
}

export function zoneSeq(cand) {
  const out = [];
  for (const w of cand.windows) if (!out.length || out[out.length - 1] !== w.zone_id) out.push(w.zone_id);
  return out;
}

const round1 = (x) => Math.round(x * 10) / 10;
const round4 = (x) => Math.round(x * 1e4) / 1e4;
