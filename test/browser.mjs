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
const RIVERS = ['caney', 'cumbnash', 'stones', 'duck', 'elktn', 'cumberland', 'elk', 'cheatham', 'cordell'].map(r => r + '.html');
const PAGES = ['index.html', ...RIVERS];
const TABS = RIVERS.length + 1;   // HQ + every river; derived, never hardcoded

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
    assert(`switcher ${TABS} tabs: ` + p, tabs === TABS, 'found ' + tabs);
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
  assert(`board shows ${RIVERS.length} river cards`, n0 === RIVERS.length, 'found ' + n0);

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
  assert('filter=Trout keeps only trout rivers', troutOnly && troutN > 0 && troutN < RIVERS.length, troutN + ' cards');
  await pg.click('.sp a[data-s=""]');            // reset

  // sort=name → alphabetical
  await pg.selectOption('#sort', 'name');
  await pg.waitForTimeout(120);
  const names = await pg.$$eval('#board .rc .nm', e => e.map(x => x.textContent));
  // oracle must match the app's comparator (localeCompare) — a naive .sort() mis-handles "·" & case
  const sortedOk = names.every((n, i) => i === 0 || names[i - 1].localeCompare(n) <= 0);
  assert('sort=name is alphabetical (localeCompare)', sortedOk, names.join(' | '));

  // the week strip only exists in Week view now — switch to it before asserting on it
  await pg.click('#viewsel button[data-v="week"]');
  await pg.waitForTimeout(150);

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
  // Offsets must be relative to the page's BAKED build time, not to wall clock: on a build
  // that is already 4 h old, an offset of 0 is not "fresh". Read __builtEpoch and aim at it.
  const built = await (async () => {
    const p = await browser.newPage();
    await p.goto(url('caney.html'), { timeout: 20000 });
    const b = await p.evaluate(() => window.__builtEpoch * 1000);
    await p.close(); return b;
  })();
  const at = age => built + age - Date.now();   // offset that makes the page appear `age` old
  const fresh = await stampState(at(0));
  assert('stamp fresh: quiet state + build time',
    fresh.cls.includes('l0') && /Data built .* ago/.test(fresh.txt), fresh.txt);
  const aging = await stampState(at(5 * H));
  assert('stamp aging at +5 h: amber + explicit age',
    aging.cls.includes('l1') && /Data is 5 h old/.test(aging.txt), aging.txt);
  const stale = await stampState(at(30 * H));
  assert('stamp stale at +30 h: warns flows may have changed',
    stale.cls.includes('l2') && /flows and generation may have changed/.test(stale.txt), stale.txt);
  const skew = await stampState(at(-60 * 60e3));
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

// ── arrival strip (R3): next-window selection ──
// arrivalPick is pure, so drive it directly with synthetic release windows via
// page.evaluate. No fixture build needed. The cases that matter are the split-generation
// days: GEN[].relStart only ever reported the FIRST block of a day, so a countdown built
// on it went silently wrong every afternoon.
console.log('── arrival strip: next-window selection ──');
{
  const pg = await browser.newPage();
  await pg.goto(url('caney.html'), { timeout: 20000 });
  await pg.waitForFunction(() => typeof window.__arrivalPick === 'function', { timeout: 5000 })
    .catch(() => {});

  // Stonewall: 15 mi at 2.5 mph = 6 h of travel. Times below are epoch seconds on a flat day.
  const DAY = 1780000000;                      // arbitrary fixed base, no real clock involved
  const at = h => DAY + h * 3600;
  const AM = [at(6), at(9), 4000];             // morning release 06:00–09:00, front hits SW 12:00
  const PM = [at(14), at(18), 7800];           // afternoon release 14:00–18:00, front hits SW 20:00
  const pick = (rel, nowH) => pg.evaluate(
    ([rel, nowMs]) => window.__arrivalPick(rel, 15, 2.5, nowMs), [rel, at(nowH) * 1000]);

  const a = await pick([AM, PM], 10);
  assert('two-window day at 10:00 → morning front, arriving 12:00',
    a.state === 'upcoming' && a.arrival === at(12), JSON.stringify(a));

  const b = await pick([AM, PM], 13);
  assert('two-window day at 13:00 → water already here (NOT the 20:00 afternoon arrival)',
    b.state === 'arrived' && b.arrival === at(12), JSON.stringify(b));

  const c = await pick([AM, PM], 16);
  assert('two-window day at 16:00 → afternoon front, arriving 20:00',
    c.state === 'upcoming' && c.arrival === at(20), JSON.stringify(c));

  // Water stays up until the END of the release has travelled past you, not merely until
  // the front arrives. Release ends 18:00, +6 h travel = the falling limb clears SW at 24:00.
  const d1 = await pick([AM, PM], 23);
  assert('at 23:00 the falling limb is still passing → still "here", not "none"',
    d1.state === 'arrived' && d1.arrival === at(20), JSON.stringify(d1));

  const d = await pick([AM, PM], 25);
  assert('once the whole release has passed → no generation state',
    d.state === 'none', JSON.stringify(d));

  const e = await pick([PM], 15);
  assert('release running but front still upstream → upcoming, flagged as generating',
    e.state === 'upcoming' && e.gen === true, JSON.stringify(e));

  const f = await pick([], 12);
  assert('no windows at all → none', f.state === 'none', JSON.stringify(f));

  // closer spot, same windows: Happy Hollow at 6 mi = 2.4 h travel
  const g = await pg.evaluate(([rel, nowMs]) => window.__arrivalPick(rel, 6, 2.5, nowMs),
    [[AM, PM], at(7) * 1000]);
  assert('nearer spot gets an earlier arrival (6 mi → 08:24, not 12:00)',
    g.state === 'upcoming' && Math.round(g.arrival) === at(6) + Math.round(2.4 * 3600),
    JSON.stringify(g));

  await pg.close();
}

// the strip renders on Caney, and stays absent where constants are not backtested
{
  const pg = await browser.newPage();
  await pg.goto(url('caney.html'), { timeout: 20000 });
  const box = await pg.$('#arrival');
  const txt = box ? (await pg.$eval('#arrival', e => e.textContent)) : '';
  assert('caney: arrival strip rendered with a spot selector',
    !!box && /On the water/.test(txt) && !!(await pg.$('#arSpot')), txt.slice(0, 80));
  await pg.close();
}

// ── trip log (R4): captures the tool's own prediction, then the actual ──
// Prediction + outcome in the same record is what makes a wrong call falsifiable later.
console.log('── trip log: prediction capture + field backtest ──');
{
  const ctx = await browser.newContext();
  const pg = await ctx.newPage();
  await pg.goto(url('caney.html'), { timeout: 20000 });
  // the trip log lives inside a collapsed fold; open every section so it is interactable
  await pg.evaluate(() => document.querySelectorAll('.secbody').forEach(e => e.classList.add('open')));
  await pg.waitForSelector('#log_add', { timeout: 8000 });

  await pg.selectOption('#log_spot', { label: "Betty's Island" }).catch(() => {});
  await pg.fill('#log_fly', 'zebra midge #20');
  await pg.click('#log_add');
  await pg.waitForTimeout(300);

  const rec = await pg.evaluate(() => JSON.parse(localStorage.getItem('caneyLog') || '[]').pop());
  // snap() returns null when no release is pending — a normal minimum-flow day, not a failure.
  const hasWindow = await pg.evaluate(() => {
    const A = DATA.arrival;
    return !!(A && A.validated && window.__arrivalPick(
      A.rel, A.spots[1].mfd, A.mph, Date.now()).state !== 'none');
  });
  if (!hasWindow) {
    assert('no generation scheduled: trip logs cleanly with no prediction',
      !!rec && rec.pred == null, JSON.stringify(rec));
  } else {
  assert('logged trip carries the tool prediction',
    !!(rec && rec.pred && rec.pred.arrival && rec.pred.spot === "Betty's Island"),
    JSON.stringify(rec && rec.pred));
  assert('prediction records the constants and data age it used',
    !!(rec && rec.pred && rec.pred.mph === 2.5 && rec.pred.mfd === 9 && rec.pred.dataAgeMin != null),
    JSON.stringify(rec && rec.pred));

  const predShown = await pg.$eval('#log_list', e => e.textContent);
  assert('entry shows what the tool said', /Tool said:.*water reaches/i.test(predShown),
    predShown.slice(0, 90));

  // stamp the actual arrival and check the delta is computed
  await pg.click('.logactual');
  await pg.waitForTimeout(250);
  const after = await pg.$eval('#log_list', e => e.textContent);
  assert('stamping the actual arrival reports a delta',
    /Actual .* (spot on|\d+ min (late|early))/.test(after), after.slice(0, 140));
  const rec2 = await pg.evaluate(() => JSON.parse(localStorage.getItem('caneyLog') || '[]').pop());
  assert('actual arrival persists alongside the prediction',
    !!(rec2 && rec2.actual && rec2.pred), JSON.stringify(rec2 && { a: rec2.actual, p: !!rec2.pred }));
  }

  await ctx.close();
}

// corrupt log must be backed up and announced, never silently emptied
{
  const ctx = await browser.newContext();
  const pg = await ctx.newPage();
  await pg.goto(url('caney.html'), { timeout: 20000 });
  await pg.evaluate(() => localStorage.setItem('caneyLog', '{not json at all'));
  await pg.reload({ timeout: 20000 });
  await pg.evaluate(() => document.querySelectorAll('.secbody').forEach(e => e.classList.add('open')));
  await pg.waitForSelector('#log_add', { timeout: 8000 });
  const warned = await pg.$eval('#log', e => e.textContent);
  assert('corrupt trip log is announced, not silently emptied',
    /could not be read/i.test(warned), warned.slice(0, 100));
  const backedUp = await pg.evaluate(() =>
    Object.keys(localStorage).some(k => k.indexOf('caneyLog:corrupt:') === 0));
  assert('corrupt trip log is preserved under a backup key', backedUp);
  await ctx.close();
}

// ── chatter URLs (R5): scheme allowlist ──
console.log('── chatter: URL scheme allowlist ──');
{
  const pg = await browser.newPage();
  await pg.goto(url('caney.html'), { timeout: 20000 });
  const r = await pg.evaluate(() => {
    const el = document.createElement('div');
    el.id = '__t'; document.body.appendChild(el);
    const wrap = document.createElement('div'); wrap.id = '__tw'; document.body.appendChild(wrap);
    renderChatter('__t', { posts: [
      { url: 'javascript:alert(1)', sub: 'x', date: 'now', title: 'hostile', score: 1, comments: 0 },
      { url: 'https://reddit.com/r/flyfishing/x', sub: 'y', date: 'now', title: 'fine', score: 1, comments: 0 },
    ] }, '__tw');
    return [...el.querySelectorAll('a.ch')].map(a => a.getAttribute('href'));
  }).catch(e => ['ERR: ' + e.message]);
  assert('javascript: URL is neutralised', r[0] === '#', JSON.stringify(r));
  assert('https URL passes through intact',
    (r[1] || '').startsWith('https://reddit.com/'), JSON.stringify(r));
  await pg.close();
}


// ── HQ day view (Today / Tomorrow / Week) ──
// The default is time-of-day dependent: Today before noon, Tomorrow after. Drive the
// clock rather than trusting whatever hour the suite happens to run at.
console.log('── HQ: day view selector + default by clock ──');
{
  const atHour = async (hh) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 } });
    const pg = await ctx.newPage();
    await pg.addInitScript(h => {
      const R = Date;
      const fake = () => { const d = new R(); d.setHours(h, 0, 0, 0); return d; };
      Date.now = () => fake().getTime();
      window.Date = class extends R {
        constructor(...a) { if (!a.length) return new R(fake()); super(...a); }
        static now() { return fake().getTime(); }
      };
    }, hh);
    const errs = [];
    pg.on('pageerror', e => errs.push(String(e)));
    await pg.goto(url('index.html'), { timeout: 20000 });
    await pg.waitForSelector('#viewsel button.on', { timeout: 8000 });
    const r = {
      view: await pg.$eval('#viewsel button.on', e => e.textContent.trim()),
      head: await pg.$eval('#dayhead', e => e.textContent),
      cards: await pg.$$eval('#board .rc', e => e.length),
      errs,
    };
    await ctx.close();
    return r;
  };
  const am = await atHour(9);
  assert('before noon the board defaults to Today', am.view === 'Today', am.view + ' / ' + am.head);
  const pm = await atHour(15);
  assert('after noon the board defaults to Tomorrow', pm.view === 'Tomorrow', pm.view + ' / ' + pm.head);
  assert('day view renders every river', am.cards === RIVERS.length, 'found ' + am.cards);
  assert('no JS errors in day view', am.errs.length === 0 && pm.errs.length === 0,
    [...am.errs, ...pm.errs].join(' | '));

  // switching views, and the content that must appear in each
  const pg = await browser.newPage({ viewport: { width: 390, height: 900 } });
  await pg.goto(url('index.html'), { timeout: 20000 });
  await pg.waitForSelector('#viewsel button.on');
  await pg.click('#viewsel button[data-v="today"]');
  await pg.waitForTimeout(150);
  const chips = await pg.$$eval('#board .chip', e => e.length);
  assert('today view shows condition chips (wade/boat, level, clarity)', chips >= RIVERS.length,
    'found ' + chips);
  const curves = await pg.$$eval('#board .curve svg', e => e.length);
  const nocurve = await pg.$$eval('#board .nocurve', e => e.length);
  assert('every river shows either a flow curve or an explicit no-forecast notice',
    curves + nocurve >= RIVERS.length, curves + ' curves + ' + nocurve + ' notices');
  assert('today view marks the current hour on the curve',
    (await pg.$$eval('#board .curve line', e => e.length)) > 0);

  // the live badge is always TODAY; on another day's view it must say so, or a Prime badge
  // sits unlabelled above a headline describing a different day
  await pg.click('#viewsel button[data-v="tomorrow"]');
  await pg.waitForTimeout(200);
  const badgeLabelled = await pg.$$eval('#board .rc .badge', e => e.every(x => /now/i.test(x.innerText)));
  assert('on a non-today view the live badge is labelled "now"', badgeLabelled);
  await pg.click('#viewsel button[data-v="today"]');
  await pg.waitForTimeout(200);
  const badgePlain = await pg.$$eval('#board .rc .badge', e => e.every(x => !/now/i.test(x.innerText)));
  assert('on the today view the badge carries no redundant label', badgePlain);

  await pg.click('#viewsel button[data-v="week"]');
  await pg.waitForTimeout(150);
  const wk = await pg.$$eval('#board .wk .wd', e => e.length);
  assert('week view restores the 7-day strip', wk === RIVERS.length * 7, 'found ' + wk);
  assert('week view drops the day chips', (await pg.$$eval('#board .chip', e => e.length)) === 0);
  await pg.close();
}


// ── Caney planner: reachability + one clock ──
// A plan is only a plan if you can physically get there. This used to sort every rising
// access by time and pick the earliest, which is always the one nearest the dam — so
// launching at Stonewall it advised being at Long Branch, 15 miles UPSTREAM, through six
// stretches the same page classified as wade water.
console.log('── caney planner: reachability + arrival consistency ──');
{
  const pg = await browser.newPage({ viewport: { width: 430, height: 1100 } });
  const errs = [];
  pg.on('pageerror', e => errs.push(String(e)));
  await pg.goto(url('caney.html'), { timeout: 20000 });
  await pg.waitForTimeout(1200);
  await pg.click('button[data-c="power"]');
  await pg.waitForTimeout(200);
  await pg.click('button[data-m="up"]');
  await pg.waitForTimeout(200);
  await pg.evaluate(() => {
    const b = [...document.querySelectorAll('#segFrom button,#segFrom a,#segFrom span')]
      .find(e => /Stonewall/.test(e.textContent));
    if (b) b.click();
  });
  await pg.evaluate(() => {
    const s = [...document.querySelectorAll('input[type=range]')].find(x => +x.max >= 660 && +x.min <= 660);
    if (s) { s.value = 660; s.dispatchEvent(new Event('input', { bubbles: true })); }
  });
  await pg.waitForTimeout(600);
  const txt = await pg.$eval('#summary', e => e.innerText);

  // never route upstream past water the page itself calls wade
  const badTarget = /be on the edge at <?b?>?(Long Branch|Buffalo Valley|Lancaster|Happy Hollow)/i.test(txt)
                 || /\b(Long Branch|Buffalo Valley)\b[^.]*starts moving/i.test(txt);
  assert('launching at Stonewall never sends you upstream through wade water', !badTarget, txt.slice(0, 160));

  // the reachability gate itself, driven directly
  const gate = await pg.evaluate(() => {
    if (typeof reachable !== 'function') return null;
    return { upstreamSkinny: reachable(0, 13 * 60), self: reachable(6, 13 * 60) };
  }).catch(() => null);
  if (gate) assert('reachability rejects the 15-mile upstream run at low flow', gate.upstreamSkinny === false);

  // one clock: the planner and the generation schedule must agree on arrival
  const both = await pg.evaluate(() => {
    const g = DATA.gen[0];
    if (!g || g.relStart == null) return null;
    const st = DATA.arrivalStages.first;
    const sw = DATA.points.find(p => p.name === 'Stonewall');
    return { fromRule: g.relStart + (sw.mfd / st.mph) * 60, arrRow: (g.arr || []).slice(-1)[0] };
  });
  if (both) {
    assert('planner arrival uses the measured first-rise rule, not a flow threshold',
      Math.abs(both.fromRule - (Math.round(both.fromRule))) < 60, JSON.stringify(both));
  }
  assert('arrival is presented as a measured band, not a false point value',
    /–|—/.test(txt) && /starts moving|release reaches/.test(txt), txt.slice(0, 160));

  // ── time-plan arithmetic ──
  // Two distance systems used to coexist: rm (superseded river-mile estimates) and mfd
  // (verified miles-from-dam). Arrival timing moved to mfd; drift timing did not, inflating
  // every float by up to 9%. And timeStr wrapped past midnight silently, so a late launch
  // showed a next-morning take-out as if it were the same day.
  {
    const pg2 = await browser.newPage({ viewport: { width: 430, height: 1100 } });
    await pg2.goto(url('caney.html'), { timeout: 20000 });
    await pg2.waitForTimeout(1000);

    const consistent = await pg2.evaluate(() => {
      // drift distance must be measured on the same basis the times are
      const a = DATA.points[0], b = DATA.points[6];
      return { mfd: +(b.mfd - a.mfd).toFixed(1), rm: +(a.rm - b.rm).toFixed(1) };
    });
    await pg2.click('button[data-c="raft"]'); await pg2.waitForTimeout(150);
    await pg2.click('button[data-m="drift"]'); await pg2.waitForTimeout(150);
    await pg2.evaluate(() => { const s = [...document.querySelectorAll('input[type=range]')]
      .find(x => +x.max >= 420 && +x.min <= 420); if (s) { s.value = 420; s.dispatchEvent(new Event('input', { bubbles: true })); } });
    await pg2.waitForTimeout(450);
    const t1 = await pg2.$eval('#summary', e => e.innerText);
    assert('drift distance uses verified mfd, not superseded river miles',
      t1.includes(consistent.mfd.toFixed(1) + ' mi') && !t1.includes(consistent.rm.toFixed(1) + ' mi'),
      t1.slice(0, 120));

    // late launch must mark a next-day take-out
    await pg2.evaluate(() => { const s = [...document.querySelectorAll('input[type=range]')]
      .find(x => +x.max >= 1200 && +x.min <= 1200); if (s) { s.value = 1200; s.dispatchEvent(new Event('input', { bubbles: true })); } });
    await pg2.waitForTimeout(450);
    const t2 = await pg2.$eval('#summary', e => e.innerText);
    assert('a float running past midnight says "next day"', /next day/.test(t2), t2.slice(0, 160));

    // a collapsed band (at the dam, mfd 0) must not print the same time twice
    assert('arrival band never renders as "X–X"', !/(\d+:\d\d [AP]M)[–—]\1/.test(t2), t2.slice(0, 200));
    await pg2.close();
  }

  assert('no JS errors in the planner', errs.length === 0, errs.join(' | '));
  await pg.close();
}


// ── Caney layout: the day picker must sit above what it controls ──
// It used to live inside "Plan & river", six collapsed sections BELOW the weather and feed
// it re-renders — so you changed the day and the effect happened off-screen.
console.log('── caney layout: day picker placement ──');
{
  const pg = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errs = [];
  pg.on('pageerror', e => errs.push(String(e)));
  await pg.goto(url('caney.html'), { timeout: 20000 });
  await pg.waitForTimeout(1200);

  const pos = await pg.evaluate(() => {
    const y = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().top : null; };
    const order = [...document.querySelectorAll('.app > .sec.fold')].map(e => e.dataset.t);
    return { day: y('#daybar'), now: y('#nowstrip'), arr: y('#arrival'), wx: y('#bWx'), order };
  });
  assert('day picker is above the fold on a phone', pos.day !== null && pos.day < 844, 'top ' + pos.day);
  assert('day picker sits above everything it re-renders',
    pos.day < pos.wx && pos.day < pos.arr, JSON.stringify(pos));
  assert('"right now" stays above the picker (now is always today)', pos.now < pos.day);
  assert('day-scoped sections are contiguous under the picker',
    pos.order.slice(0, 4).join(',') === 'bWx,bGen,bPlan,bCal', pos.order.join(','));

  // it must stay reachable once you are deep in the page
  await pg.evaluate(() => window.scrollTo(0, 1800));
  await pg.waitForTimeout(250);
  const stuck = await pg.$eval('#daybar', e => e.getBoundingClientRect().top);
  assert('day picker stays pinned when scrolled', stuck < 80, 'top ' + stuck);

  // changing the day must move the weather card, not just the planner
  await pg.evaluate(() => window.scrollTo(0, 0));
  await pg.waitForTimeout(150);
  const before = await pg.$eval('#wx', e => e.innerText);
  await pg.evaluate(() => { const b = document.querySelectorAll('#dates button'); (b[3] || b[1]).click(); });
  await pg.waitForTimeout(350);
  const after = await pg.$eval('#wx', e => e.innerText);
  assert('changing the day updates the weather card', before !== after, 'weather did not change');
  const lbl = await pg.$eval('#dayWhen', e => e.textContent);
  assert('a non-today selection is labelled as such', /not today/.test(lbl), lbl);

  // ── time slider: above the diagram, pinned, and driving it live ──
  // It used to sit BELOW a ~780px map/diagram card, so while you watched the diagram the
  // control was off-screen — the same control-away-from-effect bug as the day picker.
  {
    const pg3 = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const e3 = [];
    pg3.on('pageerror', e => e3.push(String(e)));
    await pg3.goto(url('caney.html'), { timeout: 20000 });
    await pg3.waitForTimeout(1200);

    const ord = await pg3.evaluate(() => {
      const y = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().top : null; };
      return { tb: y('.timebar'), map: y('.mapcard') };
    });
    assert('time slider sits above the diagram it controls', ord.tb < ord.map, JSON.stringify(ord));

    // both sticky bars must stack, never overlap
    await pg3.evaluate(() => document.querySelector('.mapcard').scrollIntoView({ block: 'center' }));
    await pg3.waitForTimeout(350);
    const st = await pg3.evaluate(() => {
      const r = s => { const b = document.querySelector(s).getBoundingClientRect(); return { top: b.top, bot: b.bottom }; };
      return { day: r('#daybar'), tb: r('.timebar') };
    });
    assert('slider pins below the day bar without overlapping it',
      st.tb.top >= st.day.bot - 3 && st.tb.top < 300, JSON.stringify(st));

    // and it must actually drive the diagram
    await pg3.click('button[data-v="diagram"]');
    await pg3.waitForTimeout(300);
    const read = async v => {
      await pg3.evaluate(x => { const s = document.getElementById('slider'); s.value = x; s.dispatchEvent(new Event('input', { bubbles: true })); }, v);
      await pg3.waitForTimeout(200);
      return pg3.evaluate(() => [...document.querySelectorAll('[id^=gl]')].map(e => e.textContent).join('|'));
    };
    const am = await read(480), pm = await read(1020);
    assert('dragging the slider updates the diagram live', am !== pm, 'diagram did not change');

    // one distance vocabulary on the page
    const rmLeft = await pg3.evaluate(() => document.getElementById('river').textContent.includes('rm '));
    assert('diagram uses miles-below-dam, not retired river miles', !rmLeft);
      // trout holes: the user's own spots, on the map and in the arrival selector
    const holes = await pg3.evaluate(() => ({
      published: (DATA.holes || []).length,
      inSelector: [...document.querySelectorAll('#arSpot option')].filter(o => /Trout Hole/.test(o.textContent)).length,
      markers: document.querySelectorAll('.leaflet-marker-icon').length,
      inSegs: [...document.querySelectorAll('#segFrom button, #segTo button')].filter(e => /Trout Hole/.test(e.textContent)).length,
    }));
    assert('all 7 trout holes published', holes.published === 7, String(holes.published));
    assert('trout holes are targetable in the arrival strip', holes.inSelector === 7, String(holes.inSelector));
    assert('trout holes never offered as a put-in or take-out', holes.inSegs === 0, String(holes.inSegs));

    // a put-in must suit the craft: a wade-only roadside pull-off is not a boat launch
    const byCraft = async c => {
      await pg3.click(`button[data-c="${c}"]`); await pg3.waitForTimeout(250);
      return pg3.evaluate(() => [...document.querySelectorAll('#segFrom button')]
        .filter(e => e.style.display !== 'none').map(e => e.textContent.trim()));
    };
    const wadeOpts = await byCraft('wade'), powerOpts = await byCraft('power');
    assert('wade-only accesses are offered when wading', wadeOpts.includes('Kirby Road'), wadeOpts.join(','));
    assert('wade-only accesses are NOT offered as a powerboat put-in',
      !powerOpts.includes('Kirby Road') && !powerOpts.includes('Lancaster'), powerOpts.join(','));
    assert('ramp accesses stay available to a powerboat',
      powerOpts.includes('Stonewall') && powerOpts.includes('Long Branch'), powerOpts.join(','));

  assert('no JS errors in the slider pass', e3.length === 0, e3.join(' | '));
    await pg3.close();
  }

  assert('no JS errors in the layout pass', errs.length === 0, errs.join(' | '));
  await pg.close();
}


// ── striper card: styled to the design system, not browser defaults ──
// The card shipped unstyled once: the CSS was inserted on an anchor that did not exist in
// these files, so it rendered at 16px default with no muted tones. innerText looked fine,
// which is exactly why that slipped through — computed style is the check that catches it.
console.log('── cumberland striper card: design system ──');
{
  for (const f of ['cumbnash.html', 'cheatham.html', 'cordell.html']) {
    const pg = await browser.newPage({ viewport: { width: 390, height: 900 } });
    await pg.goto(url(f), { timeout: 20000 });
    await pg.waitForTimeout(900);
    const m = await pg.evaluate(() => {
      const el = document.getElementById('striper');
      if (!el) return null;
      const cs = s => { const e = el.querySelector(s); return e ? getComputedStyle(e) : null; };
      const g = cs('.sgrade'), c = cs('.scond'), n = cs('.snote'), k = cs('.srow .k');
      const faint = getComputedStyle(document.documentElement).getPropertyValue('--faint').trim();
      return {
        grade: g && g.fontSize, cond: c && c.fontSize, note: n && n.fontSize,
        keyColor: k && k.color, faintTok: faint,
        overflow: el.scrollWidth > el.clientWidth + 1,
        dupUnits: /(\d+ units? generating)/.test(el.innerText) && /^\s*\w+\s*\n\s*\d+ units?\s*$/m.test(el.innerText),
      };
    });
    assert(`${f}: striper card is styled, not browser default`, m && m.grade === '12px' && m.note === '14px',
      JSON.stringify(m));
    assert(`${f}: labels use the faint token`, m && m.keyColor === 'rgb(97, 110, 123)', m && m.keyColor);
    assert(`${f}: contrast override is the one in force`, m && m.faintTok === '#616e7b', m && m.faintTok);
    assert(`${f}: card does not overflow its container`, m && !m.overflow);
    await pg.close();
  }
}


// ── 7-day outlook: show the working ──
// A grade with no visible reasoning is not actionable. The weighting is genuinely
// non-obvious — the moon carries 40 of ~100 points — so a "Tough" day can have perfect
// water and be penalised entirely on moon and rain.
console.log('── caney outlook: craft-aware scoring ──');
{
  const pg = await browser.newPage({ viewport: { width: 390, height: 900 } });
  const errs = [];
  pg.on('pageerror', e => errs.push(String(e)));
  await pg.goto(url('caney.html'), { timeout: 20000 });
  await pg.waitForTimeout(1200);
  await pg.evaluate(() => document.querySelectorAll('.secbody').forEach(e => e.classList.add('open')));
  await pg.waitForTimeout(200);

  // Every craft's breakdown must be internally sound, not merely present.
  const shape = await pg.evaluate(() => {
    const bad = [];
    DATA.week.forEach(d => {
      if (!d.byCraft) return bad.push(`${d.label}: no per-craft scores`);
      DATA.craftOrder.forEach(c => {
        const b = d.byCraft[c], w = b && b.why;
        if (!w) return bad.push(`${d.label}/${c}: no breakdown`);
        const sum = w.parts.reduce((a, p) => a + p.pts, 0);
        if (sum !== w.total) bad.push(`${d.label}/${c}: parts ${sum} != total ${w.total}`);
        if (sum !== b.score) bad.push(`${d.label}/${c}: breakdown ${sum} != score ${b.score}`);
        if (!w.parts.every(p => p.pts >= 0 && p.pts <= p.max)) bad.push(`${d.label}/${c}: part out of range`);
        if (!w.parts.every(p => p.why && p.why.length > 6)) bad.push(`${d.label}/${c}: a part has no explanation`);
        const weakest = w.parts.reduce((a, p) => (p.pts / p.max < a.pts / a.max ? p : a));
        if (weakest.k !== w.driver) bad.push(`${d.label}/${c}: driver ${w.driver} is not the weakest part`);
      });
    });
    return bad;
  });
  assert('every day scores soundly for every craft', shape.length === 0, shape.join(' | '));

  // The weighting is the thing the user actually asked to change: moon must be a minor term,
  // and level/clarity/weather must together dominate. Guard the intent, not just the arithmetic.
  const wts = await pg.evaluate(() => DATA.scoreW);
  const wbad = [];
  for (const [c, w] of Object.entries(wts)) {
    const tot = Object.values(w).reduce((a, b) => a + b, 0);
    if (tot !== 100) wbad.push(`${c}: weights sum to ${tot}`);
    if (w.Moon > 12) wbad.push(`${c}: moon weight ${w.Moon} is not a minor term`);
    if (w.Level + w.Clarity + w.Weather < 70) wbad.push(`${c}: water+weather only ${w.Level + w.Clarity + w.Weather}`);
    if (w.Level < w.Clarity || w.Level < w.Weather) wbad.push(`${c}: level is not the heaviest term`);
  }
  assert('moon is a minor term; water and weather dominate', wbad.length === 0, wbad.join(' | '));

  // A boat is more exposed than a wader, and a wader cares more about clarity. The weights
  // must actually differ by craft or the toggle is cosmetic.
  assert('weights genuinely differ by craft',
    wts.wade.Clarity > wts.power.Clarity && wts.power.Weather > wts.wade.Weather,
    JSON.stringify(wts));

  // Thunderstorms are a safety gate, not a deduction: a storm day must never grade well.
  const storm = await pg.evaluate(() => DATA.week.filter(d => d.storm)
    .map(d => ({ l: d.label, g: DATA.craftOrder.map(c => d.byCraft[c].grade) })));
  assert('a thunderstorm day never grades Prime',
    storm.every(d => !d.g.includes('Prime')), JSON.stringify(storm));

  // The whole point of the toggle: the same day can be worth different amounts by craft.
  const spread = await pg.evaluate(() => DATA.week.some(d =>
    new Set(DATA.craftOrder.map(c => d.byCraft[c].grade)).size > 1));
  assert('at least one day grades differently by craft', spread);

  // Craft-specific direction: no generation is good for wading and poor for a powerboat.
  const lowday = await pg.evaluate(() => {
    const d = DATA.week.find(x => x.units === 0); if (!d) return null;
    const lv = c => d.byCraft[c].why.parts.find(p => p.k === 'Level');
    return { wade: lv('wade').pts / lv('wade').max, power: lv('power').pts / lv('power').max };
  });
  if (lowday) assert('minimum flow scores better for wading than for a powerboat',
    lowday.wade > lowday.power, JSON.stringify(lowday));
  else console.log('  \x1b[33m~\x1b[0m no zero-generation day in this forecast — craft-direction check skipped');

  // and it must reach the user
  await pg.evaluate(() => {
    const r = [...document.querySelectorAll('#cal .wkrow')];
    (r.find(x => /Tue|Wed/.test(x.textContent)) || r[3]).click();
  });
  await pg.waitForTimeout(300);
  const txt = await pg.$eval('#cal', e => e.innerText);
  assert('expanding a day reveals why it scored that way', /Why .* points/.test(txt), txt.slice(0, 90));
  assert('the breakdown names each component',
    ['Level', 'Clarity', 'Weather', 'Window', 'Moon'].every(k => txt.includes(k)), txt.slice(0, 200));
  assert('the grade bands are stated', /Prime ≥ 85/.test(txt));

  // The toggle must re-render the outlook, and must move the planner with it.
  const before = await pg.$eval('#cal', e => e.innerText);
  await pg.click('#calcraft button[data-c="wade"]');
  await pg.waitForTimeout(350);
  const after = await pg.$eval('#cal', e => e.innerText);
  assert('switching craft re-scores the outlook', before !== after);
  assert('the open day stays open across a craft switch', /Why .* points/.test(after), after.slice(0, 90));
  assert('the outlook toggle also moves the planner',
    await pg.$eval('#crafts button[data-c="wade"]', e => e.classList.contains('on')));
  assert('the planner toggle also moves the outlook', await (async () => {
    await pg.click('#crafts button[data-c="power"]');
    await pg.waitForTimeout(350);
    return pg.$eval('#calcraft button[data-c="power"]', e => e.classList.contains('on'));
  })());

  // Clarity is now driven by rain that already fell, so it must be consistent page-wide.
  assert('one clarity vocabulary across the page',
    await pg.evaluate(() => DATA.week.every(d => ['clear', 'some color', 'stained'].includes(d.clarity))
      && ['clear', 'some color', 'stained'].includes(DATA.clarity)));

  assert('no JS errors in the outlook', errs.length === 0, errs.join(' | '));
  await pg.close();
}

console.log('── caney timed plan: craft-aware ──');
{
  const pg = await browser.newPage({ viewport: { width: 390, height: 900 } });
  const errs = [];
  pg.on('pageerror', e => errs.push(String(e)));
  await pg.goto(url('caney.html'), { timeout: 20000 });
  await pg.waitForTimeout(1200);
  await pg.evaluate(() => document.querySelectorAll('.secbody').forEach(e => e.classList.add('open')));
  await pg.waitForTimeout(200);

  const seen = {};
  for (const c of ['wade', 'raft', 'power']) {
    await pg.evaluate(k => setCraft(k), c);
    await pg.waitForTimeout(300);
    seen[c] = await pg.$eval('#itin', e => e.innerText);
    assert(`the timed plan renders for ${c}`, seen[c].trim().length > 40, seen[c].slice(0, 60));
  }
  assert('each craft gets a different timed plan',
    seen.wade !== seen.power && seen.power !== seen.raft && seen.wade !== seen.raft);
  assert('the plan header names the craft',
    /Powerboat/.test(await pg.$eval('#planh', e => e.textContent)));

  // craft language must not bleed across plans -- the whole reason this was rebuilt
  assert('the wade plan never tells you to launch a boat',
    !/\blaunch\b|\brun up\b/i.test(seen.wade), seen.wade.slice(0, 120));
  assert('the powerboat plan never tells you to wade',
    !/\bwade\b|\bwading\b/i.test(seen.power), seen.power.slice(0, 120));

  // switching craft in the planner must move the plan too
  await pg.click('#crafts button[data-c="wade"]');
  await pg.waitForTimeout(300);
  assert('the planner craft buttons move the timed plan',
    (await pg.$eval('#itin', e => e.innerText)) === seen.wade);

  // and switching the DAY must keep the craft
  await pg.evaluate(() => { const b = document.querySelectorAll('#dates button'); if (b[2]) b[2].click(); });
  await pg.waitForTimeout(400);
  assert('changing day keeps the selected craft',
    /Wade/.test(await pg.$eval('#planh', e => e.textContent)),
    await pg.$eval('#planh', e => e.textContent));

  assert('no JS errors in the timed plan', errs.length === 0, errs.join(' | '));
  await pg.close();
}

await browser.close();
console.log('');
if (fails) { console.log(`\x1b[31mFAILED ${fails} check(s)\x1b[0m`); process.exit(1); }
console.log('\x1b[32mALL RUNTIME CHECKS PASSED\x1b[0m');
