/**
 * Window discovery in the browser. §4, §8, §55.
 *
 * A mirror of caney/planner/opportunity.py. Same grid, same pruning, same utility — and
 * the hourly scores it optimises over are Python's, arriving in `data.hourly`.
 *
 * The pruning is the subtle part and it is deliberately identical: keep the best window
 * ending in each hour and the best starting in each hour, not just the top few by
 * standalone utility. Pruning by utility alone deletes the tight peak window that is only
 * worth fishing as the first leg of a circuit, and the itinerary search then has nothing
 * early-ending to build on.
 */
import { minDuration, sampleSeries, windowUtility } from "./utility.js";

export function findWindows(data, zoneId, species, availStart, availEnd, opts = {}) {
  const U = data.utility;
  const O = data.opportunity;
  const hourly = data.hourly[zoneId + "|" + species];
  if (!hourly || !hourly.values.length || availEnd <= availStart) return [];

  const confidence = opts.confidence !== undefined ? opts.confidence : 0;
  const locationConfidence =
    opts.locationConfidence !== undefined ? opts.locationConfidence : 0;
  const stale = !!opts.stale;
  const floorMin = opts.minMinutes !== undefined ? opts.minMinutes : minDuration(U, species);
  const grid = O.gridMinutes * 60;
  const availMin = (availEnd - availStart) / 60;

  const cands = [];
  for (let a = availStart; a < availEnd; a += grid) {
    for (let b = a + floorMin * 60; b <= availEnd; b += grid) {
      const minutes = (b - a) / 60;
      if (minutes > O.maxMinutes) break;
      const samples = sampleSeries(U, hourly.values, hourly.t0, hourly.step, a, b);
      if (!samples.length) continue;
      const { utility, parts } = windowUtility(U, samples, minutes, species, confidence,
                                               locationConfidence, 0, stale);
      cands.push({ utility, start: a, end: b, samples, parts });
    }
  }
  if (!cands.length && availMin > 0) {
    const samples = sampleSeries(U, hourly.values, hourly.t0, hourly.step,
                                 availStart, availEnd);
    if (samples.length) {
      const { utility, parts } = windowUtility(U, samples, availMin, species, confidence,
                                               locationConfidence, 0, stale);
      cands.push({ utility, start: availStart, end: availEnd, samples, parts });
    }
  }

  return prune(cands, availStart, O).map((c) => ({
    zone_id: zoneId, species, start: c.start, end: c.end, samples: c.samples,
    peak_score: round2(Math.max(...c.samples)),
    mean_score: round2(c.samples.reduce((a, b) => a + b, 0) / c.samples.length),
    floor_score: round2(Math.min(...c.samples)),
    quality: c.parts.quality,
    confidence: round1(confidence),
    location_confidence: round4(locationConfidence),
    utility: c.utility, parts: c.parts,
    duration_minutes: round1((c.end - c.start) / 60),
    stale,
    conditions_summary: opts.conditionsSummary || "",
    reasons: opts.reasons || [],
  }));
}

function prune(cands, availStart, O) {
  if (!cands.length) return [];
  const sorted = cands.slice().sort((x, y) =>
    (y.utility - x.utility) || (x.start - y.start) ||
    ((y.end - y.start) - (x.end - x.start)));
  const bucket = O.bucketMinutes * 60;
  const byEnd = new Map(), byStart = new Map();
  for (const c of sorted) {
    const eb = Math.floor((c.end - availStart) / bucket);
    const sb = Math.floor((c.start - availStart) / bucket);
    if (!byEnd.has(eb)) byEnd.set(eb, c);
    if (!byStart.has(sb)) byStart.set(sb, c);
  }
  const pool = [], seen = new Set();
  for (const c of [sorted[0], ...byEnd.values(), ...byStart.values()]) {
    const key = Math.round(c.start) + "-" + Math.round(c.end);
    if (seen.has(key)) continue;
    seen.add(key);
    pool.push(c);
  }
  pool.sort((x, y) => (y.utility - x.utility) || (x.start - y.start));
  return pool.slice(0, O.topN);
}

const round1 = (x) => Math.round(x * 10) / 10;
const round2 = (x) => Math.round(x * 100) / 100;
const round4 = (x) => Math.round(x * 1e4) / 1e4;
