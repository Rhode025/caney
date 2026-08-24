/**
 * Who may use the bot, and how much.
 *
 * Built now for one user, shaped for opening to anyone later. The whole policy is this file:
 * opening up is a config change (`OPEN_TO_ALL=1`) plus filling in one function, not a
 * refactor of the request path. Everything downstream only ever sees {allowed, tier, limit}.
 *
 * Identity is the Telegram chat id — stable, already authenticated by Telegram, and the same
 * value across bots. That is the account key today and stays the account key when a
 * subscription record hangs off it.
 *
 * Usage is metered from day one even though nobody is billed. Without a history of what a
 * real question costs there is no basis for pricing later, and metering added after launch
 * never covers the period you most want to look at.
 */

export const TIERS = {
  // The owner. No cap — this is the person paying the Anthropic bill.
  owner: { dailyQuestions: Infinity, dailyTokens: Infinity, label: "owner" },
  // What a signed-up user would get. Not reachable yet; sized so a day of real use costs
  // a few cents, which is the number a paid tier has to beat.
  free: { dailyQuestions: 20, dailyTokens: 60000, label: "free" },
  paid: { dailyQuestions: 400, dailyTokens: 1500000, label: "paid" },
};

const DAY = () => new Date().toISOString().slice(0, 10);

/** Owner chat ids, comma-separated, from a Worker secret. */
function owners(env) {
  return String(env.OWNER_CHAT_IDS || "").split(",").map((s) => s.trim()).filter(Boolean);
}

/**
 * Decide whether this chat may ask, and under which tier.
 *
 * When opening to anyone, the only change here is replacing the `unknown` branch with a
 * lookup of whatever identity system is chosen — a Claude sign-in, a Stripe customer, a
 * signup table in KV. The shape returned must not change.
 */
export async function resolveAccess(chatId, env) {
  const id = String(chatId);
  if (owners(env).includes(id)) return { allowed: true, tier: "owner", ...TIERS.owner };

  if (String(env.OPEN_TO_ALL) === "1") {
    // Placeholder for the paid path: a subscription record keyed by chat id.
    const sub = await kvGet(env, `sub:${id}`);
    const tier = sub && sub.status === "active" ? "paid" : "free";
    return { allowed: true, tier, ...TIERS[tier] };
  }

  return {
    allowed: false,
    tier: "none",
    reason: "private",
    message:
      "This bot is not open to the public yet.\n\n" +
      "Everything it knows is already on the site — conditions, flies, generation " +
      "schedules and the week ahead for 13 rivers:\nhttps://caney.pages.dev",
  };
}

/** Per-day usage for a chat. Reset is by calendar day in UTC — simple, and good enough. */
export async function getUsage(env, chatId) {
  const u = await kvGet(env, `use:${chatId}`);
  if (!u || u.day !== DAY()) return { day: DAY(), questions: 0, tokensIn: 0, tokensOut: 0 };
  return u;
}

export async function recordUsage(env, chatId, { tokensIn = 0, tokensOut = 0 } = {}) {
  const u = await getUsage(env, chatId);
  u.questions += 1;
  u.tokensIn += tokensIn;
  u.tokensOut += tokensOut;
  // 40 days: long enough to see a month of behaviour, short enough to stay tiny.
  await kvPut(env, `use:${chatId}`, u, 40 * 86400);
  return u;
}

/** Checked BEFORE the model call, so a runaway chat cannot spend past its cap. */
export function overQuota(access, usage) {
  if (!isFinite(access.dailyQuestions)) return null;
  if (usage.questions >= access.dailyQuestions) {
    return `That is ${access.dailyQuestions} questions today, which is the ${access.label} limit. It resets at midnight UTC.`;
  }
  if (usage.tokensIn + usage.tokensOut >= access.dailyTokens) {
    return `You have used today's ${access.label} allowance. It resets at midnight UTC.`;
  }
  return null;
}

async function kvGet(env, key) {
  if (!env.RG) return null;
  try { return JSON.parse((await env.RG.get(key)) || "null"); } catch (e) { return null; }
}
async function kvPut(env, key, val, ttl) {
  if (!env.RG) return;
  try { await env.RG.put(key, JSON.stringify(val), ttl ? { expirationTtl: ttl } : undefined); }
  catch (e) { /* metering must never break an answer */ }
}
