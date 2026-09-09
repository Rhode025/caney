/**
 * RiverGuide tests. No network, no model, no Cloudflare — the slicer and the access policy
 * are pure functions and they are where both the cost and the access rules live.
 *
 *   node test.mjs
 */
import { slice, detectIntent, detectRivers, tokenEstimate } from "./src/slice.js";
import { verify, repair, checkReply, isSafetySensitive, numbersIn } from "./src/guard.js";
import { resolveAccess, overQuota, TIERS } from "./src/access.js";
import { readFileSync } from "fs";

const corpus = JSON.parse(readFileSync("../out/bot.json", "utf8"));
let fails = 0;
const ok = (n) => console.log("  \x1b[32m✓\x1b[0m " + n);
const bad = (n, d) => { fails++; console.log("  \x1b[31m✗\x1b[0m " + n + (d ? " — " + d : "")); };
const is = (n, c, d) => (c ? ok(n) : bad(n, d));

console.log("── the corpus is what the bot expects ──");
is("13 rivers", corpus.rivers.length === 13, String(corpus.rivers.length));
is("carries its safety rules", (corpus.rules || []).length >= 3);
is("every river has a current read", corpus.rivers.every((r) => r.now));
console.log(`  full corpus: ~${tokenEstimate(corpus).toLocaleString()} tokens`);

console.log("\n── intent ──");
for (const [q, want] of [
  ["what fly should I use on the Caney", "fly"],
  ["what's fishing well right now", "now"],
  ["how does next week look", "week"],
  ["where can I launch a boat on the Duck", "access"],
  ["is Center Hill generating today", "generation"],
  ["is it safe to wade the Caney", "generation"],
  ["tell me about the Harpeth", "now"],
]) is(`"${q}" → ${want}`, detectIntent(q) === want, detectIntent(q));

console.log("\n── river detection ──");
for (const [q, want] of [
  ["what fly for the Caney", ["caney"]],
  ["how's the Harpeth", ["harpeth"]],
  ["Stones River conditions", ["stones"]],
]) {
  const got = detectRivers(q, corpus);
  is(`"${q}" → ${want.join(",")}`, want.every((w) => got.includes(w)), got.join(",") || "none");
}
{
  const got = detectRivers("where are the smallmouth biting", corpus);
  is("species question selects by species", got.length >= 3, got.join(","));
  const none = detectRivers("what's good today", corpus);
  is("no river named → none matched", none.length === 0, none.join(","));
}

console.log("\n── slicing is the cost model ──");
const full = tokenEstimate(corpus);
// Budgets went up in Caney 2.0: every slice now carries the immutable safety claim book
// and the zone model, which is what makes a water answer verifiable instead of merely
// plausible. Roughly +1,500 tokens per question, against a full corpus of ~34,000 — so
// slicing still saves about 90%, and the increase buys the fail-closed guard.
const cases = [
  ["what fly should I use on the Caney right now", 4200],
  ["how does the Duck look this weekend", 6000],
  ["what's fishing well right now", 12000],
  ["where can I launch on the Harpeth", 3500],
];
for (const [q, budget] of cases) {
  const cut = slice(q, corpus);
  const t = tokenEstimate(cut.payload);
  is(`"${q}" → ~${t.toLocaleString()} tok (<${budget.toLocaleString()})`, t < budget, `${t}`);
  console.log(`      ${cut.note} · ${(100 - t / full * 100).toFixed(0)}% smaller than the full corpus`);
}
{
  // Whatever is included must be byte-identical to the build — the model must never be
  // handed a rounded or reshaped number.
  const cut = slice("what fly should I use on the Caney", corpus);
  const src = corpus.rivers.find((r) => r.id === "caney");
  const got = cut.payload.rivers.find((r) => r.id === "caney");
  is("sliced fields are verbatim", JSON.stringify(got.fly) === JSON.stringify(src.fly));
  is("safety rules always travel with the data", (cut.payload.rules || []).length >= 3);
  is("build timestamp always travels", !!cut.payload.builtIso);
}

console.log("\n── access ──");
const env = { OWNER_CHAT_IDS: "7837861720", OPEN_TO_ALL: "0" };
{
  const owner = await resolveAccess(7837861720, env);
  is("owner is allowed, uncapped", owner.allowed && owner.tier === "owner" && !isFinite(owner.dailyQuestions));
  const stranger = await resolveAccess(999, env);
  is("stranger is refused while private", !stranger.allowed && stranger.reason === "private");
  is("refusal points at the public site", /caney\.pages\.dev/.test(stranger.message));
  const open = await resolveAccess(999, { ...env, OPEN_TO_ALL: "1" });
  is("flipping OPEN_TO_ALL admits strangers on the free tier", open.allowed && open.tier === "free");
  is("owner is never quota-limited", overQuota(TIERS.owner, { questions: 1e6, tokensIn: 1e9, tokensOut: 0 }) === null);
  is("free tier is capped by questions",
    typeof overQuota({ ...TIERS.free, label: "free" }, { questions: 20, tokensIn: 0, tokensOut: 0 }) === "string");
  is("free tier is capped by tokens",
    typeof overQuota({ ...TIERS.free, label: "free" }, { questions: 1, tokensIn: 60000, tokensOut: 0 }) === "string");
}

console.log("\n── the guard: fail closed on safety, annotate elsewhere ──");
{
  const cut = slice("what fly should I use on the Caney right now", corpus);
  const p = cut.payload;
  const claims = cut.claims;
  const zones = cut.zones;
  is("the slice carries the Caney claim book", claims.length > 0, String(claims.length));
  is("the slice names its zones", zones.length > 0, zones.join(","));

  // Non-safety numbers keep the gentle treatment: a wrong fly size is not a drowning risk.
  is("a fly size quoted with a full stop is NOT flagged",
     verify("Try a Sowbug #18.", p, claims, zones).ok);
  is("tippet size is not treated as a measurement",
     verify("Use 6X tippet.", p, claims, zones).ok);

  // The failures that matter — all of these must be REMOVED, not annotated.
  const cases = [
    ["an INVENTED generation time", "They will probably start generating around 11:45am."],
    ["a ROUNDED flow", "Flow is roughly 4100 cfs."],
    ["a CONVERTED number", "The release is about 7.1 cubic metres per second."],
    ["a small-looking count", "You have 2 hours before the water comes up."],
    ["an INFERRED exit time", "Be out of the water by 10:30."],
  ];
  for (const [label, reply] of cases) {
    const r = verify(reply, p, claims, zones);
    is(`${label} is REMOVED, not shipped`, r.removed.length === 1 && r.text === "",
       JSON.stringify({ removed: r.removed.length, text: r.text }));
    const shown = repair(r, claims, zones, "https://x");
    is(`${label} — the unsafe sentence is absent from what the reader sees`,
       !shown.includes(reply.replace(/\.$/, "")), shown.slice(0, 90));
    is(`${label} — the reader is told an answer was removed`,
       /removed part of that answer/.test(shown), shown.slice(0, 60));
  }

  // A claim quoted verbatim survives.
  const c = claims.find((x) => x.numbers && x.numbers.length);
  if (c) {
    const r = verify(c.text, p, claims, zones);
    // Compare with separators stripped: a claim's TEXT says "1,220 cfs" while the token
    // it licenses is "1220". An earlier version of this assertion compared them raw and
    // passed only on days when the river happened to be under 1,000 cfs.
    is("a claim quoted verbatim survives",
       r.ok && r.text.replace(/,/g, "").includes(c.numbers[0]),
       JSON.stringify({ removed: r.removed, want: c.numbers[0], got: r.text }));
    is("the guard records which claim grounded it", r.usedClaims.includes(c.id),
       r.usedClaims.join(","));
    // Scope matters: the same sentence about a DIFFERENT river must not be grounded.
    const other = verify(c.text, p, claims, ["a_zone_that_is_not_in_scope"]);
    is("a claim cannot ground a sentence about another water",
       other.removed.length === 1, JSON.stringify(other));
  } else {
    bad("the corpus carries at least one numeric safety claim", "none found");
  }

  // Classification itself.
  is("\"be out of the water by X\" is classified safety-sensitive",
     isSafetySensitive("Be out of the water by 1:42 PM."));
  is("a fly sentence is not classified safety-sensitive",
     !isSafetySensitive("Fish a #18 zebra midge on 6X."));
  is("classification is not stateful across calls",
     isSafetySensitive("Flow is 250 cfs.") && isSafetySensitive("Flow is 250 cfs."));
  is("checkReply still reports a boolean for callers that want one",
     checkReply("Generating at 11:45am.", p, claims, zones).ok === false);
}

console.log("\n── dam and place names route to the right river ──");
for (const [q, want] of [
  ["when does Center Hill start generating", "caney"],
  ["is Wolf Creek generating", "cumberland"],
  ["how is Tims Ford", "elktn"],
  ["conditions at Old Hickory", "cumbnash"],
  ["put in at Kingston Springs", "harpeth"],
]) {
  const cut = slice(q, corpus);
  is(`"${q}" → ${want}`, cut.rivers.length === 1 && cut.rivers[0] === want, cut.rivers.join(",") || "ALL");
}
{
  const cut = slice("when does Center Hill start generating tomorrow", corpus);
  const t = tokenEstimate(cut.payload);
  // The budget went up when the claim book started riding on every slice — that is the
  // cost of the safety model and it is worth paying, but it must not creep further.
  is(`a dam question costs ~${t} tokens, not the whole corpus`, t < 3600, String(t));
}

console.log("\n── §45: planning questions go to the planner, not to a second set of facts ──");
{
  const { detectPlanRequest, planPayload, planZones } = await import("./src/plan.js");
  const at = (h) => new Date(2026, 8, 9, h, 30).getTime();
  for (const [q, want] of [
    ["Where should I catch stripers around Carthage this morning?", "striped_bass-any-d0-morning"],
    ["best place for smallmouth tomorrow afternoon on a kayak", "smallmouth-kayak-d1-afternoon"],
    ["should i go wade for trout right now", "trout-wade-d0-morning"],
  ]) {
    const r = detectPlanRequest(q, at(7));
    is(`"${q.slice(0, 40)}…" → ${want}`, r && r.key === want, r ? r.key : "null");
  }
  is("a fly question is NOT a planning question",
     detectPlanRequest("what fly for the caney", at(7)) === null);
  is("a bare conditions question is NOT a planning question",
     detectPlanRequest("how is the water", at(7)) === null);

  // The real artefact the worker fetches.
  const fs = await import("fs");
  const key = "striped_bass-power-d0-morning";
  const p = `../out/plan/featured/${key}.json`;
  if (fs.existsSync(p)) {
    const plan = JSON.parse(fs.readFileSync(p, "utf8"));
    const pay = planPayload(plan);
    is("the plan payload carries the verdict and its numbers",
       ["GO", "CONDITIONAL", "SKIP"].includes(pay.verdict) &&
       typeof pay.opportunity === "number" && typeof pay.confidence === "number",
       JSON.stringify([pay.verdict, pay.opportunity, pay.confidence]));
    is("the plan payload carries a timeline", (pay.timeline || []).length > 0);
    // §46, §83 — the bot must describe THE SAME itinerary the graphical planner shows.
    is("the plan payload carries the ITINERARY, not just a summary",
       pay.itinerary && Array.isArray(pay.itinerary.segments) &&
       pay.itinerary.segments.length >= 3, JSON.stringify(pay.itinerary || {}).slice(0, 90));
    is("its zone sequence matches the plan's",
       JSON.stringify(pay.itinerary.zones) === JSON.stringify(plan.itinerary.zone_sequence));
    is("every segment carries its own time and instruction",
       pay.itinerary.segments.every((s) => s.when && s.instructions));
    is("a fishing segment carries its technique",
       pay.itinerary.segments.filter((s) => s.type === "fish").every((s) => s.technique));
    is("the four confidences travel separately (§31)",
       ["opportunity", "confidence", "locationConfidence", "researchConfidence"]
         .every((k) => typeof pay[k] === "number"), JSON.stringify(Object.keys(pay)));
    is("the backup plan travels (§39)",
       pay.backupPlan && (pay.backupPlan.branches || []).length > 0);
    is("the model versions travel (§53)",
       pay.versions && pay.versions.planner, JSON.stringify(pay.versions));
    is("why-this-won travels (§67)", (pay.whyThisWon || []).length > 0);
    is("the payload stays affordable", JSON.stringify(pay).length / 4 < 4500,
       String(Math.round(JSON.stringify(pay).length / 4)));
    is("the plan payload carries its score breakdown", (pay.scoreBreakdown || []).length > 0);
    is("the plan payload carries its safety claim book", Array.isArray(pay.safetyClaims));
    is("plan zones are resolvable for guard scoping", planZones(plan).length > 0,
       planZones(plan).join(","));
    // Everything a plan cites must be sourced (§20).
    is("every piece of plan evidence has a url",
       (pay.evidence || []).every((e) => /^https?:\/\//.test(e.url || "")),
       JSON.stringify((pay.evidence || []).map((e) => e.url).slice(0, 2)));
  } else {
    console.log("  \x1b[33m~\x1b[0m no featured plans built — run planner.py");
  }
}

console.log();
if (fails) { console.log(`\x1b[31mFAILED ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log("\x1b[32mALL RIVERGUIDE CHECKS PASSED\x1b[0m");
