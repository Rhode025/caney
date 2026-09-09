/**
 * RiverGuide calls the planner. §45.
 *
 * A question like "where should I catch stripers around Carthage this morning?" is a
 * PLANNING question, and the answer already exists: planner.py wrote it, from the same
 * FishingZone / RiverSnapshot / ResearchClaim objects the web product uses. The bot's job
 * is to explain that plan, not to invent a competing one.
 *
 * So this module detects the question, resolves it to one of the pre-built FishingPlans
 * at /plan/featured/<species>-<craft>-d<day>-<preset>.json, and hands the model the plan.
 * The model gets the verdict, the window, the zone, the timeline and the score breakdown
 * as DATA — it may explain and caveat, and the guard still deletes any safety number it
 * invents on top.
 */

const SITE = "https://caney.pages.dev";

const SPECIES = [
  ["striped_bass", /\b(striper|stripers|striped\s*bass|rockfish|linesides?)\b/i],
  ["trout", /\b(trout|rainbow|brown|brookie|cutthroat)\b/i],
  ["smallmouth", /\b(smallmouth|smallies|bronzeback|brown\s*bass)\b/i],
  ["largemouth", /\b(largemouth|bucketmouth|green\s*bass)\b/i],
];

const CRAFT = [
  ["wade", /\b(wade|wading|on\s*foot|walk\s*in)\b/i],
  ["kayak", /\b(kayak|canoe|paddle|yak)\b/i],
  ["drift", /\b(drift\s*boat|driftboat|raft)\b/i],
  ["power", /\b(power\s*boat|jet\s*boat|jon\s*boat|bass\s*boat|boat)\b/i],
];

const PRESETS = [
  ["dawn", /\b(dawn|first\s*light|daybreak|sunrise|before\s*light)\b/i],
  ["morning", /\b(morning|am\b|early)\b/i],
  ["midday", /\b(midday|mid-?day|lunch|noon)\b/i],
  ["afternoon", /\b(afternoon|pm\b)\b/i],
  ["evening", /\b(evening|dusk|last\s*light|sunset|tonight|after\s*work)\b/i],
];

const PLANNING = /\b(where should|where do|best (?:place|spot|river|water)|plan|should i (?:go|fish)|what should i do|take me|recommend)\b/i;

/** null when this is not a planning question. */
export function detectPlanRequest(text, now = Date.now()) {
  const species = (SPECIES.find(([, re]) => re.test(text)) || [])[0];
  if (!species) return null;
  const asksForAPlan = PLANNING.test(text) || /\b(today|tomorrow|this (?:morning|afternoon|evening)|right now)\b/i.test(text);
  if (!asksForAPlan) return null;

  const craft = (CRAFT.find(([, re]) => re.test(text)) || ["any"])[0];
  const day = /\btomorrow\b/i.test(text) ? 1 : 0;
  let preset = (PRESETS.find(([, re]) => re.test(text)) || [])[0];
  if (!preset) preset = presetForNow(new Date(now));
  return { species, craft, day, preset, key: `${species}-${craft}-d${day}-${preset}` };
}

function presetForNow(d) {
  const h = d.getHours();
  if (h < 5) return "dawn";
  if (h < 10) return "morning";
  if (h < 13) return "midday";
  if (h < 16) return "afternoon";
  return "evening";
}

/** Fetch the pre-built FishingPlan. Returns null on any failure — the bot then answers
 *  from the corpus alone rather than refusing (§58). */
export async function fetchPlan(req, fetchImpl = fetch, site = SITE) {
  try {
    const r = await fetchImpl(`${site}/plan/featured/${req.key}.json`, { cache: "no-store" });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

/**
 * The model's view of a plan: the decision, the ITINERARY and the reasons — not the whole
 * object. §46: RiverGuide explains this plan; it does not build a competing one, and the
 * itinerary it describes has to be the same one the graphical planner shows.
 */
export function planPayload(plan) {
  if (!plan) return null;
  const it = plan.itinerary || null;
  return {
    verdict: plan.verdict,
    why: plan.verdict_why,
    // §31, §65 — four numbers, and the bot must not collapse them into one either.
    opportunity: plan.opportunity !== undefined ? plan.opportunity : plan.score,
    confidence: plan.confidence,
    locationConfidence: plan.location_confidence,
    researchConfidence: plan.research_confidence,
    whyThisWon: plan.why_this_won || [],
    availability: plan.availability || null,
    // THE ANSWER. Everything below is supporting detail for this.
    itinerary: it ? {
      zones: it.zone_sequence,
      fishingMinutes: it.total_fishing_minutes,
      transitionMinutes: it.total_transition_minutes,
      utility: it.utility_score,
      segments: (it.segments || []).map((s) => ({
        type: s.type, when: s.start, until: s.end,
        zone: s.zone_name || s.zone_id,
        instructions: s.instructions,
        reason: (s.reason || "").slice(0, 260),
        expected: s.expected_score,
        technique: s.technique ? {
          fly: s.technique.primary_fly, size: s.technique.primary_size,
          color: s.technique.primary_color, line: s.technique.line,
          presentation: s.technique.presentation, depth: s.technique.depth,
          switchWhen: s.technique.switch_trigger,
        } : null,
        triggers: (s.triggers || []).map((t) => ({ if: t.if, then: t.then })),
      })),
    } : null,
    backupPlan: plan.backup_plan || null,
    species: plan.species,
    craft: plan.craft,
    zone: plan.location && plan.location.name,
    waterbody: plan.location && plan.location.waterbody,
    pattern: plan.location && plan.location.pattern,
    holds: plan.location && plan.location.holds,
    drive: plan.location && plan.location.drive,
    detailPage: plan.location && plan.location.detail_page,
    window: plan.best_window,
    launch: plan.access && plan.access.launch && plan.access.launch.name,
    timeline: (plan.timeline || []).map((s) => ({
      at: s.at, when: s.at_label, title: s.title, kind: s.kind,
      detail: (s.detail || "").slice(0, 200),
      uncertainty: s.uncertainty || undefined,
      branches: s.branches && s.branches.length ? s.branches : undefined,
    })),
    technique: plan.technique,
    scoreBreakdown: (plan.score_breakdown || []).map((l) =>
      ({ what: l.label, got: l.earned, of: l.possible, why: l.why })),
    versions: plan.versions || null,
    alternatives: (plan.alternatives || []).slice(0, 4).map((a) =>
      ({ name: a.name, score: a.score, why: a.what_would_flip_it || a.reason })),
    evidence: (plan.evidence || []).map((c) =>
      ({ text: c.claim_text, url: c.source_url, tier: c.source_tier })),
    limitations: plan.limitations,
    // The claim book for the plan's own zone. The guard verifies against this too.
    safetyClaims: plan.safety || [],
  };
}

/** Zone ids the plan covers, for guard scoping. */
export function planZones(plan) {
  if (!plan) return [];
  const ids = new Set();
  if (plan.primary_candidate) ids.add(plan.primary_candidate);
  for (const c of plan.safety || []) ids.add(c.zone_id);
  return [...ids];
}
