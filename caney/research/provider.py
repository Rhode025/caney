"""
The research provider abstraction and its OpenAI implementation. §17, §18, §20.

    ResearchProvider.search_primary(...)     Tier A/B only — domain-filtered to agencies
    ResearchProvider.search_secondary(...)   everything else, tagged Tier C/D

THE RULE (§20): a provider may DISCOVER a claim. It may not CREATE one. Every returned
item must carry a source URL, and ResearchClaim's constructor refuses to exist without
one. A model that summarises without citing produces nothing.

AND (§20 again): nothing a provider returns may become a safety-sensitive value.
`SAFETY_SENSITIVE_RE` marks anything that reads like a flow, a stage, a generation time or
a wade window; those claims are kept for their prose but flagged `safety_sensitive=True`,
and planner/scoring.py never reads a number out of a ResearchClaim under any circumstance.
Instrument data reaches the plan only through sources/ and SafetyClaim.

The provider is OPTIONAL. With no OPENAI_API_KEY, `build_provider()` returns NullProvider
and the deterministic planner is unaffected — every test in test/planner runs this way.
"""
import json
import os
import re
import time

from ..domain.claim import ResearchClaim, SourceTier, UnsourcedClaim, tier_for_domain
from . import cache

# §17 — the primary-search allowlist. Extended by CANEY_RESEARCH_DOMAINS (comma separated).
PRIMARY_DOMAINS = [
    "tn.gov", "tnwildlife.org", "usgs.gov", "usace.army.mil", "tva.com", "weather.gov",
    "noaa.gov", "fws.gov", "ky.gov", "fw.ky.gov", "alabama.gov", "outdooralabama.com",
    "water.noaa.gov", "epa.gov",
]

# A number a reader could act on as a water measurement. Deliberately loose: over-flagging
# a claim costs it the right to contribute a number it was never going to contribute
# anyway (nothing reads numbers out of a ResearchClaim), while under-flagging is how a
# blog's remembered flow figure would end up looking like an instrument reading.
SAFETY_SENSITIVE_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:cfs|kcfs|cubic\s*feet)"
    r"|(?:stage|gauge|gage|level)\D{0,12}\d+(?:\.\d+)?\s*(?:ft|feet|')?"
    r"|\d+(?:\.\d+)?\s*(?:ft|feet)\D{0,12}(?:stage|gauge|gage)"
    r"|generat\w*\D{0,12}\d"
    r"|releas\w*\D{0,12}\d"
    r"|wade\s+(?:until|cutoff|window)"
    r"|\d{1,2}:\d{2}\s*(?:am|pm)?\s*(?:release|generation|until)", re.I)

CLAIM_TYPE_HINTS = [
    ("stocking", r"\bstock(?:ed|ing|s)?\b"),
    ("survey", r"\b(electrofish\w*|creel|survey|sampl\w+)\b"),
    ("regulation", r"\b(creel|limit|regulation|length limit|advisory|season closed)\b"),
    ("thermal_refuge", r"\b(thermal|refuge|cool\w*\s+water|oxygenat\w+)\b"),
    ("current_response", r"\b(current|generation|discharge|flow)\b"),
    ("forage", r"\b(shad|herring|forage|bait\w*|crayfish|sculpin|alewife)\b"),
    ("seasonal_location", r"\b(spring|summer|fall|winter|spawn\w*|month|may|june|july)\b"),
    ("time_of_day", r"\b(dawn|dusk|morning|evening|low.light|night)\b"),
    ("habitat", r"\b(ledge|shoal|stump|flat|creek|bluff|structure|vegetation|wood)\b"),
    ("technique", r"\b(fly|streamer|nymph|swing|strip|leader|tippet)\b"),
    ("recent_report", r"\b(report|this week|last week|recently|currently)\b"),
]


def classify(text):
    for kind, pat in CLAIM_TYPE_HINTS:
        if re.search(pat, text, re.I):
            return kind
    return "species_presence"


class ResearchProvider:
    """Interface. Both methods return [dict] with at least url/title/text."""

    name = "none"
    enabled = False

    def search_primary(self, query, domains=None, max_results=6):
        raise NotImplementedError

    def search_secondary(self, query, max_results=6):
        raise NotImplementedError


class NullProvider(ResearchProvider):
    """No key configured, or research disabled. The planner is fully functional on this."""

    name = "disabled"
    enabled = False
    reason = "RESEARCH_ENABLED is not set, or no OPENAI_API_KEY is configured"

    def search_primary(self, query, domains=None, max_results=6):
        return [], self.reason

    def search_secondary(self, query, max_results=6):
        return [], self.reason


class OpenAIResearchProvider(ResearchProvider):
    """OpenAI Responses API with the hosted web_search tool. §17.

    No SDK dependency: this repo is stdlib-only, so it posts JSON to the REST endpoint.
    The key comes from the environment and is never written to disk, into the cache, or
    into any emitted artefact.
    """

    name = "openai"
    enabled = True
    URL = "https://api.openai.com/v1/responses"

    def __init__(self, api_key, model=None, timeout=60):
        self.api_key = api_key
        self.model = model or os.environ.get("OPENAI_RESEARCH_MODEL", "gpt-4.1-mini")
        self.timeout = timeout

    def _post(self, body):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(
            self.URL, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace")), None
        except Exception as e:                       # noqa: BLE001
            return None, "%s: %s" % (type(e).__name__, e)

    def _search(self, query, domains, max_results):
        tool = {"type": "web_search"}
        if domains:
            # Domain filtering where the API supports it (§17).
            tool["filters"] = {"allowed_domains": list(domains)}
        body = {
            "model": self.model,
            "tools": [tool],
            "tool_choice": "auto",
            "input": [
                {"role": "system", "content": (
                    "You are a fisheries research assistant. Search the web and report ONLY "
                    "what a source actually says. Every finding MUST include the exact source "
                    "URL, the page title, and a short verbatim-or-close paraphrase. Never "
                    "state a river flow, gauge stage, dam generation time or wade window as "
                    "fact — if a source gives one, do not repeat the number. If you find "
                    "nothing relevant, return an empty findings array.")},
                {"role": "user", "content": (
                    query + "\n\nReturn STRICT JSON only, no prose, in the form: "
                    '{"findings":[{"url":"...","title":"...","published":"YYYY-MM-DD or null",'
                    '"text":"...","where":"the geographic area this applies to"}]} '
                    "with at most %d findings." % max_results)},
            ],
        }
        data, err = self._post(body)
        if data is None:
            return [], err
        text = _extract_text(data)
        if not text:
            return [], "no text in the response"
        try:
            parsed = json.loads(_strip_fence(text))
        except Exception as e:                       # noqa: BLE001
            return [], "unparseable JSON from the model: %s" % e
        out = []
        for f in (parsed.get("findings") or [])[:max_results]:
            if not f.get("url"):
                continue                            # §20 — no source, no claim
            out.append({"url": f["url"], "title": f.get("title") or "",
                        "text": (f.get("text") or "").strip(),
                        "published": f.get("published"),
                        "where": f.get("where") or ""})
        return out, None

    def search_primary(self, query, domains=None, max_results=6):
        return self._search(query, domains or allowed_domains(), max_results)

    def search_secondary(self, query, max_results=6):
        return self._search(query, None, max_results)


def _extract_text(data):
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    chunks = []
    for item in data.get("output") or []:
        for c in item.get("content") or []:
            if c.get("type") in ("output_text", "text") and c.get("text"):
                chunks.append(c["text"])
    return "\n".join(chunks)


def _strip_fence(t):
    t = t.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        t = t.rsplit("```", 1)[0]
    return t.strip()


def allowed_domains():
    extra = [d.strip() for d in os.environ.get("CANEY_RESEARCH_DOMAINS", "").split(",")
             if d.strip()]
    return PRIMARY_DOMAINS + extra


class HttpResearchProvider(ResearchProvider):
    """The Research Intelligence worker (research-worker/). §16, §44.

    Preferred over calling OpenAI directly, because the worker owns the key, the cache, the
    decay curves, the dedupe, the audit trail and the spend cap — one place rather than one
    per caller. Python asks it for EVIDENCE and gets normalised claims back.

    It never raises and never returns an error to the planner: research failing must not
    take the plan with it (§43, §58, §63).
    """

    name = "worker"
    enabled = True

    def __init__(self, endpoint, timeout=25):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def _post(self, path, body):
        import urllib.request
        req = urllib.request.Request(
            self.endpoint + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace")), None
        except Exception as e:                       # noqa: BLE001
            return None, "%s: %s" % (type(e).__name__, e)

    def claims_for_zone(self, species, zone_id, date_iso, context=None, force=False):
        """([finding dicts], meta) — the worker's own normalised claims, adapted."""
        data, err = self._post("/refresh" if force else "/research", {
            "species": species, "zone_ids": [zone_id], "date": date_iso,
            "context": context or {}})
        if data is None:
            return [], {"error": err, "degraded": True}
        out = []
        for c in data.get("claims") or []:
            out.append({"url": c.get("source_url"), "title": c.get("source_title"),
                        "text": c.get("claim"), "published": c.get("published_at"),
                        "where": c.get("geographic_description"),
                        "valid_months": c.get("valid_months") or [],
                        "_tier": c.get("source_tier"),
                        "_confidence": c.get("combined_confidence")})
        meta = dict(data.get("meta") or {})
        meta["disagreements"] = data.get("disagreements") or []
        return out, meta

    def search_primary(self, query, domains=None, max_results=6):
        return [], "the worker provider is queried per zone, not per free-text query"

    def search_secondary(self, query, max_results=6):
        return [], "the worker provider is queried per zone, not per free-text query"


def build_provider(env=None):
    """The optionality gate. Never raises; research is always allowed to be absent.

    Order of preference:
      1. CANEY_RESEARCH_ENDPOINT — the worker, which holds the key and the cache.
      2. OPENAI_API_KEY direct — for a local run or a CI build with the secret.
      3. NullProvider — and the planner is completely unaffected.
    """
    env = env if env is not None else os.environ
    if str(env.get("RESEARCH_ENABLED", "")).lower() not in ("1", "true", "yes", "on"):
        return NullProvider()
    endpoint = env.get("CANEY_RESEARCH_ENDPOINT")
    if endpoint:
        return HttpResearchProvider(endpoint)
    key = env.get("OPENAI_API_KEY")
    if not key:
        return NullProvider()
    return OpenAIResearchProvider(key, env.get("OPENAI_RESEARCH_MODEL"))


# ── §18: query generation ───────────────────────────────────────────────────

def queries_for(species, zone, when, snapshot=None):
    """Several PRECISE queries. Never 'what is good fishing'."""
    from ..species.profiles import DISPLAY, profile
    import datetime as _dt
    p = profile(species)
    d = _dt.datetime.fromtimestamp(when)
    month = d.strftime("%B")
    season = p.season_of(d.month)
    full = DISPLAY[species]["full"]
    places = " ".join(dict.fromkeys(
        [zone.name] + zone.waterbody_names + ([zone.dam] if zone.dam else [])))
    state = "Tennessee"
    if "KY" in zone.name or "Kentucky" in " ".join(zone.waterbody_names):
        state = "Kentucky"
    elif "Alabama" in zone.name:
        state = "Alabama"

    qs = [
        {"family": "management",
         "q": "%s %s %s fisheries management habitat seasonal movement %s"
              % (full, places, state, season)},
        {"family": "report",
         "q": "%s fishing report %s %s %s %s"
              % (full, places, state, month, d.strftime("%Y"))},
    ]
    if zone.tailwater:
        qs.append({"family": "management",
                   "q": "%s %s tailwater current generation thermal refuge %s"
                        % (full, zone.dam or places, state)})
    if snapshot is not None and getattr(snapshot, "water_temp", None) is not None \
            and snapshot.water_temp.ok:
        qs.append({"family": "management",
                   "q": "%s water temperature %d F behaviour %s %s"
                        % (full, round(snapshot.water_temp.value), places, season)})
    qs.append({"family": "regulation",
               "q": "%s regulations creel limit length limit %s %s" % (full, places, state)})
    return qs


# ── §19: claim extraction ───────────────────────────────────────────────────

def to_claims(findings, species, zone, month):
    """[ResearchClaim] — anything unsourced or unusable is dropped, never invented around."""
    out = []
    for f in findings:
        text = (f.get("text") or "").strip()
        # §20, enforced twice: here by skipping, and again by ResearchClaim refusing to
        # exist without a source. A finding with no `url` KEY at all used to raise, which
        # would have taken the whole build down on one malformed model response.
        if not text or not (f.get("url") or "").strip():
            continue
        try:
            c = ResearchClaim(
                species=species,
                claim_type=classify(text),
                location_ids=[zone.id],
                geographic_description=f.get("where") or zone.name,
                valid_months=list(range(1, 13)),
                claim_text=text[:900],
                source_url=f["url"].strip(),
                source_title=f.get("title") or "",
                published_at=f.get("published"),
                safety_sensitive=bool(SAFETY_SENSITIVE_RE.search(text)),
            )
        except UnsourcedClaim:
            continue
        c.score(month=month, zone_ids=[zone.id])
        out.append(c)
    return out


def research_zone(provider, species, zone, when, month, snapshot=None, max_queries=3):
    """Cached, provider-optional research for one zone. Returns ([claims], meta)."""
    import datetime as _dt
    meta = {"provider": provider.name, "enabled": provider.enabled, "queries": [],
            "cached": 0, "fetched": 0, "errors": [], "refreshed_at": None,
            "latency_s": 0.0, "disagreements": []}
    if not provider.enabled:
        meta["errors"].append(getattr(provider, "reason", "research disabled"))
        return [], meta

    # The worker answers per zone and has already done the normalisation, the decay and the
    # dedupe. Asking it query-by-query would duplicate all three badly.
    if isinstance(provider, HttpResearchProvider):
        t0 = time.time()
        ctx = {}
        if snapshot is not None:
            if getattr(snapshot, "water_temp", None) is not None and snapshot.water_temp.ok:
                ctx["water_temp_f"] = float(snapshot.water_temp.value)
            if getattr(snapshot, "generation_on", None) is not None and \
                    snapshot.generation_on.ok:
                ctx["generation"] = "on" if snapshot.generation_on.value else "off"
        date_iso = _dt.datetime.fromtimestamp(when).date().isoformat()
        findings, wmeta = provider.claims_for_zone(species, zone.id, date_iso, ctx)
        meta["latency_s"] = time.time() - t0
        meta["fetched"] = int(wmeta.get("searched") or 0)  # not a measurement (a count)
        meta["cached"] = 1 if wmeta.get("cached") else 0
        meta["disagreements"] = wmeta.get("disagreements") or []
        meta["refreshed_at"] = wmeta.get("newestRetrievedAt")
        if wmeta.get("error"):
            meta["errors"].append(str(wmeta["error"]))
        return to_claims(findings, species, zone, month), meta

    claims = []
    for spec in queries_for(species, zone, when, snapshot)[:max_queries]:
        fam, q = spec["family"], spec["q"]
        k = cache.key(species, zone.id, cache.date_bucket(when, fam), fam)
        hit, at = cache.get(k, fam)
        meta["queries"].append({"query": q, "family": fam, "cached": hit is not None})
        if hit is not None:
            meta["cached"] += 1
            meta["refreshed_at"] = max(meta["refreshed_at"] or 0, at or 0)  # not a measurement
            claims.extend(to_claims(hit, species, zone, month))
            continue
        t0 = time.time()
        findings, err = provider.search_primary(q)
        meta["latency_s"] += time.time() - t0
        meta["fetched"] += 1
        if err:
            meta["errors"].append("%s: %s" % (fam, err))
            continue
        cache.put(k, findings, fam)
        meta["refreshed_at"] = time.time()
        claims.extend(to_claims(findings, species, zone, month))
    return claims, meta
