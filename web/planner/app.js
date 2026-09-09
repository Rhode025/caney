/**
 * The app shell: state, persistence, events, offline. §4-§7, §40, §42.
 *
 * Everything the user picks is persisted locally so 5:30am tomorrow starts where 5:30am
 * today left off. Nothing is sent anywhere; this is localStorage on the device.
 */
import { ago, countdown, dayLabel, esc, hm, whenLabel } from "./format.js";
import * as M from "./model.js";
import * as SEG from "./segments.js";
import * as TL from "./timeline.js";
import * as UI from "./ui.js";
import * as TRIP from "./trip.js";

const KEY = "caney.planner.v2";
const DATA_URL = "plan/data.json";

const state = {
  data: null, species: null, craft: "any", preset: "now",
  custom: { date: "", start: "06:30", end: "10:00" },
  ctx: null, onwater: false, offline: false, loadedAt: null,
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

// ── time presets (§5) ──────────────────────────────────────────────────────
export function windowFor(preset, custom, now = Date.now() / 1000) {
  const d = new Date(now * 1000);
  const at = (dayOffset, h, m = 0) => {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate() + dayOffset, h, m, 0, 0);
    return x.getTime() / 1000;
  };
  const round30 = (t) => Math.floor(t / 1800) * 1800;
  switch (preset) {
    case "now":       return [round30(now), round30(now) + 3 * 3600];
    case "next3":     return [round30(now), round30(now) + 3 * 3600];
    // First light, which is the window half this product exists to find. Today's if it
    // has not gone yet, otherwise tomorrow's — "dawn" that has already happened is not a
    // fishing window, it is a regret.
    case "dawn":      return now < at(0, 8) ? [Math.max(round30(now), at(0, 5)), at(0, 9)]
                                            : [at(1, 5), at(1, 9)];
    case "morning":   return now < at(0, 11) ? [Math.max(round30(now), at(0, 6)), at(0, 11)]
                                             : [at(1, 6), at(1, 11)];
    case "afternoon": return now < at(0, 18) ? [Math.max(round30(now), at(0, 13)), at(0, 18)]
                                             : [at(1, 13), at(1, 18)];
    case "evening":   return now < at(0, 21) ? [Math.max(round30(now), at(0, 16)), at(0, 21)]
                                             : [at(1, 16), at(1, 21)];
    case "tmorning":  return [at(1, 6), at(1, 11)];
    case "tafternoon":return [at(1, 13), at(1, 18)];
    case "custom": {
      const [y, mo, da] = (custom.date || isoToday(d)).split("-").map(Number);
      const [h0, m0] = (custom.start || "06:30").split(":").map(Number);
      const [h1, m1] = (custom.end || "10:00").split(":").map(Number);
      let a = new Date(y, mo - 1, da, h0, m0).getTime() / 1000;
      let b = new Date(y, mo - 1, da, h1, m1).getTime() / 1000;
      if (b <= a) b = a + 3600;
      return [a, b];
    }
    default: return [round30(now), round30(now) + 3 * 3600];
  }
}

function isoToday(d) {
  const p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

// ── persistence ────────────────────────────────────────────────────────────
function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify({
      species: state.species, craft: state.craft, preset: state.preset,
      custom: state.custom,
    }));
  } catch (e) { /* private mode — a preference is not worth an error */ }
}

function load() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "{}");
    if (v.species) state.species = v.species;
    if (v.craft) state.craft = v.craft;
    if (v.preset) state.preset = v.preset;
    if (v.custom) state.custom = Object.assign(state.custom, v.custom);
  } catch (e) { /* ignore */ }
}

// ── data ───────────────────────────────────────────────────────────────────
async function fetchData() {
  try {
    const r = await fetch(DATA_URL, { cache: "no-cache" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    try { localStorage.setItem(KEY + ".data", JSON.stringify({ at: Date.now() / 1000, d })); }
    catch (e) { /* dataset can exceed the quota; the service worker is the real cache */ }
    state.offline = false;
    return d;
  } catch (e) {
    // §42: offline must never imply the data is current.
    try {
      const c = JSON.parse(localStorage.getItem(KEY + ".data") || "null");
      if (c) { state.offline = true; state.loadedAt = c.at; return c.d; }
    } catch (e2) { /* ignore */ }
    return null;
  }
}

// ── rendering the picker ───────────────────────────────────────────────────
function renderPicker() {
  const d = state.data;
  const sp = $("#species");
  sp.innerHTML = Object.values(d.species).map((s) => `
    <button class="sp-card" type="button" data-species="${esc(s.key)}"
            aria-pressed="${state.species === s.key}">
      <div class="em" aria-hidden="true">${esc(s.display.emoji)}</div>
      <div><div class="nm">${esc(s.display.label.toUpperCase())}</div>
      <div class="sub">${esc(s.display.full)}</div></div>
    </button>`).join("");

  const presets = [
    ["now", "Right now"], ["next3", "Next 3 hours"], ["dawn", "Dawn"],
    ["morning", "This morning"], ["afternoon", "This afternoon"],
    ["evening", "This evening"], ["tmorning", "Tomorrow morning"],
    ["tafternoon", "Tomorrow afternoon"], ["custom", "Custom"],
  ];
  $("#times").innerHTML = presets.map(([k, l]) =>
    `<button class="chip" type="button" data-preset="${esc(k)}"
             aria-pressed="${state.preset === k}">${esc(l)}</button>`).join("");

  $("#crafts").innerHTML = d.craft.map((c) =>
    `<button class="chip" type="button" data-craft="${esc(c.key)}"
             aria-pressed="${state.craft === c.key}">${esc(c.label)}</button>`).join("");

  const cu = $("#custom");
  cu.classList.toggle("on", state.preset === "custom");
  $("#c-date").value = state.custom.date || isoToday(new Date());
  $("#c-start").value = state.custom.start;
  $("#c-end").value = state.custom.end;

  const [a, b] = windowFor(state.preset, state.custom);
  $("#windowecho").textContent = whenLabel(a, b);
  // The label never changes — it is the product's one action (§7). Only the enabled
  // state and the hint below it move, so the button a user is aiming at stays put.
  $("#go").disabled = !state.species;
  $("#gohint").textContent = state.species
    ? "One tap. Ranked candidates, the winner's exact plan, and the evidence behind it."
    : "Pick a species to enable this.";
}

// ── running the planner ────────────────────────────────────────────────────
function run() {
  const d = state.data;
  const now = Date.now() / 1000;
  const [start, end] = windowFor(state.preset, state.custom, now);
  const out = $("#result");
  out.setAttribute("aria-busy", "false");

  const p = M.planFor(d, state.species, state.craft, start, end, now);

  if (!p.itinerary) {
    out.innerHTML = `<div class="card"><h2 style="margin-top:0">Nothing fits</h2>
      <p class="small">Nothing is eligible for
      ${esc(d.species[state.species].display.full.toLowerCase())} on a
      ${esc((d.craft.find((c) => c.key === state.craft) || {}).label)} in this window.</p>
      <div style="margin-top:10px">${p.rejected.slice(0, 8).map((r) =>
        `<div class="alt out"><div class="h"><div class="nm">${esc(r.name)}</div></div>
         <div class="why">${esc(r.reason)}</div></div>`).join("")}</div></div>`;
    state.ctx = null;
    $("#startplan").hidden = true;
    return;
  }

  p.requestedEnd = end;
  const segments = SEG.build(d, p, state.species, state.craft, now);
  const [verdict, why] = M.verdict(p.opportunity, p.confidence,
                                   p.primary ? p.primary.lines : [], d);

  state.ctx = {
    plan: p, itinerary: p.itinerary, segments,
    species: state.species, craft: state.craft,
    primary: p.primary, verdict, verdictWhy: why,
    start, end,
    whyThisWon: whyThisWon(d, p),
    backupPlan: backupPlan(d, p),
    alternatives: alternatives(d, p),
    limitations: limitationsOf(d, p),
    createdAt: now,
    // §50 — frozen at plan time so a later recheck can diff against what we actually
    // predicted, not against a re-derivation of it.
    frozenClaims: d.safety.filter((c) => p.zoneSequence.includes(c.zone_id))
      .map((c) => ({ zone_id: c.zone_id, kind: c.kind, at: c.at, text: c.text })),
    datasetBuilt: d.built,
    versions: d.versions,
  };
  UI.renderPlan(out, d, state.ctx);
  wirePlan();
  $("#startplan").hidden = false;
  history.replaceState(null, "", "#" + [state.species, state.craft, state.preset].join("/"));
  announce(`Plan ready. ${verdict}. ` +
    p.zoneSequence.map((z) => d.zones[z].name).join(", then ") +
    `, ${hm(p.itinerary.windows[0].start)} to ` +
    `${hm(p.itinerary.windows[p.itinerary.windows.length - 1].end)}.`);
}

/** §67 — the short, concrete explanation. Mirrors engine._why_this_won. */
function whyThisWon(d, p) {
  const out = [];
  const w0 = p.itinerary.windows[0];
  out.push(`Best ${Math.round(w0.duration_minutes)}-minute stretch of any candidate: ` +
           `peaks at ${Math.round(w0.peak_score)}, floor ${Math.round(w0.floor_score)}.`);
  for (const l of (p.primary ? p.primary.lines : []).slice()
        .sort((a, b) => (b.earned / Math.max(1, b.possible)) - (a.earned / Math.max(1, a.possible)))
        .slice(0, 3)) {
    if (l.earned >= l.possible * 0.75) out.push(`${l.label}: ${l.why}`);
  }
  if (p.itinerary.windows.length > 1) {
    const nxt = p.itinerary.windows[1];
    out.push(`A ${Math.round(p.itinerary.parts.travelMinutes || 0)}-minute move extends the ` +
             `bite another ${Math.round(nxt.duration_minutes)} minutes at ` +
             `${d.zones[nxt.zone_id].name}.`);
  }
  const lc = d.zones[w0.zone_id].location_confidence || {};
  const rows = lc.rows || [];
  if (rows.length >= 2) {
    out.push(`Location confidence ${Math.round(lc.score)}: the access is ` +
             `${rows[0].level_label.toLowerCase()}, the reach is ` +
             `${rows[1].level_label.toLowerCase()}.`);
  }
  return out.slice(0, 6);
}

/** §39 — mirrors engine._backup_plan. */
function backupPlan(d, p) {
  const used = new Set(p.zoneSequence);
  const fallback = p.candidates.find((c) => !used.has(c.zone));
  const z0 = d.zones[p.zoneSequence[0]];
  const branches = [];
  if (z0.tailwater) {
    if (p.itinerary.windows.length > 1) {
      const nxt = d.zones[p.itinerary.windows[1].zone_id];
      branches.push({ if: "generation is cancelled, or ends before you get on the water",
        then: `Skip ${z0.name} entirely and run straight to ${nxt.name} — without current ` +
              `the first zone is the weakest water in the plan, not the strongest.` });
    } else if (fallback) {
      branches.push({ if: "generation is cancelled",
        then: `${z0.name} is current-driven — without the release it is the weakest water ` +
              `in the plan. Fish ${fallback.name} instead.` });
    }
  }
  if (fallback) {
    branches.push({ if: "the primary zone is blown out, crowded, or simply dead after an hour",
      then: `${fallback.name} is the next-best water for this species in your window` +
            (fallback.z.drive ? ` (${fallback.z.drive})` : "") + "." });
  }
  branches.push({ if: "weather turns unsafe — lightning, or wind you cannot fish",
    then: "Abort. Nothing in this plan is worth a thunderstorm on open water." });
  return { branches, fallback_zone: fallback ? fallback.zone : null };
}

/** §38 — runner-up itineraries, and the eliminated candidates. */
function alternatives(d, p) {
  const out = [];
  const seen = new Set([p.zoneSequence.join(">")]);
  for (const c of p.runners || []) {
    const zones = [];
    for (const w of c.windows) if (!zones.length || zones[zones.length - 1] !== w.zone_id) zones.push(w.zone_id);
    const key = zones.join(">");
    if (seen.has(key)) continue;
    seen.add(key);
    const gap = p.itinerary.utility - c.utility;
    const cPeak = Math.max(...c.windows.map((w) => w.peak_score));
    const wPeak = Math.max(...p.itinerary.windows.map((w) => w.peak_score));
    const cConf = Math.min(...c.windows.map((w) => w.confidence));
    const wConf = Math.min(...p.itinerary.windows.map((w) => w.confidence));
    const cLoc = Math.min(...c.windows.map((w) => w.location_confidence));
    const wLoc = Math.min(...p.itinerary.windows.map((w) => w.location_confidence));
    let why;
    if (c.windows.length < p.itinerary.windows.length) {
      why = `Staying put scores ${c.utility.toFixed(1)} against the winner's ` +
            `${p.itinerary.utility.toFixed(1)} — the move is worth more than the simplicity.`;
    } else if (cPeak > wPeak && (cConf < wConf || cLoc < wLoc)) {
      const bits = [];
      if (cConf < wConf - 1) bits.push(`forecast confidence ${Math.round(cConf)} against ${Math.round(wConf)}`);
      if (cLoc < wLoc - 0.01) bits.push(`location confidence ${Math.round(cLoc * 100)} against ${Math.round(wLoc * 100)}`);
      why = `Peaks higher (${Math.round(cPeak)} against ${Math.round(wPeak)}) and still lost ` +
            `by ${gap.toFixed(1)}: ${bits.join(" and ")}.`;
    } else {
      why = `${gap.toFixed(1)} points behind on itinerary utility.`;
    }
    out.push({
      zone_id: zones[0], name: zones.map((z) => d.zones[z].name).join(" → "),
      score: c.parts.quality || 0, utility: c.utility,
      confidence: cConf, why, detail_page: d.zones[zones[0]].detail_page,
      eliminated: false,
    });
    if (out.length >= 4) break;
  }
  for (const r of (p.rejected || []).slice(0, 3)) {
    out.push({ name: r.name, reason: r.reason, eliminated: true });
  }
  return out;
}

function limitationsOf(d, p) {
  const out = (p.primary ? p.primary.lines : []).filter((l) => !l.known)
    .map((l) => l.label + " is unknown: " + l.why.split(" (unknown")[0]);
  // §5 — a session shorter than the species minimum is still offered, because the reader
  // asked, but it must say what it is: a short session, not a plan.
  const minMin = (d.utility.minDuration || {})[p.itinerary.windows[0].species] ||
                 d.utility.defaultMinDuration;
  const fished = p.itinerary.parts.fishingMinutes || 0;
  if (fished < minMin) {
    out.push(`You have ${Math.round(fished)} minutes. The practical minimum for this ` +
             `species is about ${minMin} — this is a short session, not a plan, and the ` +
             `score is penalised accordingly.`);
  }
  const lc = Math.min(...p.itinerary.windows.map((w) => w.location_confidence));
  if (lc < 0.66) {
    out.push(`Location confidence is ${Math.round(lc * 100)}/100. The species and habitat ` +
             `evidence supports this reach, but the exact holding water has not been field ` +
             `verified — read the water yourself rather than trusting a pin.`);
  }
  if (p.daysOut >= 3) {
    out.push("This request is " + p.daysOut + " days out. Beyond about 48 hours the release " +
             "schedule and the hourly weather are seasonal expectation, not forecast.");
  }
  const z = d.zones[p.zoneSequence[0]];
  if (["reported", "unknown"].includes(z.modelConfidence)) {
    out.push("The routing model for this water is " + z.modelConfidence +
             ", not measured. Arrival timing is an estimate.");
  }
  for (const t of (p.itinerary.transitions || [])) {
    if (t.provenance === "estimated") {
      out.push(`The ${Math.round(t.minutes)}-minute move is an estimate from straight-line ` +
               `distance, not a verified route.`);
    }
  }
  if ((z.errors || []).length) out.push("Upstream problems during this build: " + z.errors.join("; "));
  if (state.offline) {
    out.push("You are offline. This plan was built from a cached snapshot loaded " +
             ago(state.loadedAt) + " — the water may have changed since.");
  }
  return out;
}

// ── events ─────────────────────────────────────────────────────────────────
function wirePlan() {
  $$("#result [data-strip]").forEach((b) => b.addEventListener("click", () => {
    const id = b.getAttribute("data-strip");
    const p = document.getElementById("strip-" + id);
    const open = b.getAttribute("aria-expanded") === "true";
    b.setAttribute("aria-expanded", String(!open));
    if (p) p.hidden = open;
  }));
  wireTrips();
  const map = $("#map");
  if (map) import("./map.js").then((m) => m.draw(map)).catch(() => {
    map.innerHTML = `<div class="spinner">Map unavailable offline.</div>`;
  });
}

function wireTrips() {
  const log = $("#logtrip");
  if (log) {
    log.addEventListener("click", () => {
      if (!state.ctx) return;
      const ctx = { ...state.ctx, technique: UI.pickTechnique(
        state.data.species[state.ctx.species], state.ctx) };
      TRIP.add(TRIP.snapshotPrediction(state.data, ctx));
      refreshTrips();
      announce("Prediction frozen. Fill in the outcome after you fish it.");
    });
  }
  const exp = $("#tripexport");
  if (exp) exp.addEventListener("click", () => {
    const blob = new Blob([TRIP.exportJson()], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "caney-trips.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  });
  const sbb = $("#tripscore");
  if (sbb) sbb.addEventListener("click", () => {
    $("#scoreboard").innerHTML = UI.renderScoreboard(TRIP.scoreboard());
  });
  refreshTrips();
}

function refreshTrips() {
  const el = $("#triplist");
  if (!el) return;
  el.innerHTML = UI.renderTrips(TRIP.load(), TRIP.QUICK_FIELDS, TRIP.OUTCOME_FIELDS,
                                TRIP.SEGMENT_FIELDS);
  $$("#triplist .tripform").forEach((f) => f.addEventListener("submit", (e) => {
    e.preventDefault();
    const id = f.getAttribute("data-trip");
    TRIP.record(id, readForm(f, id));
    refreshTrips();
    announce("Outcome recorded. The scoreboard updates with it.");
  }));
  $$("#triplist .segform").forEach((f) => f.addEventListener("submit", (e) => {
    e.preventDefault();
    const id = f.getAttribute("data-trip");
    TRIP.recordSegment(id, Number(f.getAttribute("data-seg")), readForm(f, id));
    refreshTrips();
    announce("Stretch recorded.");
  }));
}

function readForm(f, tripId) {
  const out = {};
  for (const el of f.elements) {
    if (!el.name || el.value === "") continue;
    if (el.type === "radio" && !el.checked) continue;
    if (el.name === "actual_arrival") out.actual_arrival = timeToEpoch(el.value, tripId);
    else if (el.type === "number") out[el.name] = Number(el.value);
    else out[el.name] = el.value;
  }
  return out;
}

/** "14:30" on the trip's own planned date, not on today. */
function timeToEpoch(hhmm, tripId) {
  const t = TRIP.load().find((x) => x.id === tripId);
  const base = t ? new Date(t.prediction.window.start * 1000) : new Date();
  const [h, m] = hhmm.split(":").map(Number);
  return new Date(base.getFullYear(), base.getMonth(), base.getDate(), h, m).getTime() / 1000;
}

function announce(msg) {
  const live = $("#live");
  if (live) live.textContent = msg;
}

function wire() {
  document.addEventListener("click", (e) => {
    const sp = e.target.closest("[data-species]");
    if (sp) {
      state.species = sp.getAttribute("data-species");
      save(); renderPicker();
      if (state.autoRun) run();
      return;
    }
    const pr = e.target.closest("[data-preset]");
    if (pr) { state.preset = pr.getAttribute("data-preset"); save(); renderPicker(); return; }
    const cr = e.target.closest("[data-craft]");
    if (cr) { state.craft = cr.getAttribute("data-craft"); save(); renderPicker(); return; }
  });

  $("#go").addEventListener("click", () => {
    state.autoRun = true;
    $("#result").setAttribute("aria-busy", "true");
    $("#result").innerHTML = `<div class="spinner">Working out your best plan…</div>`;
    setTimeout(run, 16);
  });

  ["c-date", "c-start", "c-end"].forEach((id) => {
    $("#" + id).addEventListener("change", (e) => {
      state.custom[id.slice(2) === "date" ? "date" : id.slice(2)] = e.target.value;
      save(); renderPicker();
    });
  });

  $("#startplan").addEventListener("click", () => setOnWater(true));

  $("#theme").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : cur === "light" ? "" : "dark";
    if (next) document.documentElement.setAttribute("data-theme", next);
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem("caney.theme", next); } catch (e) { /* ignore */ }
    $("#theme").textContent = next === "dark" ? "☾ Dark" : next === "light" ? "☀ Light" : "◐ Auto";
  });

  $("#ics").addEventListener("click", () => {
    if (!state.ctx) return;
    const ics = TL.icsFor(state.ctx.segments, state.data.zones[
      state.ctx.plan.zoneSequence[0]].name);
    const blob = new Blob([ics], { type: "text/calendar" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "caney-plan.ics";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  });
}

function setOnWater(on) {
  state.onwater = on;
  document.body.classList.toggle("onwater", on);
  if (on) {
    tickOnWater();
    state.owTimer = setInterval(tickOnWater, 30000);
  } else {
    clearInterval(state.owTimer);
  }
}

function tickOnWater() {
  if (!state.ctx) return setOnWater(false);
  UI.renderOnWater($("#onwater"), state.data, state.ctx, Date.now() / 1000);
  const b = $("#ow-exit");
  if (b) b.addEventListener("click", () => setOnWater(false), { once: true });
  const r = $("#ow-recheck");
  if (r) r.addEventListener("click", recheck, { once: true });
}

/**
 * §40, §41 — RECHECK PLAN.
 *
 * Re-fetches the dataset, re-runs the planner against the SAME request, and diffs the
 * result against the plan that was actually started. Only material changes are shown, and
 * the original is preserved untouched: the trip log needs what we predicted at plan time,
 * not what we would have predicted with hindsight (§50).
 */
async function recheck() {
  const original = state.ctx;
  if (!original) return;
  announce("Rechecking against live conditions…");
  const fresh = await fetchData();
  if (!fresh) {
    state.ctx = { ...original, delta: { changed: false, at: Date.now() / 1000,
      rows: [], advice: "Could not reach live data — nothing has been rechecked." } };
    return tickOnWater();
  }
  state.data = fresh;
  const now = Date.now() / 1000;
  const p = M.planFor(fresh, original.species, original.craft, original.start,
                      original.end, now);
  if (!p.itinerary) {
    state.ctx = { ...original, delta: { changed: true, at: now, rows: [], advice:
      "Nothing is eligible any more under current conditions. Get off the water and " +
      "re-plan." } };
    return tickOnWater();
  }
  p.requestedEnd = original.end;
  const rows = diff(fresh, original, p);
  const segments = SEG.build(fresh, p, original.species, original.craft, now);
  state.ctx = {
    ...original,
    // The delta view replaces the live half of the context; `original` stays frozen on
    // `originalPlan` so the trip log can still compare against it.
    plan: p, itinerary: p.itinerary, segments, primary: p.primary,
    originalPlan: original.originalPlan || original.plan,
    originalSegments: original.originalSegments || original.segments,
    delta: { changed: rows.length > 0, at: now, rows, advice: advice(fresh, original, p, rows) },
  };
  tickOnWater();
  announce(rows.length ? "Plan changed. " + rows[0].label + " moved." : "Plan unchanged.");
}

function diff(data, original, p) {
  const rows = [];
  const o = original.plan, n = p;
  const oz = o.zoneSequence.join(" → "), nz = n.zoneSequence.join(" → ");
  if (oz !== nz) {
    rows.push({ label: "Primary zone",
      was: o.zoneSequence.map((z) => data.zones[z].name).join(" → "),
      now: n.zoneSequence.map((z) => data.zones[z].name).join(" → "),
      detail: "The optimiser now prefers different water for the time you have left." });
  }
  const ow = o.itinerary.windows[0], nw = n.itinerary.windows[0];
  if (Math.abs(ow.start - nw.start) > 900 || Math.abs(ow.end - nw.end) > 900) {
    rows.push({ label: "Best window",
      was: hm(ow.start) + "–" + hm(o.itinerary.windows[o.itinerary.windows.length - 1].end),
      now: hm(nw.start) + "–" + hm(n.itinerary.windows[n.itinerary.windows.length - 1].end) });
  }
  for (const zid of new Set([...o.zoneSequence, ...n.zoneSequence])) {
    const kinds = ["generation_start", "generation_stop", "release_arrival"];
    for (const kind of kinds) {
      const was = (original.frozenClaims || []).find((c) => c.zone_id === zid && c.kind === kind);
      const nowC = data.safety.find((c) => c.zone_id === zid && c.kind === kind);
      if (was && nowC && was.at && nowC.at && Math.abs(was.at - nowC.at) > 900) {
        rows.push({ label: kind.replace(/_/g, " "),
          was: hm(was.at), now: hm(nowC.at),
          detail: nowC.text });
      } else if (was && !nowC) {
        rows.push({ label: kind.replace(/_/g, " "), was: hm(was.at), now: "no longer forecast",
          detail: "The release feed no longer shows this event." });
      }
    }
  }
  const oFly = (original.segments.find((s) => s.type === "fish" && s.technique) || {}).technique;
  const nFly = (state.ctxPendingFly || null) ||
    (SEG.build(data, p, original.species, original.craft, Date.now() / 1000)
      .find((s) => s.type === "fish" && s.technique) || {}).technique;
  if (oFly && nFly && oFly.primary_fly !== nFly.primary_fly) {
    rows.push({ label: "Fly", was: oFly.primary_fly, now: nFly.primary_fly,
      detail: nFly.why });
  }
  return rows;
}

function advice(data, original, p, rows) {
  if (!rows.length) return "Nothing material has changed. Keep fishing the plan.";
  const zoneRow = rows.find((r) => r.label === "Primary zone");
  if (zoneRow) {
    return "Move to " + p.zoneSequence.map((z) => data.zones[z].name).join(", then ") +
           " now — the water you planned for is no longer the best of what is left.";
  }
  const gen = rows.find((r) => /generation|release/.test(r.label));
  if (gen) {
    return "The release schedule moved. Re-read the safety step before you do anything " +
           "else: the exit time is computed from the EARLIEST arrival, and it has changed.";
  }
  return "Adjust as above. Everything else about the plan still stands.";
}

// ── boot ───────────────────────────────────────────────────────────────────
export async function boot() {
  try {
    const t = localStorage.getItem("caney.theme");
    if (t) document.documentElement.setAttribute("data-theme", t);
    $("#theme").textContent = t === "dark" ? "☾ Dark" : t === "light" ? "☀ Light" : "◐ Auto";
  } catch (e) { /* ignore */ }

  load();
  const d = await fetchData();
  if (!d) {
    $("#picker").innerHTML =
      `<div class="banner bad">Can't load the planner data and nothing is cached on this
       device. Everything below is unavailable — this is not "conditions are poor", it is
       "we have no conditions".</div>`;
    return;
  }
  state.data = d;
  if (!state.species) state.species = null;

  const age = Date.now() / 1000 - d.built;
  const banner = $("#banner");
  if (state.offline) {
    banner.className = "banner bad";
    banner.textContent = "OFFLINE — showing a cached snapshot from " + ago(d.built) +
      ". Do not treat any water number here as current.";
    banner.hidden = false;
  } else if (age > 3 * 3600) {
    banner.className = "banner warn";
    banner.textContent = "This build is " + ago(d.built) +
      ". The site rebuilds hourly; a gap this long means a build was skipped.";
    banner.hidden = false;
  }
  $("#built").textContent = "Data built " + ago(d.built) + " · " +
    (d.research.enabled ? "research on (" + d.research.provider + ")" : "research off");

  renderPicker();
  wire();

  const hash = (location.hash || "").slice(1).split("/");
  if (hash.length === 3 && d.species[hash[0]]) {
    state.species = hash[0]; state.craft = hash[1]; state.preset = hash[2];
    renderPicker(); state.autoRun = true; run();
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
  window.addEventListener("online", () => location.reload());
}

// exposed for tests
export { state, whyThisWon, backupPlan, alternatives };
