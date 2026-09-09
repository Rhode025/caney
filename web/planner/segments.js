/**
 * Turning a won itinerary into instructions, in the browser. §9, §15, §37, §38.
 *
 * A mirror of caney/planner/segments.py. Like timeline.js before it, this is PRESENTATION
 * ASSEMBLY: every time comes from a Python-minted claim or from the window boundaries the
 * optimiser chose, every technique comes from Python's technique table, and every trigger
 * comes from the claim book or the emitted hourly weather. Nothing here decides anything.
 */
import { hm } from "./format.js";

export const LAUNCH_LEAD_MINUTES = 15;

const STILLWATER_KINDS = ["reservoir_arm", "creek_arm", "backwater", "flat", "point",
                          "grass_bed", "riprap"];

export function build(data, plan, species, craft, now) {
  const wins = plan.itinerary.windows;
  const trs = plan.itinerary.transitions;
  const segs = [];
  if (!wins.length) return segs;

  const zone0 = data.zones[wins[0].zone_id];
  const launch = pickAccess(zone0, craft);
  segs.push({
    type: "launch", start: wins[0].start - LAUNCH_LEAD_MINUTES * 60, end: wins[0].start,
    zone_id: zone0.id, zone_name: zone0.name, access_id: launch ? launch.id : "",
    instructions: "Launch at " + (launch ? launch.name : zone0.name),
    reason: (launch && launch.note) ||
      "No verified access is recorded for this craft — check locally before you go.",
    location_confidence: (zone0.location_confidence || {}).score,
    kind: "heuristic",
  });

  for (let i = 0; i < wins.length; i++) {
    const w = wins[i];
    const zone = data.zones[w.zone_id];
    const claims = data.safety.filter((c) => c.zone_id === zone.id);
    const tech = techniqueFor(data, species, zone, w, claims);
    const trigs = triggersFor(data, zone, w, claims);

    segs.push({
      type: "fish", start: w.start, end: w.end,
      zone_id: zone.id, zone_name: zone.name,
      access_id: (pickAccess(zone, craft) || {}).id || "",
      instructions: ((zone.holds_parts || {})[species] || [])[0] ||
                    (zone.holds_phrase || {})[species] || zone.name,
      reason: joinSentences(((zone.holds_parts || {})[species] || [])[1],
                            windowReason(w, zone, species)),
      expected_score: w.samples.length
        ? Math.round(10 * w.samples.reduce((a, b) => a + b, 0) / w.samples.length) / 10 : null,
      confidence: w.confidence,
      location_confidence: (zone.location_confidence || {}).score,
      technique: tech, triggers: trigs, kind: "heuristic",
    });

    for (const t of trigs) {
      if (t.at && t.at > w.start && t.at < w.end && t.changes_technique) {
        segs.push({
          type: "change_technique", start: t.at, end: w.end,
          zone_id: zone.id, zone_name: zone.name,
          instructions: t.then, reason: "If " + t.if,
          claim_ids: t.claim_ids || [], kind: t.kind || "forecast", triggers: [],
        });
      }
    }

    if (i < wins.length - 1) {
      const nxt = wins[i + 1];
      const tr = trs[i];
      const moveEnd = Math.min(nxt.start, w.end + tr.minutes * 60);
      segs.push({
        type: "move", start: w.end, end: moveEnd,
        zone_id: nxt.zone_id, zone_name: data.zones[nxt.zone_id].name,
        instructions: "Move to " + data.zones[nxt.zone_id].name,
        reason: moveReason(data, w, nxt, tr), kind: "heuristic", triggers: [],
      });
      const idle = (nxt.start - moveEnd) / 60;
      if (idle > 5) {
        segs.push({
          type: "wait", start: moveEnd, end: nxt.start,
          zone_id: nxt.zone_id, zone_name: data.zones[nxt.zone_id].name,
          instructions: Math.round(idle) + " minutes spare — rig for the next zone",
          reason: "You arrive before the next window opens. That is deliberate: being in " +
                  "position early costs nothing, being late costs the window.",
          kind: "heuristic", triggers: [],
        });
      }
    }
  }

  const first = wins[0], last = wins[wins.length - 1];
  for (const zid of new Set(wins.map((w) => w.zone_id))) {
    for (const c of data.safety) {
      if (c.zone_id !== zid || c.kind !== "safe_exit" || !c.at) continue;
      if (c.at < first.start - 3600 || c.at > last.end + 5400) continue;
      segs.push({
        type: "safety_exit", start: c.at, end: c.at,
        zone_id: zid, zone_name: data.zones[zid].name,
        instructions: c.text,
        reason: "This uses the EARLIEST modelled arrival minus a 30-minute margin, not the " +
                "typical one.",
        claim_ids: [c.id], kind: "safety", triggers: [],
      });
    }
  }

  segs.push({
    type: "end", start: last.end, end: last.end,
    zone_id: last.zone_id, zone_name: data.zones[last.zone_id].name,
    instructions: "Primary opportunity is effectively over",
    reason: endReason(data, last, plan), kind: "heuristic", triggers: [],
  });

  segs.sort((a, b) => (a.start - b.start) ||
    ((a.type === "safety_exit" ? 0 : 1) - (b.type === "safety_exit" ? 0 : 1)));
  return segs;
}

/** §37 — the presentation for THIS window, plus the trigger that changes it. */
export function techniqueFor(data, species, zone, window, claims) {
  const sp = data.species[species];
  const st = data.statics[zone.id + "|" + species] || {};
  const units = st.units, genKnown = st.genKnown;
  const stillwater = STILLWATER_KINDS.includes(zone.kind);
  const lowLight = isLowLight(data, zone, window);
  const w = zone.water || {};
  const muddy = (w.clarity || {}).value === "muddy" ||
                ((w.flow_trend || {}).state === "known" && w.flow_trend.value === "rising");

  let key = "default";
  const why = [];
  const needsCurrent = species === "striped_bass";
  if (genKnown && units !== null && units !== undefined && units >= 2) {
    key = "heavy_current";
    why.push(units + " units of push means depth and a big profile");
  } else if (genKnown && units === 0 && needsCurrent) {
    key = "slack";
    why.push("no generation — go find them deep instead of on a seam");
  } else if (stillwater && lowLight) {
    key = "low_light";
    why.push("still water at low light — fish the top of the column");
  } else if (lowLight) {
    key = "low_light";
    why.push("low light is the window, so fish the top of the column");
  } else if (stillwater) {
    key = "slack";
    why.push("no current here — the cover is the structure, not the seam");
  }
  if (muddy) why.push("stained water — go bigger and darker than the size below suggests");

  const t = Object.assign({}, sp.techniques[key] || sp.techniques.default);
  const backupKey = (key === "heavy_current" || key === "default") ? "slack" : "default";
  const b = sp.techniques[backupKey] || sp.techniques.default;
  t.why = why.join("; ") || "the standard read for these conditions";
  t.backup_presentation = {
    fly: b.primary_fly, size: b.primary_size, color: b.primary_color, line: b.line,
    presentation: b.presentation, depth: b.depth, retrieve: b.retrieve,
  };
  t.switch_trigger = switchTrigger(key);
  return t;
}

function switchTrigger(key) {
  if (key === "heavy_current") {
    return "If the current slackens — a unit comes off, or the seam stops holding a line — " +
           "drop to the backup and work it deeper and slower.";
  }
  if (key === "slack") {
    return "If they start generating, switch to the current presentation and get on the " +
           "seam before the bait does.";
  }
  if (key === "low_light") {
    return "Once the sun is on the water, go subsurface: same fly family, heavier line, deeper.";
  }
  return "If forty minutes pass with nothing, change one variable — depth first, then size, " +
         "then colour. Not all three.";
}

/** §38 — explicit condition triggers, from the claim book and the hourly weather. */
export function triggersFor(data, zone, window, claims) {
  const out = [];
  for (const c of claims) {
    if (!c.at) continue;
    if (c.at < window.start - 1800 || c.at > window.end + 1800) continue;
    if (c.kind === "generation_stop") {
      out.push({ if: "generation stops (" + hm(c.at) + ")", at: c.at,
        then: "The seam dies within the hour. Go deeper and slower on the same water, or " +
              "move to the next zone.",
        kind: "forecast", claim_ids: [c.id], changes_technique: true });
    } else if (c.kind === "generation_start") {
      out.push({ if: "generation starts (" + hm(c.at) + ")", at: c.at,
        then: "Current arrives on the schedule above. Get on the seam. If you are wading, " +
              "the safe-exit step is the one that matters, not this one.",
        kind: "forecast", claim_ids: [c.id], changes_technique: true });
    } else if (c.kind === "release_arrival") {
      out.push({ if: "the released water reaches this reach", at: c.at, then: c.text,
        kind: "deterministic", claim_ids: [c.id], changes_technique: true });
    }
  }
  const rows = (data.weatherHours[zone.river] || [])
    .filter((h) => h.epoch >= window.start && h.epoch <= window.end);
  if (rows.length) {
    const wind = Math.max(...rows.map((r) => r.wind_speed || 0));
    const gust = Math.max(...rows.map((r) => r.wind_gust || 0));
    if (wind >= 15) {
      out.push({ if: "wind holds above " + Math.round(wind) + " mph", at: null,
        then: "Shorten the leader, go heavier, and fish the bank the wind is pushing into " +
              "rather than fighting it.",
        kind: "forecast", claim_ids: [], changes_technique: true });
    }
    if (gust >= 28) {
      out.push({ if: "gusts reach " + Math.round(gust) + " mph on open water", at: null,
        then: "Get off the main lake and fish the protected arms.",
        kind: "forecast", claim_ids: [], changes_technique: false });
    }
    const storm = rows.find((r) => r.thunderstorm);
    if (storm) {
      out.push({ if: "thunderstorms reach the water", at: storm.epoch,
        then: "Terminate the plan. Get off the water and off the bank.",
        kind: "safety", claim_ids: [], changes_technique: false });
    }
    const clouds = rows.map((r) => r.cloud_cover).filter((c) => c !== null && c !== undefined);
    if (clouds.length && Math.max(...clouds) - Math.min(...clouds) >= 45) {
      out.push({ if: "the cloud breaks and the sun gets on the water", at: null,
        then: "Move off the flat into the shade lines and the deeper edge of the same " +
              "structure.",
        kind: "forecast", claim_ids: [], changes_technique: true });
    }
  }
  return out;
}

/** Join fragments so the second one starts like a sentence. Mirrors segments._join. */
function joinSentences(...parts) {
  const out = [];
  for (let p of parts) {
    p = (p || "").trim();
    if (!p) continue;
    if (out.length) {
      p = p[0].toUpperCase() + p.slice(1);
      if (!/[.!?]$/.test(out[out.length - 1])) out[out.length - 1] += ".";
    }
    out.push(p);
  }
  const text = out.join(" ");
  return !text || /[.!?]$/.test(text) ? text : text + ".";
}

function windowReason(w, zone, species) {
  const ref = (zone.species_profiles || {})[species] || {};
  const bits = [];
  if (w.samples && w.samples.length) {
    bits.push("peaks at " + Math.round(w.peak_score) + " and never drops below " +
              Math.round(w.floor_score) + " across the " + Math.round(w.duration_minutes) +
              " minutes");
  }
  if (ref.pattern) bits.push(ref.pattern);
  return bits.join("; ");
}

/** §15 — say what CHANGES, not just where to go. */
export function moveReason(data, before, after, transition) {
  const drop = before.samples[before.samples.length - 1] || 0;
  const rise = after.samples[0] || 0;
  const toName = data.zones[after.zone_id].name;
  const fromName = data.zones[before.zone_id].name;
  const core = rise > drop + 4
    ? `${fromName} is falling away — it is down to about ${Math.round(drop)} by then, ` +
      `while ${toName} is running ${Math.round(rise)} and holds it for another ` +
      `${Math.round(after.duration_minutes)} minutes.`
    : `${fromName} is finished by then. ${toName} is the best remaining water inside your ` +
      `window and holds for another ${Math.round(after.duration_minutes)} minutes.`;
  const prov = { known: "on a known route", estimated: "estimated, no verified route",
                 unknown: "route unknown" }[transition.provenance] || transition.provenance;
  return core + " The move costs " + Math.round(transition.minutes) + " minutes " + prov +
         " — " + (transition.detail || transition.mode);
}

function endReason(data, last, plan) {
  const arr = data.safety.find((c) => c.zone_id === last.zone_id &&
                                      c.kind === "release_arrival" && c.at);
  if (arr && arr.at <= last.end + 1800) {
    return "The released water is in this reach by now — the fishery you planned is gone.";
  }
  if (last.samples.length &&
      last.samples[last.samples.length - 1] < last.peak_score * 0.8) {
    return "The window has fallen to about " +
           Math.round(last.samples[last.samples.length - 1]) + " from a peak of " +
           Math.round(last.peak_score) + ". Past this you are fishing memory, not conditions.";
  }
  if (last.end < plan.requestedEnd - 900) {
    return "You have time left, and nothing worth spending it on: no candidate scores well " +
           "enough in the rest of your window to be worth the fuel.";
  }
  return "End of the requested window.";
}

function isLowLight(data, zone, window) {
  const sun = data.sun[zone.river + "|" + isoDate(window.start)] || {};
  if (!sun.sunrise || !sun.sunset) return false;
  const dawn = [sun.sunrise - 2400, sun.sunrise + 5400];
  const dusk = [sun.sunset - 5400, sun.sunset + 2400];
  const ov = Math.max(0, Math.min(dawn[1], window.end) - Math.max(dawn[0], window.start)) +
             Math.max(0, Math.min(dusk[1], window.end) - Math.max(dusk[0], window.start));
  return ov >= 0.4 * Math.min(window.end - window.start, 7200);
}

export function pickAccess(zone, craft) {
  const opts = (zone.access || []).filter(
    (a) => craft === "any" || (a.craft || []).includes(craft));
  const list = opts.length ? opts : (zone.access || []);
  if (!list.length) return null;
  return list.slice().sort((a, b) =>
    ((a.verified === b.verified) ? 0 : (a.verified ? -1 : 1)) ||
    ((a.river_miles_from_dam || 0) - (b.river_miles_from_dam || 0)))[0];
}

function isoDate(epoch) {
  const d = new Date(epoch * 1000), p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}
