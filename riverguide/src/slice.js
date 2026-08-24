/**
 * Pick the smallest slice of the corpus that can answer the question.
 *
 * This is the cost model. The full corpus is ~23,000 tokens; one river is ~1,900; the
 * all-rivers summary is ~1,200. Sending everything every time costs about 12x more than
 * sending the right thing, which dwarfs anything a compressor can do — measured: headroom
 * saves 9% on this corpus, slicing saves 92%.
 *
 * Deliberately dumb and deterministic. The model does the language; this only decides what
 * it gets to read. A wrong guess here costs a slightly worse answer, never a wrong number,
 * because whatever is included is verbatim from the build.
 */

const INTENTS = [
  ["fly", /\b(fly|flies|pattern|patterns|tie on|tippet|rig|streamer|midge|nymph|dry|hatch|bug|bugs|lure|what.*use)\b/i],
  ["week", /\b(week|weekend|next few days|forecast|coming days|saturday|sunday|monday|tuesday|wednesday|thursday|friday|tomorrow|outlook|plan)\b/i],
  ["access", /\b(ramp|ramps|launch|put in|put-in|take out|take-out|access|park|boat ramp|where can i|directions|drive)\b/i],
  ["generation", /\b(generation|generating|release|releases|schedule|units?|dam|wade window|wadeable|safe to wade|water on|water off)\b/i],
  ["now", /\b(now|today|right now|currently|this morning|this afternoon|tonight|fishing well|best river|where should)\b/i],
];

/** Fields kept per intent. Anything not listed is dropped before the model sees it. */
const FIELDS = {
  base: ["id", "name", "emoji", "url", "species", "kind", "drive", "built"],
  now: ["now", "today", "weather", "solunar", "waterModel"],
  week: ["now", "week", "weather"],
  fly: ["now", "today", "fly", "hatchNow", "tips"],
  access: ["access", "today", "now"],
  generation: ["now", "today", "tomorrow", "waterModel", "tips"],
  summary: ["now", "drive"],
};

export function detectIntent(text) {
  const hits = INTENTS.filter(([, re]) => re.test(text)).map(([k]) => k);
  if (!hits.length) return "now";
  // "what fly for the weekend" is a fly question with a week qualifier — the more specific
  // intent wins, so order in INTENTS is the precedence.
  return hits[0];
}

/** Rivers named in the question, by name, id, or a distinctive word from the name. */
export function detectRivers(text, corpus) {
  const t = text.toLowerCase();
  const hit = [];
  for (const r of corpus.rivers) {
    const words = [r.id, r.name.toLowerCase(), ...r.name.toLowerCase().split(/[^a-z]+/)]
      .filter((w) => w.length >= 4 && !["river", "upper", "lower", "middle", "fork"].includes(w));
    if (words.some((w) => t.includes(w))) hit.push(r.id);
  }
  // Species questions ("where are the smallmouth") select by species instead.
  if (!hit.length) {
    for (const r of corpus.rivers) {
      if ((r.species || []).some((s) => t.includes(s.toLowerCase().split(" ")[0]))) hit.push(r.id);
    }
  }
  return [...new Set(hit)];
}

function pick(river, keys) {
  const out = {};
  for (const k of [...FIELDS.base, ...keys]) if (river[k] !== undefined) out[k] = river[k];
  return out;
}

/**
 * @returns {{payload: object, note: string, rivers: string[], intent: string}}
 */
export function slice(text, corpus) {
  const intent = detectIntent(text);
  let ids = detectRivers(text, corpus);

  // No river named. Two shapes, and choosing the wrong one is the main way this gets
  // expensive: a comparison question ("what's fishing well") needs every river but only
  // its current line; a specific question about an unnamed river needs nothing more.
  let keys, note;
  if (!ids.length) {
    ids = corpus.rivers.map((r) => r.id);
    keys = intent === "week" ? FIELDS.week : FIELDS.summary;
    note = "No river named — every river, current conditions only.";
  } else if (ids.length > 4) {
    keys = FIELDS.summary;
    note = "Several rivers matched — current conditions only.";
  } else {
    keys = FIELDS[intent] || FIELDS.now;
    note = `Matched ${ids.length} river(s), intent "${intent}".`;
  }

  const rivers = corpus.rivers.filter((r) => ids.includes(r.id)).map((r) => pick(r, keys));
  return {
    intent,
    rivers: ids,
    note,
    payload: {
      built: corpus.built,
      builtIso: corpus.builtIso,
      region: corpus.region,
      rules: corpus.rules,
      rivers,
    },
  };
}

export function tokenEstimate(payload) {
  return Math.round(JSON.stringify(payload).length / 4);
}
