/**
 * Research Intelligence worker. §16, §17, §18, §21, §42, §43, §44, §77.
 *
 * It accepts a QUESTION ABOUT EVIDENCE and returns normalised, sourced ResearchClaims.
 * It never returns freeform fishing advice, and it never fetches a URL a caller supplies.
 *
 * Security posture (§44), stated plainly because it is the point of the service existing:
 *
 *   * OPENAI_API_KEY is a Worker secret and never leaves this process.
 *   * The only outbound request is to the model provider, with a query THIS CODE built
 *     from a validated species key and validated zone ids. There is no path from caller
 *     input to an arbitrary fetch.
 *   * Every request is validated against a fixed species list and a zone-id character
 *     class before anything is spent.
 *   * Rate limits are per-IP and per-zone-per-day, and a global daily cap sits above both.
 *   * Stored claim text is length-capped and stored as text; nothing is rendered as HTML
 *     here, and every consumer escapes it.
 *
 * Failure posture (§43, §58, §63): every endpoint answers 200 with `degraded: true` rather
 * than an error status. Research going down must never take the planner with it.
 */
import { dedupe, disagreements, isStale, toClaim } from "./claims.js";
import { PRIMARY_DOMAINS, buildQueries, searchOpenAI } from "./search.js";

const SPECIES = ["striped_bass", "smallmouth", "largemouth", "trout"];
const ZONE_RE = /^[a-z0-9_]{3,48}$/;
const MAX_ZONES = 6;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const cors = {
      "access-control-allow-origin": env.ALLOW_ORIGIN || "*",
      "access-control-allow-headers": "content-type",
      "access-control-allow-methods": "GET,POST,OPTIONS",
    };
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

    try {
      if (url.pathname === "/health") return json(await health(env), cors);
      if (url.pathname === "/claims") return json(await readClaims(env, url), cors);
      if (url.pathname === "/research" && request.method === "POST") {
        return json(await research(request, env, ctx, false), cors);
      }
      if (url.pathname === "/refresh" && request.method === "POST") {
        return json(await research(request, env, ctx, true), cors);
      }
      return json({ error: "not found", endpoints: ["/health", "/claims", "/research", "/refresh"] },
                  cors, 404);
    } catch (e) {
      // §43 — never propagate a failure as a failure. The planner must keep working.
      console.error("worker", e && e.stack);
      return json({ claims: [], meta: { degraded: true, error: String(e && e.message) } }, cors);
    }
  },
};

async function research(request, env, ctx, force) {
  const t0 = Date.now();
  let body;
  try { body = await request.json(); } catch (e) { body = {}; }

  const species = String(body.species || "");
  if (!SPECIES.includes(species)) {
    return { claims: [], meta: { degraded: true, error: "unknown species" } };
  }
  const zoneIds = (Array.isArray(body.zone_ids) ? body.zone_ids : [])
    .map(String).filter((z) => ZONE_RE.test(z)).slice(0, MAX_ZONES);
  if (!zoneIds.length) {
    return { claims: [], meta: { degraded: true, error: "no valid zone_ids" } };
  }
  const date = /^\d{4}-\d{2}-\d{2}$/.test(String(body.date || "")) ? body.date
    : new Date().toISOString().slice(0, 10);
  const month = Number(date.slice(5, 7));
  const context = sanitiseContext(body.context);
  const now = Date.now() / 1000;

  // 1. Cache (§21). Keyed by species, zones, date bucket and query family.
  const cacheKey = ["r", species, zoneIds.join(","), date, force ? "f" : "c"].join(":");
  if (!force && env.CACHE) {
    const hit = await env.CACHE.get(cacheKey, "json");
    if (hit) {
      await bump(env, { cache_hits: 1 });
      return { claims: hit.claims, meta: { ...hit.meta, cached: true,
                                           latencyMs: Date.now() - t0 } };
    }
  }

  // 2. Do we already hold fresh enough evidence? (§42 — refresh only when needed.)
  const stored = await selectClaims(env, species, zoneIds);
  const fresh = stored.filter((c) => !isStale(c.claim_type, c.retrieved_at, now));
  if (!force && fresh.length >= 3) {
    const out = shape(fresh, month, zoneIds, { source: "store", searched: 0 });
    if (env.CACHE) await env.CACHE.put(cacheKey, JSON.stringify(out), { expirationTtl: 3600 });
    return { ...out, meta: { ...out.meta, latencyMs: Date.now() - t0 } };
  }

  // 3. Budget and enablement (§43).
  const gate = await budgetGate(env, zoneIds[0], force);
  if (!gate.ok) {
    return shape(stored, month, zoneIds,
                 { source: "store", degraded: true, error: gate.reason, searched: 0 });
  }
  if (String(env.RESEARCH_ENABLED || "") !== "1" || !env.OPENAI_API_KEY) {
    return shape(stored, month, zoneIds, {
      source: "store", degraded: true, searched: 0,
      error: "research disabled — no key configured, or RESEARCH_ENABLED is not 1",
    });
  }

  // 4. Search. Primary (agency domains) first, always (§19).
  const queries = buildQueries(species, zoneIds, context, date, env);
  const accepted = [];
  const audit = [];
  let searched = 0;

  for (const q of queries.slice(0, force ? 4 : 3)) {
    const started = Date.now();
    const r = await searchOpenAI(env, q.query, q.primaryOnly ? allowedDomains(env) : null);
    searched++;
    const rows = [];
    const rejects = [];
    for (const f of (r.findings || [])) {
      const res = toClaim(f, { species, zoneIds, month, now,
                               primaryOnly: q.primaryOnly, waterbodyIds: [] });
      if (res.claim) rows.push(res.claim); else rejects.push(res.reject);
    }
    accepted.push(...rows);
    audit.push({
      at: Math.round(now), species, zone_ids: JSON.stringify(zoneIds), family: q.family,
      query: q.query, provider: "openai", model: r.model || "",
      latency_ms: Date.now() - started,
      source_urls: JSON.stringify((r.findings || []).map((f) => f && f.url).filter(Boolean)),
      accepted: rows.length, rejected: rejects.length,
      reject_reasons: JSON.stringify([...new Set(rejects)].slice(0, 6)),
      tokens_in: r.tokensIn || 0, tokens_out: r.tokensOut || 0, error: r.error || null,
    });
    // §19/§20 — only fall through to the secondary tier when primary found nothing.
    if (q.primaryOnly && rows.length >= 3) break;
  }

  const merged = dedupe([...accepted, ...stored]);
  await Promise.all([
    writeClaims(env, dedupe(accepted)),
    writeAudit(env, audit),
    bump(env, { queries: searched,
                tokens_in: audit.reduce((a, x) => a + x.tokens_in, 0),
                tokens_out: audit.reduce((a, x) => a + x.tokens_out, 0) }),
  ]);

  const out = shape(merged, month, zoneIds,
                    { source: "search", searched, errors: audit.filter((a) => a.error).length });
  if (env.CACHE) await env.CACHE.put(cacheKey, JSON.stringify(out), { expirationTtl: 6 * 3600 });
  return { ...out, meta: { ...out.meta, latencyMs: Date.now() - t0 } };
}

/** What the planner receives: claims, their disagreements, and how fresh any of it is. */
function shape(claims, month, zoneIds, meta) {
  const sorted = claims.slice().sort((a, b) => b.combined_confidence - a.combined_confidence);
  const newest = sorted.reduce((a, c) => Math.max(a, c.retrieved_at || 0), 0);
  return {
    claims: sorted.slice(0, 24),
    disagreements: disagreements(sorted.slice(0, 24)),
    meta: {
      count: sorted.length, month, zoneIds,
      newestRetrievedAt: newest || null,
      tiers: countBy(sorted, (c) => c.source_tier),
      ...meta,
    },
  };
}

function sanitiseContext(ctx) {
  const out = {};
  if (!ctx || typeof ctx !== "object") return out;
  for (const k of ["generation", "season", "clarity", "trend"]) {
    if (typeof ctx[k] === "string" && /^[a-z_ ]{1,24}$/i.test(ctx[k])) out[k] = ctx[k];
  }
  if (typeof ctx.water_temp_f === "number" && ctx.water_temp_f > 20 && ctx.water_temp_f < 100) {
    out.water_temp_f = Math.round(ctx.water_temp_f);
  }
  return out;
}

function allowedDomains(env) {
  const extra = String(env.EXTRA_PRIMARY_DOMAINS || "").split(",")
    .map((s) => s.trim()).filter(Boolean);
  return PRIMARY_DOMAINS.concat(extra);
}

// ── storage ────────────────────────────────────────────────────────────────

async function selectClaims(env, species, zoneIds) {
  if (!env.DB) return [];
  const rows = await env.DB.prepare(
    "SELECT * FROM claims WHERE species = ? AND superseded_by IS NULL " +
    "ORDER BY combined_confidence DESC LIMIT 200").bind(species).all();
  return (rows.results || [])
    .map(hydrate)
    .filter((c) => !zoneIds.length || c.zone_ids.some((z) => zoneIds.includes(z)));
}

function hydrate(r) {
  return { ...r,
    zone_ids: safeJson(r.zone_ids, []), waterbody_ids: safeJson(r.waterbody_ids, []),
    valid_months: safeJson(r.valid_months, []),
    safety_sensitive: !!r.safety_sensitive };
}

async function writeClaims(env, claims) {
  if (!env.DB || !claims.length) return;
  const stmt = env.DB.prepare(
    "INSERT INTO claims (id, species, claim_type, zone_ids, waterbody_ids, " +
    "geographic_description, claim, source_url, source_title, source_domain, source_tier, " +
    "published_at, retrieved_at, valid_months, season, geographic_confidence, " +
    "seasonal_relevance, recency, source_quality, combined_confidence, safety_sensitive) " +
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) " +
    // §78 — revisiting a known source refreshes its metadata, it does not add a row.
    "ON CONFLICT DO UPDATE SET retrieved_at = excluded.retrieved_at, " +
    "recency = excluded.recency, combined_confidence = excluded.combined_confidence, " +
    "published_at = COALESCE(excluded.published_at, claims.published_at)");
  await env.DB.batch(claims.map((c) => stmt.bind(
    c.id, c.species, c.claim_type, JSON.stringify(c.zone_ids),
    JSON.stringify(c.waterbody_ids), c.geographic_description, c.claim, c.source_url,
    c.source_title, c.source_domain, c.source_tier, c.published_at, c.retrieved_at,
    JSON.stringify(c.valid_months), c.season, c.geographic_confidence, c.seasonal_relevance,
    c.recency, c.source_quality, c.combined_confidence, c.safety_sensitive ? 1 : 0)));
}

async function writeAudit(env, rows) {
  if (!env.DB || !rows.length) return;
  const stmt = env.DB.prepare(
    "INSERT INTO searches (at, species, zone_ids, family, query, provider, model, " +
    "latency_ms, source_urls, accepted, rejected, reject_reasons, tokens_in, tokens_out, " +
    "error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)");
  await env.DB.batch(rows.map((r) => stmt.bind(
    r.at, r.species, r.zone_ids, r.family, r.query, r.provider, r.model, r.latency_ms,
    r.source_urls, r.accepted, r.rejected, r.reject_reasons, r.tokens_in, r.tokens_out,
    r.error)));
}

// ── §43 · cost control ─────────────────────────────────────────────────────

function today() { return new Date().toISOString().slice(0, 10); }

async function budgetGate(env, zoneId, force) {
  if (!env.DB) return { ok: true };
  const day = today();
  const row = await env.DB.prepare("SELECT * FROM budget WHERE day = ?").bind(day).first();
  const used = (row && row.queries) || 0;
  const cap = Number(env.MAX_QUERIES_PER_DAY || 400);
  if (used >= cap) {
    return { ok: false, reason: "daily research query cap reached (" + cap + ")" };
  }
  const perZone = Number(env.MAX_QUERIES_PER_ZONE_DAY || 12);
  const zr = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM searches WHERE at > ? AND zone_ids LIKE ?")
    .bind(Math.round(Date.now() / 1000) - 86400, "%" + zoneId + "%").first();
  if (zr && zr.n >= perZone * (force ? 2 : 1)) {
    return { ok: false, reason: "per-zone daily research cap reached (" + perZone + ")" };
  }
  return { ok: true };
}

async function bump(env, delta) {
  if (!env.DB) return;
  const day = today();
  await env.DB.prepare(
    "INSERT INTO budget (day, queries, tokens_in, tokens_out, cache_hits) " +
    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(day) DO UPDATE SET " +
    "queries = queries + excluded.queries, tokens_in = tokens_in + excluded.tokens_in, " +
    "tokens_out = tokens_out + excluded.tokens_out, " +
    "cache_hits = cache_hits + excluded.cache_hits")
    .bind(day, delta.queries || 0, delta.tokens_in || 0, delta.tokens_out || 0,
          delta.cache_hits || 0).run();
}

// ── read-only endpoints ────────────────────────────────────────────────────

async function readClaims(env, url) {
  const species = url.searchParams.get("species") || "";
  if (!SPECIES.includes(species)) return { claims: [], meta: { error: "unknown species" } };
  const zone = url.searchParams.get("zone");
  const zoneIds = zone && ZONE_RE.test(zone) ? [zone] : [];
  const rows = await selectClaims(env, species, zoneIds);
  return shape(rows, new Date().getUTCMonth() + 1, zoneIds, { source: "store", searched: 0 });
}

async function health(env) {
  const out = {
    ok: true,
    enabled: String(env.RESEARCH_ENABLED || "") === "1" && !!env.OPENAI_API_KEY,
    model: env.OPENAI_RESEARCH_MODEL || "gpt-4.1-mini",
    hasKey: !!env.OPENAI_API_KEY, hasDb: !!env.DB, hasCache: !!env.CACHE,
    caps: { perDay: Number(env.MAX_QUERIES_PER_DAY || 400),
            perZoneDay: Number(env.MAX_QUERIES_PER_ZONE_DAY || 12) },
  };
  if (env.DB) {
    const b = await env.DB.prepare("SELECT * FROM budget WHERE day = ?").bind(today()).first();
    const c = await env.DB.prepare("SELECT COUNT(*) AS n FROM claims").first();
    const s = await env.DB.prepare(
      "SELECT COUNT(*) AS n, MAX(at) AS last FROM searches").first();
    out.today = b || { day: today(), queries: 0, tokens_in: 0, tokens_out: 0, cache_hits: 0 };
    out.claims = (c && c.n) || 0;
    out.searches = (s && s.n) || 0;
    out.lastSearchAt = (s && s.last) || null;
    const q = out.today.queries || 0, h = out.today.cache_hits || 0;
    out.cacheHitRate = (q + h) ? Math.round(100 * h / (q + h)) / 100 : null;
  }
  return out;
}

// ── helpers ────────────────────────────────────────────────────────────────

function countBy(rows, keyOf) {
  const out = {};
  for (const r of rows) { const k = keyOf(r); out[k] = (out[k] || 0) + 1; }
  return out;
}
function safeJson(s, fallback) {
  try { return JSON.parse(s); } catch (e) { return fallback; }
}
function json(o, headers, status = 200) {
  return new Response(JSON.stringify(o, null, 2), {
    status, headers: { "content-type": "application/json; charset=utf-8", ...headers } });
}
