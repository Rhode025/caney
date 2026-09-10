/**
 * Claim normalisation, tiering, decay and dedupe. §19, §22, §23, §24, §26, §78.
 *
 * Pure functions, no bindings, no network — so `test.mjs` covers all of it without
 * Cloudflare and without a key.
 */

/** §16 — tier is DERIVED from the domain, never asserted by whatever produced the claim. */
export const TIER_DOMAINS = {
  A: ["usgs.gov", "usace.army.mil", "water.noaa.gov", "noaa.gov", "weather.gov",
      "tva.com", "tva.gov", "cwms.usace.army.mil"],
  B: ["tn.gov", "tnwildlife.org", "fws.gov", "ky.gov", "fw.ky.gov", "alabama.gov",
      "outdooralabama.com", "eregulations.com", "utk.edu", "tntech.edu", "usda.gov",
      "epa.gov", "mdc.mo.gov", "georgiawildlife.com"],
};
export const TIER_WEIGHT = { A: 1.0, B: 0.85, C: 0.5, D: 0.25 };

/** §20 — Tier C is a judgement about the SOURCE, so it is an explicit hint list. */
export const TIER_C_HINTS = ["guide", "flyshop", "fly-shop", "outfitter", "marina",
                             "orvis", "anglers", "outdoors", "tailwater"];

export function domainOf(url) {
  try { return new URL(url).hostname.toLowerCase(); } catch (e) { return ""; }
}

export function tierFor(url) {
  const d = domainOf(url);
  if (!d) return "D";
  for (const [tier, sufs] of Object.entries(TIER_DOMAINS)) {
    for (const s of sufs) if (d === s || d.endsWith("." + s)) return tier;
  }
  if (TIER_C_HINTS.some((h) => d.includes(h))) return "C";
  return "D";
}

export const CLAIM_TYPES = [
  "species_presence", "seasonal_distribution", "migration", "thermal_refuge",
  "current_response", "generation_response", "habitat", "forage", "time_of_day",
  "weather_response", "technique", "recent_report", "stocking", "survey",
  "creel_result", "regulation",
];

const TYPE_PATTERNS = [
  ["stocking", /\bstock(?:ed|ing|s)?\b/i],
  ["creel_result", /\bcreel\b/i],
  ["survey", /\b(electrofish\w*|gill\s*net|survey|sampl\w+|population estimate)\b/i],
  ["regulation", /\b(creel limit|length limit|minimum length|regulation|advisory|closed season)\b/i],
  ["migration", /\b(migrat\w+|run upstream|move upstream|spawning run)\b/i],
  ["thermal_refuge", /\b(thermal|refuge|cool\w*\s+water|oxygenat\w+|dissolved oxygen)\b/i],
  ["generation_response", /\b(generat\w+|turbine|units? (?:running|turning)|discharge schedule)\b/i],
  ["current_response", /\b(current|flow|seam|eddy|tailrace)\b/i],
  ["forage", /\b(shad|herring|forage|bait\w*|crayfish|sculpin|alewife|bluegill)\b/i],
  ["seasonal_distribution", /\b(spring|summer|fall|autumn|winter|spawn\w*|month of|during may)\b/i],
  ["time_of_day", /\b(dawn|dusk|morning|evening|low.light|night|first light)\b/i],
  ["weather_response", /\b(front|barometric|cloud|wind|rain|storm)\b/i],
  ["habitat", /\b(ledge|shoal|stump|flat|creek|bluff|structure|vegetation|grass|wood|riprap|point)\b/i],
  ["technique", /\b(fly|streamer|nymph|swing|strip|leader|tippet|presentation)\b/i],
  ["recent_report", /\b(this week|last week|recently|currently|report for)\b/i],
];

export function classify(text) {
  for (const [type, re] of TYPE_PATTERNS) if (re.test(text)) return type;
  return "species_presence";
}

/**
 * §20 — a number that could be acted on as a water measurement. Such a claim is KEPT for
 * its language and flagged; nothing anywhere reads a number out of a ResearchClaim.
 */
export const SAFETY_SENSITIVE_RE = new RegExp(
  "\\d[\\d,]*(?:\\.\\d+)?\\s*(?:cfs|kcfs|cubic\\s*feet)" +
  "|(?:stage|gauge|gage|level)\\D{0,12}\\d+(?:\\.\\d+)?\\s*(?:ft|feet|')?" +
  "|\\d+(?:\\.\\d+)?\\s*(?:ft|feet)\\D{0,12}(?:stage|gauge|gage)" +
  "|generat\\w*\\D{0,12}\\d" +
  "|releas\\w*\\D{0,12}\\d" +
  "|wade\\s+(?:until|cutoff|window)" +
  "|\\d{1,2}:\\d{2}\\s*(?:am|pm)?\\s*(?:release|generation|until)", "i");

/**
 * §24 — claims age at very different rates. A guide's Tuesday report and an electrofishing
 * survey are not the same kind of fact, and giving them one TTL makes the recent one go
 * stale far too slowly and the structural one far too fast.
 *
 * THE TABLE IS NOT HERE ANY MORE. It is generated from caney/research/decay.py into
 * ./decay.generated.js by tools/emit_decay.py, and a Python test fails if the two drift. Python
 * owns it for the same reason CLAUDE.md gives for every calibrated constant: a value that
 * lives in two places gets edited in one — and this one did. The Python side had a single
 * step curve for all claim types and disagreed with this table by 18x on a month-old
 * fishing report.
 *
 * `ttlSeconds` is when we would go looking again; `halfLifeDays` is how fast the claim's
 * influence decays in the meantime; `floor` is how much it is always worth.
 */
export { DECAY, DEFAULT_DECAY, DECAY_ALIASES } from "./decay.generated.js";
import { DECAY, DEFAULT_DECAY, DECAY_ALIASES } from "./decay.generated.js";

export function decayFor(claimType) {
  const key = DECAY_ALIASES[claimType] || claimType;
  return DECAY[key] || DEFAULT_DECAY;
}

/** 0..1 — how much a claim of this type, this old, still counts. */
export function recency(claimType, ageDays) {
  const d = decayFor(claimType);
  const v = Math.pow(0.5, Math.max(0, ageDays) / d.halfLifeDays);
  return Math.max(d.floor, Math.min(1, v));
}

export function isStale(claimType, retrievedAt, now = Date.now() / 1000) {
  return (now - retrievedAt) > decayFor(claimType).ttlSeconds;
}

/**
 * §26 — the research influence formula, stated once:
 *
 *     source_quality x geographic_match x seasonal_match x recency
 *
 * Its TOTAL contribution is capped by the species weight config on the planner side; this
 * only produces the 0..1 strength of an individual claim.
 */
export function combinedConfidence({ tier, geographicMatch, seasonalMatch, claimType,
                                     ageDays }) {
  const q = TIER_WEIGHT[tier] !== undefined ? TIER_WEIGHT[tier] : 0.25;
  return round4(q * geographicMatch * seasonalMatch * recency(claimType, ageDays));
}

export function geographicMatch(claimZones, askedZones) {
  if (!askedZones || !askedZones.length) return 1;
  if (!claimZones || !claimZones.length) return 0.3;
  return claimZones.some((z) => askedZones.includes(z)) ? 1 : 0.3;
}

export function seasonalMatch(validMonths, month) {
  if (!validMonths || !validMonths.length || !month) return 1;
  return validMonths.includes(month) ? 1 : 0.15;
}

/**
 * §19, §20 — a finding becomes a claim, or it becomes nothing. Returns {claim} or
 * {reject: reason}, so the audit trail can record WHY something was dropped.
 */
export function toClaim(finding, ctx) {
  const url = String((finding && finding.url) || "").trim();
  if (!url) return { reject: "no source url" };
  if (!/^https?:\/\//i.test(url)) return { reject: "source url is not http(s)" };
  const text = String((finding && finding.text) || "").trim();
  if (text.length < 25) return { reject: "claim text too short to be a claim" };
  if (text.length > 1200) return { reject: "claim text implausibly long" };

  const domain = domainOf(url);
  const tier = tierFor(url);
  if (ctx.primaryOnly && !["A", "B"].includes(tier)) {
    return { reject: "primary search returned a non-agency domain: " + domain };
  }
  const claimType = classify(text);
  const validMonths = Array.isArray(finding.valid_months)
    ? finding.valid_months.filter((m) => m >= 1 && m <= 12) : [];
  const published = normaliseDate(finding.published);
  const ageDays = published
    ? Math.max(0, (ctx.now - Date.parse(published) / 1000) / 86400) : 180;

  const geo = geographicMatch(ctx.zoneIds, ctx.zoneIds);
  const sea = seasonalMatch(validMonths, ctx.month);

  return {
    claim: {
      id: hashId(url + "|" + ctx.species + "|" + text.slice(0, 160)),
      species: ctx.species,
      claim_type: claimType,
      zone_ids: ctx.zoneIds,
      waterbody_ids: ctx.waterbodyIds || [],
      geographic_description: String(finding.where || "").slice(0, 240),
      claim: text,
      source_url: url,
      source_title: String(finding.title || "").slice(0, 240),
      source_domain: domain,
      source_tier: tier,
      published_at: published,
      retrieved_at: Math.round(ctx.now),
      valid_months: validMonths,
      season: String(finding.season || ""),
      geographic_confidence: geo,
      seasonal_relevance: sea,
      recency: recency(claimType, ageDays),
      source_quality: TIER_WEIGHT[tier],
      combined_confidence: combinedConfidence({
        tier, geographicMatch: geo, seasonalMatch: sea, claimType, ageDays }),
      safety_sensitive: SAFETY_SENSITIVE_RE.test(text) ? 1 : 0,
    },
  };
}

/** §78 — the same assertion, from the same source, about the same water, once. */
export function dedupeKey(c) {
  return [c.species, c.claim_type, c.source_url, c.claim.slice(0, 160)].join("|");
}

export function dedupe(claims) {
  const seen = new Map();
  for (const c of claims) {
    const k = dedupeKey(c);
    const prev = seen.get(k);
    // Revisiting a known source REFRESHES its metadata rather than adding a row.
    if (!prev || c.retrieved_at > prev.retrieved_at) seen.set(k, c);
  }
  return [...seen.values()];
}

/** §27 — do not silently choose. Report that authorities disagree. */
export function disagreements(claims) {
  const out = [];
  const byType = {};
  for (const c of claims) (byType[c.claim_type] = byType[c.claim_type] || []).push(c);
  for (const [type, list] of Object.entries(byType)) {
    if (list.length < 2) continue;
    const tiers = new Set(list.map((c) => c.source_tier));
    if (tiers.size < 2) continue;
    const best = ["A", "B", "C", "D"].find((t) => tiers.has(t));
    out.push({
      claim_type: type,
      tiers: [...tiers].sort(),
      authoritative: best,
      note: "Sources of different authority disagree about " + type.replace(/_/g, " ") +
            ". The tier " + best + " source is weighted higher; the others are shown but " +
            "do not override it.",
    });
  }
  return out;
}

function normaliseDate(v) {
  if (!v) return null;
  const s = String(v).slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s)) ? s : null;
}

function hashId(s) {
  let h1 = 0x811c9dc5, h2 = 0x01000193;
  for (let i = 0; i < s.length; i++) {
    h1 = (h1 ^ s.charCodeAt(i)) >>> 0;
    h1 = Math.imul(h1, 16777619) >>> 0;
    h2 = (h2 + s.charCodeAt(i) * (i + 7)) >>> 0;
  }
  return "rc_" + h1.toString(16).padStart(8, "0") + h2.toString(16).padStart(8, "0");
}

function round4(x) { return Math.round(x * 1e4) / 1e4; }
