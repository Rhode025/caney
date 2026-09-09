"""
OpportunityWindow, FishingSegment, FishingItinerary. §4, §9.

The unit of the 2.1 planner is no longer "a candidate zone scored over the user's whole
availability". It is a WINDOW: a contiguous, practically fishable stretch of one zone, with
its own quality, its own duration, and its own utility. A DAY is then an itinerary — an
ordered sequence of windows joined by transitions the chosen craft can actually make.

`OpportunityWindow` is what the optimiser ranks. `FishingItinerary` is what the reader is
shown, and it is the product: launch, fish, move, fish, switch, stop.
"""
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class SegmentType:
    LAUNCH = "launch"
    FISH = "fish"
    MOVE = "move"
    #: §26 — a move WITHIN a zone, from one feature to another. Distinct from MOVE
    #: because it costs minutes rather than a transition, needs no craft check, and
    #: reads completely differently: "slide down to the mouth", not "run to Carthage".
    MOVE_FEATURE = "move_feature"
    WAIT = "wait"
    CHANGE_TECHNIQUE = "change_technique"
    SAFETY_EXIT = "safety_exit"
    OPTIONAL_BACKUP = "optional_backup"
    END = "end"

    ALL = (LAUNCH, FISH, MOVE, WAIT, CHANGE_TECHNIQUE, SAFETY_EXIT, OPTIONAL_BACKUP, END)


@dataclass
class OpportunityWindow:
    """One contiguous fishable stretch of one zone, for one species."""

    zone_id: str = ""
    species: str = ""
    start: float = 0.0
    end: float = 0.0

    #: The 15-minute samples the utility was computed from.
    samples: List[float] = field(default_factory=list)
    peak_score: float = 0.0
    mean_score: float = 0.0
    floor_score: float = 0.0
    quality: float = 0.0

    confidence: float = 0.0            # forecast confidence, 0..100
    location_confidence: float = 0.0   # 0..1

    transition_cost_before: float = 0.0   # minutes
    transition_cost_after: float = 0.0    # minutes

    utility: float = 0.0
    parts: Dict[str, float] = field(default_factory=dict)

    conditions_summary: str = ""
    reasons: List[str] = field(default_factory=list)
    stale: bool = False

    @property
    def duration_minutes(self):
        return round((self.end - self.start) / 60.0, 1)

    def overlaps(self, other, gap_seconds=0.0):
        return not (self.end + gap_seconds <= other.start or
                    other.end + gap_seconds <= self.start)

    def to_json(self):
        d = asdict(self)
        d["duration_minutes"] = self.duration_minutes
        return d


@dataclass
class FishingSegment:
    """One instruction in the day. §9."""

    type: str = SegmentType.FISH
    start: float = 0.0
    end: float = 0.0
    zone_id: str = ""
    zone_name: str = ""
    access_id: str = ""

    instructions: str = ""
    reason: str = ""

    expected_score: Optional[float] = None
    confidence: Optional[float] = None
    location_confidence: Optional[float] = None
    location_evidence: str = ""

    technique: Optional[Dict[str, Any]] = None
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    claim_ids: List[str] = field(default_factory=list)
    kind: str = "heuristic"     # deterministic | astronomical | forecast | heuristic | safety
    uncertainty: str = ""

    #: §26 — WHICH feature inside the zone, and how well it fits this window. None when
    #: the zone has no mapped features, which is an honest answer rather than a gap: it
    #: means we can name the water but not the position in it.
    feature_id: str = ""
    feature_name: str = ""
    feature_type: str = ""
    feature_confidence: str = ""
    feature_fit: Optional[float] = None
    feature_holding: str = ""

    @property
    def duration_minutes(self):
        return round((self.end - self.start) / 60.0, 1)

    def to_json(self):
        d = asdict(self)
        d["duration_minutes"] = self.duration_minutes
        return d


@dataclass
class FishingItinerary:
    """The day, as an executable sequence. §9."""

    id: str = field(default_factory=lambda: "itin_" + uuid.uuid4().hex[:10])
    created_at: float = field(default_factory=time.time)
    species: str = ""
    craft: str = "any"
    requested_start: float = 0.0
    requested_end: float = 0.0

    segments: List[FishingSegment] = field(default_factory=list)
    windows: List[OpportunityWindow] = field(default_factory=list)

    total_fishing_minutes: float = 0.0
    total_transition_minutes: float = 0.0

    utility_score: float = 0.0
    utility_parts: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    location_confidence: float = 0.0

    primary_zone: str = ""
    zone_sequence: List[str] = field(default_factory=list)
    backup_plan: Optional[Dict[str, Any]] = None
    why: List[str] = field(default_factory=list)

    @property
    def best_window(self):
        if not self.windows:
            return None
        return {"start": round(self.windows[0].start),
                "end": round(self.windows[-1].end)}

    def fishing_segments(self):
        return [s for s in self.segments if s.type == SegmentType.FISH]

    def to_json(self):
        return {
            "id": self.id, "created_at": self.created_at, "species": self.species,
            "craft": self.craft,
            "requested_start": round(self.requested_start),
            "requested_end": round(self.requested_end),
            "segments": [s.to_json() for s in self.segments],
            "windows": [w.to_json() for w in self.windows],
            "total_fishing_minutes": round(self.total_fishing_minutes, 1),
            "total_transition_minutes": round(self.total_transition_minutes, 1),
            "utility_score": round(self.utility_score, 2),
            "utility_parts": self.utility_parts,
            "confidence": round(self.confidence, 1),
            "location_confidence": round(self.location_confidence, 1),
            "primary_zone": self.primary_zone,
            "zone_sequence": self.zone_sequence,
            "backup_plan": self.backup_plan,
            "why": self.why,
            "best_window": self.best_window,
        }
