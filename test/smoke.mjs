/**
 * Post-deploy smoke test: load the LIVE site over HTTPS and assert it actually works
 * on the host, not just in out/. Catches things a file:// run cannot — TLS, redirects,
 * blocked third-party assets, and a secure context for geolocation.
 *
 * Run:  cd test && node smoke.mjs [base-url]
 * Default base: https://master.caney.pages.dev
 */
import { chromium } from 'playwright';

const BASE = (process.argv[2] || 'https://master.caney.pages.dev').replace(/\/$/, '');
const PAGES = ['index.html', 'caney.html', 'cumbnash.html', 'stones.html',
               'duck.html', 'elktn.html', 'cumberland.html', 'elk.html'];

let fails = 0;
const ok = n => console.log('  \x1b[32m✓\x1b[0m ' + n);
const bad = (n, d) => { fails++; console.log('  \x1b[31m✗\x1b[0m ' + n + (d ? ' — ' + d : '')); };
const assert = (n, c, d) => c ? ok(n) : bad(n, d);

const browser = await chromium.launch();
console.log(`── post-deploy smoke: ${BASE} ──`);

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
  const real = errs.filter(e => !/favicon/.test(e));
  assert(`${p}: no JS errors`, real.length === 0, real.join(' | '));
  await pg.close();
}

await browser.close();
console.log('');
if (fails) { console.log(`\x1b[31mSMOKE FAILED — ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log('\x1b[32mSMOKE PASSED\x1b[0m');
