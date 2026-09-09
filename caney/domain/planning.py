"""
PlanningSnapshot and PlanEnvelope — the two objects the API hands out. §7, §8.

A FishingPlan says what to do. Neither of these replaces it; they wrap it in the two
things a LIVE guide needs that a static report never did.

PLANNINGSNAPSHOT (§8) is the frozen input set. Every plan references exactly one, and the
snapshot holds every observation, series and claim id that went into it. The rule it
exists to enforce: NEVER RECONSTRUCT A HISTORICAL PLAN FROM CURRENT DATA. Ask "why did it
send me to Carthage last Tuesday" against today's gauges and you get a fiction — today's
numbers with last Tuesday's outcome attached, which is worse than no answer because it
looks like one. Replay, plan deltas, outcome calibration and regression investigation all
need the inputs as they stood, so the inputs as they stood are stored.

The id is CONTENT-ADDRESSED. Two requests a minute apart over unchanged gauges produce the
same snapshot id and share storage, and — more usefully — a delta can tell "nothing moved"
from "we re-fetched" without comparing every field.

PLANENVELOPE (§7) is the response. It carries the plan plus the metadata that makes the
plan auditable and refreshable: which snapshot, how fresh, how confident along four
independent axes, what safety applies, whether research was available, and which model
versions produced it.
"""
import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "3.0"

#: How long a plan's numbers may be trusted before the client should refresh (§11, §12).
#: Not a cache TTL — a statement about the physical world. Generation schedules revise
#: inside half an hour; that is the binding constraint, not the weather.
DEFAULT_TTL_SECONDS = 1800.0


def _canonical(obj):
    """Stable JSON for hashing. Sorted keys, no whitespace, floats rounded.

    Rounding matters: an unchanged USGS reading can re-serialise as 412.00000000000006
    after a scale multiply, and an id that flickers on float noise would make every
    refresh look like a material change.
    """
    def norm(o):
        if isinstance(o, float):
            return round(o, 6)
        if isinstance(o, dict):
            return {k: norm(v) for k, v in sorted(o.items())}
        if isinstance(o, (list, tuple)):
            return [norm(v) for v in o]
        return o
    return json.dumps(norm(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


@dataclass
class PlanningSnapshot:
    """§8 — everything one plan was computed from, frozen."""

    id: str = ""
    created_at: float = field(default_factory=time.time)
    schema_version: str = SCHEMA_VERSION

    #: {zone_id: RiverSnapshot.to_json()} — observations, weather hours, arrival bounds.
    zones: Dict[str, Any] = field(default_factory=dict)
    #: {river_id: [[epoch, cfs], …]} — the release series as fetched, not as summarised.
    release_series: Dict[str, Any] = field(default_factory=dict)
    #: {river_id: [{…hour…}]} — the weather series.
    weather_series: Dict[str, Any] = field(default_factory=dict)
    #: Claim ids only. The claims themselves live in the research store and are immutable,
    #: so storing ids keeps a snapshot small without making it ambiguous.
    research_claim_ids: List[str] = field(default_factory=list)
    safety_claim_ids: List[str] = field(default_factory=list)
    #: What the routing provider was asked and what it answered (§17). Part of the inputs:
    #: a plan that changed because the drive got longer must be explainable.
    routing: Dict[str, Any] = field(default_factory=dict)
    #: Source freshness at capture time, per zone.
    freshness: Dict[str, Any] = field(default_factory=dict)
    #: Which models were in force. §79.
    model_versions: Dict[str, str] = field(default_factory=dict)
    #: What the source layer did to produce this. Observability, §72.
    source_stats: Dict[str, Any] = field(default_factory=dict)

    def fingerprint(self):
        """Content address over the INPUTS ONLY — never over id or created_at."""
        return "snap_" + hashlib.sha256(_canonical({
            "zones": self.zones, "release": self.release_series,
            "weather": self.weather_series,
            "research": sorted(self.research_claim_ids),
            "safety": sorted(self.safety_claim_ids),
            "routing": self.routing, "versions": self.model_versions,
        }).encode("utf-8")).hexdigest()[:20]

    def seal(self):
        """Assign the content address. Called once, when the snapshot stops changing."""
        self.id = self.fingerprint()
        return self

    def to_json(self):
        d = asdict(self)
        d["id"] = self.id or self.fingerprint()
        return d

    @staticmethod
    def from_json(d):
        s = PlanningSnapshot(**{k: v for k, v in d.items()
                                if k in PlanningSnapshot.__dataclass_fields__})
        return s


class ResearchStatus:
    """§39, §92 — research is not one thing, and 'unavailable' is not 'absent'."""

    FRESH = "fresh"            # current claims, inside their decay window
    CACHED = "cached"          # served from store, still inside decay
    STALE = "stale"            # past decay; used, and said so
    DEGRADED = "degraded"      # the service was unreachable; seed corpus only
    DISABLED = "disabled"      # not configured at all
    ALL = (FRESH, CACHED, STALE, DEGRADED, DISABLED)

    LABEL = {FRESH: "Current", CACHED: "Cached", STALE: "Stale",
             DEGRADED: "Unavailable", DISABLED: "Off"}


class Confidence:
    """§46 — the headline is a word. The numbers are one tap away."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @staticmethod
    def label(opportunity, forecast, location, research):
        """One qualitative grade from four independent numbers.

        The MINIMUM dominates rather than the mean, deliberately. A plan with a 91
        opportunity on geography we score 40 is not a "medium confidence" plan in any
        sense the reader would accept — it is a strong guess about a place we cannot
        point to, and averaging the four numbers hides exactly the axis that should stop
        somebody driving. Research is excluded from the floor: unsourced biology weakens
        an explanation, it does not make the water wrong.
        """
        floor = min(float(forecast), float(location))
        if floor >= 75 and float(opportunity) >= 68:
            return Confidence.HIGH
        if floor >= 55 and float(opportunity) >= 50:
            return Confidence.MEDIUM
        return Confidence.LOW

    EXPLAIN = {
        HIGH: "Live data, mapped water, and a window that clearly beats the alternatives.",
        MEDIUM: "The plan holds, but at least one input is weaker than we would like.",
        LOW: "Treat this as a lead. Something important is unknown, stale or unverified.",
    }


@dataclass
class PlanEnvelope:
    """§7 — the API response. A plan, plus everything needed to trust and maintain it."""

    plan_id: str = field(default_factory=lambda: "plan_" + uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    schema_version: str = SCHEMA_VERSION

    request: Dict[str, Any] = field(default_factory=dict)

    #: The FishingPlan, serialised. `recommendation` rather than `plan` because the
    #: envelope IS the plan object as far as HTTP is concerned, and nesting plan.plan
    #: reads badly in every client.
    recommendation: Dict[str, Any] = field(default_factory=dict)
    itinerary: Optional[Dict[str, Any]] = None
    alternatives: List[Dict[str, Any]] = field(default_factory=list)

    snapshot_id: str = ""

    opportunity: float = 0.0
    forecast_confidence: float = 0.0
    location_confidence: float = 0.0
    research_confidence: float = 0.0
    confidence_label: str = Confidence.LOW

    freshness: List[Dict[str, Any]] = field(default_factory=list)
    safety: List[Dict[str, Any]] = field(default_factory=list)
    research_status: str = ResearchStatus.DISABLED
    model_versions: Dict[str, str] = field(default_factory=dict)

    #: §14 — the door-to-door part. None when no origin was given.
    logistics: Optional[Dict[str, Any]] = None
    #: §72 — what it cost to produce this.
    timings: Dict[str, Any] = field(default_factory=dict)
    #: Anything the planner could not do. Never silently dropped.
    limitations: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.expires_at:
            self.expires_at = self.created_at + DEFAULT_TTL_SECONDS

    def grade(self):
        self.confidence_label = Confidence.label(
            self.opportunity, self.forecast_confidence,
            self.location_confidence, self.research_confidence)
        return self.confidence_label

    def to_json(self):
        d = asdict(self)
        d["confidence_explain"] = Confidence.EXPLAIN.get(self.confidence_label, "")
        d["research_status_label"] = ResearchStatus.LABEL.get(self.research_status,
                                                              self.research_status)
        return d

    @staticmethod
    def from_json(d):
        return PlanEnvelope(**{k: v for k, v in d.items()
                               if k in PlanEnvelope.__dataclass_fields__})
