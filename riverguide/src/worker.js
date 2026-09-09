/**
 * RiverGuide — a Telegram bot that answers from the River Monitor build.
 *
 * Telegram webhook -> access check -> slice the corpus -> Claude -> reply.
 *
 * The one rule that shapes everything: this bot must never invent a number. Generation
 * schedules, wade windows and arrival times decide whether someone is standing in a river
 * when the water comes up. So the model gets verbatim build data and is told to quote or
 * decline, the corpus carries its own rules, and every answer states how old the data is.
 * It may reason and extrapolate freely about everything else — that is why it is a model
 * and not a menu.
 */
import { resolveAccess, getUsage, recordUsage, overQuota } from "./access.js";
import { slice, tokenEstimate } from "./slice.js";
import { askModel, providerName } from "./model.js";
import { verify, repair } from "./guard.js";
import { detectPlanRequest, fetchPlan, planPayload, planZones } from "./plan.js";

const CORPUS_URL = "https://caney.pages.dev/bot.json";
const SITE = "https://caney.pages.dev";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return json(await health(env));

    if (request.method !== "POST") {
      return new Response("RiverGuide bot. See " + SITE, { status: 200 });
    }
    // Telegram's own check that the POST is really from Telegram.
    if (env.WEBHOOK_SECRET &&
        request.headers.get("x-telegram-bot-api-secret-token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    let update;
    try { update = await request.json(); } catch (e) { return new Response("ok"); }

    // Answer Telegram immediately and do the work after. A model call takes seconds;
    // Telegram retries anything slow, which would ask the same question twice.
    ctx.waitUntil(handle(update, env).catch((e) => console.error("handle", e)));
    return new Response("ok");
  },
};

async function handle(update, env) {
  const msg = update.message || update.edited_message;
  if (!msg || !msg.text) return;
  const chatId = msg.chat.id;
  const text = msg.text.trim();

  if (/^\/start\b/.test(text)) {
    return send(env, chatId,
      "🎣 <b>RiverGuide</b>\n\nAsk me about Middle Tennessee rivers — conditions, flies, " +
      "generation schedules, the week ahead.\n\n<i>Try:</i>\n" +
      "• What's fishing well right now?\n• What fly for the Caney today?\n" +
      "• How does the Duck look this weekend?\n\n" +
      `Everything comes from <a href="${SITE}">the site</a>, rebuilt hourly.`);
  }

  const access = await resolveAccess(chatId, env);
  if (!access.allowed) return send(env, chatId, access.message);

  const usage = await getUsage(env, chatId);
  const over = overQuota(access, usage);
  if (over) return send(env, chatId, over);

  const corpus = await loadCorpus(env);
  if (!corpus) {
    return send(env, chatId,
      "I can't reach the conditions data right now, so I'd only be guessing. " +
      `Try <a href="${SITE}">the site</a>.`);
  }

  const cut = slice(text, corpus);

  // §45 — a planning question is answered from the planner's own FishingPlan, not from a
  // second set of facts assembled here. The bot explains the deterministic recommendation.
  const req = detectPlanRequest(text);
  const plan = req ? await fetchPlan(req) : null;
  if (plan) {
    cut.payload.plan = planPayload(plan);
    cut.payload.planNote =
      "This plan was produced by the same planner the website runs. Explain it. Do not " +
      "rank the water yourself and do not substitute your own judgement for its verdict.";
    cut.claims = cut.claims.concat(plan.safety || []);
    cut.zones = [...new Set(cut.zones.concat(planZones(plan)))];
  }

  await sendTyping(env, chatId);

  const ageH = (Date.now() / 1000 - corpus.built) / 3600;
  const answer = await ask(env, text, cut, ageH);
  if (answer.error) return send(env, chatId, answer.error);

  await recordUsage(env, chatId, { tokensIn: answer.tokensIn, tokensOut: answer.tokensOut });
  await send(env, chatId, answer.text);
}

async function ask(env, question, cut, ageH) {
  const system =
    "You are RiverGuide, answering questions about fishing conditions on rivers in Middle " +
    "Tennessee, south-central Kentucky and north Alabama.\n\n" +
    "You answer ONLY from the DATA in the user message. It is a snapshot from a build, not " +
    "a live feed.\n\n" +
    "SAFETY — this is the rule that matters most. Each river carries `safetyClaims`: " +
    "immutable sentences generated from instrument data, each with an id and the exact " +
    "numbers it licenses. Generation times, wade windows, arrival times, flows and stages " +
    "may ONLY be stated by quoting a claim's `text` verbatim. Never restate, round, " +
    "average, convert or infer one, and never state such a number that is not inside a " +
    "claim for the river being asked about.\n" +
    "A deterministic verifier runs on your reply after you write it and DELETES any " +
    "safety-shaped sentence whose numbers are not in the claim book. It does not warn the " +
    "reader and leave your sentence standing — the sentence is gone. So if you do not have " +
    "a claim, say you do not have it.\n" +
    "Claims marked bound=\"earliest\" are conservative bounds. When someone asks when to " +
    "get out of the water, that is the one to give them — never the typical figure.\n\n" +
    "SPECIES live in `zones`, not in a river's `species` label. A zone can span two " +
    "rivers. The Cordell Hull tailwater down to the Caney Fork mouth is striped-bass water " +
    "even though the Cordell page is labelled smallmouth — answer from `zones`.\n\n" +
    "Everything else — which river suits the conditions, why a fly makes sense, how the week " +
    "is shaping up — reason about freely. That is what you are for. Be concrete and brief; " +
    "two or three short paragraphs at most.\n\n" +
    "If a river's waterModel.confidence is not \"measured\", its numbers are estimates: say " +
    "so when it affects the answer. If the data does not cover what was asked, say that " +
    "plainly rather than reaching.\n\n" +
    "If the data contains a `plan` object, THAT IS THE ANSWER. It came from the same " +
    "planner the website runs, over the same zones, species weights, transitions and " +
    "sourced evidence. Your job is to explain it, not to produce one of your own.\n" +
    "Lead with `plan.itinerary`: the times, the zones, the moves and what to do at each. " +
    "That itinerary is the product — do not summarise it away into 'fish the tailrace this " +
    "morning'. Give the segments in order, with their times.\n" +
    "Then explain WHY from plan.whyThisWon and plan.scoreBreakdown. Give opportunity, " +
    "forecast confidence and location confidence as SEPARATE numbers; a high opportunity " +
    "on low location confidence means something different, and saying so is the point.\n" +
    "If plan.availability is wider than the itinerary's span, say so: the rest of the time " +
    "is not worth fishing, and that is a real finding rather than an omission.\n" +
    "Mention plan.backupPlan when the reader asks what could go wrong, or when the plan " +
    "depends on generation. If the verdict is SKIP, say so plainly rather than talking " +
    "somebody into a drive.\n" +
    "Never rank the water yourself, never substitute your own zone, and never invent a " +
    "segment that is not in the itinerary.\n\n" +
    "Telegram HTML only: <b>, <i>, <a href>. No markdown, no headings, no bullet characters.";

  const content =
    `DATA (built ${cut.payload.builtIso}, ${ageH.toFixed(1)} hours ago):\n` +
    JSON.stringify(cut.payload) +
    `\n\nQUESTION: ${question}`;

  const r = await askModel(env, system, content);
  if (r.error) return { error: r.error };

  // Verify rather than trust, and FAIL CLOSED on anything safety-shaped. A safety
  // sentence whose numbers are not in the claim book for the rivers in scope is removed
  // before the reader sees it, and replaced with what the build actually says.
  const check = verify(r.text, cut.payload, cut.claims, cut.zones);
  if (check.removed.length) {
    console.warn("guard REMOVED", r.model, JSON.stringify(check.removed.slice(0, 2)),
                 "q=", question.slice(0, 80));
  }
  if (check.unsupported.length) {
    console.warn("guard unsupported", r.model, JSON.stringify(check.unsupported),
                 "q=", question.slice(0, 80));
  }
  const url = (cut.payload.rivers[0] && cut.payload.rivers[0].url) || SITE;
  return { text: repair(check, cut.claims, cut.zones, url),
           tokensIn: r.tokensIn, tokensOut: r.tokensOut,
           guard: { removed: check.removed.length, unsupported: check.unsupported.length } };
}

// The corpus rebuilds hourly, so a 10-minute cache costs at most a little staleness and
// saves a fetch on every message. Age is always reported from the corpus's own timestamp,
// never from when it was cached.
let CACHE = { at: 0, data: null };
async function loadCorpus(env) {
  if (CACHE.data && Date.now() - CACHE.at < 10 * 60 * 1000) return CACHE.data;
  try {
    const r = await fetch(CORPUS_URL, { cache: "no-store" });
    if (!r.ok) return CACHE.data;
    const d = await r.json();
    CACHE = { at: Date.now(), data: d };
    return d;
  } catch (e) {
    return CACHE.data;
  }
}

async function health(env) {
  const corpus = await loadCorpus(env);
  return {
    ok: !!corpus,
    corpusBuilt: corpus?.builtIso || null,
    corpusAgeH: corpus ? +((Date.now() / 1000 - corpus.built) / 3600).toFixed(2) : null,
    rivers: corpus?.rivers?.length ?? 0,
    fullCorpusTokens: corpus ? tokenEstimate(corpus) : null,
    provider: providerName(env),
    model: providerName(env) === "anthropic"
      ? (env.ANTHROPIC_MODEL || "claude-opus-5") : (env.WORKERS_MODEL || "@cf/meta/llama-3.3-70b-instruct-fp8-fast"),
    hasAiBinding: !!env.AI,
    hasKey: !!env.ANTHROPIC_API_KEY,
    hasBotToken: !!env.TELEGRAM_TOKEN,
    openToAll: String(env.OPEN_TO_ALL) === "1",
  };
}

async function tg(env, method, body) {
  return fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
async function send(env, chat_id, text) {
  const r = await tg(env, "sendMessage",
    { chat_id, text, parse_mode: "HTML", disable_web_page_preview: true });
  if (!r.ok) console.error("sendMessage", r.status, await r.text().catch(() => ""));
}
const sendTyping = (env, chat_id) =>
  tg(env, "sendChatAction", { chat_id, action: "typing" }).catch(() => {});
const json = (o) => new Response(JSON.stringify(o, null, 2),
  { headers: { "content-type": "application/json; charset=utf-8" } });
