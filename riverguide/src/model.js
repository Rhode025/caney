/**
 * Which model answers. One function, two providers, chosen by config.
 *
 * Measured 2026-08-24 on the real task (slice + the adversarial safety prompts):
 *
 *   llama-3.3-70b-instruct-fp8-fast   1.4-3.0s   held the safety line on all four
 *   llama-4-scout-17b-16e-instruct    0.7-7.9s   held the safety line on all four
 *   mistral-small-3.1-24b-instruct    0.5-1.6s   held the safety line on all four
 *   qwen3.8-27b                       9-18s      returned an EMPTY response every time
 *
 * All three working open models refused to convert cfs, refused to guess a generation time,
 * and refused to invent a river that was not in the data. That is why Workers AI is the
 * default: it runs inside this Worker, needs no second API key, and is free at this volume.
 *
 * Claude remains available and is not merely a fallback — MODEL_PROVIDER=anthropic switches
 * the whole bot. Keep it wired: a four-prompt bake-off is evidence, not a safety suite
 * (issue #40), and if the open models turn out to drift on harder questions the escape
 * hatch is a config change rather than a rewrite.
 *
 * Whichever answers, guard.js checks the reply afterwards. That is what makes this a cost
 * decision instead of a safety one.
 */
import Anthropic from "@anthropic-ai/sdk";

export const DEFAULT_WORKERS_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";

export function providerName(env) {
  return String(env.MODEL_PROVIDER || "workersai").toLowerCase();
}

/**
 * @returns {{text?: string, error?: string, tokensIn: number, tokensOut: number, model: string}}
 */
export async function askModel(env, system, content) {
  return providerName(env) === "anthropic"
    ? askAnthropic(env, system, content)
    : askWorkersAI(env, system, content);
}

async function askWorkersAI(env, system, content) {
  const model = env.WORKERS_MODEL || DEFAULT_WORKERS_MODEL;
  if (!env.AI) return { error: "No AI binding configured.", tokensIn: 0, tokensOut: 0, model };
  try {
    const r = await env.AI.run(model, {
      messages: [{ role: "system", content: system }, { role: "user", content }],
      max_tokens: 500,
      // Low but not zero: the answer should be steady across identical questions, while
      // still reading as a person rather than a form letter.
      temperature: 0.3,
    });
    const text = String(r?.response ?? "").trim();
    if (!text) {
      // qwen3.8-27b does exactly this. Say so rather than sending an empty message.
      return { error: "The model returned nothing.", tokensIn: 0, tokensOut: 0, model };
    }
    const u = r?.usage || {};
    return {
      text,
      tokensIn: u.prompt_tokens || Math.round(content.length / 4),
      tokensOut: u.completion_tokens || Math.round(text.length / 4),
      model,
    };
  } catch (e) {
    return { error: String(e?.message || e), tokensIn: 0, tokensOut: 0, model };
  }
}

async function askAnthropic(env, system, content) {
  const model = env.ANTHROPIC_MODEL || "claude-opus-5";
  if (!env.ANTHROPIC_API_KEY) {
    return { error: "No Anthropic key configured.", tokensIn: 0, tokensOut: 0, model };
  }
  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY });
  try {
    const r = await client.beta.messages.create({
      model,
      max_tokens: 1200,
      // Retrieval and explanation over supplied data — the hard reasoning already happened
      // at build time, so low effort keeps it fast without costing accuracy.
      output_config: { effort: "low" },
      // Opus 5 can decline; without this the request simply stops and the user hears nothing.
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      system,
      messages: [{ role: "user", content }],
    });
    if (r.stop_reason === "refusal") {
      return { error: "I can't answer that one.", tokensIn: 0, tokensOut: 0, model };
    }
    const text = r.content.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
    return {
      text: text || "I don't have anything useful on that.",
      tokensIn: r.usage?.input_tokens || 0,
      tokensOut: r.usage?.output_tokens || 0,
      model,
    };
  } catch (e) {
    const m = String(e?.message || e);
    if (/credit balance|billing/i.test(m)) {
      return { error: "The bot is out of API credit.", tokensIn: 0, tokensOut: 0, model };
    }
    if (/rate|429/.test(m)) {
      return { error: "Too many questions at once — try again shortly.", tokensIn: 0, tokensOut: 0, model };
    }
    return { error: m.slice(0, 160), tokensIn: 0, tokensOut: 0, model };
  }
}
