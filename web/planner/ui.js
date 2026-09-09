/**
 * Rendering. §8, §32, §33, §36, §37, §38, §40.
 *
 * Presentation only — no thresholds, no scoring, no time arithmetic beyond formatting.
 * Every string that could contain data goes through esc(); every href through safeUrl().
 */
import { ago, esc, hm, num, obs, safeUrl, whenLabel, countdown, dayLabel } from "./format.js";
import { confidenceLabel, evidenceFor } from "./model.js";
import * as TL from "./timeline.js";

const TIER_LABEL = {
  A: "Official instrument data", B: "Fisheries research / management",
  C: "Local field report (non-agency)", D: "Community report (unverified)",
};

// The dataset, stashed once so leaf renderers can read published constants without every
// helper taking a `data` parameter. Set on every renderPlan call.
const DATA_REF = { d: null };

export function renderPlan(root, data, ctx) {
  DATA_REF.d = data;

  // §69 — the order IS the argument. Verdict, then the day, then where, then how, then
  // why, and only then the dashboard. The 2.0 page put conditions before the plan and made
  // the reader do the interpreting; that is the job we are supposed to be doing for them.
  root.innerHTML =
    header(data, ctx) +
    availabilityStrip(ctx) +
    itineraryBlock(data, ctx) +
    whereBlock(data, ctx) +
    techniqueBlock(data, ctx) +
    whyThisWon(ctx) +
    backupBlock(ctx) +
    bestTime(data, ctx) +
    conditionsStrip(data, ctx) +
    safetyBlock(data, ctx) +
    scoreBreakdown(ctx) +
    researchStatus(data, ctx) +
    evidenceDrawer(data, ctx) +
    locationDrawer(data, ctx) +
    freshnessDrawer(ctx) +
    mapBlock(data, ctx) +
    alternativesBlock(ctx, data) +
    askBlock(ctx) +
    tripBlock(ctx) +
    limitations(ctx);
}

/** §65 — four numbers, none of which implies the others. */
function header(data, ctx) {
  const sp = data.species[ctx.species];
  const p = ctx.plan;
  const wins = p.itinerary.windows;
  const title = p.zoneSequence.map((z) => data.zones[z].name).join(" → ");
  return `<div class="card">
    <div class="eyebrow">${esc(sp.display.full)}</div>
    <div class="placehead">
      <div class="planlabel">BEST PLAN</div>
      <div class="when" data-clock>${esc(whenLabel(wins[0].start, wins[wins.length - 1].end))}</div>
      <div class="zone">${esc(title)}</div>
    </div>
    <div class="verdict" style="margin-top:14px">
      <div class="badge ${esc(ctx.verdict)}">${esc(ctx.verdict)}</div>
    </div>
    <div class="scores">
      ${scoreCell("Opportunity", p.opportunity, "How good the fishing looks in this window.")}
      ${scoreCell("Forecast conf.", p.confidence, "How much of it we actually measured.")}
      ${scoreCell("Location conf.", p.locationConfidence, "How well we know WHERE.", "loc")}
      ${scoreCell("Research", p.researchConfidence, "How well sourced the biology is.")}
    </div>
    <p class="small" style="margin:12px 0 0">${esc(ctx.verdictWhy)}</p>
  </div>`;
}

function scoreCell(label, value, help, id) {
  const v = value === null || value === undefined ? "—" : Math.round(value);
  return `<div class="scorecell" title="${esc(help)}"${id ? ` data-score="${esc(id)}"` : ""}>
    <div class="n">${esc(String(v))}</div>
    <div class="l">${esc(label)}</div></div>`;
}

/** §8, §68 — availability is a constraint, not an instruction. */
function availabilityStrip(ctx) {
  const p = ctx.plan;
  const wins = p.itinerary.windows;
  const fishing = Math.round(p.itinerary.parts.fishingMinutes || 0);
  const avail = Math.round((ctx.end - ctx.start) / 60);
  return `<div class="availbar">
    <div class="ab"><div class="l">You can fish</div>
      <div class="v" data-clock>${esc(hm(ctx.start))} – ${esc(hm(ctx.end))}</div></div>
    <div class="arrow" aria-hidden="true">→</div>
    <div class="ab"><div class="l">Best fishing</div>
      <div class="v hi" data-clock>${esc(hm(wins[0].start))} – ${esc(hm(wins[wins.length - 1].end))}</div></div>
    <div class="note">${fishing} of your ${avail} minutes are worth fishing${
      wins.length > 1 ? `, across ${wins.length} zones` : ""}.</div>
  </div>`;
}

/** §66 — the itinerary IS the product. It comes before the dashboard. */
function itineraryBlock(data, ctx) {
  return `<h2>Your ${partOfDay(ctx.start)}</h2><div class="card"><ol class="steps">` +
    ctx.segments.map((s) => {
      const cls = s.type === "safety_exit" ? "safety"
        : s.type === "fish" ? "fish" : s.type === "move" ? "move" : "";
      const range = s.end > s.start + 60 ? `${hm(s.start)}–${hm(s.end)}` : hm(s.start);
      const trig = (s.triggers || []).filter((t) => t.then).slice(0, 3);
      return `<li class="${cls}">
        <div class="t">${esc(range)}</div>
        <div>
          <div class="ttl">${esc(s.instructions)}
            <span class="kind ${esc(s.kind || "heuristic")}">${esc(String(s.type).replace(/_/g, " "))}</span></div>
          ${s.reason ? `<div class="dt">${esc(s.reason)}</div>` : ""}
          ${s.expected_score !== null && s.expected_score !== undefined
            ? `<div class="unc">expected ${Math.round(s.expected_score)} / 100 across this stretch</div>` : ""}
          ${s.technique ? techniqueLine(s.technique) : ""}
          ${trig.length ? trig.map((t) =>
            `<div class="branch"><b>If ${esc(t.if)}:</b> ${esc(t.then)}</div>`).join("") : ""}
        </div></li>`;
    }).join("") + `</ol>
  <p class="tiny" style="margin-top:12px">Times come from the release feed, the sun and the
  hourly forecast. Steps tagged <b>safety exit</b> use the conservative bound, never the
  typical one.</p></div>`;
}

function techniqueLine(t) {
  return `<div class="segtech"><b>${esc(t.primary_fly)}</b> ${esc(t.primary_size)} ·
    ${esc(t.primary_color)} · ${esc(t.line)}
    <span class="tiny">${esc(t.presentation)}, ${esc(t.depth)}</span></div>`;
}

function partOfDay(start) {
  const h = new Date(start * 1000).getHours();
  if (h < 11) return "morning";
  if (h < 16) return "afternoon";
  if (h < 21) return "evening";
  return "session";
}

/** §30, §72 — WHERE, in language graded to how well we know it. */
function whereBlock(data, ctx) {
  const zone = data.zones[ctx.plan.zoneSequence[0]];
  const launch = ctx.segments.find((s) => s.type === "launch");
  const lc = zone.location_confidence || {};
  return `<h2>Where</h2><div class="card"><div class="instr">
    ${row("Launch", launch
      ? `<b>${esc(String(launch.instructions).replace(/^Launch at /, ""))}</b>` +
        (launch.reason ? `<br><span class="small">${esc(launch.reason)}</span>` : "")
      : `<span class="state-unknown">no verified access for this craft</span>`)}
    ${row("Water", `<b>${esc(zone.name)}</b> · ${esc(zone.kind_label || "")}` +
      (zone.drive ? ` <span class="small">${esc(zone.drive)}</span>` : ""))}
    ${row("Fish", esc((zone.holds_phrase || {})[ctx.species] || ""))}
    ${row("Confidence", `<b>${Math.round(lc.score || 0)}/100</b> —
      <span class="small">${esc((lc.rows || []).map((r) => r.label.toLowerCase() + ": " +
        r.level_label.toLowerCase()).join(" · "))}</span>`)}
  </div></div>`;
}

function techniqueBlock(data, ctx) {
  const first = ctx.segments.find((s) => s.type === "fish" && s.technique);
  if (!first) return "";
  const t = first.technique;
  const b = t.backup_presentation || {};
  return `<h2>Tie this on</h2><div class="card"><div class="instr">
    ${row("Primary", `<b>${esc(t.primary_fly)}</b> ${esc(t.primary_size)} · ${esc(t.primary_color)}`)}
    ${row("Line", esc(t.line))}
    ${row("Leader", esc(t.leader))}
    ${row("Present", esc(t.presentation))}
    ${row("Depth", esc(t.depth))}
    ${row("Retrieve", esc(t.retrieve))}
    ${row("Backup", `${esc(b.fly || t.backup_fly)} ${esc(b.size || t.backup_size)}` +
      (b.line ? ` · ${esc(b.line)}` : ""))}
    ${row("Switch when", `<span class="small">${esc(t.switch_trigger || "")}</span>`)}
    ${row("Why", `<span class="small">${esc(t.why)}</span>`)}
  </div></div>`;
}

/** §67 — a concise explanation, before the deep evidence drawer. */
function whyThisWon(ctx) {
  if (!ctx.whyThisWon || !ctx.whyThisWon.length) return "";
  return `<h2>Why this won</h2><div class="card flat"><ul class="whylist">` +
    ctx.whyThisWon.map((w) => `<li>${esc(w)}</li>`).join("") + `</ul></div>`;
}

/** §39 */
function backupBlock(ctx) {
  const b = ctx.backupPlan;
  if (!b || !(b.branches || []).length) return "";
  return `<h2>If it falls apart</h2><div class="card flat">` +
    b.branches.map((x) =>
      `<div class="branch"><b>If ${esc(x.if)}:</b> ${esc(x.then)}</div>`).join("") + `</div>`;
}

function row(k, v) {
  return `<div class="row"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;
}

/** §36, §70 — glanceable conditions, AFTER the decision (§69). */
function conditionsStrip(data, ctx) {
  const zone = data.zones[ctx.plan.zoneSequence[0]];
  const w = zone.water || {};
  const wins = ctx.plan.itinerary.windows;
  const start = wins[0].start, end = wins[wins.length - 1].end;
  const hours = (data.weatherHours[zone.river] || [])
    .filter((h) => h.epoch >= start && h.epoch <= end);
  const mean = (k) => {
    const v = hours.map((h) => h[k]).filter((x) => x !== null && x !== undefined);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };
  const sun = data.sun[zone.river + "|" + isoDate(start)] || {};
  const moon = data.lunar[zone.river + "|" + isoDate(start)] || {};
  const flow = obs(w.flow);
  const gen = (w.generation_on || {}).state === "known"
    ? (w.generation_on.value ? "generation ON" : "generation off")
    : "generation unknown";
  const wind = mean("wind_speed"), cloud = mean("cloud_cover"), temp = mean("air_temperature");
  const dir = (hours[Math.floor(hours.length / 2)] || {}).wind_dir_label || "";
  const maj = (moon.major_windows || [])[0];

  const cell = (id, lbl, big, sub, detail) =>
    `<button class="cell" type="button" data-strip="${esc(id)}" aria-expanded="false">
       <div class="lbl">${esc(lbl)}</div>
       <div class="big${big === "unknown" ? " state-unknown" : ""}">${esc(big)}</div>
       <div class="sub">${esc(sub)}</div>
     </button><div class="tiny" id="strip-${esc(id)}" hidden
          style="grid-column:1/-1;padding:2px 4px 8px">${detail}</div>`;

  return `<h2>Conditions</h2><div class="strip">` +
    cell("water", "Water", flow.text,
         gen + ((w.flow_trend || {}).state === "known" ? " · " + w.flow_trend.value : ""),
         `${esc((w.flow || {}).source || "—")} · ${esc((w.flow || {}).age || "unknown")}. ` +
         `Release: ${esc((w.generation || {}).source || "—")} · ${esc((w.generation || {}).age || "unknown")}.` +
         (zone.generationForecast && zone.generationForecast.state !== "known"
           ? ` <span class="state-unknown">Release forecast ${esc(zone.generationForecast.state)}: ${esc(zone.generationForecast.note || "")}</span>` : "")) +
    cell("weather", "Weather", temp === null ? "unknown" : Math.round(temp) + "°F",
         (wind === null ? "wind unknown" : Math.round(wind) + " mph " + dir) +
         (cloud === null ? "" : " · " + Math.round(cloud) + "% cloud"),
         "Open-Meteo hourly, evaluated across the plan window — not a daily average.") +
    cell("light", "Light", sun.sunrise ? "sunrise " + hm(sun.sunrise) : "unknown",
         sun.sunset ? "sunset " + hm(sun.sunset) : "",
         "Astronomical, exact for this date and location.") +
    cell("moon", "Moon",
         moon.known ? moon.illumination + "% " + (moon.waxing ? "waxing" : "waning") : "unknown",
         maj ? "major " + hm(maj.start) + "–" + hm(maj.end) : "",
         `${esc(moon.phase || "")} ${esc(moon.source || "")} <b>A weak secondary signal</b>, ` +
         `capped at ${data.moonMaxShare * 100}% of the score by design — shown because it is ` +
         `worth knowing, not because it decides anything.`) +
    `</div>`;
}


/**
 * §37 — the day as an opportunity timeline.
 *
 * Bar height is the ABSOLUTE weighted score for that hour, 0 to 1, not a min-max stretch.
 * A stretched axis made a day that is uniformly decent look like a day with a dramatic
 * best hour, which is the opposite of what this chart is for: the reader has to be able
 * to see that 6-9am really does beat 2-5pm, and equally that some days it does not.
 * Hours with no data are drawn as an outline, never as a bar.
 */
export function bestTime(data, ctx) {
  const species = ctx.species;
  const wins = ctx.plan.itinerary.windows;
  const cand = { zone: ctx.plan.zoneSequence[0],
                 z: data.zones[ctx.plan.zoneSequence[0]],
                 window: { start: wins[0].start, end: wins[wins.length - 1].end } };
  const series = data.series[cand.zone + "|" + species];
  const g = data.gates[cand.zone];
  if (!series) return "";
  const dayStart = startOfDay(cand.window.start);
  const W = 100, H = 46;
  const weights = data.weights[species];
  const dynWeight = Object.entries(weights)
    .filter(([k]) => series.keys.includes(k)).reduce((a, [, v]) => a + v, 0) || 1;

  const bars = [];
  for (let h = 0; h < 24; h++) {
    const t = dayStart + h * 3600;
    const i = Math.round((t - series.t0) / series.step);
    if (i < 0 || i >= series.hours) { bars.push(null); continue; }
    let v = 0, known = true;
    for (const k of series.keys) {
      v += (series.values[k][i] || 0) * (weights[k] || 0);
      if (series.known[k][i] === 0) known = false;
    }
    bars.push({ v: v / dynWeight, known });
  }

  const bw = W / 24;
  let svg = "";
  for (let h = 0; h < 24; h++) {
    const x = (h * bw).toFixed(2), w = (bw - 0.5).toFixed(2);
    // the track: every hour gets one, so an empty hour is visibly empty
    svg += `<rect x="${x}" y="2" width="${w}" height="${H - 4}" rx="0.8"
            fill="var(--line-2)" opacity="0.55"/>`;
    if (bars[h] === null) continue;
    const t = dayStart + h * 3600;
    const inWin = t >= cand.window.start - 1 && t < cand.window.end;
    const gi = Math.round((t - data.horizon.t0) / 3600);
    const storm = g && g.storm[gi] === 1;
    const wet = g && g.wet[gi] === 1;
    const hh = Math.max(2, bars[h].v * (H - 6));
    const fill = storm ? "var(--skip)" : wet ? "var(--cond)"
               : inWin ? "var(--accent)" : "var(--muted)";
    svg += `<rect x="${x}" y="${(H - 2 - hh).toFixed(2)}" width="${w}" height="${hh.toFixed(2)}"
            rx="0.8" fill="${fill}" opacity="${inWin || storm || wet ? 1 : 0.42}"/>`;
    if (!bars[h].known) {
      svg += `<rect x="${x}" y="${(H - 2 - hh).toFixed(2)}" width="${w}" height="${hh.toFixed(2)}"
              rx="0.8" fill="none" stroke="var(--faint)" stroke-width="0.4"
              stroke-dasharray="1 1"/>`;
    }
  }
  const x0 = ((cand.window.start - dayStart) / 3600) * bw;
  const x1 = ((cand.window.end - dayStart) / 3600) * bw;
  svg += `<rect x="${x0.toFixed(2)}" y="0" width="${Math.max(1, x1 - x0).toFixed(2)}"
          height="${H}" fill="none" stroke="var(--accent)" stroke-width="0.6" rx="1"/>`;

  const bestHour = bars.reduce((acc, b, i) => (b && (!acc || b.v > acc.v) ? { v: b.v, i } : acc), null);
  return `<h2>When to be there</h2>
    <div class="card tl">
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
           aria-label="Hour-by-hour opportunity for ${esc(data.species[species].display.full)} on this water. Your window runs ${esc(hm(cand.window.start))} to ${esc(hm(cand.window.end))}${bestHour ? ", and the strongest hour of the day starts at " + esc(hm(dayStart + bestHour.i * 3600)) : ""}.">${svg}</svg>
      <div class="axis"><span>12a</span><span>6a</span><span>noon</span><span>6p</span><span>12a</span></div>
      <div class="maplegend">
        <span><i style="background:var(--accent)"></i>your window</span>
        <span><i style="background:var(--muted);opacity:.42"></i>rest of the day</span>
        <span><i style="background:var(--cond)"></i>released water in the reach</span>
        <span><i style="background:var(--skip)"></i>thunderstorm hour</span>
        <span><i style="background:var(--line-2)"></i>no data</span>
      </div>
      <p class="tiny">Height is the hour's own score on this water, on a fixed 0-100 scale —
      not stretched to fill the chart. Dashed outlines are hours with a missing input.</p>
    </div>`;
}

/**
 * §37 — the technique for a segment, read from what Python already chose.
 *
 * 2.0 picked the presentation in the browser from the fit values. 2.1 does it per SEGMENT
 * in caney/planner/segments.py, where the zone kind, the units turning and the light are
 * all in scope — so this only reads the answer.
 */
export function pickTechnique(sp, ctx) {
  const seg = (ctx.segments || []).find((s) => s.type === "fish" && s.technique);
  if (seg) return seg.technique;
  return Object.assign({ why: "the standard read for these conditions" },
                       sp.techniques.default);
}


function safetyBlock(data, ctx) {
  const zones = ctx.plan.zoneSequence;
  const claims = data.safety.filter((c) => zones.includes(c.zone_id));
  const exit = claims.filter((c) => ["safe_exit", "wade_cutoff", "release_arrival",
                                     "weather_hazard"].includes(c.kind));
  const hazards = zones.flatMap((z) => (data.zones[z].hazards || []));
  if (!exit.length && !hazards.length) return "";
  return `<div class="card safety-card">
    <h3>Safety</h3>
    <ul style="margin:6px 0 0;padding-left:18px">
      ${exit.map((c) => `<li><b>${esc(c.text)}</b>
        <span class="tiny">${esc(c.source || "")}${c.bound === "earliest" ? " · conservative bound" : ""}</span></li>`).join("")}
      ${hazards.map((h) => `<li>${esc(h)}</li>`).join("")}
    </ul>
    <p class="tiny" style="margin:10px 0 0">§45: these are fixed claims generated from
    instrument data. Nothing in this app — including the chat assistant and any research
    source — may restate, round, infer or override one.</p>
  </div>`;
}

function scoreBreakdown(ctx) {
  const cand = ctx.primary;
  if (!cand || !cand.lines || !cand.lines.length) return "";
  return `<h2>Why this score</h2><div class="card bars">` + cand.lines.map((l) => {
    const pct = l.possible ? (l.earned / l.possible) * 100 : 0;
    return `<div class="bar${l.known ? "" : " unknown"}">
      <div class="nm">${esc(l.label)}</div>
      <div class="n">+${l.earned.toFixed(1)} / ${l.possible}</div>
      <div class="track"><div class="fill" style="width:${Math.max(0, Math.min(100, pct)).toFixed(0)}%"></div></div>
      <div class="why">${esc(l.why)}</div>
    </div>`;
  }).join("") + `<p class="tiny" style="margin-top:10px">These are the component weights for
  the primary zone's opening window. Weights are published config, not code — see
  docs/SCORING.md. Hatched bars are components with no data: they score neutral and are
  charged against confidence instead.</p></div>`;
}

function evidenceDrawer(data, ctx) {
  const species = ctx.species;
  const sp = data.species[species];
  const zoneId = ctx.plan.zoneSequence[0];
  const z = data.zones[zoneId];
  const claims = evidenceFor(data, zoneId, species);
  const ref = (z.species_profiles || {})[species] || {};
  const conflict = disagreement(claims);
  const it = ctx.plan.itinerary;
  return `<details class="drawer"><summary>Why this plan? <span class="tiny">sources, biology, model</span></summary>
    <div class="body">
      <h3>Live data</h3>
      <div class="fresh">${(data.freshness[zoneId] || []).map((r) =>
        `<div class="r"><span class="l">${esc(r.label)}${r.source ? " · " + esc(r.source) : ""}</span>
         <span class="v state-${esc(r.state)}">${esc(r.age)}</span></div>`).join("") ||
        `<div class="tiny">No live signals recorded for this water.</div>`}</div>

      <h3>Biology</h3>
      <p class="small">${esc(ref.pattern || "")} ${esc(ref.holds || "")}</p>
      <p class="small">Forage: ${esc((sp.forage || []).join(", "))}
      <span class="tiny">(${esc(sp.evidence.temp === "sourced" ? "sourced" : "heuristic")};
      ${esc(sp.sources.forage || "angling convention")})</span></p>
      <p class="tiny">${ref.heuristic
        ? "This zone's species pattern is a HEURISTIC — angling convention, not an agency document."
        : "This zone's species pattern is backed by the sourced claims below."}</p>

      <h3>Recent research</h3>
      ${conflict ? `<div class="banner warn">${esc(conflict)}</div>` : ""}
      ${claims.length ? claims.map((c) => `<div class="cite">
        <span class="tier ${esc(c.source_tier)}">TIER ${esc(c.source_tier)}</span>
        ${esc(c.claim_text)}<br>
        <a href="${esc(safeUrl(c.source_url))}" target="_blank" rel="noopener">${esc(c.source_title || c.source_domain)}</a>
        <span class="tiny">${esc(TIER_LABEL[c.source_tier] || "")} · ${esc(claimAge(c))}
        · confidence ${(c.confidence || 0).toFixed(2)}${c.safety_sensitive ? " · flagged safety-sensitive: numbers in it are NOT used" : ""}</span>
      </div>`).join("") : `<p class="tiny">No sourced claim mentions this water for this species.</p>`}

      <h3>Model</h3>
      <p class="small">Routing confidence: <b>${esc(z.modelConfidence)}</b>.
      ${esc(z.modelNote || "")} ${esc((z.arrival && z.arrival.note) || "")}</p>
      ${z.arrival && z.arrival.first ? `<p class="tiny">Arrival at ${esc(z.mfd)} miles below
      ${esc(z.dam || "the dam")}: earliest ${z.arrival.first.earliest_h} h, typical
      ${z.arrival.first.typical_h} h, later edge ${z.arrival.first.latest_h} h.</p>` : ""}
      <p class="tiny">planner ${esc((data.versions || {}).planner || "?")} ·
      species ${esc((data.versions || {}).species_model || "?")} ·
      zones ${esc((data.versions || {}).zone_model || "?")} ·
      research ${esc((data.versions || {}).research || "?")} ·
      utility ${(it.utility || 0).toFixed(1)} =
      quality ${(it.parts.quality || 0).toFixed(1)}
      × duration ${(it.parts.duration_factor || 0).toFixed(2)}
      × confidence ${(it.parts.confidence_factor || 0).toFixed(2)}
      × location ${(it.parts.location_factor || 0).toFixed(2)}
      − travel ${(it.parts.transition || 0).toFixed(1)}
      ${it.parts.breadth ? "+ breadth " + it.parts.breadth.toFixed(1) : ""}
      ${it.parts.complexity ? "− complexity " + it.parts.complexity.toFixed(1) : ""}.</p>
    </div></details>`;
}

/** §27 — conflicting sources are surfaced, not silently resolved. */
export function disagreement(claims) {
  const byType = {};
  for (const c of claims) (byType[c.claim_type] = byType[c.claim_type] || []).push(c);
  for (const [type, list] of Object.entries(byType)) {
    if (list.length < 2) continue;
    const tiers = new Set(list.map((c) => c.source_tier));
    if (tiers.size > 1 && (tiers.has("C") || tiers.has("D"))) {
      return "Research confidence reduced: sources of different authority disagree about " +
             type.replace(/_/g, " ") + " on this water. The agency source is weighted higher.";
    }
  }
  return "";
}

function claimAge(c) {
  if (c.published_at) return ago(Date.parse(c.published_at) / 1000);
  if (c.retrieved_at) return "retrieved " + ago(c.retrieved_at);
  return "undated";
}

/** §71 — compact research status, including when it is unavailable. */
function researchStatus(data, ctx) {
  const r = data.research || {};
  const claims = evidenceFor(data, ctx.plan.zoneSequence[0], ctx.species);
  const primary = claims.filter((c) => c.source_tier === "A" || c.source_tier === "B");
  const newest = claims.map((c) => c.published_at ? Date.parse(c.published_at) / 1000
                                                  : c.retrieved_at)
    .filter(Boolean).sort((a, b) => b - a)[0];
  if (!r.enabled) {
    return `<div class="card flat"><div class="k2">Research</div>
      <p class="small">Current web research is temporarily unavailable. This plan is based on
      live water, weather and ${primary.length} stored
      ${primary.length === 1 ? "source" : "sources"} of fishery evidence.</p>
      ${newest ? `<p class="tiny">Newest stored source: ${esc(ago(newest))}.</p>` : ""}</div>`;
  }
  return `<div class="card flat"><div class="k2">Research</div>
    <p class="small">${primary.length} current primary
    ${primary.length === 1 ? "source" : "sources"} for this water.</p>
    <p class="tiny">${newest ? "Newest: " + esc(ago(newest)) + "." : ""}
    ${r.refreshedAt ? " Last refreshed " + esc(ago(r.refreshedAt)) + "." : ""}
    Provider: ${esc(r.provider || "none")}.</p></div>`;
}

/** §72 — tapping location confidence explains what it is made of. */
function locationDrawer(data, ctx) {
  const zoneId = ctx.plan.zoneSequence[0];
  const lc = data.zones[zoneId].location_confidence || {};
  const rows = lc.rows || [];
  return `<details class="drawer" id="locdrawer"><summary>Location confidence
    <span class="tiny">${Math.round(lc.score || 0)}/100 — what we know about WHERE</span></summary>
    <div class="body">
      ${rows.map((r) => `<div class="cite">
        <b>${esc(r.label)}:</b> ${esc(r.level_label)}
        <span class="tiny">(prior ${r.prior})</span><br>
        <span class="small">${esc(r.detail)}</span></div>`).join("")}
      ${lc.verification && lc.verification.source ? `<p class="tiny">Verification:
        ${esc(lc.verification.status)}${lc.verification.verified_at ? " · " + esc(lc.verification.verified_at) : ""}
        · ${esc(lc.verification.source)}. ${esc(lc.verification.notes || "")}</p>` : ""}
      <p class="tiny">These are <b>initial priors, not calibrated measurements</b>. They are
      ordered correctly and they cost a candidate real utility, which is what stops a
      beautiful-looking reach nobody has stood in from beating a verified one.</p>
    </div></details>`;
}

function freshnessDrawer(ctx) {
  const rows = (ctx.primary && ctx.primary.confRows) || [];
  return `<details class="drawer"><summary>Data freshness <span class="tiny">per signal</span></summary>
    <div class="body"><div class="fresh">${rows.map((r) =>
      `<div class="r"><span class="l">${esc(r.label)}</span>
       <span class="v state-${esc(r.state)}">${esc(r.state)}</span></div>
       <div class="tiny" style="margin:-2px 0 4px">${esc(r.detail || "")}</div>`).join("")}
    </div>
    <p class="tiny">Confidence is computed from exactly these rows. There is no single
    "updated" timestamp on purpose — a 4-minute-old gauge and a 14-day-old fishing report
    are not the same kind of fresh.</p></div></details>`;
}

/** §32, §73 — the map: itinerary numbered, geometry styled by how well we know it. */
function mapBlock(data, ctx) {
  const zones = ctx.plan.zoneSequence.map((z) => data.zones[z]);
  if (!zones.some((z) => z.geometry && (z.geometry.points || []).length)) return "";
  const launchSeg = ctx.segments.find((s) => s.type === "launch") || {};
  const payload = {
    sequence: zones.map((z, i) => ({
      n: i + 1, id: z.id, name: z.name, geometry: z.geometry, access: z.access,
      launch: i === 0 ? launchSeg.access_id : null,
    })),
  };
  return `<h2>On the map</h2>
    <div id="map" data-geometry='${esc(JSON.stringify(payload))}'
         role="region" aria-label="Map of ${esc(zones.map((z) => z.name).join(" then "))} — launch, target zones and access points"></div>
    <div class="maplegend">
      <span><i style="background:var(--go)"></i>launch</span>
      <span><i style="background:var(--accent)"></i>zone 1</span>
      <span><i style="background:var(--cond)"></i>zone 2+</span>
      <span><i class="lg-dash"></i>agency-described reach</span>
      <span><i class="lg-dot"></i>modelled habitat, not field verified</span>
    </div>
    <p class="tiny">Solid shapes are verified geometry. Dashed shapes are reaches an agency
    described without naming a spot. Dotted areas are modelled from habitat — drawn
    differently because they are known differently.</p>`;
}

/** §38 — the runner-up itineraries, and why each lost. */
function alternativesBlock(ctx, data) {
  const alts = ctx.alternatives || [];
  if (!alts.length) return "";
  return `<h2>Alternatives</h2><div class="card">` + alts.map((a) => {
    if (a.eliminated) {
      return `<div class="alt out"><div class="h"><div class="nm">${esc(a.name)}</div>
        <div class="sc">out</div></div><div class="why">${esc(a.reason)}</div></div>`;
    }
    return `<div class="alt"><div class="h"><div class="nm">${esc(a.name)}</div>
      <div class="sc">${Math.round(a.score)} opp · ${Math.round(a.confidence)} conf</div></div>
      <div class="why">${esc(a.why)}</div>
      ${a.detail_page ? `<div class="tiny"><a href="${esc(a.detail_page)}">Full river page →</a></div>` : ""}
      </div>`;
  }).join("") + `</div>`;
}


/**
 * §46, §47 — a research box, deliberately secondary to the planner.
 *
 * It sits inside a finished plan, and the questions it offers are ABOUT that plan. The
 * homepage is not a chatbot: the graphical flow is the product and this explains it.
 */
function askBlock(ctx) {
  const primary = ctx.plan.zoneSequence[0];
  const alt = (ctx.alternatives || []).find((a) => !a.eliminated);
  const moved = ctx.plan.zoneSequence.length > 1;
  const qs = [
    alt ? `Why ${DATA_REF.d.zones[primary].name} instead of ${alt.name}?` : null,
    moved ? "Why is the move worth it?" : "Why not move somewhere else?",
    "Where do they go if generation stops?",
    "Why did you pick this window and not the whole morning?",
  ].filter(Boolean);
  return `<details class="drawer"><summary>Ask about this plan…
    <span class="tiny">answers come from this plan's own data</span></summary>
    <div class="body">
      <p class="small">RiverGuide answers from the exact plan above — the same zones, the
      same claim book, the same sources, the same itinerary. It explains the
      recommendation; it does not make one of its own, and a deterministic verifier removes
      any water number it cannot trace to a claim.</p>
      <div class="chips">${qs.map((q) =>
        `<a class="chip" href="https://t.me/share/url?url=${encodeURIComponent(q)}"
            target="_blank" rel="noopener">${esc(q)}</a>`).join("")}</div>
      <p class="tiny">Opens RiverGuide on Telegram. This plan is
      <code>${esc(ctx.plan.zoneSequence.join(" → "))}</code> for
      <code>${esc(ctx.species)}</code> — mention the water and the bot pulls this exact
      itinerary.</p>
    </div></details>`;
}


function tripBlock(ctx) {
  return `<details class="drawer" id="tripdrawer"><summary>Log this trip
    <span class="tiny">prediction → outcome → calibration</span></summary>
    <div class="body">
      <p class="small">Logging saves <b>what Caney predicted right now</b> — the score, the
      confidence, the arrival distribution, the fly — before you know how it went. Fill in
      the outcome afterwards and the residuals become computable. Stored on this device
      only.</p>
      <button class="btn primary" id="logtrip" type="button">Freeze this prediction</button>
      <div id="triplist" style="margin-top:14px"></div>
      <div class="chips" style="margin-top:10px">
        <button class="btn" id="tripexport" type="button">Export log</button>
        <button class="btn" id="tripscore" type="button">Model scoreboard</button>
      </div>
      <div id="scoreboard"></div>
    </div></details>`;
}

/** §44, §51 — model performance, shown rather than buried in a footer. */
export function renderScoreboard(sb) {
  const pct = (v) => (v === null || v === undefined ? "—" : Math.round(v * 100) + "%");
  const n = (v, d = 1) => (v === null || v === undefined ? "—" : Number(v).toFixed(d));
  const band = (rows, key, unit) => `<div class="fresh">${rows.map((b) =>
    `<div class="r"><span class="l">${esc(b.band || b.key)} (n=${b.n})</span>
     <span class="v">${unit === "pct" ? pct(b[key]) : n(b[key], 2)}</span></div>`).join("")}</div>`;

  return `<div class="card flat" style="margin-top:12px">
    <h3 style="margin-top:0">Model scoreboard</h3>
    <p class="tiny">${sb.fished} fished trip(s) of ${sb.trips} logged${
      sb.versions.length ? " · " + sb.versions.map((v) => v.version + " (" + v.n + ")").join(", ") : ""}.
      Every measure below refuses to print a figure until it has enough data — a model
      whose validation is one trip should say so.</p>

    <h3>Water-arrival residual</h3>
    <div class="fresh">
      <div class="r"><span class="l">Median residual (typical vs actual)</span>
        <span class="v">${n(sb.arrival.medianResidualMin, 0)} min</span></div>
      <div class="r"><span class="l">Mean absolute error</span>
        <span class="v">${n(sb.arrival.meanAbsMin, 0)} min</span></div>
      <div class="r"><span class="l">Inside the earliest→latest bounds</span>
        <span class="v">${pct(sb.arrival.insideBounds)}</span></div>
      <div class="r"><span class="l">Arrived BEFORE the earliest bound</span>
        <span class="v ${sb.arrival.earlierThanEarliest ? "state-error" : ""}">${sb.arrival.earlierThanEarliest}</span></div>
    </div>
    <p class="small">${esc(sb.arrival.verdict)}</p>
    <p class="tiny">${esc(sb.arrival.safetyNote)}</p>

    <h3>Does a 90 outperform an 80?</h3>
    ${band(sb.opportunity.bands, "meanRating")}
    <p class="small">Correlation ${n(sb.opportunity.correlation, 2)} (n=${sb.opportunity.n}).
    ${esc(sb.opportunity.verdict)}</p>

    <h3>Does high confidence mean higher accuracy?</h3>
    ${band(sb.calibration.bands, "meanRating")}
    <p class="small">${esc(sb.calibration.verdict)}</p>

    <h3>Does location confidence predict the right place?</h3>
    ${band(sb.location.bands, "rightPlace", "pct")}
    <p class="small">${esc(sb.location.verdict)}</p>

    <h3>Which species model performs best?</h3>
    ${band(sb.species.rows, "meanRating")}
    ${sb.species.verdict ? `<p class="small">${esc(sb.species.verdict)}</p>` : ""}

    <h3>Which zones are poorly calibrated?</h3>
    <div class="fresh">${sb.zones.rows.map((z) =>
      `<div class="r"><span class="l">${esc(z.key)} (n=${z.n})</span>
       <span class="v">gap ${n(z.gap, 2)}</span></div>`).join("") ||
      `<div class="tiny">No rated trips yet.</div>`}</div>
    <p class="tiny">Gap = predicted opportunity (rescaled to 1–5) minus the rating you gave.
    A large positive gap means the model was more optimistic than the day.</p>

    <h3>Does the itinerary optimiser beat a single zone?</h3>
    <div class="fresh">
      <div class="r"><span class="l">Multi-zone plans (n=${sb.itinerary.multiN})</span>
        <span class="v">${n(sb.itinerary.multiMean, 2)}</span></div>
      <div class="r"><span class="l">Single-zone plans (n=${sb.itinerary.singleN})</span>
        <span class="v">${n(sb.itinerary.singleMean, 2)}</span></div>
    </div>
    <p class="small">${esc(sb.itinerary.verdict)}</p>

    <h3>Does research improve results?</h3>
    <div class="fresh">
      <div class="r"><span class="l">With ≥2 sourced claims (n=${sb.research.withN})</span>
        <span class="v">${n(sb.research.withMean, 2)}</span></div>
      <div class="r"><span class="l">With fewer (n=${sb.research.withoutN})</span>
        <span class="v">${n(sb.research.withoutMean, 2)}</span></div>
    </div>
    ${sb.research.verdict ? `<p class="small">${esc(sb.research.verdict)}</p>` : ""}

    <h3>Segment-level</h3>
    <div class="fresh"><div class="r">
      <span class="l">Expected segment score vs fish caught (n=${sb.segments.fished})</span>
      <span class="v">${n(sb.segments.correlation, 2)}</span></div></div>
    <p class="small">${esc(sb.segments.verdict)}</p>
  </div>`;
}

/** §48, §49 — the low-friction outcome form, then the optional detail, then segments. */
export function renderTrips(trips, quickFields, detailFields, segmentFields) {
  if (!trips.length) return `<p class="tiny">Nothing logged yet on this device.</p>`;
  return trips.slice(0, 8).map((t) => {
    const p = t.prediction;
    const done = t.outcome && t.outcome.recordedAt;
    const zones = (p.zoneSequence || [p.zone]).join(" → ");
    return `<div class="alt">
      <div class="h"><div class="nm">${esc(p.zoneName || zones)} · ${esc(p.species)}</div>
        <div class="sc">${Math.round(p.opportunity !== undefined ? p.opportunity : p.score)} opp
          · ${Math.round(p.confidence)} conf · ${Math.round(p.locationConfidence || 0)} loc</div></div>
      <div class="why">Predicted ${esc(p.verdict)} for ${esc(hm(p.window.start))}–${esc(hm(p.window.end))}${
        p.predictedArrival ? ` · water typical ${esc(hm(p.predictedArrival.typical))}` : ""}</div>
      ${done ? `<div class="tiny">Recorded: fished ${esc(t.outcome.fished || "—")},
        rating ${esc(String(t.outcome.rating || "—"))}, right place
        ${esc(t.outcome.right_place || "—")}${t.outcome.fly_that_worked
          ? ", " + esc(t.outcome.fly_that_worked) : ""}</div>`
        : `<form class="tripform" data-trip="${esc(t.id)}" style="margin-top:8px">
             <div class="quickgrid">${quickFields.map((f) => fieldHtml(f, t.id)).join("")}</div>
             <details class="drawer" style="margin:10px 0"><summary>Add detail
               <span class="tiny">optional</span></summary>
               <div class="body">${detailFields.map((f) => fieldHtml(f, t.id)).join("")}</div>
             </details>
             <button class="btn primary" type="submit">Save</button>
           </form>`}
      ${done && (p.segments || []).some((s) => s.type === "fish")
        ? segmentForms(t, segmentFields) : ""}
    </div>`;
  }).join("");
}

function segmentForms(t, fields) {
  const fishSegs = (t.prediction.segments || []).filter((s) => s.type === "fish");
  const recorded = t.segmentOutcomes || {};
  return `<details class="drawer" style="margin-top:8px"><summary>Per-stretch outcomes
    <span class="tiny">calibrates the itinerary, not just the day</span></summary>
    <div class="body">${fishSegs.map((s) => recorded[s.i]
      ? `<div class="cite"><b>${esc(hm(s.start))}–${esc(hm(s.end))} ${esc(s.zone)}</b> —
          ${esc(String(recorded[s.i].caught || 0))} fish${recorded[s.i].fly
            ? " on " + esc(recorded[s.i].fly) : ""}</div>`
      : `<form class="segform" data-trip="${esc(t.id)}" data-seg="${s.i}">
          <div class="tiny">${esc(hm(s.start))}–${esc(hm(s.end))} · ${esc(s.zone)}
            · expected ${s.expected === null ? "—" : Math.round(s.expected)}</div>
          <div class="quickgrid">${fields.map((f) => fieldHtml(f, t.id + "-" + s.i)).join("")}</div>
          <button class="btn" type="submit" style="margin-top:6px">Save stretch</button>
        </form>`).join("")}</div></details>`;
}

function fieldHtml(f, id) {
  const fid = "f-" + id + "-" + f.key;
  if (f.type === "choice") {
    return `<fieldset class="choice"><legend>${esc(f.label)}</legend>
      ${f.options.map(([v, l], i) =>
        `<label><input type="radio" name="${esc(f.key)}" value="${esc(v)}"
           id="${esc(fid)}-${i}"><span>${esc(l)}</span></label>`).join("")}</fieldset>`;
  }
  if (f.type === "rating") {
    return `<fieldset class="choice rating"><legend>${esc(f.label)}</legend>
      ${[1, 2, 3, 4, 5].map((v) =>
        `<label><input type="radio" name="${esc(f.key)}" value="${v}"
           id="${esc(fid)}-${v}"><span>${v}</span></label>`).join("")}</fieldset>`;
  }
  if (f.type === "select") {
    return `<div class="field"><label for="${fid}">${esc(f.label)}</label>
      <select id="${fid}" name="${esc(f.key)}">${f.options.map((o) =>
        `<option value="${esc(o)}">${esc(o || "—")}</option>`).join("")}</select></div>`;
  }
  if (f.type === "textarea") {
    return `<div class="field"><label for="${fid}">${esc(f.label)}</label>
      <textarea id="${fid}" name="${esc(f.key)}" rows="2"></textarea></div>`;
  }
  const type = f.type === "number" ? "number" : f.type === "time" ? "time" : "text";
  return `<div class="field"><label for="${fid}">${esc(f.label)}</label>
    <input id="${fid}" name="${esc(f.key)}" type="${type}"
      ${f.min !== undefined ? `min="${f.min}"` : ""} ${f.max !== undefined ? `max="${f.max}"` : ""}></div>`;
}


function limitations(ctx) {
  if (!ctx.limitations.length) return "";
  return `<h2>Limitations</h2><div class="card flat"><ul style="margin:0;padding-left:18px">` +
    ctx.limitations.map((l) => `<li class="small">${esc(l)}</li>`).join("") + `</ul></div>`;
}

/** §40 — on-water mode: NOW / NEXT / ALARM / WATER / FLY, readable one-handed. */
export function renderOnWater(root, data, ctx, now) {
  const segs = ctx.segments;
  const past = segs.filter((s) => s.start <= now);
  const nowSeg = past.length ? past[past.length - 1] : segs[0];
  const next = segs.find((s) => s.start > now);
  const safety = segs.find((s) => s.type === "safety_exit" && s.start > now);
  const t = (segs.find((s) => s.type === "fish" && s.start <= now && s.end > now) ||
             segs.find((s) => s.type === "fish") || {}).technique || {};
  const zones = ctx.plan.zoneSequence;
  const change = data.safety.filter((c) => zones.includes(c.zone_id) &&
      ["generation_start", "generation_stop", "release_arrival"].includes(c.kind) &&
      (c.at || 0) > now).sort((a, b) => a.at - b.at)[0];
  const delta = ctx.delta;

  root.innerHTML = `
    ${delta ? deltaBlock(delta) : ""}
    <div class="ow-block"><div class="k">Now</div>
      <div class="v">${esc(nowSeg ? nowSeg.instructions : ctx.plan.zoneSequence[0])}</div>
      <div class="s">${esc(nowSeg ? nowSeg.reason : "")}</div></div>
    <div class="ow-block"><div class="k">Next</div>
      <div class="v">${next ? esc(next.instructions) : "Window complete"}</div>
      <div class="s">${next ? esc(hm(next.start)) + " · in " + esc(countdown(next.start, now)) : ""}</div></div>
    ${safety ? `<div class="ow-block safety"><div class="k">Alarm — safe exit</div>
      <div class="v">${esc(hm(safety.start))}</div>
      <div class="s">${esc(countdown(safety.start, now))} from now. ${esc(safety.instructions)}</div></div>` : ""}
    <div class="ow-block"><div class="k">Water</div>
      <div class="v">${change ? "changes in " + esc(countdown(change.at, now)) : "no change forecast"}</div>
      <div class="s">${change ? esc(change.text) : "Inside the planning horizon nothing is scheduled to change."}</div></div>
    <div class="ow-block"><div class="k">Fly</div>
      <div class="v">${esc(t.primary_fly || "—")}</div>
      <div class="s">${esc([t.primary_size, t.primary_color, t.line].filter(Boolean).join(" · "))}</div>
      ${t.switch_trigger ? `<div class="s">${esc(t.switch_trigger)}</div>` : ""}</div>
    <div class="ow-block"><div class="k">Map</div>
      <div class="s"><a href="${esc(mapsUrl(data, ctx))}" target="_blank" rel="noopener">Open the next launch in Maps →</a></div></div>
    <div class="chips" style="margin-top:20px">
      <button class="btn primary" id="ow-recheck" type="button">RECHECK PLAN</button>
      <button class="btn" id="ow-exit" type="button">Leave on-water mode</button>
    </div>`;
}

/** §41 — what CHANGED, and nothing else. */
export function deltaBlock(delta) {
  if (!delta) return "";
  if (!delta.changed) {
    return `<div class="banner ok">PLAN UNCHANGED — rechecked ${esc(ago(delta.at))}. ` +
           `Live water and weather still match the plan you started.</div>`;
  }
  return `<div class="banner bad"><b>PLAN CHANGED</b></div>
    <div class="card flat"><div class="k2">What changed</div>
    ${delta.rows.map((r) => `<div class="deltarow">
      <div class="dk">${esc(r.label)}</div>
      <div class="dv"><span class="was">was ${esc(r.was)}</span>
        <span class="now">now ${esc(r.now)}</span></div>
      ${r.detail ? `<div class="tiny">${esc(r.detail)}</div>` : ""}
    </div>`).join("")}
    <p class="small" style="margin-top:10px">${esc(delta.advice)}</p>
    <p class="tiny">The original plan is preserved for the trip log — recalibration needs
    what we predicted, not what we later wished we had predicted.</p></div>`;
}

function mapsUrl(data, ctx) {
  const now = Date.now() / 1000;
  const seg = ctx.segments.find((s) => s.type === "fish" && s.end > now) ||
              ctx.segments.find((s) => s.type === "fish");
  const zone = data.zones[(seg || {}).zone_id || ctx.plan.zoneSequence[0]];
  const a = (zone.access || []).find((x) => x.lat !== null && x.lat !== undefined);
  if (!a) return "";
  return "https://www.google.com/maps/search/?api=1&query=" + a.lat + "," + a.lon;
}

function isoDate(epoch) {
  const d = new Date(epoch * 1000), p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

/** Local midnight of the day containing `epoch`, on the reader's own clock. */
function startOfDay(epoch) {
  const d = new Date(epoch * 1000);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 1000;
}

export { isoDate };
