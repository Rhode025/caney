"""
FishingPlan — the canonical answer object. §10.

One schema, consumed by the web UI, RiverGuide, the tests, the .ics alarms and the trip
log. Anything that wants to know what Caney recommends reads this; nothing scrapes HTML.

Unknown stays unknown. Every field that can be absent is an Observation or None — there
are no invented defaults anywhere in this file.
"""
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .observation import Observation, DataState


class Verdict:
    GO = "GO"
    CONDITIONAL = "CONDITIONAL"
    SKIP = "SKIP"
    ALL = (GO, CONDITIONAL, SKIP)


class StepKind:
    """§9 — deterministic timing must be distinguishable from fishing heuristics."""
    DETERMINISTIC = "deterministic"   # an instrument reading or a modelled arrival bound
    ASTRONOMICAL = "astronomical"     # sunrise/sunset/moon — exact
    FORECAST = "forecast"             # a forecast event, with its own uncertainty
    HEURISTIC = "heuristic"           # species behaviour / guide craft
    SAFETY = "safety"                 # a hard exit or abort instruction


@dataclass
class TimelineStep:
    at: Optional[float] = None        # epoch, or None for "when condition X occurs"
    at_label: str = ""                # "5:45 AM" — rendered client-side from `at`
    until: Optional[float] = None
    title: str = ""
    detail: str = ""
    kind: str = StepKind.HEURISTIC
    zone_id: str = ""
    claim_ids: List[str] = field(default_factory=list)
    condition: str = ""               # for conditional branches (§39)
    branches: List[Dict[str, Any]] = field(default_factory=list)
    uncertainty: str = ""             # "earliest 2:05 · typical 2:30 · latest 2:50"

    def to_json(self):
        return asdict(self)


@dataclass
class ScoreLine:
    key: str
    label: str
    earned: float
    possible: float
    why: str = ""

    def to_json(self):
        return asdict(self)


@dataclass
class Technique:
    """§35 — what to tie on NOW, not a fly inventory."""
    primary_fly: str = ""
    primary_size: str = ""
    primary_color: str = ""
    backup_fly: str = ""
    backup_size: str = ""
    line: str = ""
    leader: str = ""
    presentation: str = ""
    depth: str = ""
    retrieve: str = ""
    why: str = ""

    def to_json(self):
        return asdict(self)


@dataclass
class FishingPlan:
    id: str = field(default_factory=lambda: "plan_" + uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    species: str = ""
    requested_window: Dict[str, Any] = field(default_factory=dict)   # {start,end,iso,tz}
    craft: str = "any"

    verdict: str = Verdict.SKIP
    verdict_why: str = ""
    score: float = 0.0                 # 0..100
    confidence: float = 0.0            # 0..100, deliberately a SEPARATE number (§31)

    primary_candidate: str = ""
    alternatives: List[Dict[str, Any]] = field(default_factory=list)

    best_window: Dict[str, Any] = field(default_factory=dict)        # {start,end,why}
    location: Dict[str, Any] = field(default_factory=dict)
    access: Dict[str, Any] = field(default_factory=dict)

    timeline: List[TimelineStep] = field(default_factory=list)
    technique: Optional[Technique] = None

    water: Dict[str, Observation] = field(default_factory=dict)
    weather: Dict[str, Observation] = field(default_factory=dict)
    lunar: Dict[str, Any] = field(default_factory=dict)
    biological_context: Dict[str, Any] = field(default_factory=dict)

    evidence: List[Dict[str, Any]] = field(default_factory=list)
    score_breakdown: List[ScoreLine] = field(default_factory=list)

    safety: List[Dict[str, Any]] = field(default_factory=list)       # SafetyClaim json
    data_freshness: List[Dict[str, Any]] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_json(self):
        def obs(d):
            return {k: (v.to_json() if isinstance(v, Observation) else v)
                    for k, v in (d or {}).items()}
        return {
            "id": self.id, "created_at": self.created_at, "species": self.species,
            "requested_window": self.requested_window, "craft": self.craft,
            "verdict": self.verdict, "verdict_why": self.verdict_why,
            "score": round(self.score, 1), "confidence": round(self.confidence, 1),
            "primary_candidate": self.primary_candidate,
            "alternatives": self.alternatives,
            "best_window": self.best_window,
            "location": self.location, "access": self.access,
            "timeline": [s.to_json() for s in self.timeline],
            "technique": self.technique.to_json() if self.technique else None,
            "water": obs(self.water), "weather": obs(self.weather),
            "lunar": self.lunar, "biological_context": self.biological_context,
            "evidence": self.evidence,
            "score_breakdown": [s.to_json() for s in self.score_breakdown],
            "safety": self.safety, "data_freshness": self.data_freshness,
            "limitations": self.limitations,
        }
