/**
 * Query construction and the OpenAI web-search call. §17, §18, §19, §20, §21.
 *
 * THE RULE THAT SHAPES EVERY QUERY (§21): we do not ask an AI where the fish are. We ask
 * for EVIDENCE, from named authorities, about a named piece of water, in a named month —
 * and then combine what comes back with deterministic live data ourselves.
 *
 *   bad   "Where should I catch stripers today?"
 *   good  "Striped bass Cordell Hull Dam Caney Fork Tennessee — TWRA seasonal
 *          distribution, current and generation response, September"
 */

/** §19 — primary search hits these first, always. Extended by EXTRA_PRIMARY_DOMAINS. */
export const PRIMARY_DOMAINS = [
  "tn.gov", "tnwildlife.org", "tva.com", "usgs.gov", "usace.army.mil", "weather.gov",
  "noaa.gov", "water.noaa.gov", "fws.gov", "ky.gov", "fw.ky.gov", "alabama.gov",
  "outdooralabama.com",
];

/** Human names for zone ids, so a query says "Cordell Hull" and not "cordell_tailwater". */
export const ZONE_TERMS = {
  carthage_confluence: "Cordell Hull Dam Caney Fork confluence Carthage Cumberland River",
  cordell_tailwater: "Cordell Hull Dam tailwater Carthage Cumberland River",
  cordell_creek_arms: "Cordell Hull Reservoir Defeated Creek",
  cordell_granville_reach: "Cordell Hull Reservoir Granville Gainesboro Celina",
  caney_upper: "Caney Fork River Center Hill Dam tailwater",
  caney_middle: "Caney Fork River Stonewall Gordonsville",
  caney_lower: "Caney Fork River Carthage Cumberland confluence",
  oldhickory_tailrace: "Old Hickory Dam tailwater Cumberland River Nashville",
  oldhickory_creek_arms: "Old Hickory Reservoir Bledsoe Station Camp Drakes Creek",
  oldhickory_embayments: "Old Hickory Reservoir lower embayments Shutes Branch",
  cheatham_tailrace: "Cheatham Dam tailwater Cumberland River Ashland City",
  priest_creek_arms: "J. Percy Priest Reservoir Stewart Creek Suggs Creek",
  centerhill_shoreline: "Center Hill Reservoir rocky shoreline points bluffs",
  duck_upper: "Duck River Columbia Tennessee",
  duck_middle: "Duck River Williamsport Leatherwood Tennessee",
  duck_lower: "Duck River Centerville Tennessee",
  buffalo_river: "Buffalo River Tennessee scenic river Lobelville Linden",
  harpeth_river: "Harpeth River Tennessee Narrows Kingston Springs",
  stones_river: "Stones River J. Percy Priest Dam tailwater Tennessee",
  elk_tims_ford: "Elk River Tims Ford Dam tailwater Tennessee",
  elk_alabama: "Elk River Alabama Wheeler Prospect",
  cumberland_ky: "Cumberland River Wolf Creek Dam Burkesville Kentucky",
};

const SPECIES_TERMS = {
  striped_bass: "striped bass", smallmouth: "smallmouth bass",
  largemouth: "largemouth bass", trout: "trout",
};

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December"];

/**
 * §18 — several precise queries, primary-source first. The families map onto the TTLs in
 * claims.js: management questions are asked rarely, reports often.
 */
export function buildQueries(species, zoneIds, context, date, env) {
  const sp = SPECIES_TERMS[species] || species;
  const place = zoneIds.map((z) => ZONE_TERMS[z] || z.replace(/_/g, " "))
    .join(" ").slice(0, 220);
  const month = MONTHS[Number(date.slice(5, 7)) - 1] || "";
  const year = date.slice(0, 4);
  const state = /Kentucky/.test(place) ? "Kentucky"
    : /Alabama/.test(place) ? "Alabama" : "Tennessee";

  const qs = [
    { family: "management", primaryOnly: true,
      query: `${sp} ${place} ${state} — agency evidence on seasonal distribution, ` +
             `habitat use and forage. What does the wildlife agency say about where this ` +
             `species is found in this water and when?` },
    { family: "recent_report", primaryOnly: true,
      query: `${sp} fishing report ${place} ${state} ${month} ${year} — the most recent ` +
             `state agency fishing report covering this water.` },
  ];

  if (/tailwater|Dam/.test(place)) {
    qs.push({ family: "generation_response", primaryOnly: true,
      query: `${sp} ${place} — agency or fisheries-research evidence on how this species ` +
             `responds to dam generation, current and cold-water thermal refuge.` });
  }
  if (context && context.water_temp_f) {
    qs.push({ family: "thermal_refuge", primaryOnly: true,
      query: `${sp} behaviour at ${context.water_temp_f} F water temperature ${place} ` +
             `${state} — thermal tolerance and refuge use, fisheries research.` });
  }
  qs.push({ family: "regulation", primaryOnly: true,
    query: `${sp} regulations creel limit and length limit ${place} ${state} — current ` +
           `agency regulation page.` });

  // §20 — secondary only after primary, and clearly marked as non-agency.
  qs.push({ family: "recent_report", primaryOnly: false,
    query: `${sp} ${place} recent fishing conditions ${month} ${year} — reports from ` +
           `established guide services, fly shops or marinas. Identify the source clearly.` });

  return qs;
}

const SYSTEM = [
  "You are a fisheries EVIDENCE retrieval assistant. You do not give fishing advice and you",
  "do not answer questions about where to fish. You search, and you report what a source",
  "actually says.",
  "",
  "Rules, all of them hard:",
  "1. Every finding MUST carry the exact source URL, the page title, and a short",
  "   verbatim-or-close paraphrase of what that page says. No URL means no finding.",
  "2. Never state a river flow, gauge stage, dam generation time, release schedule or wade",
  "   window as fact. If a source contains one, do not repeat the number.",
  "3. Do not synthesise across sources. One finding, one source.",
  "4. If you find nothing relevant, return an empty findings array. An empty answer is",
  "   correct and useful; an invented one is neither.",
  "5. Prefer the most recent authoritative page. Give published dates where the page shows",
  "   one, in YYYY-MM-DD.",
].join("\n");

/**
 * Calls the Responses API with the hosted web_search tool, domain-filtered where the API
 * supports it (§17). Returns {findings, model, tokensIn, tokensOut, error} and NEVER
 * throws — research failing must not take the planner with it.
 */
export async function searchOpenAI(env, query, allowedDomains) {
  const model = env.OPENAI_RESEARCH_MODEL || "gpt-4.1-mini";
  const tool = { type: "web_search" };
  if (allowedDomains && allowedDomains.length) {
    tool.filters = { allowed_domains: allowedDomains };
  }
  const body = {
    model,
    tools: [tool],
    tool_choice: "auto",
    input: [
      { role: "system", content: SYSTEM },
      { role: "user", content: query +
        "\n\nReturn STRICT JSON only, no prose, no code fence, in this shape:\n" +
        '{"findings":[{"url":"...","title":"...","published":"YYYY-MM-DD or null",' +
        '"text":"what the source says","where":"the water this applies to",' +
        '"valid_months":[1,2,3]}]}\n' +
        "At most 6 findings. valid_months is the months the claim applies to; omit it if " +
        "the claim is year-round." },
    ],
  };

  let res;
  try {
    res = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: { "content-type": "application/json",
                 authorization: "Bearer " + env.OPENAI_API_KEY },
      body: JSON.stringify(body),
    });
  } catch (e) {
    return { findings: [], model, error: "network: " + String(e && e.message) };
  }
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    return { findings: [], model, error: "http " + res.status + " " + t.slice(0, 200) };
  }

  let data;
  try { data = await res.json(); } catch (e) {
    return { findings: [], model, error: "unparseable response" };
  }
  const text = extractText(data);
  if (!text) return { findings: [], model, error: "no text in response",
                      tokensIn: usage(data, "input"), tokensOut: usage(data, "output") };
  let parsed;
  try { parsed = JSON.parse(stripFence(text)); } catch (e) {
    return { findings: [], model, error: "model did not return JSON",
             tokensIn: usage(data, "input"), tokensOut: usage(data, "output") };
  }
  return {
    findings: Array.isArray(parsed.findings) ? parsed.findings.slice(0, 6) : [],
    model, tokensIn: usage(data, "input"), tokensOut: usage(data, "output"),
  };
}

export function extractText(data) {
  if (typeof data.output_text === "string" && data.output_text) return data.output_text;
  const chunks = [];
  for (const item of data.output || []) {
    for (const c of item.content || []) {
      if ((c.type === "output_text" || c.type === "text") && c.text) chunks.push(c.text);
    }
  }
  return chunks.join("\n");
}

export function stripFence(t) {
  let s = String(t).trim();
  if (s.startsWith("```")) {
    s = s.slice(s.indexOf("\n") + 1);
    const i = s.lastIndexOf("```");
    if (i >= 0) s = s.slice(0, i);
  }
  return s.trim();
}

function usage(data, which) {
  const u = data && data.usage;
  if (!u) return 0;
  return which === "input" ? (u.input_tokens || 0) : (u.output_tokens || 0);
}
