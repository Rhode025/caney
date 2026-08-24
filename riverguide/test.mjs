/**
 * RiverGuide tests. No network, no model, no Cloudflare — the slicer and the access policy
 * are pure functions and they are where both the cost and the access rules live.
 *
 *   node test.mjs
 */
import { slice, detectIntent, detectRivers, tokenEstimate } from "./src/slice.js";
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
const cases = [
  ["what fly should I use on the Caney right now", 3500],
  ["how does the Duck look this weekend", 6000],
  ["what's fishing well right now", 6000],
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

console.log();
if (fails) { console.log(`\x1b[31mFAILED ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log("\x1b[32mALL RIVERGUIDE CHECKS PASSED\x1b[0m");
