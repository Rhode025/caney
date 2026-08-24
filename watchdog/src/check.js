/**
 * The watchdog decision, kept free of Cloudflare so it can be tested anywhere.
 *
 * Why this exists (#2): on 2026-08-21 the deploy stopped and nothing said so for 55 hours.
 * The site kept serving a page that looked current. Any monitor living inside GitHub Actions
 * would have been dead for the same reason the deploy was, so the check has to run somewhere
 * else and must never call GitHub to do its job.
 */

export const STALE_SEC = 3 * 3600;      // the site should rebuild hourly; 3h means ~3 missed runs
export const RIVER_LAG_SEC = 6 * 3600;  // one river far behind the rest = that generator is failing
export const REMIND_SEC = 6 * 3600;     // while broken, re-alert at most this often

/**
 * Decide what (if anything) to say, given the site's status endpoint and when we last spoke.
 *
 * @param {object|null} site   parsed /site.json, or null if it could not be fetched
 * @param {string|null} fetchError  why the fetch failed, when site is null
 * @param {number} nowSec      current epoch seconds
 * @param {object} last        {state, at} from storage — the previous verdict
 * @returns {{state:string, alert:null|{title:string, body:string, priority:string, tags:string}}}
 */
export function decide(site, fetchError, nowSec, last = {}) {
  const prev = last.state || "ok";
  const since = last.at ? nowSec - last.at : Infinity;

  // The endpoint being unreachable is itself a failure worth hearing about — it means the
  // site is down, not merely stale. Distinguished from stale so the message is actionable.
  if (!site || typeof site.built !== "number") {
    return emit("unreachable", prev, since, {
      title: "River Monitor is unreachable",
      body: `Could not read the freshness endpoint: ${fetchError || "no build timestamp in the response"}. ` +
            `The site may be down, or the deploy may have published a broken build.`,
      priority: "high",
      tags: "rotating_light",
    });
  }

  const age = nowSec - site.built;

  if (age > STALE_SEC) {
    return emit("stale", prev, since, {
      title: `River Monitor has not rebuilt in ${hours(age)}`,
      body: `Last build ${site.builtIso || new Date(site.built * 1000).toISOString()} (${hours(age)} ago). ` +
            `The site is still serving that build, so every arrival time and live reading on it is ` +
            `from then. Check the Actions run history — billing, a disabled schedule, or a failing build.`,
      priority: "high",
      tags: "warning",
    });
  }

  // The deploy ran, but one generator fell back to cache and its river is hours behind.
  // Quieter than a dead deploy, because twelve rivers are still correct.
  if (typeof site.oldestRiverAgeSec === "number" && site.oldestRiverAgeSec > RIVER_LAG_SEC) {
    return emit("river-lag", prev, since, {
      title: `${site.oldestRiver} is ${hours(site.oldestRiverAgeSec)} behind the rest of the site`,
      body: `The site rebuilt ${hours(age)} ago but ${site.oldestRiver} did not refresh with it — ` +
            `its generator is probably failing upstream and falling back to cache.`,
      priority: "default",
      tags: "arrow_down",
    });
  }

  // Recovered: say so once, so a silent channel is never ambiguous between "fine" and "broken".
  if (prev !== "ok") {
    return {
      state: "ok",
      alert: {
        title: "River Monitor is publishing again",
        body: `Built ${hours(age)} ago across ${site.rivers} rivers.`,
        priority: "low",
        tags: "white_check_mark",
      },
    };
  }
  return { state: "ok", alert: null };
}

// Alert on entering a bad state, then at most every REMIND_SEC while it persists — so a
// two-day outage is a handful of notifications rather than one every cron tick.
function emit(state, prev, since, alert) {
  const isNew = state !== prev;
  return { state, alert: isNew || since >= REMIND_SEC ? alert : null };
}

function hours(sec) {
  const h = sec / 3600;
  if (h < 1) return `${Math.round(sec / 60)} min`;
  if (h < 48) return `${h < 10 ? h.toFixed(1).replace(/\.0$/, "") : Math.round(h)} h`;
  return `${Math.round(h / 24)} days`;
}
