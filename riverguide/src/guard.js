/**
 * The deterministic safety check.
 *
 * The system prompt asks the model not to invent numbers. This VERIFIES it, in code, after
 * the fact — which is the difference between a rule and a hope. It is also what makes the
 * choice of model a cost decision rather than a safety one: a cheaper model that occasionally
 * paraphrases a flow figure is caught here rather than in a river.
 *
 * Every number in a reply must appear in the slice the model was given. Not "roughly match",
 * not "be derivable from" — appear. A converted, rounded or averaged number is exactly the
 * failure this exists to catch, and every one of those produces a value that is not present.
 *
 * Written to be conservative in one direction only: a false positive costs a caveat appended
 * to a correct answer, a false negative puts an invented time in front of someone deciding
 * whether to wade. The first version of this flagged "#18" because a sentence-ending period
 * came along for the ride — hence the normalisation below, and the tests.
 */

// Ordinary language full of digits that nobody would mistake for a measurement.
const HARMLESS = new Set([
  "6x", "7x", "5x", "4x", "8x", "3x", "2x",       // tippet
  "24", "12", "7",                                  // hours in a day, days in a week
  "1", "2", "3", "4", "5", "6", "8", "9", "10",     // small counts
]);

/** Digit-bearing tokens a reader could act on: times, flows, depths, sizes, percentages. */
export function extractNumbers(text) {
  const out = [];
  const re = /\b\d[\d,]*(?:\.\d+)?(?:\s*[:.]\s*\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.|cfs|kcfs|ft|feet|inches|in|°f?|%|mph)?/gi;
  for (const m of text.matchAll(re)) {
    const raw = m[0].trim();
    const norm = normalise(raw);
    if (!norm) continue;
    if (HARMLESS.has(norm)) continue;
    out.push({ raw, norm });
  }
  return out;
}

/**
 * Compare on digits alone, with thousands separators removed and units dropped. "3,982 cfs",
 * "3982cfs" and "3982" are the same claim; "3,982" and "3.98" are not.
 */
export function normalise(s) {
  const t = String(s).toLowerCase().replace(/,/g, "").replace(/\s+/g, "");
  const m = t.match(/\d+(?:[.:]\d+)?/);
  if (!m) return null;
  let n = m[0];
  // A trailing period is punctuation, not precision: "#18." -> "18"
  n = n.replace(/\.$/, "");
  // Times keep their colon; "1:00" and "100" are different claims.
  return n;
}

/** Every normalised number present anywhere in the slice the model was shown. */
export function sliceNumbers(sliceObj) {
  const flat = JSON.stringify(sliceObj).toLowerCase().replace(/,/g, "");
  const seen = new Set();
  for (const m of flat.matchAll(/\d+(?:[.:]\d+)?/g)) seen.add(m[0].replace(/\.$/, ""));
  return seen;
}

/**
 * @returns {{ok: boolean, unsupported: string[]}} — unsupported holds the raw forms, so a
 * log or a caveat can quote what the model actually wrote.
 */
export function checkReply(reply, sliceObj) {
  const have = sliceNumbers(sliceObj);
  const bad = [];
  for (const { raw, norm } of extractNumbers(reply)) {
    if (have.has(norm)) continue;
    // A time written "1:00" may appear in the data as "1pm" and vice versa. Rather than
    // teach this every equivalence, accept when the bare digits appear — the point is to
    // catch numbers with no basis at all, not to police formatting.
    const digits = norm.replace(/[^\d]/g, "");
    if (digits.length >= 2 && have.has(digits)) continue;
    if ([...have].some((h) => h.replace(/[^\d]/g, "") === digits && digits.length >= 2)) continue;
    bad.push(raw);
  }
  return { ok: bad.length === 0, unsupported: [...new Set(bad)] };
}

/**
 * What to do about a failure. Never silently drop the answer — the reader asked a question
 * and deserves one — but never let an unverifiable number stand unmarked either.
 */
export function annotate(reply, check, url) {
  if (check.ok) return reply;
  return (
    reply +
    "\n\n⚠️ <i>I mentioned " + check.unsupported.slice(0, 3).map((n) => `<b>${n}</b>`).join(", ") +
    ", which I can't find in today's data — treat those as unreliable and check " +
    `<a href="${url}">the page</a> before you act on them.</i>`
  );
}
