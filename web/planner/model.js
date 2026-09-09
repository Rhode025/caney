/**
 * The browser half of the planner. §30, §31, §47.
 *
 * THIS FILE COMPUTES NO MODEL. Every number it touches was produced by Python and shipped
 * in out/plan/data.json: the hourly component fits, the static fits, the weights, the
 * confidence signals, the eligibility flags, the safety claims. What lives here is
 * assembly — the weighted sum, the window argmax, the published ranking blend and the
 * gates — because a static site cannot call Python when the user drags a time slider.
 *
 * The contract with Python is pinned by test/planner/test_parity.mjs, which replays
 * out/plan/parity.json (Python's own scores for sampled windows) through this module and
 * fails on a disagreement larger than 0.05 points.
 *
 * Rule: if you find yourself about to write a threshold, a curve or a coefficient in this
 * file, it belongs in caney/planner/ instead.
 */

export const DYNAMIC = ["light", "weather", "moon", "generation"];

/** Overlap-weighted mean of an hourly series across [start, end). Mirrors scoring.aggregate. */
export function aggregate(series, key, start, end) {
  const vals = series.values[key];
  if (!vals || !vals.length) return null;
  const { t0, step } = series;
  let num = 0, den = 0, known = true, idx = 0;
  for (let i = 0; i < vals.length; i++) {
    const a = t0 + i * step, b = a + step;
    const ov = Math.max(0, Math.min(b, end) - Math.max(a, start));
    if (ov <= 0) continue;
    num += vals[i] * ov;
    den += ov;
    if (series.known[key][i] === 0) known = false;
  }
  if (den <= 0) return null;
  const mid = (start + end) / 2;
  idx = Math.max(0, Math.min(vals.length - 1, Math.floor((mid - t0) / step)));
  return { value: num / den, why: whyAt(series, key, idx), known };
}

function whyAt(series, key, i) {
  const table = series.whyTable[key] || [];
  const ix = (series.why[key] || [])[i];
  return table[ix] || "";
}

/** {score, lines, fits} for one candidate over one window. */
export function score(data, zoneId, species, craft, start, end) {
  const key = zoneId + "|" + species;
  const series = data.series[key];
  const st = data.statics[key];
  const weights = data.weights[species];
  if (!series || !st || !weights) return null;

  const fits = {};
  for (const k of Object.keys(weights)) {
    if (DYNAMIC.includes(k)) {
      const a = aggregate(series, k, start, end);
      fits[k] = a
        ? { v: a.value, why: a.why, known: a.known }
        : { v: data.neutralFit, why: "no hourly value in this window", known: false };
    } else if (k === "access") {
      fits[k] = st.accessByCraft[craft] || st.accessByCraft.any;
    } else {
      fits[k] = st.static[k] ||
        { v: data.neutralFit, why: "component not computed", known: false };
    }
  }

  let total = 0;
  const lines = [];
  for (const [k, w] of Object.entries(weights).sort((a, b) => b[1] - a[1])) {
    const f = fits[k];
    const earned = f.v * w;
    total += earned;
    lines.push({
      key: k,
      label: data.componentLabels[k] || k,
      earned: Math.round(earned * 10) / 10,
      possible: w,
      why: f.why + (f.known ? "" : " (unknown — charged to confidence, not to score)"),
      known: f.known,
    });
  }
  return { score: Math.round(total * 10) / 10, lines, fits };
}

/** §31 — the ONE published blend, shipped from Python as two constants. */
export function rankKey(sc, conf, rank) {
  return sc * (rank.base + rank.conf * (conf / 100));
}

export function confidenceFor(data, zoneId, species, daysOut) {
  const c = data.confidence[zoneId + "|" + species];
  if (!c) return { value: 0, rows: [] };
  let v = c.value;
  const rows = c.rows.slice();
  const hp = data.horizonPenalty || { fromDays: 3, perDay: 12, max: 45 };
  if (daysOut >= hp.fromDays) {
    const pen = Math.min(hp.max, hp.perDay * (daysOut - (hp.fromDays - 1)));
    v = Math.max(0, Math.round((v - pen) * 10) / 10);
    rows.push({
      key: "horizon", label: "Forecast horizon", state: "stale", weight: 0,
      detail: daysOut + " days out — seasonal expectation, not a forecast",
    });
  }
  return { value: v, rows };
}

export function confidenceLabel(c, data) {
  const table = (data && data.confidenceLabels) ||
    [[78, "HIGH CONFIDENCE"], [55, "MODERATE CONFIDENCE"], [32, "LOW CONFIDENCE"],
     [0, "VERY LOW CONFIDENCE"]];
  for (const [floor, label] of table) if (c >= floor) return label;
  return table[table.length - 1][1];
}

/**
 * §30 step 2 — the eligibility GATES. Every flag was decided in Python; this only reads
 * them. A gate removes a candidate; it never merely lowers its score.
 */
export function gate(data, zoneId, species, craft, start, end, month) {
  const g = data.gates[zoneId];
  if (!g) return "no eligibility data for this water";
  if (craft !== "any" && !g.craft.includes(craft)) {
    const label = (data.craft.find((c) => c.key === craft) || {}).label || craft;
    return "no access on this water serves a " + label;
  }
  const months = (g.seasons || {})[species];
  if (months && !months.includes(month)) {
    return "outside the seasonal pattern for this species here";
  }
  const hours = hourRange(data, g, start, end);
  if (hours.length && hours.every((i) => g.storm[i] === 1)) {
    return "thunderstorms forecast across the entire requested window";
  }
  if (craft === "wade") {
    if (g.tailwater) {
      if (g.noReleaseForecast) {
        return "wade request on a tailwater with no release forecast — this plan cannot " +
               "bound the wade window, so it will not offer one";
      }
      if (hours.length && hours.every((i) => g.wet[i] === 1)) {
        return "the release runs through this entire window — the reach is not wadeable";
      }
    } else if (g.flowTooHighToWade) {
      return g.flowTooHighDetail || "flow is far above the measured no-wade threshold";
    }
  }
  return null;
}

/** Indices into the gate arrays covering [start, end). They are anchored on horizon.t0. */
function hourRange(data, g, start, end) {
  const base = data.horizon.t0;
  const n = (g.storm || []).length;
  const out = [];
  for (let i = Math.max(0, Math.floor((start - base) / 3600)); i < n; i++) {
    const t = base + i * 3600;
    if (t >= end) break;
    out.push(i);
  }
  return out;
}

import { findWindows } from "./opportunity.js";
import { search as itinSearch, zoneSeq } from "./itin.js";

/**
 * §4, §8, §30 — the 2.1 pipeline, in the browser.
 *
 * 2.0 asked "which zone scores highest over the whole period the user gave?" and answered
 * with a mean. This asks "what is the best executable day inside that period?" and answers
 * with an itinerary. The scoring, the utility constants, the transition graph and the
 * hourly series are all Python's; what happens here is selection.
 */
//: How many runner-up itineraries to keep for the alternatives block (§38). Display only.
const RUNNERS_SHOWN = 5;

export function planFor(data, species, craft, start, end, now) {
  const month = new Date(start * 1000).getMonth() + 1;
  const daysOut = daysBetween(now, start);
  const rejected = [];
  const candidates = [];
  let allWindows = [];

  for (const [zid, z] of Object.entries(data.zones)) {
    if (!z.species_profiles || !z.species_profiles[species]) continue;
    const reason = gate(data, zid, species, craft, start, end, month);
    if (reason) { rejected.push({ zone: zid, name: z.name, reason }); continue; }

    const conf = confidenceFor(data, zid, species, daysOut);
    const loc = (z.location_confidence || {}).value || 0;
    const stale = ["flow", "generation"].some(
      (k) => ((z.water || {})[k] || {}).state === "stale");
    const windows = findWindows(data, zid, species, start, end, {
      confidence: conf.value, locationConfidence: loc, stale,
      conditionsSummary: conditionsSummary(z),
    });
    if (!windows.length) {
      rejected.push({ zone: zid, name: z.name, reason: "no fishable window inside your time" });
      continue;
    }
    const w = score(data, zid, species, craft, windows[0].start, windows[0].end);
    candidates.push({
      zone: zid, name: z.name, z, windows,
      confidence: conf.value, confRows: conf.rows,
      locationConfidence: loc,
      lines: w ? w.lines : [], fits: w ? w.fits : {},
      score: w ? w.score : 0,
      bestUtility: windows[0].utility,
    });
    allWindows = allWindows.concat(windows);
  }

  if (!allWindows.length) return { itinerary: null, candidates, rejected, daysOut };

  const seqs = itinSearch(data, allWindows, craft, species);
  if (!seqs.length) return { itinerary: null, candidates, rejected, daysOut };

  const winner = seqs[0];
  const byZone = Object.fromEntries(candidates.map((c) => [c.zone, c]));
  const primary = byZone[winner.windows[0].zone_id];
  candidates.sort((a, b) => b.bestUtility - a.bestUtility);

  return {
    itinerary: winner, runners: seqs.slice(1, 1 + RUNNERS_SHOWN),
    candidates, rejected, daysOut,
    primary, byZone,
    opportunity: round1(winner.parts.quality || 0),
    confidence: Math.min(...winner.windows.map((w) => w.confidence)),
    locationConfidence: round1(100 * Math.min(...winner.windows.map((w) => w.location_confidence))),
    researchConfidence: researchConfidence(data, winner.windows[0].zone_id, species),
    zoneSequence: zoneSeq(winner),
  };
}

function conditionsSummary(z) {
  const w = z.water || {};
  const bits = [];
  if ((w.flow || {}).state === "known") bits.push(Math.round(w.flow.value).toLocaleString() + " cfs");
  if ((w.generation_on || {}).state === "known") {
    bits.push("generation " + (w.generation_on.value ? "on" : "off"));
  }
  if ((w.water_temp || {}).state === "known") bits.push(Math.round(w.water_temp.value) + "°F");
  return bits.join(" · ");
}

/** §31 — research confidence as its own number. Mirrors engine._research_confidence. */
export function researchConfidence(data, zoneId, species) {
  const rows = evidenceFor(data, zoneId, species);
  if (!rows.length) return 0;
  const top = rows.slice().sort((a, b) => b.confidence - a.confidence).slice(0, 4);
  return round1(100 * top.reduce((a, c) => a + c.confidence, 0) / top.length);
}

/** The claim bodies, with the confidence they carry AT THIS ZONE. */
export function evidenceFor(data, zoneId, species) {
  const refs = data.evidence[zoneId + "|" + species] || [];
  return refs.map((r) => {
    const id = typeof r === "string" ? r : r.id;
    const c = data.claims[id];
    if (!c) return null;
    return Object.assign({}, c, {
      confidence: typeof r === "string" ? 0 : (r.confidence || 0),
      geographic_match: typeof r === "string" ? null : r.geographic_match,
    });
  }).filter(Boolean);
}

export function daysBetween(now, then) {
  const a = new Date(now * 1000), b = new Date(then * 1000);
  a.setHours(0, 0, 0, 0); b.setHours(0, 0, 0, 0);
  return Math.round((b - a) / 86400000);
}

/** §8 — the verdict, from the same rule as engine._verdict. */
export function verdict(opportunity, confidence, lines, data) {
  const V = (data && data.verdictThresholds) ||
    { go: 68, confident: 55, fishable: 50, hardComponent: 0.2 };
  const hard = (lines || []).filter((l) => l.known && l.earned <= l.possible * V.hardComponent);
  if (opportunity >= V.go && confidence >= V.confident && !hard.length) {
    return ["GO", "Good water, good window, and the numbers behind it are observed."];
  }
  if (opportunity >= V.go && confidence < V.confident) {
    return ["CONDITIONAL",
      "The fishery reads well but too much of it is unmeasured — treat the timing as " +
      "provisional and verify the release before you commit."];
  }
  if (opportunity >= V.fishable) {
    return ["CONDITIONAL", "Fishable, with a real limitation: " +
      (hard.length ? hard[0].why : "several components are only average.")];
  }
  return ["SKIP", "Nothing here scores well enough to be worth the drive: " +
    (hard.length ? hard[0].why : "every component is weak in this window.")];
}

const round1 = (x) => Math.round(x * 10) / 10;
