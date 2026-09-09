/**
 * Post-deploy smoke for the planner. §49, §57.
 *
 * Runs against the LIVE site after `pages deploy`, because a deploy can succeed and still
 * serve a stale or broken page. It asks the questions a reader would ask: is the homepage
 * the planner, is the dataset fresh, does a plan actually generate, and does anything
 * throw in a real browser.
 *
 *   node test/planner-smoke.mjs [https://caney.pages.dev]
 */
import { chromium } from "playwright";

const SITE = process.argv[2] || "https://caney.pages.dev";
let fails = 0;
const ok = (n) => console.log("  \x1b[32m✓\x1b[0m " + n);
const bad = (n, d) => { fails++; console.log("  \x1b[31m✗\x1b[0m " + n + (d ? " — " + d : "")); };
const is = (n, c, d) => (c ? ok(n) : bad(n, d));

console.log("── post-deploy smoke: " + SITE + " ──");

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

const res = await page.goto(SITE + "/", { waitUntil: "networkidle", timeout: 45000 });
is("homepage returns 200", res && res.status() === 200, String(res && res.status()));
is("served over HTTPS", SITE.startsWith("https://") ? page.url().startsWith("https://") : true);
is("the homepage is the planner",
   (await page.locator("h1").textContent()).includes("What do you want to catch"));

const data = await (await ctx.request.get(SITE + "/plan/data.json")).json();
const ageH = (Date.now() / 1000 - data.built) / 3600;
console.log(`      dataset built ${ageH.toFixed(1)} h ago · ${Object.keys(data.zones).length} zones · ` +
            `${data.safety.length} safety claims · research ${data.research.provider}`);
is("the planner dataset is fresh (under 6 h)", ageH < 6, ageH.toFixed(1) + " h");
is("every species is present in the dataset",
   ["striped_bass", "smallmouth", "largemouth", "trout"].every((s) => data.species[s]));
is("the Carthage confluence zone is published", !!data.zones.carthage_confluence);
is("safety claims are published", data.safety.length > 0, String(data.safety.length));

// The build report, which the watchdog can also read.
const build = await (await ctx.request.get(SITE + "/plan/build.json")).json();
is("the build reported its duration", typeof build.durationSeconds === "number",
   String(build.durationSeconds));
// A build served entirely from cache makes zero fetches, which is a success, not a
// failure — so the assertion is on the failure RATE, not on the ratio.
const f = build.http;
is("no source fetch failed catastrophically",
   f.fetches === 0 || f.failures / f.fetches < 0.5, JSON.stringify(f));
is("the build reached its sources or its cache",
   f.fetches + f.hits_disk + f.hits_memo > 0, JSON.stringify(f));

// A real plan, end to end, on the live site.
await page.click('[data-species="striped_bass"]');
await page.click('[data-preset="now"]');
await page.click("#go");
await page.waitForSelector("#result .verdict, #result .card h2", { timeout: 25000 });
const verdict = await page.locator("#result .badge").count();
is("a plan generates on the live site", verdict > 0 ||
   /Nothing fits/.test(await page.locator("#result").textContent()));

is("no JavaScript errors on the live site", errors.length === 0, errors.slice(0, 2).join(" | "));

await browser.close();
console.log();
if (fails) { console.log(`\x1b[31mSMOKE FAILED: ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log("\x1b[32mPOST-DEPLOY SMOKE PASSED\x1b[0m");
