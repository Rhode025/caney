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
import Anthropic from "@anthropic-ai/sdk";
import { resolveAccess, getUsage, recordUsage, overQuota } from "./access.js";
import { slice, tokenEstimate } from "./slice.js";

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
  await sendTyping(env, chatId);

  const ageH = (Date.now() / 1000 - corpus.built) / 3600;
  const answer = await ask(env, text, cut, ageH);
  if (answer.error) return send(env, chatId, answer.error);

  await recordUsage(env, chatId, { tokensIn: answer.tokensIn, tokensOut: answer.tokensOut });
  await send(env, chatId, answer.text);
}

async function ask(env, question, cut, ageH) {
  if (!env.ANTHROPIC_API_KEY) return { error: "The bot isn't finished being set up yet." };
  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY });

  const system =
    "You are RiverGuide, answering questions about fishing conditions on rivers in Middle " +
    "Tennessee, south-central Kentucky and north Alabama.\n\n" +
    "You answer ONLY from the DATA in the user message. It is a snapshot from a build, not " +
    "a live feed.\n\n" +
    "SAFETY — this is the rule that matters most. Dam generation schedules, wade windows, " +
    "arrival times and flow figures decide whether someone is standing in a river when the " +
    "water rises. Quote those EXACTLY as the data gives them, or say you do not have them. " +
    "Never restate, round, average, convert or infer one. If asked whether it is safe to " +
    "wade, give the data's own words and tell them to verify the release schedule before " +
    "they get in.\n\n" +
    "Everything else — which river suits the conditions, why a fly makes sense, how the week " +
    "is shaping up, what to do with a forecast — reason about freely. That is what you are " +
    "for. Be concrete and brief; two or three short paragraphs at most.\n\n" +
    "If a river's waterModel.confidence is not \"measured\", its numbers are estimates: say " +
    "so when it affects the answer. If the data does not cover what was asked, say that " +
    "plainly rather than reaching. Link the river's url when you name one.\n\n" +
    "Telegram HTML only: <b>, <i>, <a href>. No markdown, no headings, no bullet characters.";

  const content =
    `DATA (built ${cut.payload.builtIso}, ${ageH.toFixed(1)} hours ago):\n` +
    JSON.stringify(cut.payload) +
    `\n\nQUESTION: ${question}`;

  try {
    const r = await client.beta.messages.create({
      model: "claude-opus-5",
      max_tokens: 1200,
      // A retrieval-and-explain task over supplied data. Low effort keeps it fast and cheap
      // without costing accuracy — the hard reasoning already happened at build time.
      output_config: { effort: "low" },
      // Opus 5 can decline; without this the request simply stops and the user gets silence.
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      system,
      messages: [{ role: "user", content }],
    });
    if (r.stop_reason === "refusal") {
      return { error: "I can't answer that one. Try asking about conditions, flies or access." };
    }
    const out = r.content.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
    return {
      text: out || "I don't have anything useful on that.",
      tokensIn: r.usage?.input_tokens || 0,
      tokensOut: r.usage?.output_tokens || 0,
    };
  } catch (e) {
    const m = String(e?.message || e);
    if (/credit balance|billing/i.test(m)) {
      return { error: "The bot is out of API credit. (Owner: top up at console.anthropic.com.)" };
    }
    if (/rate|429/.test(m)) return { error: "Too many questions at once — try again in a moment." };
    console.error("anthropic", m);
    return { error: "Something went wrong reaching the model. Try again shortly." };
  }
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
