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
const VERSION = 2;

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
 * Freeze the prediction. Called when the user logs a plan, BEFORE they know anything
 * about how it went — that ordering is the whole point.
 */
export function snapshotPrediction(data, ctx) {
  const { cand, species, craft, steps } = ctx;
  const z = cand.z;
  const arrival = data.safety.find(
    (c) => c.zone_id === cand.zone && c.kind === "release_arrival");
  const exit = data.safety.find(
    (c) => c.zone_id === cand.zone && c.kind === "safe_exit");
  const tech = steps && ctx.technique ? ctx.technique : null;
  return {
    builtAt: data.built,
    plannedAt: Math.round(Date.now() / 1000),
    species, craft,
    zone: cand.zone, zoneName: z.name,
    verdict: ctx.verdict,
    score: cand.score,
    confidence: cand.confidence,
    window: { start: cand.window.start, end: cand.window.end },
    // The numbers the model will be graded on.
    predictedArrival: arrival && Array.isArray(arrival.value)
      ? { earliest: arrival.value[0], typical: arrival.value[1], latest: arrival.value[2] }
      : null,
    predictedSafeExit: exit ? exit.value : null,
    predictedFlow: (z.water.flow || {}).value,
    predictedFlowState: (z.water.flow || {}).state,
    predictedGeneration: (z.water.generation || {}).value,
    predictedWaterTemp: (z.water.water_temp || {}).value,
    predictedClarity: (z.water.clarity || {}).value,
    modelConfidence: z.modelConfidence,
    breakdown: cand.lines.map((l) => ({ k: l.key, got: l.earned, of: l.possible })),
    fly: tech ? tech.primary_fly : null,
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

/** §43 — what the angler records afterwards. Every field is optional. */
export const OUTCOME_FIELDS = [
  { key: "fished", label: "Did you fish it?", type: "bool" },
  { key: "species_caught", label: "Species caught", type: "text" },
  { key: "count", label: "How many", type: "number" },
  { key: "largest", label: "Largest (in)", type: "number" },
  { key: "rating", label: "Rate the day (1-5)", type: "number", min: 1, max: 5 },
  { key: "actual_arrival", label: "Water actually came up at", type: "time" },
  { key: "actual_clarity", label: "Clarity you saw", type: "select",
    options: ["", "clear", "stained", "colored", "muddy"] },
  { key: "actual_temp", label: "Water temp if known (°F)", type: "number" },
  { key: "fly_that_worked", label: "Fly that actually worked", type: "text" },
  { key: "where_holding", label: "Where the fish actually were", type: "text" },
  { key: "notes", label: "Notes", type: "textarea" },
];

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
 * §44 — the model scoreboard.
 *
 * Four measures, each reported with its own sample size, and each reported as UNKNOWN
 * until there is enough data. A model whose validation is one trip should say so rather
 * than print a number.
 */
export function scoreboard(trips = load()) {
  const done = trips.filter((t) => t.outcome && t.outcome.fished);

  // 1. Water-arrival residual: predicted TYPICAL vs observed, in minutes.
  const arr = done
    .filter((t) => t.prediction.predictedArrival && t.outcome.actual_arrival)
    .map((t) => (t.outcome.actual_arrival - t.prediction.predictedArrival.typical) / 60);
  const inBounds = done
    .filter((t) => t.prediction.predictedArrival && t.outcome.actual_arrival)
    .filter((t) => t.outcome.actual_arrival >= t.prediction.predictedArrival.earliest &&
                   t.outcome.actual_arrival <= t.prediction.predictedArrival.latest);
  const early = done
    .filter((t) => t.prediction.predictedArrival && t.outcome.actual_arrival)
    .filter((t) => t.outcome.actual_arrival < t.prediction.predictedArrival.earliest);

  // 2. Candidate score vs the angler's rating.
  const rated = done.filter((t) => t.outcome.rating);
  const corr = pearson(rated.map((t) => t.prediction.score),
                       rated.map((t) => Number(t.outcome.rating)));

  // 3. Species recommendation success: did they catch the species they asked for?
  const spTried = done.filter((t) => t.outcome.species_caught !== undefined);
  const spHit = spTried.filter((t) =>
    String(t.outcome.species_caught || "").toLowerCase()
      .includes(shortName(t.prediction.species)));

  // 4. Confidence calibration: high-confidence plans should be right more often.
  const bands = [["high", 78, 101], ["moderate", 55, 78], ["low", 0, 55]];
  const calibration = bands.map(([name, lo, hi]) => {
    const rows = rated.filter((t) => t.prediction.confidence >= lo &&
                                     t.prediction.confidence < hi);
    return { band: name, n: rows.length,
             meanRating: rows.length ? mean(rows.map((t) => Number(t.outcome.rating))) : null };
  });

  return {
    trips: trips.length,
    fished: done.length,
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
        ? early.length + " trip(s) saw water BEFORE the earliest bound — that is the " +
          "bound safety decisions use, so it is the number to move first."
        : "no trip has seen water before the earliest bound",
    },
    rating: {
      n: rated.length,
      correlation: corr,
      verdict: rated.length < 8 ? "not enough rated trips to say" :
        (corr === null ? "unknown" : corr > 0.4 ? "the score tracks the day" :
         corr > 0.1 ? "the score tracks the day weakly" : "the score does not track the day"),
    },
    species: {
      n: spTried.length,
      hitRate: spTried.length ? spHit.length / spTried.length : null,
      verdict: spTried.length < 5 ? "not enough trips to say" : null,
    },
    calibration: {
      bands: calibration,
      verdict: rated.length < 12 ? "not enough rated trips to say" :
        monotonic(calibration.map((b) => b.meanRating))
          ? "confidence bands rank in the right order"
          : "confidence is NOT tracking outcome — the bands are out of order",
    },
  };
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
