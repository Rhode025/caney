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
    //
    // NOT `cf: {cacheTtl: 0}` as well: the Workers runtime rejects the pair outright
    // ("CacheTtl: 0, is not compatible with cache: no-store header"), which is invisible
    // to a local test and only shows up once deployed. It surfaced as a permanent
    // `unreachable` verdict — the watchdog reporting itself broken, which is the right
    // failure mode, but a watchdog that cries wolf every 15 minutes gets muted.
    const r = await fetch(STATUS_URL, { cache: "no-store" });
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

  // Record the verdict as ANNOUNCED only if it actually got out. Marking it announced on a
  // failed send would start the 6 h reminder clock on a notification nobody received — the
  // watchdog would go quiet believing it had spoken, which is the exact silent failure it
  // exists to prevent. A failed send instead leaves the state unchanged so the next tick
  // retries, and is remembered so `GET /` can show that the alert path is broken.
  if (!opts.dryRun) {
    const delivered = !alert || (sent && sent.ok);
    if (delivered && (verdict.state !== last.state || verdict.alert)) {
      await env.WATCHDOG.put(KEY, JSON.stringify({ state: verdict.state, at: now }));
    } else if (!delivered) {
      await env.WATCHDOG.put(KEY, JSON.stringify({
        ...last, lastSendError: { at: now, ...sent },
      }));
    }
  }

  return {
    checkedAt: new Date(now * 1000).toISOString(),
    state: verdict.state,
    // Surfaced so `GET /` answers "is the alert path working?" and not just "is the site ok?".
    // A watchdog that cannot deliver is as useless as no watchdog, and it cannot tell you so
    // through the channel that is broken.
    lastSendError: last.lastSendError || null,
    siteBuiltAgeSec: site ? now - site.built : null,
    oldestRiver: site ? site.oldestRiver : null,
    fetchError,
    wouldAlert: !!verdict.alert,
    alert: alert || null,
    sent,
    dryRun: !!opts.dryRun,
  };
}

// ntfy.sh: free, and reaches a phone with no account on the receiving end. NTFY_TOPIC is a
// Worker secret because on ntfy the topic name IS the credential.
//
// NTFY_TOKEN is not optional in practice. Anonymous publishing is rate-limited per source
// IP, and Workers egress from Cloudflare's shared pool — which ntfy has long since throttled.
// Measured 2026-08-24: every anonymous publish from the Worker returned 429, while the same
// request from a laptop returned 200. With a token the limit attaches to the ntfy account
// instead of the IP. Without one this function will fail, loudly, on every alert.
//
// Swap this function for any other channel — nothing else in the watchdog depends on it.
async function notify(env, alert) {
  const topic = env.NTFY_TOPIC;
  if (!topic) return { ok: false, error: "NTFY_TOPIC is not set" };
  const headers = {
    Title: alert.title,
    Priority: alert.priority || "default",
    Tags: alert.tags || "warning",
    Click: "https://github.com/Rhode025/caney/actions",
  };
  if (env.NTFY_TOKEN) headers.Authorization = "Bearer " + env.NTFY_TOKEN;
  try {
    const r = await fetch(`https://ntfy.sh/${topic}`, { method: "POST", body: alert.body, headers });
    const hint = r.status === 429 && !env.NTFY_TOKEN
      ? "rate-limited — set the NTFY_TOKEN secret (see watchdog/README.md)"
      : undefined;
    return { ok: r.ok, status: r.status, ...(hint ? { hint } : {}) };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
}
