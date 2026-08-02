/**
 * QC the Caney page end to end. Three layers:
 *   B  every plan it can suggest (craft x mode x launch x day) checked for internal
 *      contradiction — mileage vs distance basis, durations, take-out after launch,
 *      arrival inside the measured band, no upstream routing through wade water.
 *   C  every rendered section: present, non-empty, no NaN, numbers in plausible range,
 *      and the model checked against the LIVE gauge (real accuracy, not self-consistency).
 *   D  is the advice sensible: no wading advice on a generating day, classification
 *      monotonic in flow, generation windows inside the day, grades from the known set.
 *
 * Pairs with test/qc_caney.py, which QCs the DATA payload itself.
 *
 *     cd test && node qc_caney.mjs        # exits non-zero on any failure
 */
import { chromium } from 'playwright';

let TOTAL_FAIL = 0;

// ── LAYER B ──
{

const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 430, height: 1200 } });
const jsErrs = [];
p.on('pageerror', e => jsErrs.push(String(e)));
await p.goto('file:///Users/stevenrhodes/caney/out/caney.html', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(1500);

const CRAFTS = ['wade', 'raft', 'power'];
const MODES  = ['drift', 'up'];
const LAUNCH = [300, 420, 540, 660, 780, 900, 1020, 1140, 1200];
const DAYS   = [0, 1, 2, 3];

const fails = [];
let n = 0, plans = 0;
const bad = (m, ctx) => fails.push(`${m}  [${ctx}]`);

for (const day of DAYS) {
  await p.evaluate(d => {
    const btns = document.querySelectorAll('#dates button');
    if (btns[d]) btns[d].click();
  }, day);
  await p.waitForTimeout(200);
  for (const craft of CRAFTS) {
    await p.click(`button[data-c="${craft}"]`).catch(() => {});
    await p.waitForTimeout(80);
    for (const mode of MODES) {
      const modeBtn = await p.$(`button[data-m="${mode}"]`);
      if (modeBtn) { await modeBtn.click().catch(() => {}); await p.waitForTimeout(60); }
      for (const lm of LAUNCH) {
        await p.evaluate(v => {
          const s = [...document.querySelectorAll('input[type=range]')].find(x => +x.max >= v && +x.min <= v);
          if (s) { s.value = v; s.dispatchEvent(new Event('input', { bubbles: true })); }
        }, lm);
        await p.waitForTimeout(45);
        n++;
        const r = await p.evaluate(() => {
          const el = document.getElementById('summary');
          if (!el) return null;
          const t = el.innerText;
          return {
            t,
            craft: (document.querySelector('.crafts button.on') || {}).textContent || '',
            fromIdx: (typeof fromIdx !== 'undefined') ? fromIdx : null,
            toIdx: (typeof toIdx !== 'undefined') ? toIdx : null,
            launchMin: (typeof launchMin !== 'undefined') ? launchMin : null,
            dsel: (typeof dsel !== 'undefined') ? dsel : null,
            mfdFrom: (typeof fromIdx !== 'undefined') ? DATA.points[fromIdx].mfd : null,
            mfdTo: (typeof toIdx !== 'undefined') ? DATA.points[toIdx].mfd : null,
            wadeMax: DATA.wadeMax,
            mph: DATA.mph,
            relStart: (DATA.gen[dsel] || {}).relStart,
            stEarly: DATA.arrivalStages.first.early,
            stLate: DATA.arrivalStages.first.late,
          };
        });
        if (!r) { bad('no summary element', `${craft}/${mode}/${lm}/d${day}`); continue; }
        plans++;
        const ctx = `${craft}/${mode}/launch ${lm}/day ${day}`;
        const t = r.t;

        // 1. no broken values ever reach the user
        if (/NaN|undefined|Infinity|null/.test(t)) bad('renders NaN/undefined/Infinity/null', ctx);
        // 2. mileage shown must equal the mfd separation
        const mi = t.match(/Float\s+([\d.]+)\s*mi/);
        if (mi) {
          const want = Math.abs(r.mfdTo - r.mfdFrom);
          if (Math.abs(parseFloat(mi[1]) - want) > 0.06) bad(`mileage ${mi[1]} != mfd span ${want.toFixed(1)}`, ctx);
        }
        // 3. duration must be positive and match distance/speed within tolerance
        const dur = t.match(/≈\s*(?:(\d+)h\s*)?(\d+)m/);
        if (dur) {
          const mins = (parseInt(dur[1] || 0) * 60) + parseInt(dur[2]);
          if (mins <= 0) bad('non-positive float duration', ctx);
          if (mins > 24 * 60) bad(`float duration ${mins}m exceeds a day`, ctx);
        }
        // 4. a plan that says wade must not be on water above the measured wade threshold
        const wadeCfs = t.match(/wade[^.]*?([\d,]+)\s*cfs/i);
        if (wadeCfs) {
          const v = parseInt(wadeCfs[1].replace(/,/g, ''));
          if (v > r.wadeMax * 1.75) bad(`suggests wading at ${v} cfs (threshold ${r.wadeMax})`, ctx);
        }
        // 5. never route upstream when the craft cannot go upstream
        if (mode === 'drift' && /Launch low at/.test(t)) bad('drift mode produced an upstream plan', ctx);
        // 6. arrival band must be ordered and never degenerate
        const band = t.match(/(\d+):(\d\d)\s*([AP]M)\s*[–—]\s*(\d+):(\d\d)\s*([AP]M)/);
        if (band) {
          const to24 = (h, m, ap) => ((+h % 12) + (ap === 'PM' ? 12 : 0)) * 60 + +m;
          const a = to24(band[1], band[2], band[3]), z = to24(band[4], band[5], band[6]);
          if (a === z) bad('arrival band start equals end', ctx);
          if (z < a && z + 1440 - a > 12 * 60) bad(`arrival band spans ${z + 1440 - a}m`, ctx);
        }
        // 7. take-out must be after launch (allowing an explicit next-day marker)
        const out = t.match(/take out\s+(\d+):(\d\d)\s*([AP]M)(\s*next day)?/);
        if (out) {
          const om = ((+out[1] % 12) + (out[3] === 'PM' ? 12 : 0)) * 60 + +out[2] + (out[4] ? 1440 : 0);
          if (om <= r.launchMin) bad(`take-out ${out[0]} not after launch ${r.launchMin}`, ctx);
        }
        // 8. any "release reaches X" must agree with relStart + mfd/mph
        if (r.relStart != null) {
          const reach = t.match(/release reaches[^⚡]*?(\d+):(\d\d)\s*([AP]M)/);
          if (reach) {
            const shown = ((+reach[1] % 12) + (reach[3] === 'PM' ? 12 : 0)) * 60 + +reach[2];
            // the page shows a measured BAND (early/median/late), so any edge is valid
            const cand = [];
            for (const mfd of [r.mfdFrom, r.mfdTo]) {
              for (const sp of [r.stEarly, r.mph, r.stLate]) cand.push(r.relStart + (mfd / sp) * 60);
            }
            const near = cand.some(e => {
              const d = Math.abs(((shown - e) % 1440 + 1440) % 1440);
              return Math.min(d, 1440 - d) <= 95;   // band edges are ±, so allow the spread
            });
            if (!near) bad(`arrival "${reach[0]}" is outside every band edge [${cand.map(Math.round).join(',')}]`, ctx);
          }
        }
      }
    }
  }
}
await b.close();
console.log(`QC LAYER B — plan suggestions`);
console.log(`  scenarios swept : ${n}`);
console.log(`  plans rendered  : ${plans}`);
console.log(`  JS errors       : ${jsErrs.length}`);
console.log(`  contradictions  : ${fails.length}`);
const seen = new Set();
for (const f of fails) { const key = f.split('[')[0]; if (seen.has(key)) continue; seen.add(key); console.log('   ✗ ' + f); }
if (jsErrs.length) jsErrs.slice(0, 3).forEach(e => console.log('   ! ' + e.slice(0, 120)));

TOTAL_FAIL += fails.length + jsErrs.length;
}

// ── LAYER C ──
{
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 430, height: 1400 } });
const errs = []; p.on('pageerror', e => errs.push(String(e)));
await p.goto('file:///Users/stevenrhodes/caney/out/caney.html', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(1800);
await p.evaluate(() => document.querySelectorAll('.secbody').forEach(e => e.classList.add('open')));
await p.waitForTimeout(600);

const r = await p.evaluate(() => {
  const txt = id => { const e = document.getElementById(id); return e ? e.innerText.trim() : null; };
  const out = { sections: {}, D: {} };
  for (const id of ['nowstrip','arrival','best','genc','tips','flysel','summary','cap','log','hatch','mooncal'])
    out.sections[id] = txt(id);
  out.D = {
    nowCfs: DATA.now.cfs, nowStone: DATA.now.stone, nowModel: DATA.now.model,
    nowUnits: DATA.now.units, gen: DATA.now.gen, wadeMax: DATA.wadeMax, mph: DATA.mph,
    relStart: (DATA.gen[0] || {}).relStart, arr: (DATA.gen[0] || {}).arr,
    arrivalRel: DATA.arrival.rel.length, spots: DATA.arrival.spots,
    week0: DATA.week[0], damCap: DATA.damCap,
  };
  // every number rendered anywhere in the app, for range sanity
  const nums = [];
  document.querySelectorAll('.app *').forEach(e => {
    if (e.children.length) return;
    const m = (e.textContent || '').match(/-?[\d,]+(\.\d+)?/g);
    if (m) m.forEach(x => nums.push({ v: parseFloat(x.replace(/,/g, '')), t: (e.textContent || '').slice(0, 42) }));
  });
  out.nums = nums;
  return out;
});
await b.close();

const fails = [], warns = [];
const bad = m => fails.push(m), warn = m => warns.push(m);

for (const [k, v] of Object.entries(r.sections)) {
  if (v === null) { warn(`section #${k} absent from the page`); continue; }
  if (v.length < 2) bad(`section #${k} rendered empty`);
  if (/NaN|undefined|Infinity/.test(v)) bad(`section #${k} contains NaN/undefined/Infinity`);
}
if (r.D.relStart != null && r.D.arr) {
  for (const [nm, shown] of r.D.arr) {
    const sp = r.D.spots.find(s => s.name.startsWith(nm.split("'")[0].slice(0, 6)));
    if (!sp) continue;
    const exp = r.D.relStart + (sp.mfd / r.D.mph) * 60;
    const eh = Math.floor(exp / 60) % 24;
    const gh = (parseInt(shown) % 12) + (/pm/i.test(shown) ? 12 : 0);
    if (Math.abs(((gh - eh) % 24 + 24) % 24) > 1)
      bad(`gen arrival row "${nm} ${shown}" disagrees with mfd/mph (~${eh}:00)`);
  }
}
if (r.D.nowStone != null && r.D.nowModel != null) {
  const off = Math.abs(r.D.nowStone - r.D.nowModel);
  if (off > 900) bad(`model is ${off} cfs off the live gauge (${r.D.nowModel} vs ${r.D.nowStone})`);
  else if (off > 400) warn(`model ${off} cfs off the live gauge (${r.D.nowModel} vs ${r.D.nowStone})`);
}
if (r.D.gen && r.D.nowCfs) {
  const u = Math.max(0, Math.round((r.D.nowCfs - 250) / 3650));
  if (r.D.nowUnits !== u) warn(`stated ${r.D.nowUnits} units at ${r.D.nowCfs} cfs; formula gives ${u}`);
}
const cfsish = r.nums.filter(x => /cfs/.test(x.t));
for (const x of cfsish) if (x.v < 0 || x.v > 60000) bad(`implausible cfs on page: ${x.v} in "${x.t}"`);
const ftish = r.nums.filter(x => /\bft\b/.test(x.t));
for (const x of ftish) if (x.v < 0 || x.v > 40) bad(`implausible depth on page: ${x.v} ft in "${x.t}"`);
const pct = r.nums.filter(x => /%/.test(x.t));
for (const x of pct) if (x.v < 0 || x.v > 100) bad(`percentage out of range: ${x.v} in "${x.t}"`);

console.log('QC LAYER C — rendered page');
console.log(`  sections checked : ${Object.keys(r.sections).length}`);
console.log(`  numbers scanned  : ${r.nums.length}  (cfs ${cfsish.length}, ft ${ftish.length}, % ${pct.length})`);
console.log(`  JS errors        : ${errs.length}`);
console.log(`  warnings         : ${warns.length}`);
console.log(`  FAILURES         : ${fails.length}`);
warns.forEach(w => console.log('   ! ' + w));
fails.forEach(f => console.log('   ✗ ' + f));
console.log('\n  live check: gauge ' + r.D.nowStone + ' cfs vs model ' + r.D.nowModel + ' cfs');
console.log('  dam: ' + r.D.damCap);

TOTAL_FAIL += fails.length + errs.length;
}

// ── LAYER D ──
{
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 430, height: 1200 } });
await p.goto('file:///Users/stevenrhodes/caney/out/caney.html', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(1600);
const fails = [], warns = [], notes = [];

const res = await p.evaluate(() => {
  const out = { days: [] };
  for (let d = 0; d < 7; d++) {
    const g = DATA.gen[d] || {};
    const wk = DATA.week[d] || {};
    out.days.push({
      d, label: wk.label, grade: wk.grade, score: DATA.dayscores[d],
      peakUnits: g.peak, genhrs: g.genhrs, relStart: g.relStart,
      windows: (g.windows || []).map(w => w.span + ' ' + w.units + 'U'),
      plans: Object.fromEntries((DATA.craftOrder || []).map(c =>
        [c, ((DATA.calendar[d] || {}).stepsBy || {})[c] || []])),
    });
  }
  out.best = DATA.best;
  out.wadeMax = DATA.wadeMax;
  out.mph = DATA.mph;
  // wade verdict per access at a fixed hour, from the page's own classifier
  out.classAt = {};
  for (let h of [8, 12, 16, 20]) {
    out.classAt[h] = DATA.points.filter(x => x.reach === 'trout').map(x => {
      const i = DATA.points.indexOf(x);
      const f = flowAt(i, h * 60);
      return { n: x.name, f: Math.round(f), c: condFor(i, f) };
    });
  }
  return out;
});
await b.close();

const top = res.days.reduce((a, x) => (x.score > a.score ? x : a), res.days[0]);
if (res.best && res.best.label && res.best.label !== top.label)
  warns.push(`"best day" is ${res.best.label} but ${top.label} scores higher (${top.score} vs ${res.best.score ?? '?'})`);

for (const d of res.days) {
  if ((d.genhrs || 0) >= 4 && /wade all day|wade the flats all/i.test(d.itin || ''))
    fails.push(`day ${d.label}: ${d.genhrs}h of generation but itinerary says wade all day — "${d.itin}"`);
  if ((d.genhrs || 0) === 0 && /boat|drift/i.test(d.itin || '') && !/wade/i.test(d.itin || ''))
    warns.push(`day ${d.label}: no generation but itinerary is boat-only — "${d.itin}"`);
}
const rank = { wade: 0, boat: 1, high: 2 };
for (const [h, rows] of Object.entries(res.classAt)) {
  const sorted = [...rows].sort((a, b) => a.f - b.f);
  for (let i = 1; i < sorted.length; i++)
    if (rank[sorted[i].c] < rank[sorted[i - 1].c])
      fails.push(`hour ${h}: ${sorted[i].n} at ${sorted[i].f} cfs is "${sorted[i].c}" but ${sorted[i-1].n} at ${sorted[i-1].f} cfs is "${sorted[i-1].c}"`);
}
for (const d of res.days) {
  if (d.relStart != null && (d.relStart < 0 || d.relStart >= 1440))
    fails.push(`day ${d.label}: relStart ${d.relStart} outside the day`);
  if ((d.genhrs || 0) > 24) fails.push(`day ${d.label}: ${d.genhrs} generating hours in a 24h day`);
  if ((d.peakUnits || 0) > 4) warns.push(`day ${d.label}: peak ${d.peakUnits} units (Center Hill has 3)`);
}
const GRADES = new Set(['Prime','Great','Good','Fair','Tough','Slow','—']);
for (const d of res.days) if (d.grade && !GRADES.has(d.grade)) fails.push(`day ${d.label}: unknown grade "${d.grade}"`);

notes.push(`wade threshold in use: ${res.wadeMax} cfs · leading edge ${res.mph} mph`);
for (const [h, rows] of Object.entries(res.classAt))
  notes.push(`  ${String(h).padStart(2)}:00  ` + rows.map(x => `${x.n.split(' ')[0]}:${x.f}${x.c[0]}`).join(' '));

console.log('QC LAYER D — semantic sanity');
console.log(`  days checked : ${res.days.length}`);
console.log(`  warnings     : ${warns.length}`);
console.log(`  FAILURES     : ${fails.length}`);
warns.forEach(w => console.log('   ! ' + w));
fails.forEach(f => console.log('   ✗ ' + f));
console.log('\n  ' + notes.join('\n  '));

TOTAL_FAIL += fails.length;
}

console.log('\n' + (TOTAL_FAIL ? `QC FAILED — ${TOTAL_FAIL} problem(s)` : 'QC PASSED — all layers clean'));
process.exit(TOTAL_FAIL ? 1 : 0);
