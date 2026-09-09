/**
 * The app shell: state, persistence, events, offline. §4-§7, §40, §42.
 *
 * Everything the user picks is persisted locally so 5:30am tomorrow starts where 5:30am
 * today left off. Nothing is sent anywhere; this is localStorage on the device.
 */
import { ago, dayLabel, esc, hm, whenLabel } from "./format.js";
import * as M from "./model.js";
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
    ["now", "Right now"], ["next3", "Next 3 hours"], ["morning", "This morning"],
    ["afternoon", "This afternoon"], ["evening", "This evening"],
    ["tmorning", "Tomorrow morning"], ["tafternoon", "Tomorrow afternoon"],
    ["custom", "Custom"],
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
  const month = new Date(start * 1000).getMonth() + 1;
  const { ranked, rejected, daysOut } = M.rank(d, state.species, state.craft, start, end,
                                               month, now);
  const out = $("#result");
  out.setAttribute("aria-busy", "false");

  if (!ranked.length) {
    out.innerHTML = `<div class="card"><h2 style="margin-top:0">Nothing fits</h2>
      <p class="small">Nothing is eligible for
      ${esc(d.species[state.species].display.full.toLowerCase())} on a
      ${esc((d.craft.find((c) => c.key === state.craft) || {}).label)} in this window.</p>
      <div style="margin-top:10px">${rejected.slice(0, 8).map((r) =>
        `<div class="alt out"><div class="h"><div class="nm">${esc(r.name)}</div></div>
         <div class="why">${esc(r.reason)}</div></div>`).join("")}</div></div>`;
    state.ctx = null;
    $("#startplan").hidden = true;
    return;
  }

  const best = ranked[0];
  best.statics = d.statics[best.zone + "|" + state.species] || {};
  const [verdict, why] = M.verdict(best, d);
  const steps = TL.build(d, best, state.species, state.craft);
  const alternatives = ranked.slice(1, 4).map((c) => altOf(c, best))
    .concat(rejected.slice(0, 3).map((r) =>
      ({ name: r.name, reason: r.reason, eliminated: true })));

  state.ctx = {
    cand: best, species: state.species, craft: state.craft, steps, alternatives,
    verdict, verdictWhy: why, start, end,
    limitations: limitationsOf(best, d, daysOut),
  };
  UI.renderPlan(out, d, state.ctx);
  wirePlan();
  $("#startplan").hidden = false;
  history.replaceState(null, "", "#" + [state.species, state.craft, state.preset].join("/"));
  announce(`Plan ready. ${verdict}. ${best.name}, ${hm(best.window.start)} to ${hm(best.window.end)}.`);
}

function altOf(c, best) {
  const bl = Object.fromEntries(best.lines.map((l) => [l.key, l]));
  let why = "";
  if (c.score > best.score) {
    why = "Scored " + c.score.toFixed(1) + " to the winner's " + best.score.toFixed(1) +
          ", but on " + Math.round(c.confidence) + "-point confidence against " +
          Math.round(best.confidence) + " — too much of it is unmeasured to send you there.";
  } else {
    const gaps = c.lines.map((l) => ({ l, gap: (bl[l.key] ? bl[l.key].earned : 0) - l.earned }))
      .filter((g) => g.gap > 0).sort((a, b) => b.gap - a.gap);
    why = gaps.length
      ? c.name + " would move above the winner if this improved: " + gaps[0].l.why
      : "Scored lower across the board.";
  }
  return { name: c.name, score: c.score, confidence: c.confidence, why,
           detail_page: c.z.detail_page, eliminated: false };
}

function limitationsOf(cand, d, daysOut) {
  const out = cand.lines.filter((l) => !l.known)
    .map((l) => l.label + " is unknown: " + l.why.split(" (unknown")[0]);
  if (daysOut >= 3) {
    out.push("This request is " + daysOut + " days out. Beyond about 48 hours the release " +
             "schedule and the hourly weather are seasonal expectation, not forecast.");
  }
  const z = cand.z;
  if (["reported", "unknown"].includes(z.modelConfidence)) {
    out.push("The routing model for this water is " + z.modelConfidence +
             ", not measured. Arrival timing is an estimate.");
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
        state.data.species[state.ctx.species], state.ctx.cand) };
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
  el.innerHTML = UI.renderTrips(TRIP.load(), TRIP.OUTCOME_FIELDS);
  $$("#triplist .tripform").forEach((f) => f.addEventListener("submit", (e) => {
    e.preventDefault();
    const id = f.getAttribute("data-trip");
    const out = {};
    for (const el2 of f.elements) {
      if (!el2.name || el2.value === "") continue;
      if (el2.name === "fished") out.fished = el2.value === "1";
      else if (el2.name === "actual_arrival") out.actual_arrival = timeToEpoch(el2.value, id);
      else if (el2.type === "number") out[el2.name] = Number(el2.value);
      else out[el2.name] = el2.value;
    }
    TRIP.record(id, out);
    refreshTrips();
    announce("Outcome recorded. The scoreboard updates with it.");
  }));
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
    const ics = TL.icsFor(state.ctx.steps, state.ctx.cand.name);
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
export { state, altOf };
