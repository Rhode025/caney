/**
 * Assembling the itinerary in the browser. §9, §39.
 *
 * EVERY TIME IN HERE CAME FROM PYTHON. The safety claims carry their own epochs and their
 * own wording; this file places them in order and labels which kind of statement each one
 * is. It never computes an arrival, never rounds a claim, and never writes a number that
 * is not already inside a claim's text.
 */
import { hm } from "./format.js";

export const KINDS = {
  DETERMINISTIC: "deterministic",
  ASTRONOMICAL: "astronomical",
  FORECAST: "forecast",
  HEURISTIC: "heuristic",
  SAFETY: "safety",
};

function claimsFor(data, zoneId) {
  return data.safety.filter((c) => c.zone_id === zoneId);
}

function pick(claims, kind, after) {
  for (const c of claims) {
    if (c.kind !== kind) continue;
    if (after !== undefined && (c.at || 0) < after) continue;
    return c;
  }
  return null;
}

export function pickLaunch(zone, craft) {
  const opts = (zone.access || []).filter(
    (a) => craft === "any" || (a.craft || []).includes(craft));
  const list = opts.length ? opts : (zone.access || []);
  if (!list.length) return null;
  return list.slice().sort((a, b) =>
    (a.verified === b.verified ? 0 : a.verified ? -1 : 1) ||
    ((a.river_miles_from_dam || 0) - (b.river_miles_from_dam || 0)))[0];
}

export function build(data, cand, species, craft) {
  const zone = cand.z;
  const { start, end } = cand.window;
  const claims = claimsFor(data, cand.zone);
  const ref = zone.species_profiles[species] || {};
  const steps = [];
  const sun = data.sun[zone.river + "|" + isoDate(start)] || {};
  const moon = data.lunar[zone.river + "|" + isoDate(start)] || {};
  const launch = pickLaunch(zone, craft);

  steps.push({
    at: start - 900, kind: KINDS.HEURISTIC,
    title: "Launch at " + (launch ? launch.name : zone.name),
    detail: launch ? (launch.note || "") :
      "No verified access recorded for this craft — check locally before you go.",
  });

  steps.push({
    at: start, until: Math.min(end, start + 2400), kind: KINDS.HEURISTIC,
    title: "Fish " + ((ref.habitat && ref.habitat[0]) || (zone.habitat || [])[0] || zone.name),
    detail: ref.holds || "Work the primary habitat for this species on this water.",
  });

  if (sun.sunrise && sun.sunrise >= start - 3600 && sun.sunrise <= end) {
    steps.push({ at: sun.sunrise, kind: KINDS.ASTRONOMICAL, title: "Sunrise",
      detail: "The low-light edge closes over the next hour or so — take the best water " +
              "first, not last." });
  }
  if (sun.sunset && sun.sunset >= start && sun.sunset <= end + 3600) {
    steps.push({ at: sun.sunset, kind: KINDS.ASTRONOMICAL, title: "Sunset",
      detail: "Last light is the second-best window of the day for this fish." });
  }
  for (const w of moon.major_windows || []) {
    if (w.start >= start && w.start <= end) {
      steps.push({ at: w.start, until: w.end, kind: KINDS.HEURISTIC, title: "Solunar major",
        detail: "A weak, secondary signal — worth being on your best water for it, never " +
                "worth choosing a worse day for. Approximate to ±40 min." });
    }
  }

  const genStart = pick(claims, "generation_start", start - 7200);
  const genStop = pick(claims, "generation_stop", start - 7200);
  const arrival = pick(claims, "release_arrival", start - 7200);
  const safeExit = pick(claims, "safe_exit", start - 7200);

  if (arrival && Array.isArray(arrival.value)) {
    const [e, m, l] = arrival.value;
    if (e >= start - 3600 && e <= end + 5400) {
      steps.push({ at: m, kind: KINDS.DETERMINISTIC,
        title: "Released water reaches this zone", detail: arrival.text,
        uncertainty: "earliest " + hm(e) + " · typical " + hm(m) + " · later edge " + hm(l),
        claimIds: [arrival.id] });
    }
  }
  if (safeExit && safeExit.at && safeExit.at >= start - 3600 && safeExit.at <= end + 5400) {
    steps.push({ at: safeExit.at, kind: KINDS.SAFETY,
      title: "SAFE EXIT — be out of the water",
      detail: safeExit.text + " This uses the EARLIEST modelled arrival minus a " +
              "30-minute margin, not the typical one.",
      claimIds: [safeExit.id] });
  }

  const moveTo = ref.move_to || [];
  let moveAt;
  if (arrival && Array.isArray(arrival.value) &&
      arrival.value[0] > start && arrival.value[0] < end) {
    moveAt = Math.max(start + 900, arrival.value[0] - 1200);
  } else if (genStop && genStop.at > start && genStop.at < end) {
    moveAt = genStop.at;
  } else {
    moveAt = start + (end - start) * 0.55;
  }
  if (moveTo.length) {
    const nz = data.zones[moveTo[0]];
    steps.push({ at: moveAt, kind: KINDS.HEURISTIC,
      title: "Move toward " + (nz ? nz.name : moveTo[0]),
      detail: "Second zone for this species when the first stops producing or the water " +
              "state changes.", zoneId: moveTo[0] });
  } else {
    // Nowhere better to go still needs a move: four hours on one shoal wastes a window.
    const habitat = (ref.habitat && ref.habitat.length ? ref.habitat : zone.habitat) || [];
    const second = habitat[1] || habitat[0];
    if (second) {
      steps.push({ at: moveAt, kind: KINDS.HEURISTIC,
        title: "Rotate to the next " + second,
        detail: "No second zone beats this one in this window, so move WITHIN it: leave " +
                "the water you have covered and find the same structure again downstream.",
        zoneId: cand.zone });
    }
  }

  const branches = [];
  if (genStop) {
    const nz = data.zones[moveTo[0]];
    branches.push({
      if: "generation stops" + (genStop.at ? " (" + hm(genStop.at) + ")" : ""),
      then: "The seam dies within the hour. Move to " +
            (nz ? nz.name : "the nearest structure") + " and fish it slow and deep.",
    });
  }
  if (genStart) {
    branches.push({
      if: "generation starts" + (genStart.at ? " (" + hm(genStart.at) + ")" : ""),
      then: "Current arrives on the schedule above. If you are wading, the SAFE EXIT step " +
            "is the one that matters, not this one.",
    });
  }
  const storms = claims.filter((c) => c.kind === "weather_hazard");
  const g = data.gates[cand.zone];
  const stormy = g && (g.storm || []).some((v, i) => {
    const t = data.horizon.t0 + i * 3600;
    return v === 1 && t >= start && t < end;
  });
  if (storms.length || stormy) {
    branches.push({ if: "thunderstorms reach the water",
      then: "Terminate the plan. Get off the water and off the bank." });
  }
  if (branches.length) {
    steps.push({ at: null, kind: KINDS.FORECAST, title: "If conditions change",
      detail: "Branches, in the order they are most likely to fire.", branches });
  }

  // The next water change, even when it lands outside the window (mirrors timeline.py).
  if (!steps.some((s) => s.kind === KINDS.DETERMINISTIC)) {
    const later = claims
      .filter((c) => ["generation_start", "generation_stop", "release_arrival"].includes(c.kind))
      .filter((c) => c.at !== null && c.at !== undefined && c.at > end)
      .sort((a, b) => a.at - b.at)[0];
    if (later) {
      steps.push({ at: later.at, kind: KINDS.DETERMINISTIC,
        title: "Next water change — after your window",
        detail: later.text + " Nothing scheduled changes this reach inside the window you " +
                "asked for.", claimIds: [later.id] });
    } else if (zone.generationForecast && zone.generationForecast.state === "known") {
      steps.push({ at: end, kind: KINDS.DETERMINISTIC,
        title: "No water change is scheduled",
        detail: "The release feed shows no generation change for this reach inside the " +
                "planning horizon. Verify it before you get in anyway." });
    } else {
      // A free-flowing river's deterministic anchor is the gauge, not a release schedule.
      const flow = pick(claims, "flow");
      if (flow) {
        steps.push({ at: start, kind: KINDS.DETERMINISTIC,
          title: "The water you are walking into",
          detail: flow.text + " There is no dam on this water, so the gauge is the whole " +
                  "story — and it moves with the rain, not with a schedule.",
          claimIds: [flow.id] });
      }
    }
  }

  steps.push({ at: end, kind: KINDS.HEURISTIC, title: "Primary window ends",
    detail: closeReason(arrival, genStop, sun, start, end) });

  steps.sort((a, b) => (a.at === null) - (b.at === null) || (a.at || 0) - (b.at || 0));
  return steps;
}

function closeReason(arrival, genStop, sun, start, end) {
  if (arrival && Array.isArray(arrival.value) && arrival.value[0] <= end) {
    return "The released water is in this reach by now — the fishery you planned is gone.";
  }
  if (sun.sunrise && end > sun.sunrise + 10800) {
    return "The low-light edge is long gone and the light is against you.";
  }
  if (genStop && genStop.at >= start && genStop.at <= end) {
    return "Generation ends and the current that concentrated the fish goes with it.";
  }
  return "End of the requested window.";
}

function isoDate(epoch) {
  const d = new Date(epoch * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

/**
 * §41 — one .ics per alarm-worthy SEGMENT. Safety alarms use the conservative time.
 *
 * Expanded for 2.1: an itinerary has more moments worth an alarm than a single-zone plan
 * did — the launch, every move, every technique switch, and the safe exit. A phone alarm
 * is the only mechanism that rings with no signal, a locked screen and the browser closed,
 * which is all three conditions at the river.
 */
export function icsFor(steps, title) {
  const pad = (n) => String(n).padStart(2, "0");
  const stamp = (t) => {
    const d = new Date(t * 1000);
    return d.getUTCFullYear() + pad(d.getUTCMonth() + 1) + pad(d.getUTCDate()) + "T" +
           pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + "00Z";
  };
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Caney//Planner//EN",
                 "CALSCALE:GREGORIAN", "METHOD:PUBLISH"];
  let n = 0;
  const ALARMED = ["launch", "move", "safety_exit", "change_technique", "fish"];
  for (const s of steps) {
    const at = s.at !== undefined ? s.at : s.start;
    if (at === null || at === undefined) continue;
    const kind = s.type || s.kind;
    const label = s.instructions || s.title || "";
    if (!ALARMED.includes(kind) && ![KINDS.SAFETY, KINDS.DETERMINISTIC].includes(kind) &&
        !/^(Launch|Move|Solunar|Sunrise)/.test(label)) continue;
    n++;
    // Safety gets a longer lead: ten minutes is not enough warning to walk out of a river.
    const lead = kind === "safety_exit" || kind === KINDS.SAFETY ? "-PT25M" : "-PT10M";
    lines.push("BEGIN:VEVENT",
      "UID:caney-" + Math.round(at) + "-" + n + "@caney.pages.dev",
      "DTSTAMP:" + stamp(Date.now() / 1000),
      "DTSTART:" + stamp(at),
      "DTEND:" + stamp((s.end && s.end > at ? s.end : at + 900)),
      "SUMMARY:" + ics(title + " — " + label),
      "DESCRIPTION:" + ics((s.reason || s.detail || "") +
                           (s.uncertainty ? " (" + s.uncertainty + ")" : "")),
      "BEGIN:VALARM", "TRIGGER:" + lead, "ACTION:DISPLAY",
      "DESCRIPTION:" + ics(label), "END:VALARM", "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}

function ics(s) {
  return String(s).replace(/([,;\\])/g, "\\$1").replace(/\n/g, "\\n");
}
