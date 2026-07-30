/**
 * Runtime QA for the river tool. Loads every generated page in headless Chromium,
 * asserts ZERO console/page errors (this is what catches things like the negative-<rect>
 * SVG bug), then exercises the HQ: species filter, sort modes, day-tap detail, and
 * card-body navigation. Exit 0 = pass, 1 = fail.
 *
 * Run:  cd test && bun install && node browser.mjs      (or: bun run test)
 */
import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import path from 'path';

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'out');
const url = f => 'file://' + path.join(OUT, f);
const RIVERS = ['caney', 'cumbnash', 'stones', 'duck', 'elktn', 'cumberland', 'elk'].map(r => r + '.html');
const PAGES = ['index.html', ...RIVERS];

let fails = 0;
const ok  = (n) => console.log('  \x1b[32m✓\x1b[0m ' + n);
const bad = (n, d) => { fails++; console.log('  \x1b[31m✗\x1b[0m ' + n + (d ? ' — ' + d : '')); };
const assert = (n, cond, d) => cond ? ok(n) : bad(n, d);

const browser = await chromium.launch();

// ── every page: no JS errors, switcher intact, map present ──
console.log('── runtime: pages load clean ──');
for (const p of PAGES) {
  const errs = [];
  const pg = await browser.newPage({ viewport: { width: 900, height: 1400 } });
  pg.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)); });
  pg.on('pageerror', e => errs.push('pageerror: ' + String(e).slice(0, 120)));
  await pg.goto(url(p), { waitUntil: 'networkidle', timeout: 20000 }).catch(e => errs.push('nav: ' + e.message));
  await pg.waitForTimeout(500);
  const real = errs.filter(e => !/favicon/.test(e));
  assert('no JS errors: ' + p, real.length === 0, real.join(' | '));
  if (p !== 'index.html') {
    const tabs = await pg.$$eval('.switch a', a => a.length).catch(() => 0);
    assert('switcher 8 tabs: ' + p, tabs === 8, 'found ' + tabs);
    const map = await pg.$('#lmap');
    assert('map present: ' + p, !!map);
  }
  await pg.close();
}

// ── HQ interactions ──
console.log('── HQ interactions ──');
{
  const errs = [];
  const pg = await browser.newPage({ viewport: { width: 980, height: 1700 } });
  pg.on('pageerror', e => errs.push(String(e)));
  await pg.goto(url('index.html'), { waitUntil: 'networkidle' });
  await pg.waitForTimeout(400);

  const n0 = await pg.$$eval('#board .rc', e => e.length);
  assert('board shows 7 river cards', n0 === 7, 'found ' + n0);

  // filter chips never include removed species
  const chips = await pg.$$eval('#spf a', a => a.map(x => x.dataset.s).filter(Boolean));
  const removed = chips.filter(c => ['Catfish', 'Sauger', 'Crappie'].includes(c));
  assert('no removed-species chips', removed.length === 0, removed.join(','));
  assert('Panfish chip present', chips.includes('Panfish'));

  // filter by Trout → only trout rivers
  await pg.click('.sp a[data-s="Trout"]');
  await pg.waitForTimeout(120);
  const troutOnly = await pg.$$eval('#board .rc .tags', els => els.every(t => /Trout/.test(t.textContent)));
  const troutN = await pg.$$eval('#board .rc', e => e.length);
  assert('filter=Trout keeps only trout rivers', troutOnly && troutN > 0 && troutN < 7, troutN + ' cards');
  await pg.click('.sp a[data-s=""]');            // reset

  // sort=name → alphabetical
  await pg.selectOption('#sort', 'name');
  await pg.waitForTimeout(120);
  const names = await pg.$$eval('#board .rc .nm', e => e.map(x => x.textContent));
  // oracle must match the app's comparator (localeCompare) — a naive .sort() mis-handles "·" & case
  const sortedOk = names.every((n, i) => i === 0 || names[i - 1].localeCompare(n) <= 0);
  assert('sort=name is alphabetical (localeCompare)', sortedOk, names.join(' | '));

  // per-day weather row aligned above the day cells
  const align = await pg.$eval('#board .rc', c => {
    const wx = c.querySelector('.wxrow').children.length;
    const wk = c.querySelector('.wk').children.length;
    const a = c.querySelector('.wxrow .wxc').getBoundingClientRect();
    const d = c.querySelector('.wk .wd').getBoundingClientRect();
    return { wx, wk, aligned: Math.abs(a.left - d.left) < 2 };
  });
  assert('7 weather cols aligned over 7 day cells', align.wx === 7 && align.wk === 7 && align.aligned,
    JSON.stringify(align));

  // day-tap reveals the note inline and does NOT navigate
  await pg.click('#board .rc .wd');
  await pg.waitForTimeout(120);
  const noteShown = await pg.$eval('#board .rc .wknote', e => !e.hidden && e.textContent.length > 5);
  assert('day-tap reveals note, stays on HQ', noteShown && pg.url().endsWith('index.html'));

  // card-body click navigates to that river
  const href = await pg.$eval('#board .rc', a => a.getAttribute('href'));
  await pg.click('#board .rc .nm');
  await pg.waitForTimeout(300);
  assert('card click opens the river page', pg.url().endsWith(href), 'went to ' + pg.url().split('/').pop());

  assert('no HQ page errors during interaction', errs.length === 0, errs.join('|'));
  await pg.close();
}

// ── build stamp (R2): the page must say how old its data is ──
// Every number on these pages is baked at generation time, so the page's age IS the
// data's age. These drive the device clock forward to check each staleness state, and
// backward to check skew detection — the clock-injection capability the CEO review
// flagged as missing. Shifts Date.now only; no fixture build required.
console.log('── build stamp: staleness + clock skew ──');
{
  const stampState = async (offsetMs) => {
    const ctx = await browser.newContext();
    const pg = await ctx.newPage();
    if (offsetMs) await pg.addInitScript(off => {
      const R = Date.now.bind(Date); Date.now = () => R() + off;
    }, offsetMs);
    await pg.goto(url('caney.html'), { timeout: 20000 });
    await pg.waitForSelector('#bstamp', { timeout: 5000 });
    const r = await pg.$eval('#bstamp', e => ({ cls: e.className, txt: e.textContent.trim() }));
    await ctx.close();
    return r;
  };
  const H = 3600e3;
  const fresh = await stampState(0);
  assert('stamp fresh: quiet state + build time',
    fresh.cls.includes('l0') && /Data built .* ago/.test(fresh.txt), fresh.txt);
  const aging = await stampState(5 * H);
  assert('stamp aging at +5 h: amber + explicit age',
    aging.cls.includes('l1') && /Data is 5 h old/.test(aging.txt), aging.txt);
  const stale = await stampState(30 * H);
  assert('stamp stale at +30 h: warns flows may have changed',
    stale.cls.includes('l2') && /flows and generation may have changed/.test(stale.txt), stale.txt);
  const skew = await stampState(-60 * 60e3);
  assert('stamp detects a device clock running behind the build',
    skew.cls.includes('skew') && /clock looks wrong/.test(skew.txt), skew.txt);

  // parity rule: it has to be on every page, not just the one we drove
  const missing = [];
  for (const p of PAGES) {
    const pg = await browser.newPage();
    await pg.goto(url(p), { timeout: 20000 });
    if (!(await pg.$('#bstamp'))) missing.push(p);
    await pg.close();
  }
  assert('build stamp renders on all ' + PAGES.length + ' pages', missing.length === 0,
    'missing on ' + missing.join(', '));
}

await browser.close();
console.log('');
if (fails) { console.log(`\x1b[31mFAILED ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log('\x1b[32mALL RUNTIME CHECKS PASSED\x1b[0m');
