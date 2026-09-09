/**
 * Rendering. §8, §32, §33, §36, §37, §38, §40.
 *
 * Presentation only — no thresholds, no scoring, no time arithmetic beyond formatting.
 * Every string that could contain data goes through esc(); every href through safeUrl().
 */
import { ago, esc, hm, num, obs, safeUrl, whenLabel, countdown, dayLabel } from "./format.js";
import { confidenceLabel } from "./model.js";
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
  const { cand, species, craft, steps, alternatives, verdict, verdictWhy } = ctx;
  const z = cand.z;
  const sp = data.species[species];
  const launch = TL.pickLaunch(z, craft);
  const takeout = (z.access || []).filter((a) => !launch || a.id !== launch.id)
    .find((a) => craft === "any" || (a.craft || []).includes(craft));
  const ref = z.species_profiles[species] || {};

  root.innerHTML =
    section(header(sp, z, cand, verdict, verdictWhy)) +
    section(instructions(z, ref, launch, takeout, steps, species)) +
    section(conditionsStrip(data, z, cand)) +
    section(bestTime(data, cand, species, craft)) +
    section(itinerary(steps)) +
    section(technique(data, sp, cand, species)) +
    safetyBlock(data, z, cand, steps) +
    section(scoreBreakdown(cand)) +
    evidenceDrawer(data, cand, species, sp) +
    freshnessDrawer(cand, data, z) +
    mapBlock(z, launch, takeout) +
    section(alternativesBlock(alternatives, data)) +
    section(askBlock(ctx)) +
    section(tripBlock(ctx)) +
    section(limitations(ctx));
}

function section(html) { return html || ""; }

function header(sp, z, cand, verdict, why) {
  const w = cand.window;
  return `<div class="card">
    <div class="eyebrow">${esc(sp.display.full)}</div>
    <div class="placehead">
      <div class="zone">${esc(z.name)}</div>
      <div class="when" data-clock>${esc(whenLabel(w.start, w.end))}</div>
    </div>
    <div class="verdict" style="margin-top:14px">
      <div class="badge ${esc(verdict)}">${esc(verdict)}</div>
      <div class="nums">
        <div class="score">${cand.score.toFixed(0)} <span>/ 100</span></div>
        <div class="conf">${esc(confidenceLabel(cand.confidence, DATA_REF.d))} · ${cand.confidence.toFixed(0)}/100</div>
      </div>
    </div>
    <p class="small" style="margin:12px 0 0">${esc(why)}</p>
    <p class="tiny" style="margin:6px 0 0">Window chosen because ${esc(w.why)}.</p>
  </div>`;
}

function instructions(z, ref, launch, takeout, steps, species) {
  const move = steps.find((s) => /^Move toward/.test(s.title));
  const stop = steps.find((s) => s.kind === TL.KINDS.SAFETY) ||
               steps.find((s) => s.title === "Primary window ends");
  const rows = [
    ["Launch", launch
      ? `<b>${esc(launch.name)}</b><br><span class="small">${esc(launch.note || "")}</span>` +
        (launch.verified ? "" : ` <span class="tiny">(coordinates not verified to RIVER_SPEC §2)</span>`)
      : `<span class="state-unknown">no verified access for this craft</span>`],
    ["Start", `<b>${esc(z.name)}</b> — ${esc(ref.pattern || "")}`],
    ["Fish", esc(ref.holds || (z.habitat || []).join(", "))],
    ["Move", move ? `<b>${esc(move.title.replace(/^Move toward /, ""))}</b> at about ${esc(hm(move.at))}` +
      `<br><span class="small">${esc(move.detail)}</span>`
      : `<span class="small">One zone plan — nothing better to shift to inside this window.</span>`],
    ["Stop", stop ? `<b>${esc(hm(stop.at))}</b> — ${esc(stop.detail)}` : "—"],
  ];
  if (takeout) rows.splice(1, 0, ["Take out", esc(takeout.name)]);
  return `<div class="card"><div class="instr">` +
    rows.map(([k, v]) => `<div class="row"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`).join("") +
    `</div></div>`;
}

function conditionsStrip(data, z, cand) {
  const w = z.water || {};
  const hours = (data.weatherHours[z.river] || [])
    .filter((h) => h.epoch >= cand.window.start && h.epoch <= cand.window.end);
  const mean = (k) => {
    const v = hours.map((h) => h[k]).filter((x) => x !== null && x !== undefined);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };
  const sun = data.sun[z.river + "|" + isoDate(cand.window.start)] || {};
  const moon = data.lunar[z.river + "|" + isoDate(cand.window.start)] || {};
  const flow = obs(w.flow);
  const gen = w.generation_on && w.generation_on.state === "known"
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
     </button><div class="tiny" id="strip-${esc(id)}" hidden style="grid-column:1/-1;padding:2px 4px 8px">${detail}</div>`;

  return `<h2>Conditions</h2><div class="strip">` +
    cell("water", "Water", flow.text,
         gen + (w.flow_trend && w.flow_trend.state === "known" ? " · " + w.flow_trend.value : ""),
         `${esc((w.flow || {}).source || "—")} · ${esc((w.flow || {}).age || "unknown")}. ` +
         `Release: ${esc((w.generation || {}).source || "—")} · ${esc((w.generation || {}).age || "unknown")}.` +
         (z.generationForecast && z.generationForecast.state !== "known"
           ? ` <span class="state-unknown">Release forecast ${esc(z.generationForecast.state)}: ${esc(z.generationForecast.note || "")}</span>` : "")) +
    cell("weather", "Weather", temp === null ? "unknown" : Math.round(temp) + "°F",
         (wind === null ? "wind unknown" : Math.round(wind) + " mph " + dir) +
         (cloud === null ? "" : " · " + Math.round(cloud) + "% cloud"),
         "Open-Meteo hourly, evaluated across your window — not a daily average.") +
    cell("light", "Light", sun.sunrise ? "sunrise " + hm(sun.sunrise) : "unknown",
         sun.sunset ? "sunset " + hm(sun.sunset) : "",
         "Astronomical, exact for this date and location.") +
    cell("moon", "Moon", moon.known ? moon.illumination + "% " + (moon.waxing ? "waxing" : "waning") : "unknown",
         maj ? "major " + hm(maj.start) + "–" + hm(maj.end) : "",
         `${esc(moon.phase || "")}. ${esc(moon.source || "")} A weak secondary signal, capped at ` +
         `${data.moonMaxShare * 100}% of the score by design.`) +
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
export function bestTime(data, cand, species, craft) {
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

function itinerary(steps) {
  return `<h2>The plan</h2><div class="card"><ol class="steps">` + steps.map((s) => {
    const branches = (s.branches || []).map((b) =>
      `<div class="branch"><b>If ${esc(b.if)}:</b> ${esc(b.then)}</div>`).join("");
    return `<li class="${s.kind === TL.KINDS.SAFETY ? "safety" : ""}">
      <div class="t">${esc(s.at === null ? "—" : hm(s.at))}</div>
      <div>
        <div class="ttl">${esc(s.title)}<span class="kind ${esc(s.kind)}">${esc(s.kind)}</span></div>
        <div class="dt">${esc(s.detail)}</div>
        ${s.uncertainty ? `<div class="unc">${esc(s.uncertainty)}</div>` : ""}
        ${branches}
      </div></li>`;
  }).join("") + `</ol>
  <p class="tiny" style="margin-top:12px">Each step says where its timing came from.
  <b>deterministic</b> and <b>safety</b> steps come from instrument feeds through a fixed
  claim; <b>heuristic</b> steps are guide craft and are not verified.</p></div>`;
}

function technique(data, sp, cand, species) {
  const t = pickTechnique(sp, cand);
  return `<h2>Tie this on</h2><div class="card"><div class="instr">
    ${row("Primary", `<b>${esc(t.primary_fly)}</b> ${esc(t.primary_size)} · ${esc(t.primary_color)}`)}
    ${row("Backup", `${esc(t.backup_fly)} ${esc(t.backup_size)}`)}
    ${row("Line", esc(t.line))}
    ${row("Leader", esc(t.leader))}
    ${row("Present", esc(t.presentation))}
    ${row("Depth", esc(t.depth))}
    ${row("Retrieve", esc(t.retrieve))}
    ${row("Why", `<span class="small">${esc(t.why)}</span>`)}
  </div></div>`;
}

function row(k, v) {
  return `<div class="row"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;
}

/** §35 — chosen from the water in front of you, from Python's technique table. */
export function pickTechnique(sp, cand) {
  const st = cand.statics || {};
  const units = st.units, genKnown = st.genKnown;
  const light = cand.fits.light;
  const clarity = cand.fits.clarity;
  let key = "default";
  const why = [];
  if (genKnown && units >= 2) {
    key = "heavy_current"; why.push(units + " units of push means depth and a big profile");
  } else if (genKnown && units === 0 && sp.key === "striped_bass") {
    key = "slack"; why.push("no generation — you have to go find them deep instead of on a seam");
  } else if (light && light.v >= 0.8 && /low-light/.test(light.why || "")) {
    key = "low_light"; why.push("low light is the window, so fish the top of the column");
  }
  if (clarity && /muddy/.test(clarity.why || "")) {
    why.push("muddy water — go bigger and darker than the size below suggests");
  }
  const t = Object.assign({}, sp.techniques[key] || sp.techniques.default);
  t.why = why.join("; ") || "the standard read for these conditions";
  return t;
}

function safetyBlock(data, z, cand, steps) {
  const claims = data.safety.filter((c) => c.zone_id === cand.zone);
  const exit = claims.filter((c) => ["safe_exit", "wade_cutoff", "release_arrival",
                                     "weather_hazard"].includes(c.kind));
  if (!exit.length && !(z.hazards || []).length) return "";
  return `<div class="card safety-card">
    <h3>Safety</h3>
    <ul style="margin:6px 0 0;padding-left:18px">
      ${exit.map((c) => `<li><b>${esc(c.text)}</b>
        <span class="tiny">${esc(c.source || "")}${c.bound === "earliest" ? " · conservative bound" : ""}</span></li>`).join("")}
      ${(z.hazards || []).map((h) => `<li>${esc(h)}</li>`).join("")}
    </ul>
    <p class="tiny" style="margin:10px 0 0">These sentences are fixed claims generated from
    instrument data. Nothing in this app — including the chat assistant — may restate,
    round or infer one.</p>
  </div>`;
}

function scoreBreakdown(cand) {
  return `<h2>Why this score</h2><div class="card bars">` + cand.lines.map((l) => {
    const pct = l.possible ? (l.earned / l.possible) * 100 : 0;
    return `<div class="bar${l.known ? "" : " unknown"}">
      <div class="nm">${esc(l.label)}</div>
      <div class="n">+${l.earned.toFixed(1)} / ${l.possible}</div>
      <div class="track"><div class="fill" style="width:${Math.max(0, Math.min(100, pct)).toFixed(0)}%"></div></div>
      <div class="why">${esc(l.why)}</div>
    </div>`;
  }).join("") + `<p class="tiny" style="margin-top:10px">Weights are published config, not
  code — see docs/SPECIES_SCORING.md. Hatched bars are components with no data: they score
  neutral and are charged against confidence instead.</p></div>`;
}

function evidenceDrawer(data, cand, species, sp) {
  const ids = data.evidence[cand.zone + "|" + species] || [];
  const claims = ids.map((i) => data.claims[i]).filter(Boolean);
  const z = cand.z;
  const ref = z.species_profiles[species] || {};
  return `<details class="drawer"><summary>Why this plan? <span class="tiny">sources, biology, model</span></summary>
    <div class="body">
      <h3>Live data</h3>
      <div class="fresh">${(data.freshness[cand.zone] || []).map((r) =>
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
      ${claims.length ? claims.map((c) => `<div class="cite">
        <span class="tier ${esc(c.source_tier)}">TIER ${esc(c.source_tier)}</span>
        ${esc(c.claim_text)}<br>
        <a href="${esc(safeUrl(c.source_url))}" target="_blank" rel="noopener">${esc(c.source_title || c.source_domain)}</a>
        <span class="tiny">${esc(TIER_LABEL[c.source_tier] || "")}${c.published_at ? " · " + esc(c.published_at) : ""}
        · confidence ${(c.confidence || 0).toFixed(2)}${c.safety_sensitive ? " · flagged safety-sensitive: numbers in it are NOT used" : ""}</span>
      </div>`).join("") : `<p class="tiny">No sourced claim mentions this water for this species.</p>`}
      <p class="tiny">Research provider: ${esc(data.research.provider)}
      ${data.research.enabled ? "" : "(disabled — the plan above is fully deterministic)"}.
      ${data.research.refreshedAt ? "Last refreshed " + esc(ago(data.research.refreshedAt)) + "." : ""}</p>

      <h3>Model</h3>
      <p class="small">Routing confidence: <b>${esc(z.modelConfidence)}</b>.
      ${esc(z.modelNote || "")} ${esc((z.arrival && z.arrival.note) || "")}</p>
      ${z.arrival && z.arrival.first ? `<p class="tiny">Arrival at ${esc(z.mfd)} miles below
      ${esc(z.dam || "the dam")}: earliest ${z.arrival.first.earliest_h} h, typical
      ${z.arrival.first.typical_h} h, later edge ${z.arrival.first.latest_h} h.
      ${esc(z.arrival.source || "")}</p>` : ""}
    </div></details>`;
}

function freshnessDrawer(cand, data, z) {
  return `<details class="drawer"><summary>Data freshness <span class="tiny">per signal</span></summary>
    <div class="body"><div class="fresh">${cand.confRows.map((r) =>
      `<div class="r"><span class="l">${esc(r.label)}</span>
       <span class="v state-${esc(r.state)}">${esc(r.state)}</span></div>
       <div class="tiny" style="margin:-2px 0 4px">${esc(r.detail || "")}</div>`).join("")}
    </div>
    <p class="tiny">Confidence is computed from exactly these rows. There is no single
    "updated" timestamp on purpose — a 4-minute-old gauge and a 14-day-old fishing report
    are not the same kind of fresh.</p></div></details>`;
}

function mapBlock(z, launch, takeout) {
  const geom = z.geometry;
  if (!geom || !geom.points || !geom.points.length) return "";
  return `<h2>Where</h2>
    <div id="map" data-geometry='${esc(JSON.stringify({
      geom, launch, takeout, name: z.name, access: z.access,
    }))}' role="region"
         aria-label="Map of ${esc(z.name)} — launch, target zone and access points"></div>
    <div class="maplegend">
      <span><i style="background:var(--go)"></i>launch</span>
      <span><i style="background:var(--accent)"></i>primary zone</span>
      <span><i style="background:var(--cond)"></i>other access</span>
    </div>
    <p class="tiny">${esc(geom.verified ? "Verified geometry: " : "Unverified geometry: ")}
    ${esc(geom.source || "")}. ${esc(geom.note || "")}
    ${geom.kind === "corridor" ? "This source describes a reach, so it is drawn as a corridor — not as a pin on a spot that no source named." : ""}</p>`;
}

function alternativesBlock(alts, data) {
  if (!alts.length) return "";
  return `<h2>Alternatives</h2><div class="card">` + alts.map((a) => {
    if (a.eliminated) {
      return `<div class="alt out"><div class="h"><div class="nm">${esc(a.name)}</div>
        <div class="sc">out</div></div><div class="why">${esc(a.reason)}</div></div>`;
    }
    return `<div class="alt"><div class="h"><div class="nm">${esc(a.name)}</div>
      <div class="sc">${a.score.toFixed(0)} / ${a.confidence.toFixed(0)} conf</div></div>
      <div class="why">${esc(a.why)}</div>
      ${a.detail_page ? `<div class="tiny"><a href="${esc(a.detail_page)}">Full river page →</a></div>` : ""}
      </div>`;
  }).join("") + `</div>`;
}

/** §46 — a research box, deliberately secondary to the planner. */
function askBlock(ctx) {
  const qs = [
    "Why " + ctx.cand.name + " instead of " + ((ctx.alternatives[0] || {}).name || "the alternative") + "?",
    "Where do they move if generation stops?",
    "Why did you pick this window?",
  ];
  return `<details class="drawer"><summary>Ask about this plan…
    <span class="tiny">answers come from this plan's own data</span></summary>
    <div class="body">
      <p class="small">RiverGuide answers from the exact plan above — the same zones, the
      same claim book, the same sources. It explains the recommendation; it does not make
      one of its own, and a deterministic verifier removes any water number it cannot
      trace to a claim.</p>
      <div class="chips">${qs.map((q) =>
        `<a class="chip" href="https://t.me/share/url?url=${encodeURIComponent(q)}"
            target="_blank" rel="noopener">${esc(q)}</a>`).join("")}</div>
      <p class="tiny">Opens RiverGuide on Telegram. The plan is at
      <code>${esc(ctx.cand.zone)}</code> — mention it and the bot will pull this exact plan.</p>
    </div></details>`;
}

/** §43 — freeze the prediction now; record the outcome later. */
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

/** §44 — model performance, shown rather than buried in a footer. */
export function renderScoreboard(sb) {
  const pct = (v) => (v === null || v === undefined ? "—" : Math.round(v * 100) + "%");
  const n = (v, d = 1) => (v === null || v === undefined ? "—" : Number(v).toFixed(d));
  return `<div class="card flat" style="margin-top:12px">
    <h3 style="margin-top:0">Model scoreboard</h3>
    <p class="tiny">${sb.fished} fished trip(s) of ${sb.trips} logged.</p>

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

    <h3>Score vs how the day actually was</h3>
    <div class="fresh"><div class="r"><span class="l">Correlation (n=${sb.rating.n})</span>
      <span class="v">${n(sb.rating.correlation, 2)}</span></div></div>
    <p class="small">${esc(sb.rating.verdict)}</p>

    <h3>Species recommendation</h3>
    <div class="fresh"><div class="r"><span class="l">Caught the target species (n=${sb.species.n})</span>
      <span class="v">${pct(sb.species.hitRate)}</span></div></div>
    ${sb.species.verdict ? `<p class="small">${esc(sb.species.verdict)}</p>` : ""}

    <h3>Confidence calibration</h3>
    <div class="fresh">${sb.calibration.bands.map((b) =>
      `<div class="r"><span class="l">${esc(b.band)} confidence (n=${b.n})</span>
       <span class="v">${n(b.meanRating, 2)} mean rating</span></div>`).join("")}</div>
    <p class="small">${esc(sb.calibration.verdict)}</p>
    <p class="tiny">Weakly validated numbers are shown here, not hidden. A measure with
    too few trips says so instead of printing a figure.</p>
  </div>`;
}

/** The outcome form for one logged trip. */
export function renderTrips(trips, fields) {
  if (!trips.length) return `<p class="tiny">Nothing logged yet on this device.</p>`;
  return trips.slice(0, 8).map((t) => {
    const p = t.prediction;
    const done = t.outcome && t.outcome.recordedAt;
    return `<div class="alt">
      <div class="h"><div class="nm">${esc(p.zoneName)} · ${esc(p.species)}</div>
        <div class="sc">${p.score} / ${Math.round(p.confidence)} conf</div></div>
      <div class="why">Predicted ${esc(p.verdict)} for ${esc(hm(p.window.start))}–${esc(hm(p.window.end))}${
        p.predictedArrival ? ` · water typical ${esc(hm(p.predictedArrival.typical))}` : ""}</div>
      ${done ? `<div class="tiny">Outcome recorded: rating ${esc(t.outcome.rating || "—")},
        ${esc(t.outcome.count || 0)} fish${t.outcome.fly_that_worked
          ? ", " + esc(t.outcome.fly_that_worked) : ""}</div>`
        : `<form class="tripform" data-trip="${esc(t.id)}" style="margin-top:8px">
             ${fields.map((f) => fieldHtml(f, t.id)).join("")}
             <button class="btn" type="submit" style="margin-top:8px">Save outcome</button>
           </form>`}
    </div>`;
  }).join("");
}

function fieldHtml(f, id) {
  const fid = "f-" + id + "-" + f.key;
  if (f.type === "bool") {
    return `<div class="field"><label for="${fid}">${esc(f.label)}</label>
      <select id="${fid}" name="${esc(f.key)}"><option value="">—</option>
      <option value="1">Yes</option><option value="0">No</option></select></div>`;
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

/** §40 — on-water mode: NOW / NEXT / WATER / FLY, big enough to read one-handed. */
export function renderOnWater(root, data, ctx, now) {
  const { cand, species, steps } = ctx;
  const sp = data.species[species];
  const past = steps.filter((s) => s.at !== null && s.at <= now);
  const nowStep = past.length ? past[past.length - 1] : steps[0];
  const next = steps.find((s) => s.at !== null && s.at > now);
  const safety = steps.find((s) => s.kind === TL.KINDS.SAFETY && s.at > now);
  const t = pickTechnique(sp, cand);
  const change = data.safety.filter((c) => c.zone_id === cand.zone &&
    ["generation_start", "generation_stop", "release_arrival"].includes(c.kind) &&
    (c.at || 0) > now).sort((a, b) => a.at - b.at)[0];

  root.innerHTML = `
    <div class="ow-block"><div class="k">Now</div>
      <div class="v">${esc(nowStep ? nowStep.title : cand.z.name)}</div>
      <div class="s">${esc(nowStep ? nowStep.detail : "")}</div></div>
    <div class="ow-block"><div class="k">Next</div>
      <div class="v">${next ? esc(next.title) : "Window complete"}</div>
      <div class="s">${next ? esc(hm(next.at)) + " · in " + esc(countdown(next.at, now)) : ""}</div></div>
    ${safety ? `<div class="ow-block safety"><div class="k">Alarm — safe exit</div>
      <div class="v">${esc(hm(safety.at))}</div>
      <div class="s">${esc(countdown(safety.at, now))} from now. ${esc(safety.detail)}</div></div>` : ""}
    <div class="ow-block"><div class="k">Water</div>
      <div class="v">${change ? "changes in " + esc(countdown(change.at, now)) : "no change forecast"}</div>
      <div class="s">${change ? esc(change.text) : "Inside the planning horizon nothing is scheduled to change."}</div></div>
    <div class="ow-block"><div class="k">Fly</div>
      <div class="v">${esc(t.primary_fly)}</div>
      <div class="s">${esc(t.primary_size)} · ${esc(t.primary_color)} · ${esc(t.line)}</div></div>
    <div class="ow-block"><div class="k">Map</div>
      <div class="s"><a href="${esc(mapsUrl(cand.z, ctx.craft))}" target="_blank" rel="noopener">Open the launch in Maps →</a></div></div>
    <button class="btn" id="ow-exit" style="margin-top:20px">Leave on-water mode</button>`;
}

function mapsUrl(z, craft) {
  const a = TL.pickLaunch(z, craft);
  if (!a || a.lat === null || a.lat === undefined) return "";
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
