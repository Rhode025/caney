/**
 * Runtime QA for the species-first planner. §49, §52, §62.
 *
 * Drives the built site in a real browser at PHONE WIDTH FIRST, walks the six scenarios
 * from §62, and runs axe on the result. Everything here is behaviour a static check
 * cannot see: does the plan actually render, does the timeline order, does the safe-exit
 * step appear where it should, does a keyboard reach the CTA.
 *
 *   node test/planner.mjs [baseUrl]
 */
import { chromium } from "playwright";
import { readFileSync, existsSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const ROOT = new URL("../out/", import.meta.url).pathname;
const AXE = new URL("./vendor-axe.js", import.meta.url).pathname;

let fails = 0;
const ok = (n) => console.log("  \x1b[32m✓\x1b[0m " + n);
const bad = (n, d) => { fails++; console.log("  \x1b[31m✗\x1b[0m " + n + (d ? " — " + d : "")); };
const is = (n, c, d) => (c ? ok(n) : bad(n, d));
const section = (t) => console.log("\n\x1b[1m── " + t + " ──\x1b[0m");

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
               ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml",
               ".webmanifest": "application/manifest+json" };

function serve(port) {
  return new Promise((res) => {
    const s = createServer((req, r) => {
      let p = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname));
      if (p.endsWith("/")) p += "index.html";
      const f = join(ROOT, p);
      if (!f.startsWith(ROOT) || !existsSync(f)) { r.writeHead(404); return r.end("nope"); }
      r.writeHead(200, { "content-type": MIME[extname(f)] || "application/octet-stream" });
      r.end(readFileSync(f));
    });
    s.listen(port, () => res(s));
  });
}

const PORT = 8931;
const BASE = process.argv[2] || `http://127.0.0.1:${PORT}`;
const server = process.argv[2] ? null : await serve(PORT);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });

async function plan(species, preset, craft) {
  await page.goto(BASE + "/index.html", { waitUntil: "networkidle" });
  await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
  await page.reload({ waitUntil: "networkidle" });
  await page.click(`[data-species="${species}"]`);
  await page.click(`[data-preset="${preset}"]`);
  await page.click(`[data-craft="${craft}"]`);
  await page.click("#go");
  await page.waitForSelector("#result .verdict, #result .card h2", { timeout: 20000 });
}

section("§4 — the homepage asks the product's question");
await page.goto(BASE + "/index.html", { waitUntil: "networkidle" });
is("h1 asks what to catch",
   (await page.locator("h1").textContent()).trim() === "What do you want to catch?");
const species = await page.locator(".sp-card .nm").allTextContents();
is("all four species are offered as large cards",
   JSON.stringify(species) === JSON.stringify(["STRIPERS", "SMALLMOUTH", "LARGEMOUTH", "TROUT"]),
   species.join(","));
const box = await page.locator(".sp-card").first().boundingBox();
is("a species card is a big touch target", box.height >= 88 && box.width >= 140,
   `${Math.round(box.width)}x${Math.round(box.height)}`);
is("no river card is on the homepage", (await page.locator(".rc").count()) === 0);
is("the primary action is FIND MY BEST PLAN",
   (await page.locator("#go").textContent()).includes("FIND MY BEST PLAN"));
is("the CTA is disabled until a species is chosen", await page.locator("#go").isDisabled());
is("eight time presets are offered", (await page.locator("#times .chip").count()) === 8);
is("five craft options are offered", (await page.locator("#crafts .chip").count()) === 5);
is("the river encyclopedia is still linked",
   (await page.locator('a[href="rivers.html"]').count()) > 0);

section("§62 — the six scenarios, at phone width");
const SCENARIOS = [
  ["striped_bass", "now", "any", "Stripers → right now"],
  ["striped_bass", "tmorning", "power", "Stripers → tomorrow morning"],
  ["smallmouth", "afternoon", "kayak", "Smallmouth → this afternoon"],
  ["largemouth", "evening", "any", "Largemouth → evening"],
  ["trout", "morning", "wade", "Trout → morning wade"],
  ["trout", "afternoon", "power", "Trout → afternoon power boat"],
];
for (const [sp, when, craft, label] of SCENARIOS) {
  await plan(sp, when, craft);
  const hasPlan = (await page.locator("#result .verdict").count()) > 0;
  if (!hasPlan) {
    // A refusal is a legitimate answer, but it must say why (§58).
    const txt = await page.locator("#result").textContent();
    is(label + " — a refusal explains itself", /Nothing fits/.test(txt) && txt.length > 120,
       txt.slice(0, 100));
    continue;
  }
  const verdict = (await page.locator("#result .badge").textContent()).trim();
  const zone = (await page.locator(".placehead .zone").textContent()).trim();
  const when2 = (await page.locator(".placehead .when").textContent()).trim();
  is(`${label} → ${verdict} · ${zone}`, ["GO", "CONDITIONAL", "SKIP"].includes(verdict), verdict);
  is(label + " — names a specific place", zone.length > 3, zone);
  is(label + " — names a specific window", /\d/.test(when2), when2);
  is(label + " — has an itinerary", (await page.locator(".steps li").count()) >= 4);
  is(label + " — has a score breakdown", (await page.locator(".bars .bar").count()) >= 6);
  is(label + " — tells you what to tie on",
     /Primary/.test(await page.locator("#result").textContent()));
  is(label + " — shows the evidence drawer",
     (await page.locator("details.drawer").count()) >= 2);
  is(label + " — never scrolls horizontally",
     await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  // Wade plans on a tailwater must carry a conservative exit.
  if (craft === "wade") {
    const txt = await page.locator("#result").textContent();
    is(label + " — a wade plan states a safety boundary",
       /SAFE EXIT|Be out of the water|release forecast/i.test(txt), txt.slice(0, 80));
  }
}

section("§9 / §3.5 — the itinerary distinguishes its kinds of time");
await plan("trout", "morning", "wade");
if ((await page.locator("#result .verdict").count()) > 0) {
  const kinds = await page.locator(".steps .kind").allTextContents();
  is("steps declare where their timing came from", kinds.length > 0, kinds.join(","));
  is("at least one step is deterministic or astronomical",
     kinds.some((k) => /deterministic|astronomical/.test(k)), kinds.join(","));
  const times = await page.locator(".steps .t").allTextContents();
  const mins = times.filter((t) => /\d/.test(t)).map(toMin);
  is("the itinerary is in time order",
     mins.every((v, i) => i === 0 || v >= mins[i - 1]), times.join(" "));
  const unc = await page.locator(".steps .unc").allTextContents();
  is("modelled arrival is shown as a distribution, not a single time",
     unc.length === 0 || unc.every((u) => /earliest.*typical.*edge/.test(u)), unc.join(" | "));
}

section("§40 — on-water mode");
await plan("striped_bass", "now", "any");
if ((await page.locator("#startplan").isVisible())) {
  await page.click("#startplan");
  await page.waitForSelector(".ow-block");
  const blocks = await page.locator(".ow-block .k").allTextContents();
  is("on-water mode shows NOW / NEXT / WATER / FLY",
     ["Now", "Next", "Water", "Fly"].every((b) => blocks.includes(b)), blocks.join(","));
  is("the planner UI is hidden in on-water mode",
     !(await page.locator(".pick-panel").isVisible()));
  const v = await page.locator(".ow-block .v").first().boundingBox();
  const fs = await page.evaluate(() =>
    getComputedStyle(document.querySelector(".ow-block .v")).fontSize);
  is("on-water type is big enough to read at arm's length", parseFloat(fs) >= 22, fs);
  await page.click("#ow-exit");
}

section("§43 — the trip log freezes the prediction");
await plan("striped_bass", "tmorning", "power");
await page.click("#tripdrawer summary");
await page.click("#logtrip");
await page.waitForSelector(".tripform");
is("logging a plan creates an outcome form",
   (await page.locator(".tripform .field").count()) >= 8);
const frozen = await page.evaluate(() =>
  JSON.parse(localStorage.getItem("caney.trips.v2")).trips[0].prediction);
is("the frozen prediction carries the score and confidence",
   typeof frozen.score === "number" && typeof frozen.confidence === "number");
is("the frozen prediction carries the arrival distribution or says there is none",
   frozen.predictedArrival === null ||
   ["earliest", "typical", "latest"].every((k) => k in frozen.predictedArrival));
is("the frozen prediction records which build made it", !!frozen.builtAt);

section("§53 — dark mode is a real palette, not a filter");
await page.emulateMedia({ colorScheme: "dark" });
await page.goto(BASE + "/index.html", { waitUntil: "networkidle" });
const darkBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
await page.emulateMedia({ colorScheme: "light" });
await page.reload({ waitUntil: "networkidle" });
const lightBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
is("the OS preference changes the palette", darkBg !== lightBg, `${darkBg} vs ${lightBg}`);
is("dark mode is actually dark", lum(darkBg) < 0.2, darkBg);
is("light mode is actually light", lum(lightBg) > 0.7, lightBg);
await page.click("#theme");
const forced = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
is("a manual override wins over the OS", forced === "dark", String(forced));
is("the override survives a reload",
   await page.reload({ waitUntil: "networkidle" }).then(() =>
     page.evaluate(() => document.documentElement.getAttribute("data-theme"))) === "dark");

section("§52 — accessibility");
await page.emulateMedia({ colorScheme: "light" });
await plan("striped_bass", "tmorning", "power");
// WCAG 2.5.8 exempts links that sit INLINE inside a sentence — a citation in the middle
// of a paragraph cannot be 44px without wrecking the prose. Everything else must be.
const small = await page.evaluate(() => {
  const bad = [];
  for (const el of document.querySelectorAll("button, a[href], select, input, summary")) {
    const r = el.getBoundingClientRect();
    if (!r.width && !r.height) continue;
    if (getComputedStyle(el).display === "inline") continue;   // inline-in-text exception
    if (r.height < 40 || r.width < 40) {
      bad.push((el.tagName + "." + el.className + " " + el.textContent.trim().slice(0, 14))
        .slice(0, 48));
    }
  }
  return bad;
});
is("every non-inline interactive control is at least 40px", small.length === 0,
   small.slice(0, 4).join(", "));
const focusable = await page.evaluate(() => {
  document.querySelector("#go").focus();
  const s = getComputedStyle(document.activeElement, ":focus-visible");
  return { tag: document.activeElement.id, outline: s.outlineWidth };
});
is("the CTA is focusable", focusable.tag === "go", JSON.stringify(focusable));
is("dynamic plan changes are announced",
   (await page.locator("#live[aria-live=polite]").count()) === 1);
is("the busy state is exposed while planning",
   (await page.locator("#result[aria-live]").count()) === 1);
is("there is a skip link", (await page.locator("a.skip-link").count()) === 1);
is("the opportunity chart has a text alternative",
   ((await page.locator(".tl svg").getAttribute("aria-label")) || "").length > 40);
is("the map has a text alternative",
   ((await page.locator("#map").getAttribute("aria-label")) || "").length > 4);

await page.addScriptTag({ path: AXE });
const axeResult = await page.evaluate(async () =>
  await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } }));
const serious = axeResult.violations.filter((v) => ["serious", "critical"].includes(v.impact));
is(`axe: no serious or critical WCAG 2 AA violations (${axeResult.violations.length} total)`,
   serious.length === 0,
   serious.map((v) => `${v.id} x${v.nodes.length}`).join(", "));
for (const v of axeResult.violations) {
  console.log(`      \x1b[33m~\x1b[0m axe ${v.impact}: ${v.id} — ${v.nodes.length} node(s)`);
}

section("§42 — offline never implies the data is current");
is("a service worker is registered",
   await page.evaluate(() => navigator.serviceWorker.getRegistrations().then((r) => r.length > 0)));
const man = await (await ctx.request.get(BASE + "/manifest.webmanifest")).json();
is("the manifest is installable",
   man.name && man.start_url && man.display === "standalone" && man.icons.length >= 2);
for (const i of man.icons) {
  const r = await ctx.request.get(BASE + "/" + i.src);
  is(`manifest icon exists: ${i.src}`, r.ok(), String(r.status()));
}
is("Leaflet is bundled locally, not from a CDN",
   (await ctx.request.get(BASE + "/assets/leaflet.js")).ok());

section("console");
is("no JavaScript errors anywhere in this run", errors.length === 0,
   errors.slice(0, 3).join(" | "));

function toMin(t) {
  const m = t.match(/(\d+):(\d+)\s*(AM|PM)?/i);
  if (!m) return 0;
  let h = Number(m[1]) % 12;
  if (/pm/i.test(m[3] || "")) h += 12;
  return h * 60 + Number(m[2]);
}
function lum(rgb) {
  const m = rgb.match(/\d+/g).map(Number);
  return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255;
}

await browser.close();
if (server) server.close();
console.log();
if (fails) { console.log(`\x1b[31mFAILED ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log("\x1b[32mALL PLANNER RUNTIME CHECKS PASSED\x1b[0m");
