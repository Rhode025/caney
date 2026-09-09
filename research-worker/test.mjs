/**
 * Research worker tests. No network, no Cloudflare, no key.
 *
 *   node test.mjs
 *
 * Everything worth testing here is a pure function: tiering, classification, decay,
 * normalisation, dedupe, disagreement and query construction. The Worker glue is thin by
 * design so that this covers the parts that can be wrong.
 */
import * as C from "./src/claims.js";
import * as S from "./src/search.js";

let fails = 0;
const ok = (n) => console.log("  \x1b[32m✓\x1b[0m " + n);
const bad = (n, d) => { fails++; console.log("  \x1b[31m✗\x1b[0m " + n + (d ? " — " + d : "")); };
const is = (n, c, d) => (c ? ok(n) : bad(n, d));
const eq = (n, a, b) => is(n, JSON.stringify(a) === JSON.stringify(b),
                           JSON.stringify(a) + " != " + JSON.stringify(b));
const NOW = Date.parse("2026-09-09T12:00:00Z") / 1000;

console.log("── §16 tiering is derived from the domain, never asserted ──");
eq("usgs.gov is tier A", C.tierFor("https://waterdata.usgs.gov/x"), "A");
eq("usace.army.mil is tier A", C.tierFor("https://www.usace.army.mil/x"), "A");
eq("tn.gov is tier B", C.tierFor("https://www.tn.gov/twra/x"), "B");
eq("a subdomain still resolves", C.tierFor("https://tailwaters.fw.ky.gov/x"), "B");
eq("a guide service is tier C", C.tierFor("https://caneyforkguides.com/report"), "C");
eq("a forum is tier D", C.tierFor("https://www.reddit.com/r/flyfishing"), "D");
eq("garbage is tier D", C.tierFor("not a url"), "D");
is("A outranks D", C.TIER_WEIGHT.A > C.TIER_WEIGHT.D);
is("the tier order is strict",
   C.TIER_WEIGHT.A > C.TIER_WEIGHT.B && C.TIER_WEIGHT.B > C.TIER_WEIGHT.C &&
   C.TIER_WEIGHT.C > C.TIER_WEIGHT.D);

console.log("\n── §23 claim types ──");
eq("stocking", C.classify("TWRA stocked 4,000 rainbow trout in March"), "stocking");
eq("survey", C.classify("Spring electrofishing survey results for black bass"), "survey");
eq("creel", C.classify("The 2024 creel survey found"), "creel_result");
eq("regulation", C.classify("A 14-inch minimum length limit applies"), "regulation");
eq("thermal_refuge", C.classify("Cool oxygenated tailwater provides thermal refuge"),
   "thermal_refuge");
eq("generation_response", C.classify("Fish respond when the turbines are generating"),
   "generation_response");
eq("migration", C.classify("Fish migrate upstream to spawn each spring"), "migration");
is("every classification is a known type",
   C.CLAIM_TYPES.includes(C.classify("something entirely unremarkable about a fish")));

console.log("\n── §24 decay: a guide report and a survey are not the same kind of fact ──");
is("a weekly report is stale within a day",
   C.isStale("recent_report", NOW - 2 * 86400, NOW));
is("a species-presence claim is not stale after a month",
   !C.isStale("species_presence", NOW - 30 * 86400, NOW));
is("a regulation must be rechecked weekly",
   C.isStale("regulation", NOW - 10 * 86400, NOW));
is("a five-year-old field report is worth almost nothing",
   C.recency("recent_report", 5 * 365) <= 0.06,
   String(C.recency("recent_report", 5 * 365)));
is("a current agency report is worth everything",
   C.recency("recent_report", 1) > 0.85, String(C.recency("recent_report", 1)));
is("a five-year-old survey still counts for a lot",
   C.recency("survey", 5 * 365) > 0.4, String(C.recency("survey", 5 * 365)));
is("a regulation does not decay in influence",
   C.recency("regulation", 5 * 365) > 0.9, String(C.recency("regulation", 5 * 365)));
is("§62: a 5-year-old field report carries far less weight than a current TWRA report",
   C.recency("recent_report", 5 * 365) < C.recency("recent_report", 2) * 0.2);
for (const t of C.CLAIM_TYPES) {
  const d = C.decayFor(t);
  is("decay is configured for " + t, d && d.ttlSeconds > 0 && d.halfLifeDays > 0);
}

console.log("\n── §26 research influence ──");
const strong = C.combinedConfidence({ tier: "B", geographicMatch: 1, seasonalMatch: 1,
                                      claimType: "seasonal_distribution", ageDays: 30 });
const weakGeo = C.combinedConfidence({ tier: "B", geographicMatch: 0.3, seasonalMatch: 1,
                                       claimType: "seasonal_distribution", ageDays: 30 });
const weakSeason = C.combinedConfidence({ tier: "B", geographicMatch: 1, seasonalMatch: 0.15,
                                          claimType: "seasonal_distribution", ageDays: 30 });
const weakTier = C.combinedConfidence({ tier: "D", geographicMatch: 1, seasonalMatch: 1,
                                        claimType: "seasonal_distribution", ageDays: 30 });
is("wrong water costs a claim most of its weight", weakGeo < strong * 0.4);
is("wrong season costs a claim most of its weight", weakSeason < strong * 0.25);
is("a community source is worth a fraction of an agency one", weakTier < strong * 0.35);
is("§26: a stale guide blog barely moves anything",
   C.combinedConfidence({ tier: "D", geographicMatch: 1, seasonalMatch: 1,
                          claimType: "recent_report", ageDays: 900 }) < 0.05);

console.log("\n── §19, §20 normalisation: no source, no claim ──");
const ctx = { species: "striped_bass", zoneIds: ["carthage_confluence"], month: 9,
              now: NOW, primaryOnly: true };
const good = C.toClaim({ url: "https://www.tn.gov/twra/a", title: "TWRA",
  text: "Striped bass are concentrated from Cordell Hull Dam downstream to the mouth of " +
        "the Caney Fork River.", published: "2026-06-01" }, ctx);
is("a sourced agency finding becomes a claim", !!good.claim);
eq("its tier is derived", good.claim.source_tier, "B");
is("it carries its citation",
   good.claim.source_url && good.claim.source_domain === "www.tn.gov");
is("it is scored", good.claim.combined_confidence > 0);
is("it is not safety-sensitive", !good.claim.safety_sensitive);
for (const [label, f] of [
  ["no url", { text: "Fish are there and have been all week, reportedly." }],
  ["empty url", { url: "", text: "Fish are there and have been all week, reportedly." }],
  ["javascript url", { url: "javascript:alert(1)", text: "Fish are there all week now." }],
  ["no text", { url: "https://www.tn.gov/x" }],
  ["text too short", { url: "https://www.tn.gov/x", text: "fish" }],
]) {
  const r = C.toClaim(f, ctx);
  is(label + " is rejected with a reason", !r.claim && !!r.reject, JSON.stringify(r));
}
is("§19: primary search refuses a non-agency domain",
   !!C.toClaim({ url: "https://reddit.com/r/x",
                 text: "They were absolutely stacked below the dam this morning." },
               ctx).reject);
is("secondary search accepts it, tiered down",
   C.toClaim({ url: "https://reddit.com/r/x",
               text: "They were absolutely stacked below the dam this morning." },
             { ...ctx, primaryOnly: false }).claim.source_tier === "D");

console.log("\n── §20 a search-derived number never becomes a measurement ──");
for (const t of ["The dam was releasing 4,000 cfs on Tuesday morning for the whole day.",
                 "The gauge stage was 4.2 ft at first light on Tuesday morning.",
                 "They generate at 11:00 most weekday mornings through the summer."]) {
  const r = C.toClaim({ url: "https://www.tn.gov/twra/x", text: t }, ctx);
  is("flagged safety-sensitive: " + t.slice(0, 38), !!r.claim.safety_sensitive);
}
is("ordinary prose is not flagged",
   !C.toClaim({ url: "https://www.tn.gov/twra/x",
                text: "Gizzard shad and skipjack herring make up the forage base here." },
              ctx).claim.safety_sensitive);

console.log("\n── §78 dedupe ──");
const a1 = good.claim;
const a2 = { ...a1, retrieved_at: a1.retrieved_at + 3600 };
const b1 = { ...a1, id: "other", source_url: "https://www.tn.gov/twra/b" };
const dd = C.dedupe([a1, a2, b1]);
eq("the same assertion from the same source appears once", dd.length, 2);
is("revisiting refreshes rather than duplicating",
   dd.find((c) => c.source_url === a1.source_url).retrieved_at === a2.retrieved_at);

console.log("\n── §27 disagreement is surfaced, not resolved ──");
const conflict = C.disagreements([
  { claim_type: "forage", source_tier: "B" },
  { claim_type: "forage", source_tier: "D" },
]);
is("a tier clash on one claim type is reported", conflict.length === 1);
eq("the authoritative tier is named", conflict[0].authoritative, "B");
is("the note explains what happens", /weighted higher/.test(conflict[0].note));
eq("agreement produces nothing",
   C.disagreements([{ claim_type: "forage", source_tier: "B" },
                    { claim_type: "forage", source_tier: "B" }]).length, 0);

console.log("\n── §18, §21 query construction ──");
const qs = S.buildQueries("striped_bass", ["carthage_confluence"], { water_temp_f: 74 },
                          "2026-09-09", {});
is("several queries are built", qs.length >= 4, String(qs.length));
is("primary comes first", qs[0].primaryOnly === true);
is("at least one secondary query exists", qs.some((q) => !q.primaryOnly));
is("every query names the species", qs.every((q) => /striped bass/i.test(q.query)));
is("every query names the water",
   qs.every((q) => /Cordell Hull|Caney Fork|Carthage/i.test(q.query)));
is("§21: no query asks where the fish are",
   !qs.some((q) => /where should|where are the fish|best spot/i.test(q.query)));
is("the month is named", qs.some((q) => /September/.test(q.query)));
is("a tailwater gets a generation-response query",
   qs.some((q) => q.family === "generation_response"));
is("a known temperature gets a thermal query",
   qs.some((q) => q.family === "thermal_refuge" && /74 F/.test(q.query)));
is("every zone id has a human name", Object.keys(S.ZONE_TERMS).length >= 20);

console.log("\n── §17, §19 the primary allowlist ──");
for (const d of ["tn.gov", "tva.com", "usgs.gov", "usace.army.mil", "weather.gov",
                 "noaa.gov", "fws.gov"]) {
  is("allowlist includes " + d, S.PRIMARY_DOMAINS.includes(d));
}
is("every allowlisted domain is tier A or B",
   S.PRIMARY_DOMAINS.every((d) => ["A", "B"].includes(C.tierFor("https://" + d + "/x"))));

console.log("\n── response parsing ──");
eq("a fenced JSON block is unwrapped",
   S.stripFence("```json\n{\"findings\":[]}\n```"), "{\"findings\":[]}");
eq("plain JSON is left alone", S.stripFence("{\"a\":1}"), "{\"a\":1}");
eq("output_text is preferred", S.extractText({ output_text: "hello" }), "hello");
eq("content blocks are joined",
   S.extractText({ output: [{ content: [{ type: "output_text", text: "a" },
                                        { type: "output_text", text: "b" }] }] }), "a\nb");
eq("an empty response yields empty text", S.extractText({}), "");

console.log();
if (fails) { console.log(`\x1b[31mFAILED ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log("\x1b[32mALL RESEARCH WORKER CHECKS PASSED\x1b[0m");
