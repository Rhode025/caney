/**
 * The window utility function, in the browser. §6, §7, §55, §56.
 *
 * A LINE-FOR-LINE MIRROR of caney/planner/utility.py, and nothing more. Every constant
 * arrives in `data.utility` — none is written here — so this file contains arithmetic and
 * no model. `test/planner/test_parity.mjs` replays Python's own utilities for sampled
 * windows through these functions and fails on a disagreement larger than 0.05.
 *
 * Why it is duplicated at all: the site is static, so an interactive "what about
 * 6:25-8:05 instead?" cannot call Python. §56 permits the browser to "select from
 * precomputed opportunities"; the numbers being selected over are Python's.
 */

export function minDuration(U, species) {
  const m = U.minDuration || {};
  return m[species] !== undefined ? m[species] : U.defaultMinDuration;
}

/** Peak-weighted quality of a list of 0..100 scores. */
export function quality(U, samples) {
  const xs = samples.filter((s) => s !== null && s !== undefined).map(Number);
  if (!xs.length) return 0;
  const n = Math.max(1, Math.floor(xs.length / 3));
  const desc = xs.slice().sort((a, b) => b - a);
  let peak = 0;
  for (let i = 0; i < n; i++) peak += desc[i];
  peak /= n;
  let cube = 0;
  for (const x of xs) cube += Math.pow(x / 100, 3);
  const cubic = 100 * Math.cbrt(cube / xs.length);
  const floor = Math.min(...xs);
  return round4(U.wPeak * peak + U.wCubic * cubic + U.wFloor * floor);
}

export function durationFactor(U, minutes, species) {
  const m = Math.max(0, Number(minutes));
  let d = U.dBase + U.dSpan * Math.min(1, m / U.idealMinutes);
  if (m < minDuration(U, species)) d *= U.shortPenalty;
  return round6(d);
}

export function confidenceFactor(U, confidence) {
  return round6(U.cBase + U.cSpan * Math.max(0, Math.min(100, Number(confidence))) / 100);
}

export function locationFactor(U, locationConfidence) {
  return round6(U.lBase + U.lSpan * Math.max(0, Math.min(1, Number(locationConfidence))));
}

export function windowUtility(U, samples, minutes, species, confidence,
                              locationConfidence, transitionMinutes = 0, stale = false) {
  const q = quality(U, samples);
  const d = durationFactor(U, minutes, species);
  const c = confidenceFactor(U, confidence);
  const l = locationFactor(U, locationConfidence);
  const transition = U.transitionCostPerMin * Math.max(0, Number(transitionMinutes));
  const stalePen = stale ? U.stalePenalty : 0;
  const u = q * d * c * l - transition - stalePen;
  return {
    utility: round4(u),
    parts: {
      quality: q, duration_factor: d, confidence_factor: c, location_factor: l,
      transition: round4(transition), staleness: stalePen, utility: round4(u),
    },
  };
}

/** Sample an hourly score series across [start, end) by linear interpolation. */
export function sampleSeries(U, values, t0, step, start, end) {
  const out = [];
  if (end <= start || !values || !values.length) return out;
  const stepsec = U.sampleMinutes * 60;
  const n = values.length;
  let t = start;
  while (t < end - 1) {
    const pos = (t - t0) / step;
    const i = Math.floor(pos);
    const frac = pos - i;
    let v;
    if (i < 0) v = values[0];
    else if (i >= n - 1) v = values[n - 1];
    else v = values[i] + (values[i + 1] - values[i]) * frac;
    out.push(round6(Number(v)));
    t += stepsec;
  }
  return out;
}

// Python rounds to a fixed number of places at each step; matching that exactly is what
// keeps the parity delta at zero rather than at 1e-12 drifting into 0.06 over a sum.
function round4(x) { return Math.round(x * 1e4) / 1e4; }
function round6(x) { return Math.round(x * 1e6) / 1e6; }
