/**
 * The deterministic safety boundary. §3.3, §20.
 *
 * WHAT WAS WRONG WITH THE OLD ONE, because it is the reason this file is shaped like this:
 *
 *   1. It compared a reply's numbers against EVERY number anywhere in the slice, flattened
 *      to bare digits. "3,982" in a fly-box note licensed "3,982 cfs" in a wade sentence.
 *      Numeric presence somewhere did not prove the number belonged to that river, that
 *      measurement or that claim.
 *   2. Its HARMLESS set discarded small values after units were normalised away, so "2"
 *      and "3" passed unconditionally — including "the water comes up in 2 hours".
 *   3. On failure it SHIPPED THE SENTENCE and appended a warning. A reader who has already
 *      decided to wade does not un-decide because of an italic footnote. Unsafe prose was
 *      preserved by design.
 *
 * WHAT THIS DOES INSTEAD:
 *
 *   Python mints immutable SafetyClaims (caney/domain/claim.py) with stable ids and an
 *   explicit list of the digit-tokens each claim licenses, scoped to ONE zone. This module
 *   splits a reply into sentences, decides which are safety-sensitive, and for those
 *   requires every number to come from a claim about the water actually under discussion.
 *
 *   A safety-sensitive sentence that cannot be grounded is REMOVED — fail closed — and
 *   replaced with the claim text, or with an explicit "I don't have that" when there is no
 *   claim. Non-safety numbers (fly sizes, tippet, temperatures) keep the old, gentler
 *   treatment: they are annotated, because a wrong fly size is not a drowning risk.
 */

/** The vocabulary that makes a numeric sentence safety-sensitive. */
const SAFETY_CUES = new RegExp(
  "(\\b(" +
  "generat\\w*|release[sd]?|releasing|discharge|units?\\s+(?:turning|running|on)|" +
  "wade|wading|wadeable|waders?|exit|cut\\s*off|cutoff|" +
  "flow|cfs|kcfs|stage|gauge|gage|level|rise|rising|rises|arrival|arrives?|" +
  "front|crest|peak|lake\\s+elevation|thunderstorm|lightning|flood" +
  ")\\b)" +
  // Phrases, not single words. "Be out of the water by 1:42" contains no cue word at all,
  // which is how the first version of this let the single most dangerous sentence class
  // through untouched.
  "|(\\b(?:get|be|stay|climb)\\s+out\\b)" +
  "|(\\b(?:in|out\\s+of|on|off)\\s+the\\s+water\\b)" +
  "|(\\bcomes?\\s+up\\b)|(\\bcoming\\s+up\\b)|(\\bturn\\s+(?:it\\s+)?on\\b)" +
  "|(\\bsafe\\s*exit\\b)|(\\bwater\\s+(?:will\\s+)?(?:reach|hit|arrive)\\b)", "i");

// Two copies on purpose. A /g regex carries lastIndex, so calling .test() on the same
// object alternates true/false between calls — which silently let every second unsafe
// sentence through the classifier. The global one is only ever used with matchAll.
const NUM_RE = /\d[\d,]*(?:\.\d+)?(?::\d{2})?/g;
const HAS_NUM = /\d/;

/** Split on sentence ends, keeping the terminator so reassembly reads naturally. */
export function sentences(text) {
  return String(text)
    .split(/(?<=[.!?])\s+|(?<=<br\s*\/?>)|\n+/)
    .filter((s) => s.trim().length);
}

/** Digit tokens in a string, normalised the way Python's claim_numbers() does. */
export function numbersIn(text) {
  const out = [];
  for (const m of String(text).replace(/,/g, "").matchAll(NUM_RE)) {
    const t = m[0].replace(/\.$/, "");
    if (t && !out.includes(t)) out.push(t);
  }
  return out;
}

export function isSafetySensitive(sentence) {
  return SAFETY_CUES.test(sentence) && HAS_NUM.test(sentence);
}

/**
 * Build the licensed-number set from a claim book.
 *
 * `claims` are SafetyClaim objects as Python emitted them: {id, kind, zone_id, text,
 * numbers[]}. `scope` limits which zones count — a question about the Caney must not be
 * grounded by a Cheatham claim. Pass null to allow every zone in the slice.
 */
/** Claims arrive from Python as `zone_id` and from the bot corpus as `zone`. Accept both:
 *  a silently-undefined zone made every scope check pass, which is the failure mode this
 *  whole module exists to prevent. */
export function claimZone(c) {
  return c.zone_id !== undefined ? c.zone_id : c.zone;
}

function inScopeOf(c, scope) {
  return !scope || !scope.length || scope.includes(claimZone(c));
}

export function licensedNumbers(claims, scope) {
  const set = new Set();
  for (const c of claims || []) {
    if (!inScopeOf(c, scope)) continue;
    for (const n of c.numbers || []) set.add(String(n));
  }
  return set;
}

/** Whitespace, case and markup differences must not defeat a verbatim quote. */
function normaliseForMatch(s) {
  return String(s).replace(/<[^>]*>/g, " ").toLowerCase()
    .replace(/[\u2018\u2019\u201c\u201d]/g, "'")
    .replace(/[^a-z0-9:.,%\- ]+/g, " ")
    .replace(/\s+/g, " ").trim().replace(/[.,\s]+$/, "");
}

function grounded(n, licensed) {
  if (licensed.has(n)) return true;
  // A time may be written "1:00" where the claim says "1" plus "00", or vice versa.
  // Accept only when the FULL digit string of the reply's token is itself licensed —
  // never when a substring happens to appear somewhere.
  const bare = n.replace(/[^\d]/g, "");
  for (const l of licensed) {
    if (l.replace(/[^\d]/g, "") === bare && bare.length >= 2) return true;
  }
  return false;
}

/**
 * @param {string} reply           what the model wrote
 * @param {object} sliceObj        the corpus slice it was shown (for non-safety numbers)
 * @param {Array}  claims          SafetyClaim objects in scope
 * @param {Array}  scope           zone ids the question is about, or null for all
 * @returns {{text, ok, removed:[], unsupported:[], usedClaims:[]}}
 */
export function verify(reply, sliceObj, claims, scope) {
  const licensed = licensedNumbers(claims, scope);
  const sliceNums = sliceNumbers(sliceObj);
  const kept = [];
  const removed = [];
  const unsupported = [];
  const usedClaims = new Set();

  // A claim quoted VERBATIM is always allowed, whatever incidental digits its own text
  // carries. Claims name their gauge ("USGS 03424860") and their age ("50 min ago"), and
  // neither is a number the claim asserts — so those are not in its licensed set. Without
  // this rule the guard deleted the one thing the model is explicitly told to do.
  const claimTexts = (claims || [])
    .filter((c) => inScopeOf(c, scope))
    .map((c) => ({ id: c.id, norm: normaliseForMatch(c.text) }));

  for (const s of sentences(reply)) {
    const sn = normaliseForMatch(s);
    const quoted = claimTexts.find((c) => c.norm && (sn.includes(c.norm) || c.norm.includes(sn)));
    if (quoted && isSafetySensitive(s)) {
      usedClaims.add(quoted.id);
      kept.push(s);
      continue;
    }
    if (isSafetySensitive(s)) {
      const nums = numbersIn(s);
      const bad = nums.filter((n) => !grounded(n, licensed));
      if (bad.length) {
        // FAIL CLOSED. The sentence never reaches the reader.
        removed.push({ sentence: s.trim(), numbers: bad });
        continue;
      }
      for (const c of claims || []) {
        if (!inScopeOf(c, scope)) continue;
        if ((c.numbers || []).some((n) => nums.includes(String(n)))) usedClaims.add(c.id);
      }
      kept.push(s);
      continue;
    }
    // Not safety-shaped. Numbers still have to have come from somewhere, but an
    // ungrounded fly size costs a caveat, not a deletion.
    for (const n of numbersIn(s)) {
      if (!sliceNums.has(n) && !grounded(n, licensed) && !HARMLESS.has(n)) {
        unsupported.push(n);
      }
    }
    kept.push(s);
  }

  return {
    text: kept.join(" ").trim(),
    ok: removed.length === 0,
    removed,
    unsupported: [...new Set(unsupported)],
    usedClaims: [...usedClaims],
  };
}

/**
 * Turn a verification into what the reader actually sees.
 *
 * A removed safety sentence is replaced by the CLAIM TEXT for the same kind of fact when
 * one exists — the reader asked a real question and deserves the real answer — and by an
 * explicit refusal when it does not. Never by the model's own words.
 */
export function repair(result, claims, scope, url) {
  let text = result.text;

  if (result.removed.length) {
    const kinds = new Set();
    for (const r of result.removed) {
      for (const [kind, re] of Object.entries(KIND_CUES)) {
        if (re.test(r.sentence)) kinds.add(kind);
      }
    }
    const inScope = (claims || []).filter((c) => inScopeOf(c, scope));
    // Prefer a claim of the same kind as the sentence that was removed. Failing that,
    // quote what the build DOES say about this water — the reader asked a real question,
    // and "here is the verified fact next door" beats a bare refusal.
    let quote = inScope.filter((c) => kinds.has(c.kind)).slice(0, 3);
    if (!quote.length) {
      quote = inScope.filter((c) => ["safe_exit", "generation_start", "generation_stop",
                                     "release_arrival", "wade_cutoff", "flow"]
        .includes(c.kind)).slice(0, 2);
    }

    text += "\n\n⚠️ <b>I removed part of that answer.</b> It stated water or generation " +
            "numbers I cannot trace to today's build, and this bot will not guess at a " +
            "number someone might stand in a river on.";
    if (quote.length) {
      text += "\n\nWhat the build actually says:\n" +
              quote.map((c) => "• " + escapeHtml(c.text)).join("\n");
    } else {
      text += " I do not have a verified figure for that right now.";
    }
    if (url) text += `\n\nCheck <a href="${url}">the page</a> and the USACE release ` +
                     "schedule before you get in.";
  }

  if (result.unsupported.length) {
    text += "\n\n<i>I also mentioned " +
      result.unsupported.slice(0, 3).map((n) => `<b>${escapeHtml(n)}</b>`).join(", ") +
      ", which I can't find in today's data — treat those as unreliable.</i>";
  }
  return text.trim();
}

/** Which claim kind answers which kind of removed sentence. */
const KIND_CUES = {
  generation_start: /\b(generat\w*|release[sd]?|releasing|turn\s+(?:it\s+)?on|start)\b/i,
  generation_stop:  /\b(generat\w*|release[sd]?|stop|shut|off)\b/i,
  release_arrival:  /\b(arriv\w*|reach\w*|comes?\s+up|coming\s+up|front|rise|rising)\b/i,
  safe_exit:        /\b(exit|get\s+out|be\s+out|out\s+of\s+the\s+water|wade|wading|safe)\b/i,
  wade_cutoff:      /\b(wade|wading|wadeable|cut\s*off|cutoff)\b/i,
  flow:             /\b(flow|cfs|kcfs|discharge)\b/i,
  stage:            /\b(stage|gauge|gage|level|feet|ft)\b/i,
  weather_hazard:   /\b(thunderstorm|lightning|storm|flood)\b/i,
};

/** Ordinary language full of digits that nobody would act on as a measurement. */
const HARMLESS = new Set([
  "6x", "7x", "5x", "4x", "3x", "2x", "1x", "0x",
  "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "12", "24",
]);

/** Every normalised number present anywhere in the slice the model was shown. */
export function sliceNumbers(sliceObj) {
  const flat = JSON.stringify(sliceObj || {}).toLowerCase().replace(/,/g, "");
  const seen = new Set();
  for (const m of flat.matchAll(/\d+(?:[.:]\d+)?/g)) seen.add(m[0].replace(/\.$/, ""));
  return seen;
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Back-compat shim for callers that only want the boolean. */
export function checkReply(reply, sliceObj, claims, scope) {
  const r = verify(reply, sliceObj, claims, scope);
  return { ok: r.ok && !r.unsupported.length, unsupported: r.unsupported, removed: r.removed };
}
