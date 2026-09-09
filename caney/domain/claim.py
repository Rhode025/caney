"""
Claims — the immutable facts anything downstream is allowed to state.

Two kinds, with very different rules.

SafetyClaim
    A number a person could get hurt by: generation start/stop, flow, stage, wade cutoff,
    release arrival, forecast release, dangerous-weather timing. Produced ONLY by
    deterministic Python from instrument data. Each carries a stable claim_id.

    Downstream — the web UI, the .ics alarms, RiverGuide, the bot corpus — may render a
    claim by id. Nothing may restate, round, convert, average or infer one. The verifier
    in riverguide/src/guard.js checks generated prose against the claim book by id and
    FAILS CLOSED: an unverifiable safety sentence is removed, not annotated. The old
    behaviour (ship the sentence with a warning attached) put an invented wade time in
    front of a reader who had already started walking to the river.

ResearchClaim
    Something a source says about fish: presence, seasonal location, forage, technique.
    May originate from web research, but MUST carry a source. No source, no claim.
    A ResearchClaim may never be promoted into a SafetyClaim (§20).
"""
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, List, Dict


# ── safety ──────────────────────────────────────────────────────────────────

class SafetyKind:
    """Every value class that can decide whether someone should be in the water."""
    GENERATION_START = "generation_start"
    GENERATION_STOP = "generation_stop"
    FLOW = "flow"
    STAGE = "stage"
    WADE_CUTOFF = "wade_cutoff"
    SAFE_EXIT = "safe_exit"
    RELEASE_ARRIVAL = "release_arrival"
    FORECAST_RELEASE = "forecast_release"
    WEATHER_HAZARD = "weather_hazard"
    LAKE_ELEVATION = "lake_elevation"

    ALL = (GENERATION_START, GENERATION_STOP, FLOW, STAGE, WADE_CUTOFF, SAFE_EXIT,
           RELEASE_ARRIVAL, FORECAST_RELEASE, WEATHER_HAZARD, LAKE_ELEVATION)


@dataclass(frozen=True)
class SafetyClaim:
    """One immutable, deterministically derived safety statement.

    `text` is the ONLY wording permitted for this claim anywhere in the product. `numbers`
    is the exact set of digit-tokens the claim licenses, which is what the guard checks.
    """
    id: str
    kind: str
    zone_id: str
    text: str
    numbers: tuple = ()
    value: Any = None
    unit: str = ""
    at: Optional[float] = None            # epoch the claim is about
    bound: str = "typical"                # "earliest" | "typical" | "latest" | "measured"
    source: str = ""
    source_url: str = ""
    state: str = "known"
    observed_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)

    def to_json(self):
        d = asdict(self)
        d["numbers"] = list(self.numbers)
        return d


def make_claim_id(kind, zone_id, text):
    """Stable across builds for the same claim, so an alarm or a log can reference it."""
    h = hashlib.sha1(("%s|%s|%s" % (kind, zone_id, text)).encode("utf-8")).hexdigest()[:10]
    return "sc_%s_%s" % (kind[:4], h)


_NUM_RE = None


def claim_numbers(text):
    """Every digit-token a reader could act on in `text`, normalised the way guard.js does.

    Kept here, in Python, next to the claim it describes, so the emitted claim book and the
    JS verifier cannot drift: the book ships the token list, the verifier only compares.
    """
    global _NUM_RE
    if _NUM_RE is None:
        import re
        _NUM_RE = re.compile(r"\d+(?::\d{2})?(?:\.\d+)?")
    out = []
    for m in _NUM_RE.finditer(text.replace(",", "")):
        t = m.group(0).rstrip(".")
        if t and t not in out:
            out.append(t)
    return tuple(out)


class ClaimBook:
    """The set of safety claims a given plan is allowed to make.

    Emitted alongside every plan. `guard.js` loads it and checks generated prose against
    it by exact numeric token, per zone. Nothing else may add to it at render time.
    """

    def __init__(self):
        self._claims = {}

    def add(self, kind, zone_id, text, value=None, unit="", at=None, bound="typical",
            source="", source_url="", state="known", observed_at=None, numbers=None):
        """`numbers` overrides the licensed digit tokens.

        Derived-from-text is the default and is right for most claims, but it over-licenses
        when the sentence carries incidental digits — a gauge id, or "(50 min ago)". A
        claim that says the flow is 1,500 cfs must not license the number 50 in some other
        sentence about when the water comes up. Pass the value tokens explicitly wherever
        the text contains a number the claim does not actually assert."""
        if kind not in SafetyKind.ALL:
            raise ValueError("unknown safety kind: %r" % (kind,))
        cid = make_claim_id(kind, zone_id, text)
        c = SafetyClaim(id=cid, kind=kind, zone_id=zone_id, text=text,
                        numbers=tuple(numbers) if numbers is not None else claim_numbers(text),
                        value=value, unit=unit, at=at,
                        bound=bound, source=source, source_url=source_url, state=state,
                        observed_at=observed_at)
        self._claims[cid] = c
        return c

    def get(self, cid):
        return self._claims.get(cid)

    def __len__(self):
        return len(self._claims)

    def __iter__(self):
        return iter(self._claims.values())

    def for_zone(self, zone_id):
        return [c for c in self._claims.values() if c.zone_id == zone_id]

    def allowed_numbers(self, zone_id=None):
        """The union of digit-tokens any safety sentence about this zone may contain."""
        out = set()
        for c in self._claims.values():
            if zone_id is None or c.zone_id == zone_id:
                out.update(c.numbers)
        return out

    def to_json(self):
        return [c.to_json() for c in self._claims.values()]


# ── research ────────────────────────────────────────────────────────────────

class SourceTier:
    """§16. Authority order. A lower tier may never override a higher one."""
    A = "A"   # direct official instrument/agency data — USGS, USACE, TVA, NOAA/NWS
    B = "B"   # primary fisheries research & management — TWRA, USFWS, universities
    C = "C"   # recent local field intelligence — guides, fly shops, marinas
    D = "D"   # community intelligence — forums, Reddit, user trip logs

    ORDER = {A: 4, B: 3, C: 2, D: 1}
    WEIGHT = {A: 1.0, B: 0.85, C: 0.5, D: 0.25}
    LABEL = {
        A: "Official instrument data",
        B: "Fisheries research / management",
        C: "Local field report (non-agency)",
        D: "Community report (unverified)",
    }


# Domains that establish a tier without a human deciding. Anything not listed is D.
TIER_DOMAINS = {
    SourceTier.A: ("usgs.gov", "usace.army.mil", "water.noaa.gov", "noaa.gov",
                   "weather.gov", "tva.com", "tva.gov", "cwms.usace.army.mil"),
    SourceTier.B: ("tn.gov", "tnwildlife.org", "fws.gov", "ky.gov", "alabama.gov",
                   "outdooralabama.com", "eregulations.com", "utk.edu", "tntech.edu",
                   "usda.gov", "epa.gov"),
}


def tier_for_domain(domain):
    d = (domain or "").lower().lstrip(".")
    for tier, sufs in TIER_DOMAINS.items():
        for s in sufs:
            if d == s or d.endswith("." + s):
                return tier
    return SourceTier.D


CLAIM_TYPES = ("species_presence", "seasonal_location", "thermal_refuge", "current_response",
               "forage", "time_of_day", "habitat", "technique", "recent_report", "stocking",
               "survey", "regulation")


@dataclass
class ResearchClaim:
    """One sourced statement about fish. §19."""
    id: str = ""
    species: str = ""
    claim_type: str = ""
    location_ids: List[str] = field(default_factory=list)
    geographic_description: str = ""
    season: str = ""
    valid_months: List[int] = field(default_factory=list)
    claim_text: str = ""
    source_url: str = ""
    source_title: str = ""
    source_domain: str = ""
    published_at: Optional[str] = None
    retrieved_at: Optional[float] = None
    source_tier: str = SourceTier.D
    source_quality: float = 0.25
    recency_score: float = 0.0
    geographic_match: float = 0.0
    seasonal_match: float = 0.0
    confidence: float = 0.0
    safety_sensitive: bool = False

    def __post_init__(self):
        if not self.source_url:
            # §20: no source, no claim. This is a hard invariant, not a warning — an
            # unsourced claim is exactly what "AI made it up" looks like in a dataclass.
            raise UnsourcedClaim("ResearchClaim %r has no source_url" % (self.claim_text[:60],))
        if not self.source_domain:
            self.source_domain = _domain_of(self.source_url)
        if self.source_tier == SourceTier.D:
            self.source_tier = tier_for_domain(self.source_domain)
        self.source_quality = SourceTier.WEIGHT.get(self.source_tier, 0.25)
        if not self.id:
            self.id = "rc_" + hashlib.sha1(
                ("%s|%s|%s" % (self.source_url, self.species, self.claim_text)
                 ).encode("utf-8")).hexdigest()[:12]
        if self.retrieved_at is None:
            self.retrieved_at = time.time()

    def score(self, month=None, zone_ids=()):
        """0..1 — how much this claim should move a candidate's research component."""
        seasonal = 1.0
        if self.valid_months and month:
            seasonal = 1.0 if month in self.valid_months else 0.15
        self.seasonal_match = seasonal
        geo = 1.0 if (not zone_ids or set(self.location_ids) & set(zone_ids)) else 0.3
        self.geographic_match = geo
        rec = self.recency_score if self.recency_score else _recency(self.published_at)
        self.recency_score = rec
        self.confidence = round(self.source_quality * seasonal * geo * (0.55 + 0.45 * rec), 4)
        return self.confidence

    def to_json(self):
        return asdict(self)


class UnsourcedClaim(ValueError):
    """A research claim was constructed with no source. §20."""


def _domain_of(url):
    try:
        from urllib.parse import urlparse
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _recency(published_at):
    """1.0 for this week, decaying to a floor of 0.35 — old agency science is still science."""
    if not published_at:
        return 0.5
    try:
        import datetime as dt
        d = dt.date.fromisoformat(str(published_at)[:10])
        days = (dt.date.today() - d).days
    except Exception:
        return 0.5
    if days <= 7:    return 1.0
    if days <= 30:   return 0.9
    if days <= 120:  return 0.75
    if days <= 400:  return 0.55
    return 0.35
