# Deploy watchdog

Answers one question every 15 minutes: **is the site still rebuilding?**

On 2026-08-21 GitHub Actions stopped running (billing) and the site served a 55-hour-old
build that still called Friday "Today". Nothing said so. This is what says so.

## The rule it exists for

**The watchdog must not share a failure domain with the thing it watches.** A monitor running
as a GitHub Action would have been just as dead as the deploy it was meant to watch. So it
runs on Cloudflare's cron, and it never calls GitHub to do its job — it only *links* to the
Actions page in the notification, for you to click.

## What it checks

It reads `https://caney.pages.dev/site.json`, which `hq.py` writes last in the build:

```json
{"built": 1787535863, "builtIso": "...", "rivers": 13,
 "oldestRiver": "caney", "oldestRiverAgeSec": 36}
```

| State | Meaning | Priority |
|---|---|---|
| `stale` | no rebuild in 3 h — the site rebuilds hourly, so ~3 missed runs | high |
| `unreachable` | endpoint down, or the deploy published something broken | high |
| `river-lag` | the site rebuilt but one generator is 6 h behind — it is failing upstream and falling back to cache | default |
| `ok` | quiet, except one message on recovery so silence is never ambiguous | low |

Alerts on entering a bad state, then at most every 6 h while it persists. A repeat of the
55-hour outage is ~10 notifications, not 220.

## Deploy

Needs Node 20+ (`nvm install 20`) and your Cloudflare login.

```bash
cd watchdog
nvm use 20                                  # wrangler needs Node 20+; 18 is not enough
npx wrangler login                          # opens the browser once
npx wrangler kv namespace create WATCHDOG   # paste the printed id into wrangler.toml
npx wrangler deploy                         # must come BEFORE the secret — it creates the Worker
npx wrangler secret put NTFY_TOPIC          # any long random string — see below
```

Order matters: `secret put` targets a Worker that already exists, and `deploy` fails while
`wrangler.toml` still holds the placeholder KV id. So: namespace → id → deploy → secret.
The Worker runs without the secret; it just reports `NTFY_TOPIC is not set` instead of
sending, which is a safe state to be in for the minute between those two commands.

**The alert channel is Telegram.** Free, pushes to a phone, and its limits are per bot rather
than per source IP — which is what matters here.

1. In Telegram, message **@BotFather** → `/newbot` → give it a name. It replies with a token
   like `8123456789:AAH...`.
2. `npx wrangler secret put TELEGRAM_TOKEN` and paste that.
3. **Send your new bot any message** (search its @username, tap Start). Telegram will not
   let a bot message you first.
4. Get the chat id:
   `curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | grep -o '"id":[0-9-]*' | head -1`
5. `npx wrangler secret put TELEGRAM_CHAT_ID` and paste the number.

To use a different channel — Discord, Slack, Pushover — replace `notify()` in
`src/worker.js`; nothing else depends on it.

### Why not ntfy.sh

It was the first choice and it does not work from a Worker. The free tier reports
`limits.basis: "ip"` and enforces that **even for authenticated requests**, so a valid access
token changed nothing: every publish from the Worker returned `429`, while the identical
request from a laptop returned `200`. Cloudflare Workers egress from a shared pool ntfy has
long since throttled. A structural incompatibility, not a misconfiguration — recorded here so
nobody spends another hour on it. Their paid tier flips the basis to `account` and would work.

### If an alert cannot be delivered

The watchdog does **not** mark a verdict as announced unless the send actually succeeded.
Otherwise the 6 h reminder clock would start on a notification nobody received and it would
go quiet believing it had spoken — the exact silent failure it exists to prevent. A failed
send is retried on the next tick and recorded, so `GET /` reports it:

```json
"lastSendError": {"at": 1787574887, "ok": false, "status": 429, "hint": "..."}
```

Worth glancing at whenever you check the verdict: `state: "ok"` means the *site* is healthy,
not that the alarm can reach you.

## Verify it works

```bash
node test.mjs                             # the real decision logic, incl. against the live endpoint
curl "https://<worker>.workers.dev/"          # current verdict, sends nothing
curl "https://<worker>.workers.dev/?test=1&send"  # forces one notification through
```

The last one is the check that matters — a watchdog whose alert path has never fired is not
a watchdog. Do it once at deploy, and again if you ever change the topic.

To exercise the real path end to end: disable the scheduled workflow in GitHub, wait three
hours, confirm the alert arrives, re-enable, confirm the recovery message.

## Related tickets

- **#5** a freshness probe run *by* this watchdog rather than by CI
- **#3** a second publisher (launchd + wrangler) so a dead deploy is survivable, not just visible
- **#6** the 60-day public-repo cron auto-disable — the next way this can happen silently
