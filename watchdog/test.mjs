/**
 * Watchdog tests. Runs the REAL decision function — the same module the Worker imports —
 * against the live endpoint and against each failure mode, with no Cloudflare involved.
 *
 *   node watchdog/test.mjs
 */
import { decide, STALE_SEC, RIVER_LAG_SEC, REMIND_SEC } from "./src/check.js";

let fails = 0;
const ok = (n) => console.log("  \x1b[32m✓\x1b[0m " + n);
const bad = (n, d) => { fails++; console.log("  \x1b[31m✗\x1b[0m " + n + (d ? " — " + d : "")); };
const is = (n, cond, d) => (cond ? ok(n) : bad(n, d));

const NOW = 1_800_000_000;
const site = (over = {}) => ({ built: NOW - 600, builtIso: "x", rivers: 13, oldestRiver: "caney", oldestRiverAgeSec: 60, ...over });

console.log("── the healthy case stays silent ──");
{
  const v = decide(site(), null, NOW, { state: "ok", at: NOW - 99999 });
  is("fresh site → no alert", v.state === "ok" && v.alert === null, JSON.stringify(v));
}

console.log("\n── the failure that actually happened ──");
{
  // 2026-08-21: deploys stopped, the site kept serving a 55-hour-old build.
  const v = decide(site({ built: NOW - 55 * 3600 }), null, NOW, {});
  is("55 h stale → alerts", v.state === "stale" && !!v.alert, JSON.stringify(v.state));
  is("says how long in days", /2 days/.test(v.alert.title), v.alert.title);
  is("points at the Actions history", /Actions/.test(v.alert.body));
  is("high priority", v.alert.priority === "high");
}
{
  const justUnder = decide(site({ built: NOW - (STALE_SEC - 60) }), null, NOW, {});
  is("just under the threshold stays quiet", justUnder.alert === null);
  const justOver = decide(site({ built: NOW - (STALE_SEC + 60) }), null, NOW, {});
  is("just over the threshold alerts", justOver.state === "stale" && !!justOver.alert);
}

console.log("\n── the site being down is not the same as being stale ──");
{
  const v = decide(null, "HTTP 522", NOW, {});
  is("unreachable → alerts", v.state === "unreachable" && !!v.alert);
  is("quotes the failure", /522/.test(v.alert.body), v.alert.body);
  const noTs = decide({ rivers: 13 }, null, NOW, {});
  is("endpoint without a build timestamp → unreachable", noTs.state === "unreachable");
}

console.log("\n── one river silently falling behind ──");
{
  const v = decide(site({ oldestRiverAgeSec: RIVER_LAG_SEC + 3600, oldestRiver: "duckmid" }), null, NOW, {});
  is("river lag → alerts", v.state === "river-lag" && !!v.alert);
  is("names the river", /duckmid/.test(v.alert.title), v.alert.title);
  is("lower priority than a dead deploy", v.alert.priority === "default");
  const fresh = decide(site({ oldestRiverAgeSec: 300 }), null, NOW, {});
  is("a normal spread between generators is silent", fresh.alert === null);
}

console.log("\n── it must not become noise ──");
{
  const stale = site({ built: NOW - 55 * 3600 });
  const first = decide(stale, null, NOW, {});
  is("first sighting alerts", !!first.alert);
  const soon = decide(stale, null, NOW + 900, { state: "stale", at: NOW });
  is("15 min later stays quiet", soon.alert === null && soon.state === "stale");
  const later = decide(stale, null, NOW + REMIND_SEC + 60, { state: "stale", at: NOW });
  is("re-reminds after the reminder window", !!later.alert);
  // The real outage was 55 h. At one tick per 15 min that is 220 ticks.
  let spoke = 0, lastState = {};
  for (let t = 0; t <= 55 * 3600; t += 900) {
    const v = decide(site({ built: NOW - t }), null, NOW, lastState);
    if (v.alert) { spoke++; lastState = { state: v.state, at: NOW }; }
    else if (v.state !== lastState.state) lastState = { state: v.state, at: lastState.at || NOW };
  }
  is("a 55 h outage is a handful of alerts, not hundreds", spoke <= 12, `${spoke} alerts`);
}

console.log("\n── recovery is announced, so silence is never ambiguous ──");
{
  const v = decide(site(), null, NOW, { state: "stale", at: NOW - 3600 });
  is("recovered → says so once", v.state === "ok" && !!v.alert && /publishing again/.test(v.alert.title));
  const after = decide(site(), null, NOW + 60, { state: "ok", at: NOW });
  is("and then goes quiet", after.alert === null);
}

console.log("\n── against the LIVE endpoint ──");
try {
  // Mirror the Worker exactly: a non-2xx OR an unparseable body (Cloudflare Pages answers a
  // missing path with its 404 *page*, not a JSON error) both mean "cannot read freshness".
  const r = await fetch("https://caney.pages.dev/site.json", { cache: "no-store" });
  let live = null, err = r.ok ? null : `HTTP ${r.status}`;
  if (r.ok) { try { live = await r.json(); } catch (e) { err = "response was not JSON"; } }
  const now = Math.floor(Date.now() / 1000);
  const v = decide(live, err, now, {});
  console.log(`  endpoint: HTTP ${r.status}` + (live ? `, built ${Math.round((now - live.built) / 60)} min ago, ${live.rivers} rivers` : ""));
  is("the live site reads as healthy", v.state === "ok" && v.alert === null, JSON.stringify(v));
  // and the same endpoint, aged, must trip it
  if (live) {
    const aged = decide({ ...live, built: live.built - 4 * 3600 }, null, now, {});
    is("the same endpoint aged 4 h trips the alarm", aged.state === "stale" && !!aged.alert);
  }
} catch (e) {
  bad("live endpoint reachable", String(e.message || e));
}

console.log();
if (fails) { console.log(`\x1b[31mFAILED ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log("\x1b[32mALL WATCHDOG CHECKS PASSED\x1b[0m");
