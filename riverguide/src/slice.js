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
  ["species", /\b(striper|stripers|striped bass|smallmouth|largemouth|trout|bass)\b/i],
  ["now", /\b(now|today|right now|currently|this morning|this afternoon|tonight|fishing well|best river|where should)\b/i],
];

/** Fields kept per intent. Anything not listed is dropped before the model sees it. */
// safetyClaims rides on EVERY slice, not just the generation one. The guard verifies
// replies against the claim book, and a slice without it makes every water sentence
// ungroundable — the model would be told about conditions it is then forbidden to
// describe. `zones` rides along too: species questions are answered from the zone model,
// not from a page's species label (§3.1).
const FIELDS = {
  base: ["id", "name", "emoji", "url", "species", "kind", "drive", "built",
         "safetyClaims", "zones"],
  // Trimmed views. The guard needs a claim's licensed `numbers` and id; the MODEL does
  // not — it is only ever allowed to quote `text`. Sending the numeric allowlist to the
  // model both costs tokens and reads like an invitation to recombine them.
  now: ["now", "today", "weather", "solunar", "waterModel"],
  week: ["now", "week", "weather"],
  fly: ["now", "today", "fly", "hatchNow", "tips"],
  access: ["access", "today", "now"],
  generation: ["now", "today", "tomorrow", "waterModel", "tips"],
  species: ["now", "today", "waterModel"],
  summary: ["now", "drive"],
};

export function detectIntent(text) {
  const hits = INTENTS.filter(([, re]) => re.test(text)).map(([k]) => k);
  if (!hits.length) return "now";
  // "what fly for the weekend" is a fly question with a week qualifier — the more specific
  // intent wins, so order in INTENTS is the precedence.
  return hits[0];
}

/**
 * Names people actually use that are not river names. Found by testing: "when does Center
 * Hill generate" matched NOTHING, so it shipped all thirteen rivers — 5,549 tokens for a
 * question about one. Dams, lakes and towns are how anglers refer to these reaches.
 */
const ALIASES = {
  caney:      ["center hill", "centerhill", "stonewall", "betty's island", "bettys island", "happy hollow", "long branch", "smith fork"],
  cumberland: ["wolf creek", "kendall", "burkesville", "winfrey"],
  elktn:      ["tims ford", "timsford", "fayetteville"],
  elk:        ["wheeler", "prospect", "joe wheeler"],
  stones:     ["percy priest", "priest", "j. percy priest"],
  cumbnash:   ["old hickory", "nashville", "shelby bottoms", "cleeces"],
  cheatham:   ["cheatham dam", "ashland city"],
  cordell:    ["cordell hull", "carthage"],
  duckup:     ["columbia", "chickasaw trace", "iron bridge"],
  duckmid:    ["williamsport", "leatherwood"],
  ducklow:    ["centerville", "littlelot"],
  buffalo:    ["flatwoods", "lobelville"],
  harpeth:    ["narrows", "kingston springs", "newsom", "hidden lake"],
};

/** Rivers named in the question, by name, id, alias, or a distinctive word from the name. */
export function detectRivers(text, corpus) {
  const t = text.toLowerCase();
  const hit = [];
  for (const [id, names] of Object.entries(ALIASES)) {
    if (names.some((n) => t.includes(n)) && corpus.rivers.some((r) => r.id === id)) hit.push(id);
  }
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

/** Which safety claims matter most when the view has to be trimmed. */
const KIND_RANK = ["safe_exit", "wade_cutoff", "release_arrival", "generation_start",
                   "generation_stop", "weather_hazard", "flow", "stage",
                   "forecast_release", "lake_elevation"];

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
  const claims = rivers.flatMap((r) => r.safetyClaims || []);
  const zoneIds = rivers.flatMap((r) => (r.zones || []).map((z) => z.id));

  // Only the research claims the sliced zones actually cite — the corpus carries them all,
  // and shipping seventeen of them to answer one question is the cost mistake this module
  // exists to avoid.
  const wanted = new Set();
  for (const r of rivers) {
    for (const z of r.zones || []) {
      for (const ids2 of Object.values(z.evidence || {})) for (const i of ids2) wanted.add(i);
    }
  }
  const researchClaims = {};
  for (const id of wanted) {
    if (corpus.researchClaims && corpus.researchClaims[id]) {
      researchClaims[id] = corpus.researchClaims[id];
    }
  }

  // What the MODEL sees: the claim sentences and nothing else about them.
  const modelRivers = rivers.map((r) => {
    const o = { ...r };
    if (o.safetyClaims) {
      // Soonest first, then a cap. The claim text already names its zone, so `zone` is
      // redundant here; the guard keeps the untrimmed book either way, so a claim dropped
      // from this view can still ground nothing worse than silence.
      o.safetyClaims = o.safetyClaims
        .slice()
        .sort((a, b) => KIND_RANK.indexOf(a.kind) - KIND_RANK.indexOf(b.kind))
        .slice(0, 10)
        .map((c) => ({ kind: c.kind, bound: c.bound, text: c.text }));
    }
    if (o.zones) {
      // `holds` is a paragraph per species per zone. It is the answer to "where do I
      // fish", and noise on "is the dam running" — so it rides only where it is the point.
      const wantHolds = ["species", "access", "now"].includes(intent);
      o.zones = o.zones.map((z) => (intent === "species" ? z
        : { id: z.id, name: z.name, species: z.species, craft: z.craft,
            tailwater: z.tailwater, ...(wantHolds ? { holds: z.holds } : {}) }));
    }
    return o;
  });

  return {
    intent,
    rivers: ids,
    note,
    // Every zone id in the slice. The guard scopes verification to these: a claim about
    // Cheatham may not ground a sentence about the Caney.
    zones: zoneIds,
    claims,
    payload: {
      built: corpus.built,
      builtIso: corpus.builtIso,
      region: corpus.region,
      rules: corpus.rules,
      planner: corpus.planner,
      researchClaims,
      rivers: modelRivers,
    },
  };
}

export function tokenEstimate(payload) {
  return Math.round(JSON.stringify(payload).length / 4);
}
