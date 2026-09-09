/**
 * Post-deploy smoke test: load the LIVE site over HTTPS and assert it actually works
 * on the host, not just in out/. Catches things a file:// run cannot — TLS, redirects,
 * blocked third-party assets, and a secure context for geolocation.
 *
 * This covers the RIVER PAGES and the river board. The planner homepage has a different
 * contract — no riverlib build stamp, an ES-module bootstrap, a dataset to be fresh — and
 * is covered by planner-smoke.mjs, which runs immediately after this.
 *
 * Run:  cd test && node smoke.mjs [base-url]
 * Default base: https://caney.pages.dev (production; the master.* alias is dead)
 */
import { chromium } from 'playwright';
import { readdirSync } from 'node:fs';

const BASE = (process.argv[2] || 'https://caney.pages.dev').replace(/\/$/, '');

// DERIVED from the build, never hand-maintained. The hardcoded list this replaced had
// gone stale in both directions: it still asked for duck.html, which has not existed
// since the Duck was split into three reaches, and it did not know about the four rivers
// added since. verify.py already learned this lesson; so has this.
const STATUS = new URL('../out/status/', import.meta.url).pathname;
const RIVER_PAGES = readdirSync(STATUS)
  .filter((f) => f.endsWith('.json'))
  .map((f) => f.replace(/\.json$/, '.html'))
  .sort();
const PAGES = [...RIVER_PAGES, 'rivers.html', 'roadmap.html'];

let fails = 0;
const ok = n => console.log('  \x1b[32m✓\x1b[0m ' + n);
const bad = (n, d) => { fails++; console.log('  \x1b[31m✗\x1b[0m ' + n + (d ? ' — ' + d : '')); };
const assert = (n, c, d) => c ? ok(n) : bad(n, d);

// Losing the network mid-run while fetching an OSM tile is not a JS error, and this check
// exists to catch JS errors. Failing on connectivity turns a page-quality gate into a
// flaky one, which is how a gate stops being believed. Everything else still fails: a 404,
// a CSP violation, any pageerror, and any console.error the page itself raised.
const TRANSIENT = /net::ERR_(NETWORK_CHANGED|INTERNET_DISCONNECTED|TIMED_OUT|CONNECTION_\w+|NAME_NOT_RESOLVED|ABORTED|ADDRESS_UNREACHABLE)/;

const browser = await chromium.launch();
console.log(`── post-deploy smoke: ${BASE} ──`);
console.log(`   ${RIVER_PAGES.length} river pages + the board and the roadmap`);

for (const p of PAGES) {
  const errs = [];
  const pg = await browser.newPage({ viewport: { width: 390, height: 844 } }); // phone-sized
  pg.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)); });
  pg.on('pageerror', e => errs.push('pageerror: ' + String(e).slice(0, 120)));
  const resp = await pg.goto(`${BASE}/${p}`, { waitUntil: 'domcontentloaded', timeout: 30000 })
    .catch(e => { errs.push('nav: ' + e.message); return null; });
  await pg.waitForTimeout(1200);

  assert(`${p}: 200 over HTTPS`, !!resp && resp.status() === 200,
    resp ? 'status ' + resp.status() : 'no response');
  assert(`${p}: secure context (geolocation will work)`,
    await pg.evaluate(() => window.isSecureContext).catch(() => false));
  assert(`${p}: build stamp rendered`, !!(await pg.$('#bstamp')));
  assert(`${p}: switcher links back to the planner`,
    !!(await pg.$('a[href="index.html"]')));
  const real = errs.filter(e => !/favicon/.test(e) && !TRANSIENT.test(e));
  const flaky = errs.filter(e => TRANSIENT.test(e));
  if (flaky.length) console.log(`      \x1b[33m~\x1b[0m ${flaky.length} transient network `
    + `failure(s) fetching third-party assets — not counted`);
  assert(`${p}: no JS errors`, real.length === 0, real.join(' | '));
  await pg.close();
}

await browser.close();
console.log('');
if (fails) { console.log(`\x1b[31mSMOKE FAILED — ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log('\x1b[32mSMOKE PASSED\x1b[0m');
