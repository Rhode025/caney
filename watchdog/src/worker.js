/**
 * Cloudflare Worker — the deploy watchdog for River Monitor (#2).
 *
 * Runs on Cloudflare's cron, NOT in GitHub Actions, and never calls GitHub. That is the
 * whole point: on 2026-08-21 Actions stopped running and anything watching from inside it
 * would have been just as dead as the deploy it was meant to watch.
 *
 * Free tier throughout: Workers cron triggers and the KV free plan both cost nothing, and
 * this writes to KV only when the verdict changes.
 */
import { decide } from "./check.js";

const STATUS_URL = "https://caney.pages.dev/site.json";
const KEY = "watchdog:last";

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(run(env));
  },

  // GET / runs the same check and shows the verdict, so the watchdog itself can be
  // eyeballed without waiting for a cron tick. ?test=1 forces a notification through,
  // which is how you confirm the alert path before trusting it.
  async fetch(request, env) {
    const url = new URL(request.url);
    const result = await run(env, { dryRun: !url.searchParams.has("send"), force: url.searchParams.has("test") });
    return new Response(JSON.stringify(result, null, 2), {
      headers: { "content-type": "application/json; charset=utf-8" },
    });
  },
};

async function run(env, opts = {}) {
  const now = Math.floor(Date.now() / 1000);

  let site = null, fetchError = null;
  try {
    // cache:no-store — a cached copy of the status file would report the site as fresh
    // long after it stopped rebuilding, which is precisely the failure being watched for.
    const r = await fetch(STATUS_URL, { cf: { cacheTtl: 0 }, cache: "no-store" });
    if (!r.ok) fetchError = `HTTP ${r.status}`;
    else site = await r.json();
  } catch (e) {
    fetchError = String(e && e.message || e);
  }

  let last = {};
  try { last = JSON.parse(await env.WATCHDOG.get(KEY) || "{}"); } catch (e) { /* first run */ }

  const verdict = decide(site, fetchError, now, last);
  const alert = opts.force
    ? { title: "River Monitor watchdog test", body: "If you are reading this, the alert path works.", priority: "default", tags: "white_check_mark" }
    : verdict.alert;

  let sent = null;
  if (alert && !opts.dryRun) sent = await notify(env, alert);

  // Only record when the verdict changes, so the reminder clock measures time since we
  // last SPOKE rather than time since the last cron tick.
  if (!opts.dryRun && (verdict.state !== last.state || verdict.alert)) {
    await env.WATCHDOG.put(KEY, JSON.stringify({ state: verdict.state, at: now }));
  }

  return {
    checkedAt: new Date(now * 1000).toISOString(),
    state: verdict.state,
    siteBuiltAgeSec: site ? now - site.built : null,
    oldestRiver: site ? site.oldestRiver : null,
    fetchError,
    wouldAlert: !!verdict.alert,
    alert: alert || null,
    sent,
    dryRun: !!opts.dryRun,
  };
}

// ntfy.sh: no account, no key, works to a phone with the free app. NTFY_TOPIC is set as a
// Worker secret so the topic (which is effectively the password) is not in the repo.
// Swap this function for any other channel — nothing else in the watchdog depends on it.
async function notify(env, alert) {
  const topic = env.NTFY_TOPIC;
  if (!topic) return { ok: false, error: "NTFY_TOPIC is not set" };
  try {
    const r = await fetch(`https://ntfy.sh/${topic}`, {
      method: "POST",
      body: alert.body,
      headers: {
        Title: alert.title,
        Priority: alert.priority || "default",
        Tags: alert.tags || "warning",
        Click: "https://github.com/Rhode025/caney/actions",
      },
    });
    return { ok: r.ok, status: r.status };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
}
