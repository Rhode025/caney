/**
 * Trip log → evidence engine, and the model scoreboard. §43, §44.
 *
 * The goal is `prediction → outcome → calibration`, not a fishing diary. So the moment a
 * plan is logged, WHAT CANEY PREDICTED is frozen alongside it: the score, the confidence,
 * the arrival distribution, the expected flow and generation state, the fly it chose. When
 * the outcome is filled in later, the two sit side by side and the residuals are
 * computable — which is the only way to find out whether 2.5 mph is right, whether the
 * confidence numbers mean anything, and whether the species weights need moving.
 *
 * Storage is localStorage on the device, with explicit export. Nothing leaves the phone.
 */
import { hm } from "./format.js";

const KEY = "caney.trips.v2";
const VERSION = 3;

export function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "null");
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;                  // v1: a bare array
    return raw.trips || [];
  } catch (e) {
    return [];
  }
}

function save(trips) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ version: VERSION, trips }));
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * §50 — freeze the plan-time evidence. Called when the user logs a plan, BEFORE they know
 * anything about how it went; that ordering is the whole point.
 *
 * 2.1 freezes materially more than 2.0 did, because the questions in §51 cannot be answered
 * without it: the hourly opportunity scores, the candidate ranking, the winning itinerary,
 * the conditions, the research claims, the four confidences, the model versions and the
 * weights. None of it is ever overwritten — a recheck writes a delta alongside, never over.
 */
export function snapshotPrediction(data, ctx) {
  const p = ctx.plan;
  const zones = p.zoneSequence;
  const wins = p.itinerary.windows;
  const zone0 = data.zones[zones[0]];
  const claims = data.safety.filter((c) => zones.includes(c.zone_id));
  const arrival = claims.find((c) => c.kind === "release_arrival");
  const exit = claims.find((c) => c.kind === "safe_exit");
  const tech = (ctx.segments.find((s) => s.type === "fish" && s.technique) || {}).technique;

  return {
    builtAt: data.built,
    plannedAt: Math.round(Date.now() / 1000),
    species: ctx.species, craft: ctx.craft,
    requested: { start: Math.round(ctx.start), end: Math.round(ctx.end) },

    // §53 — so a result stored today is still interpretable after the model moves.
    versions: data.versions || {},
    weights: (data.weights || {})[ctx.species] || {},
    utilityConstants: data.utility || {},

    verdict: ctx.verdict,
    opportunity: p.opportunity,
    confidence: p.confidence,
    locationConfidence: p.locationConfidence,
    researchConfidence: p.researchConfidence,
    utility: p.itinerary.utility,
    utilityParts: p.itinerary.parts,

    zone: zones[0], zoneName: zone0.name, zoneSequence: zones,
    zoneKind: zone0.kind,
    window: { start: Math.round(wins[0].start), end: Math.round(wins[wins.length - 1].end) },

    // The itinerary as executed-intent, segment by segment (§49).
    segments: ctx.segments.map((s, i) => ({
      i, type: s.type, start: Math.round(s.start), end: Math.round(s.end),
      zone: s.zone_id, instructions: s.instructions,
      expected: s.expected_score === undefined ? null : s.expected_score,
      fly: s.technique ? s.technique.primary_fly : null,
    })),

    // The hourly opportunity curve for every candidate that was ranked (§50).
    hourly: Object.fromEntries(p.candidates.slice(0, 6).map((c) => [
      c.zone, (data.hourly[c.zone + "|" + ctx.species] || {}).values || []])),
    hourlyT0: (data.hourly[zones[0] + "|" + ctx.species] || {}).t0 || null,
    ranking: p.candidates.slice(0, 6).map((c) => ({
      zone: c.zone, utility: c.bestUtility, confidence: c.confidence,
      locationConfidence: c.locationConfidence })),

    // The numbers the model will be graded on.
    predictedArrival: arrival && Array.isArray(arrival.value)
      ? { earliest: arrival.value[0], typical: arrival.value[1], latest: arrival.value[2] }
      : null,
    predictedSafeExit: exit ? exit.value : null,
    predictedFlow: ((zone0.water || {}).flow || {}).value,
    predictedFlowState: ((zone0.water || {}).flow || {}).state,
    predictedGeneration: ((zone0.water || {}).generation || {}).value,
    predictedWaterTemp: ((zone0.water || {}).water_temp || {}).value,
    modelConfidence: zone0.modelConfidence,
    conditions: wins[0].conditions_summary || "",

    research: (data.evidence[zones[0] + "|" + ctx.species] || []).map((r) => {
      const id = typeof r === "string" ? r : r.id;
      const c = data.claims[id] || {};
      return { id, tier: c.source_tier, type: c.claim_type, url: c.source_url,
               confidence: typeof r === "string" ? null : r.confidence };
    }),
    researchProvider: (data.research || {}).provider,

    fly: tech ? tech.primary_fly : null,
    breakdown: (ctx.primary ? ctx.primary.lines : [])
      .map((l) => ({ k: l.key, got: l.earned, of: l.possible, known: l.known })),

    // §54 — a slot for a shadow scorer's ranking, stored and never displayed.
    shadow: data.shadow || null,
  };
}

export function add(prediction) {
  const trips = load();
  const trip = {
    id: "trip_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36),
    prediction,
    outcome: null,
  };
  trips.unshift(trip);
  save(trips);
  return trip;
}

/**
 * §48 — the FIRST screen, and it has to be almost free to answer. Four taps, no typing.
 * Friction here is the only thing between the model and the calibration data it needs.
 */
export const QUICK_FIELDS = [
  { key: "fished", label: "Did you fish the plan?", type: "choice",
    options: [["yes", "Yes"], ["partly", "Partly"], ["no", "No"]] },
  { key: "target_caught", label: "Target species caught?", type: "choice",
    options: [["yes", "Yes"], ["no", "No"]] },
  { key: "rating", label: "How was the fishing?", type: "rating", min: 1, max: 5 },
  { key: "right_place", label: "Did Caney put you in the right place?", type: "choice",
    options: [["yes", "Yes"], ["partly", "Partly"], ["no", "No"]] },
];

/** §43 — the optional detail, behind a disclosure. Every field is optional. */
export const OUTCOME_FIELDS = [
  { key: "count", label: "How many", type: "number" },
  { key: "largest", label: "Largest (in)", type: "number" },
  { key: "species_caught", label: "Species caught", type: "text" },
  { key: "actual_arrival", label: "Water actually came up at", type: "time" },
  { key: "actual_clarity", label: "Clarity you saw", type: "select",
    options: ["", "clear", "stained", "colored", "muddy"] },
  { key: "actual_temp", label: "Water temp if known (°F)", type: "number" },
  { key: "fly_that_worked", label: "Fly that actually worked", type: "text" },
  { key: "where_holding", label: "Where the fish actually were", type: "text" },
  { key: "notes", label: "Notes", type: "textarea" },
];

/** §49 — per-segment outcomes, which calibrate far better than one trip-wide rating. */
export const SEGMENT_FIELDS = [
  { key: "fished", label: "Fished it?", type: "choice",
    options: [["yes", "Yes"], ["no", "No"]] },
  { key: "caught", label: "Fish", type: "number" },
  { key: "largest", label: "Largest (in)", type: "number" },
  { key: "holding", label: "Where they actually were", type: "text" },
  { key: "fly", label: "What actually worked", type: "text" },
  { key: "notes", label: "Notes", type: "text" },
];

export function recordSegment(id, index, outcome) {
  const trips = load();
  const t = trips.find((x) => x.id === id);
  if (!t) return null;
  t.segmentOutcomes = t.segmentOutcomes || {};
  t.segmentOutcomes[index] = Object.assign({}, t.segmentOutcomes[index], outcome,
                                           { recordedAt: Math.round(Date.now() / 1000) });
  save(trips);
  return t;
}

export function record(id, outcome) {
  const trips = load();
  const t = trips.find((x) => x.id === id);
  if (!t) return null;
  t.outcome = { ...(t.outcome || {}), ...outcome,
                recordedAt: Math.round(Date.now() / 1000) };
  save(trips);
  return t;
}

export function remove(id) {
  save(load().filter((t) => t.id !== id));
}

export function exportJson() {
  return JSON.stringify({ version: VERSION, exportedAt: Date.now() / 1000,
                          trips: load() }, null, 2);
}

export function importJson(text) {
  const parsed = JSON.parse(text);
  const incoming = Array.isArray(parsed) ? parsed : (parsed.trips || []);
  const have = new Set(load().map((t) => t.id));
  const merged = load().concat(incoming.filter((t) => t && t.id && !have.has(t.id)));
  save(merged);
  return merged.length;
}

/**
 * §44, §51, §52 — the model scoreboard.
 *
 * The questions it has to answer, in the brief's own words:
 *
 *   Does a 90 score actually outperform an 80?
 *   Does high confidence correspond to higher accuracy?
 *   Which species model performs best?
 *   Which zones are poorly calibrated?
 *   Does research improve results?
 *   Does the itinerary optimiser outperform single-zone recommendations?
 *
 * Every measure reports its own sample size and REFUSES to print a figure until there is
 * enough data. That refusal is the feature: a model whose validation is one trip should
 * say so rather than print a number somebody will act on. Grouped by model version (§53),
 * because a calibration result computed across a weight change means nothing.
 */
export function scoreboard(trips = load()) {
  const done = trips.filter((t) => t.outcome && fished(t));

  // 1. Water-arrival residual: predicted TYPICAL vs observed, in minutes.
  const arrRows = done.filter((t) => t.prediction.predictedArrival && t.outcome.actual_arrival);
  const arr = arrRows.map((t) =>
    (t.outcome.actual_arrival - t.prediction.predictedArrival.typical) / 60);
  const inBounds = arrRows.filter((t) =>
    t.outcome.actual_arrival >= t.prediction.predictedArrival.earliest &&
    t.outcome.actual_arrival <= t.prediction.predictedArrival.latest);
  const early = arrRows.filter((t) =>
    t.outcome.actual_arrival < t.prediction.predictedArrival.earliest);

  const rated = done.filter((t) => t.outcome.rating);

  // 2. Does a 90 outperform an 80? Bucket by opportunity, compare mean rating.
  const oppBands = [["90+", 90, 101], ["80-89", 80, 90], ["70-79", 70, 80], ["<70", 0, 70]]
    .map(([band, lo, hi]) => {
      const rows = rated.filter((t) => opp(t) >= lo && opp(t) < hi);
      return { band, n: rows.length,
               meanRating: rows.length ? mean(rows.map((t) => Number(t.outcome.rating))) : null };
    });

  // 3. Confidence calibration.
  const confBands = [["high", 78, 101], ["moderate", 55, 78], ["low", 0, 55]]
    .map(([band, lo, hi]) => {
      const rows = rated.filter((t) => t.prediction.confidence >= lo &&
                                       t.prediction.confidence < hi);
      return { band, n: rows.length,
               meanRating: rows.length ? mean(rows.map((t) => Number(t.outcome.rating))) : null,
               rightPlace: rate(rows, (t) => t.outcome.right_place === "yes") };
    });

  // 4. Location confidence vs "did Caney put you in the right place".
  const locBands = [["85+", 85, 101], ["62-84", 62, 85], ["<62", 0, 62]]
    .map(([band, lo, hi]) => {
      const rows = done.filter((t) => {
        const v = t.prediction.locationConfidence;
        return v !== undefined && v >= lo && v < hi && t.outcome.right_place;
      });
      return { band, n: rows.length, rightPlace: rate(rows, (t) => t.outcome.right_place === "yes") };
    });

  // 5. Per species, and per zone — which models are weak.
  const bySpecies = group(rated, (t) => t.prediction.species).map(([k, rows]) => ({
    key: k, n: rows.length, meanRating: mean(rows.map((t) => Number(t.outcome.rating))),
    targetHit: rate(rows, (t) => t.outcome.target_caught === "yes"),
  })).sort((a, b) => (b.meanRating || 0) - (a.meanRating || 0));

  const byZone = group(rated, (t) => t.prediction.zone).map(([k, rows]) => ({
    key: k, n: rows.length, meanRating: mean(rows.map((t) => Number(t.outcome.rating))),
    meanOpportunity: mean(rows.map(opp)),
    // Poor calibration = the model was confident and the day was not good.
    gap: mean(rows.map((t) => opp(t) / 20 - Number(t.outcome.rating))),
  })).sort((a, b) => Math.abs(b.gap || 0) - Math.abs(a.gap || 0));

  // 6. Does the itinerary optimiser beat a single zone?
  const multi = rated.filter((t) => (t.prediction.zoneSequence || []).length > 1);
  const single = rated.filter((t) => (t.prediction.zoneSequence || []).length <= 1);

  // 7. Does research help?
  const withRes = rated.filter((t) => (t.prediction.research || []).length >= 2);
  const withoutRes = rated.filter((t) => (t.prediction.research || []).length < 2);

  const corr = pearson(rated.map(opp), rated.map((t) => Number(t.outcome.rating)));

  return {
    trips: trips.length, fished: done.length,
    versions: group(done, (t) => (t.prediction.versions || {}).planner || "unknown")
      .map(([k, rows]) => ({ version: k, n: rows.length })),
    arrival: {
      n: arr.length,
      medianResidualMin: arr.length ? median(arr) : null,
      meanAbsMin: arr.length ? mean(arr.map(Math.abs)) : null,
      insideBounds: arr.length ? inBounds.length / arr.length : null,
      earlierThanEarliest: early.length,
      verdict: arr.length < 5 ? "not enough trips to say" :
        (Math.abs(median(arr)) < 30 ? "the typical arrival is close" :
         median(arr) > 0 ? "the model runs EARLY — water arrives later than predicted"
                         : "the model runs LATE — water arrives sooner than predicted"),
      safetyNote: early.length
        ? early.length + " trip(s) saw water BEFORE the earliest bound — that is the bound " +
          "safety decisions use, so it is the number to move first."
        : "no trip has seen water before the earliest bound",
    },
    opportunity: {
      n: rated.length, correlation: corr, bands: oppBands,
      verdict: rated.length < 10 ? "not enough rated trips to say" :
        monotonicDown(oppBands.map((b) => b.meanRating))
          ? "higher opportunity scores do produce better days"
          : "opportunity is NOT tracking outcome — the bands are out of order",
    },
    calibration: {
      bands: confBands,
      verdict: rated.length < 12 ? "not enough rated trips to say" :
        monotonicDown(confBands.map((b) => b.meanRating))
          ? "confidence bands rank in the right order"
          : "confidence is NOT tracking outcome — the bands are out of order",
    },
    location: {
      bands: locBands,
      verdict: done.length < 10 ? "not enough trips to say" :
        monotonicDown(locBands.map((b) => b.rightPlace))
          ? "location confidence predicts whether you were in the right place"
          : "location confidence is NOT tracking whether the place was right",
    },
    species: { rows: bySpecies, verdict: rated.length < 12 ? "not enough rated trips to say" : null },
    zones: { rows: byZone.slice(0, 8),
             verdict: rated.length < 12 ? "not enough rated trips to say" :
               "largest gap: " + (byZone[0] ? byZone[0].key : "—") },
    itinerary: {
      multiN: multi.length, singleN: single.length,
      multiMean: multi.length ? mean(multi.map((t) => Number(t.outcome.rating))) : null,
      singleMean: single.length ? mean(single.map((t) => Number(t.outcome.rating))) : null,
      verdict: (multi.length < 5 || single.length < 5)
        ? "not enough multi-zone trips to say"
        : (mean(multi.map((t) => Number(t.outcome.rating))) >
           mean(single.map((t) => Number(t.outcome.rating)))
            ? "multi-zone plans are outperforming single-zone ones"
            : "multi-zone plans are NOT outperforming single-zone ones — the move may not " +
              "be worth what the optimiser charges for it"),
    },
    research: {
      withN: withRes.length, withoutN: withoutRes.length,
      withMean: withRes.length ? mean(withRes.map((t) => Number(t.outcome.rating))) : null,
      withoutMean: withoutRes.length ? mean(withoutRes.map((t) => Number(t.outcome.rating))) : null,
      verdict: (withRes.length < 5 || withoutRes.length < 5)
        ? "not enough trips on both sides to say" : null,
    },
    segments: segmentStats(done),
  };
}

/** §49 — segment-level outcomes calibrate the itinerary, not just the day. */
function segmentStats(done) {
  const rows = [];
  for (const t of done) {
    for (const [i, o] of Object.entries(t.segmentOutcomes || {})) {
      const seg = (t.prediction.segments || []).find((s) => String(s.i) === String(i));
      if (!seg || seg.expected === null || seg.expected === undefined) continue;
      rows.push({ expected: seg.expected, caught: Number(o.caught || 0),
                  fished: o.fished === "yes", zone: seg.zone });
    }
  }
  const fishedRows = rows.filter((r) => r.fished);
  return {
    n: rows.length, fished: fishedRows.length,
    correlation: fishedRows.length >= 3
      ? pearson(fishedRows.map((r) => r.expected), fishedRows.map((r) => r.caught)) : null,
    verdict: fishedRows.length < 8
      ? "not enough logged segments to say"
      : "expected segment score vs fish actually caught",
  };
}

function fished(t) {
  const f = t.outcome.fished;
  return f === true || f === "yes" || f === "partly";
}
function opp(t) {
  const p = t.prediction;
  return p.opportunity !== undefined ? p.opportunity : p.score;
}
function rate(rows, pred) {
  return rows.length ? rows.filter(pred).length / rows.length : null;
}
function group(rows, keyOf) {
  const m = new Map();
  for (const r of rows) {
    const k = keyOf(r);
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(r);
  }
  return [...m.entries()];
}
function monotonicDown(a) {
  const v = a.filter((x) => x !== null && x !== undefined);
  if (v.length < 2) return false;
  for (let i = 1; i < v.length; i++) if (v[i] > v[i - 1]) return false;
  return true;
}


function shortName(sp) {
  return { striped_bass: "strip", smallmouth: "smallmouth", largemouth: "largemouth",
           trout: "trout" }[sp] || sp;
}

function mean(a) { return a.length ? a.reduce((x, y) => x + y, 0) / a.length : null; }

function median(a) {
  if (!a.length) return null;
  const s = a.slice().sort((x, y) => x - y);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function pearson(x, y) {
  const n = x.length;
  if (n < 3) return null;
  const mx = mean(x), my = mean(y);
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < n; i++) {
    num += (x[i] - mx) * (y[i] - my);
    dx += (x[i] - mx) ** 2;
    dy += (y[i] - my) ** 2;
  }
  return dx && dy ? num / Math.sqrt(dx * dy) : null;
}

function monotonic(a) {
  const v = a.filter((x) => x !== null);
  if (v.length < 2) return false;
  for (let i = 1; i < v.length; i++) if (v[i] > v[i - 1]) return false;
  return true;
}
