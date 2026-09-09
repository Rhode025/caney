#!/usr/bin/env node
/**
 * §73 — the JS bundle budget, enforced.
 *
 *     node tools/check_bundle.mjs [dir] [--budget 150]
 *
 * A budget nobody checks is a wish. This one is checked in CI and fails the build.
 *
 * 150 KB gzipped of first-load JS is not a performance nicety here: the app has to open
 * in a boat ramp parking lot on one bar, and every extra 50 KB is a real second of
 * somebody standing in the dark. It is also the number that keeps the "just add a map
 * library" conversation honest — Leaflet plus tiles is a third of the budget and a
 * network dependency, which is why web-v3/src/components/Map.tsx draws SVG instead.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join, extname } from "node:path";

const dir = process.argv[2] ?? "web-v3/dist";
const bi = process.argv.indexOf("--budget");
const BUDGET_KB = bi > -1 ? Number(process.argv[bi + 1]) : 150;

function walk(d) {
  const out = [];
  for (const name of readdirSync(d)) {
    const p = join(d, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

let files;
try {
  files = walk(dir);
} catch {
  console.error(`no build at ${dir} — run \`npm run build\` in web-v3 first`);
  process.exit(2);
}

const rows = [];
let jsGz = 0, cssGz = 0;
for (const f of files) {
  const raw = readFileSync(f);
  const gz = gzipSync(raw).length;
  const ext = extname(f);
  if (ext === ".js") jsGz += gz;
  if (ext === ".css") cssGz += gz;
  if (ext === ".js" || ext === ".css" || ext === ".html") {
    rows.push([f.replace(dir + "/", ""), raw.length, gz]);
  }
}

rows.sort((a, b) => b[2] - a[2]);
for (const [name, raw, gz] of rows) {
  console.log(`  ${name.padEnd(40)} ${String((raw / 1024).toFixed(1)).padStart(8)} KB  ` +
              `gzip ${String((gz / 1024).toFixed(1)).padStart(7)} KB`);
}
const kb = jsGz / 1024;
console.log("");
console.log(`  first-load JS  ${kb.toFixed(1)} KB gzipped   (budget ${BUDGET_KB} KB)`);
console.log(`  CSS            ${(cssGz / 1024).toFixed(1)} KB gzipped`);

if (kb > BUDGET_KB) {
  console.error(`\n  OVER BUDGET by ${(kb - BUDGET_KB).toFixed(1)} KB. §73.`);
  process.exit(1);
}
console.log(`  ${(BUDGET_KB - kb).toFixed(1)} KB of headroom.`);
