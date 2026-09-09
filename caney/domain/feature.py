"""
FishingFeature — the layer below FishingZone, where you actually cast. §22-§26.

A zone answers "which piece of water"; it does not answer "where in it". "Cordell Hull
tailrace" is twelve hundred yards of river and the difference between the outside seam and
the slack behind the wall is the difference between a morning and a blank. 3.0 adds the
finer layer so the itinerary can say WHICH seam, and say it with a confidence the reader
can weigh.

This is not a spot list. It is a habitat model: features are the hydraulic and structural
positions that hold fish, described from the same agency and survey material the zones
came from, and each one states how well its position is known.

§25 IS ENFORCED HERE, NOT DOCUMENTED HERE. A search result reading "stripers concentrate
between Cordell Hull Dam and the Caney Fork" licenses a corridor. It does not license
36.274193,-85.912103. Six decimal places is a tenth of a metre; asserting that from prose
is a fabrication that reads exactly like a survey, and it is the single most expensive
thing this file could get wrong — somebody drives to it. So a POINT geometry at anything
below OFFICIAL_GIS raises `InventedWaypoint` at construction. You cannot write the bug.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .location import LocationEvidence, Verification


class InventedWaypoint(ValueError):
    """Raised when a feature claims a precision its evidence does not support."""


class GeometryConfidence:
    """How the shape was arrived at, strongest first. §24."""

    FIELD_VERIFIED = "FIELD_VERIFIED"        # somebody stood here and recorded it
    OFFICIAL_GIS = "OFFICIAL_GIS"            # published agency coordinates or GIS layer
    AGENCY_DESCRIBED = "AGENCY_DESCRIBED"    # an agency described the water in prose
    OSM_DERIVED = "OSM_DERIVED"              # traced from OpenStreetMap hydrography
    MODELED = "MODELED"                      # inferred from current, structure, bathymetry
    UNVERIFIED = "UNVERIFIED"                # plausible from the map alone

    ORDER = (FIELD_VERIFIED, OFFICIAL_GIS, AGENCY_DESCRIBED, OSM_DERIVED, MODELED,
             UNVERIFIED)

    #: Only these may carry a single coordinate. Everything else is a corridor or an area.
    #: AGENCY_DESCRIBED is deliberately NOT in this set: an agency naming a reach is the
    #: exact input §25 says must not become a pin.
    POINT_ALLOWED = (FIELD_VERIFIED, OFFICIAL_GIS)

    LABEL = {
        FIELD_VERIFIED: "Field verified", OFFICIAL_GIS: "Official GIS",
        AGENCY_DESCRIBED: "Agency described", OSM_DERIVED: "Map derived",
        MODELED: "Modelled", UNVERIFIED: "Unverified",
    }

    EXPLAIN = {
        FIELD_VERIFIED: "Recorded on the water.",
        OFFICIAL_GIS: "Published coordinates from the agency that owns the feature.",
        AGENCY_DESCRIBED: ("An agency described this water in prose. The stretch is real; "
                           "the exact position within it is not published."),
        OSM_DERIVED: "Traced from OpenStreetMap hydrography — the shape, not the fishing.",
        MODELED: ("Inferred from current, structure and depth. Nobody has confirmed fish "
                  "hold here."),
        UNVERIFIED: "Plausible from the map alone. Treat it as a lead, not a destination.",
    }

    #: Priors, on the same 0..1 scale as LocationEvidence and for the same reason: the
    #: ORDER is load-bearing, the exact numbers are not calibrated. docs/GEOGRAPHY.md.
    PRIOR = {
        FIELD_VERIFIED: 0.98, OFFICIAL_GIS: 0.95, AGENCY_DESCRIBED: 0.80,
        OSM_DERIVED: 0.70, MODELED: 0.60, UNVERIFIED: 0.40,
    }

    #: Map rendering, so a modelled guess never draws like a surveyed pin (§24).
    STYLE = {
        FIELD_VERIFIED: {"kind": "pin", "weight": 3, "opacity": 0.95, "dash": None},
        OFFICIAL_GIS: {"kind": "pin", "weight": 3, "opacity": 0.90, "dash": None},
        AGENCY_DESCRIBED: {"kind": "line", "weight": 6, "opacity": 0.60, "dash": "10 6"},
        OSM_DERIVED: {"kind": "line", "weight": 4, "opacity": 0.55, "dash": "6 6"},
        MODELED: {"kind": "area", "weight": 3, "opacity": 0.35, "dash": "4 6"},
        UNVERIFIED: {"kind": "area", "weight": 2, "opacity": 0.22, "dash": "2 8"},
    }

    #: The zone layer speaks LocationEvidence. One vocabulary maps onto the other rather
    #: than the two drifting apart with a hand-written translation at each call site.
    TO_LOCATION_EVIDENCE = {
        FIELD_VERIFIED: LocationEvidence.VERIFIED_ACCESS,
        OFFICIAL_GIS: LocationEvidence.VERIFIED_ACCESS,
        AGENCY_DESCRIBED: LocationEvidence.AGENCY_DESCRIBED_REACH,
        OSM_DERIVED: LocationEvidence.VERIFIED_ZONE,
        MODELED: LocationEvidence.MODELED_HABITAT,
        UNVERIFIED: LocationEvidence.UNVERIFIED_CANDIDATE,
    }

    @staticmethod
    def prior(level):
        return GeometryConfidence.PRIOR.get(level,
                                            GeometryConfidence.PRIOR[GeometryConfidence.UNVERIFIED])

    @staticmethod
    def rank(level):
        try:
            return GeometryConfidence.ORDER.index(level)
        except ValueError:
            return len(GeometryConfidence.ORDER)


class FeatureType:
    """The hydraulic or structural positions this product knows how to reason about. §22."""

    TAILRACE_SEAM = "tailrace_seam"
    DAM_CURRENT_BREAK = "dam_current_break"
    TRIBUTARY_MOUTH = "tributary_mouth"
    CREEK_MOUTH = "creek_mouth"
    CHANNEL_SWING = "channel_swing"
    SHOAL = "shoal"
    ISLAND_HEAD = "island_head"
    ISLAND_TAIL = "island_tail"
    LEDGE = "ledge"
    BLUFF_BANK = "bluff_bank"
    RIPRAP = "riprap"
    GRASS_EDGE = "grass_edge"
    FLAT = "flat"
    POINT = "point"
    BACKWATER = "backwater"

    ALL = (TAILRACE_SEAM, DAM_CURRENT_BREAK, TRIBUTARY_MOUTH, CREEK_MOUTH, CHANNEL_SWING,
           SHOAL, ISLAND_HEAD, ISLAND_TAIL, LEDGE, BLUFF_BANK, RIPRAP, GRASS_EDGE, FLAT,
           POINT, BACKWATER)

    LABEL = {
        TAILRACE_SEAM: "Tailrace seam", DAM_CURRENT_BREAK: "Dam current break",
        TRIBUTARY_MOUTH: "Tributary mouth", CREEK_MOUTH: "Creek mouth",
        CHANNEL_SWING: "Channel swing", SHOAL: "Shoal", ISLAND_HEAD: "Island head",
        ISLAND_TAIL: "Island tail", LEDGE: "Ledge", BLUFF_BANK: "Bluff bank",
        RIPRAP: "Riprap", GRASS_EDGE: "Grass edge", FLAT: "Flat", POINT: "Point",
        BACKWATER: "Backwater",
    }

    #: Features whose fishing is created by moving water. The planner uses this to decide
    #: whether a feature is even worth visiting with the dam off (§89).
    CURRENT_DRIVEN = (TAILRACE_SEAM, DAM_CURRENT_BREAK, TRIBUTARY_MOUTH, CREEK_MOUTH,
                      CHANNEL_SWING, SHOAL, ISLAND_HEAD, ISLAND_TAIL)

    #: Features that fish on structure and level rather than discharge.
    STRUCTURE_DRIVEN = (LEDGE, BLUFF_BANK, RIPRAP, GRASS_EDGE, FLAT, POINT, BACKWATER)


class HydraulicBehavior:
    """What the feature does as discharge changes. §23 `hydraulic_behavior`."""

    NEEDS_CURRENT = "needs_current"        # dead without generation
    IMPROVES_WITH_CURRENT = "improves_with_current"
    BEST_ON_FALLING = "best_on_falling"    # fishes as the water drops back
    BEST_ON_RISING = "best_on_rising"
    CURRENT_INDIFFERENT = "current_indifferent"
    BLOWN_BY_CURRENT = "blown_by_current"  # unfishable once the dam is on hard

    ALL = (NEEDS_CURRENT, IMPROVES_WITH_CURRENT, BEST_ON_FALLING, BEST_ON_RISING,
           CURRENT_INDIFFERENT, BLOWN_BY_CURRENT)

    LABEL = {
        NEEDS_CURRENT: "Needs current", IMPROVES_WITH_CURRENT: "Better with current",
        BEST_ON_FALLING: "Best on falling water", BEST_ON_RISING: "Best on rising water",
        CURRENT_INDIFFERENT: "Current-indifferent", BLOWN_BY_CURRENT: "Blown out by current",
    }


@dataclass
class FeatureGeometry:
    """A shape and the evidence that licenses it. §24, §25."""

    kind: str = "corridor"                       # point | corridor | area
    points: List[List[float]] = field(default_factory=list)
    confidence: str = GeometryConfidence.MODELED
    source: str = ""
    note: str = ""

    def __post_init__(self):
        if self.kind == "point" and \
                self.confidence not in GeometryConfidence.POINT_ALLOWED:
            raise InventedWaypoint(
                "geometry confidence %s may not carry a point — %r licenses a corridor "
                "or an area, never a waypoint (§25). Describe the stretch instead."
                % (self.confidence, GeometryConfidence.LABEL.get(self.confidence,
                                                                 self.confidence)))
        if self.kind == "point" and len(self.points) != 1:
            raise InventedWaypoint("a point geometry needs exactly one coordinate")
        if self.kind == "corridor" and len(self.points) < 2:
            raise InventedWaypoint(
                "a corridor needs both endpoints — one coordinate IS a waypoint (§25)")

    def centroid(self):
        if not self.points:
            return None
        return [round(sum(p[0] for p in self.points) / len(self.points), 6),
                round(sum(p[1] for p in self.points) / len(self.points), 6)]

    def to_json(self):
        d = asdict(self)
        d["centroid"] = self.centroid()
        d["confidence_label"] = GeometryConfidence.LABEL.get(self.confidence)
        d["confidence_explain"] = GeometryConfidence.EXPLAIN.get(self.confidence)
        d["style"] = GeometryConfidence.STYLE.get(self.confidence)
        d["prior"] = GeometryConfidence.prior(self.confidence)
        return d


@dataclass
class FeatureSpeciesProfile:
    """How one species uses one feature."""

    species: str
    months: List[int] = field(default_factory=lambda: list(range(1, 13)))
    holding: str = ""              # where on the feature the fish actually sit
    weight: float = 1.0            # 0..1, the feature's pull for this species IN its zone
    evidence: List[str] = field(default_factory=list)   # ResearchClaim / source ids
    heuristic: bool = True

    def in_season(self, month):
        return month in self.months

    def to_json(self):
        return asdict(self)


@dataclass
class FishingFeature:
    """§23. One habitat feature inside one zone."""

    id: str
    zone_id: str
    name: str
    feature_type: str
    geometry: Optional[FeatureGeometry] = None
    species_profiles: Dict[str, FeatureSpeciesProfile] = field(default_factory=dict)
    hydraulic_behavior: str = HydraulicBehavior.CURRENT_INDIFFERENT
    holding_behavior: str = ""              # prose: what the fish are doing here
    techniques: List[str] = field(default_factory=list)   # technique ids, see species layer
    source_refs: List[str] = field(default_factory=list)
    verification: Verification = field(default_factory=Verification)
    notes: str = ""
    #: Minutes it is worth fishing this feature before the plan should move on. A seam
    #: below a dam is a twenty-minute proposition; a grass flat is an hour.
    typical_minutes: int = 45

    def __post_init__(self):
        if self.feature_type not in FeatureType.ALL:
            raise ValueError("unknown feature type %r" % self.feature_type)
        if self.hydraulic_behavior not in HydraulicBehavior.ALL:
            raise ValueError("unknown hydraulic behaviour %r" % self.hydraulic_behavior)

    @property
    def confidence(self):
        return self.geometry.confidence if self.geometry else GeometryConfidence.UNVERIFIED

    @property
    def location_evidence(self):
        """The zone layer's vocabulary, so one confidence model runs through both."""
        return GeometryConfidence.TO_LOCATION_EVIDENCE.get(
            self.confidence, LocationEvidence.UNVERIFIED_CANDIDATE)

    @property
    def prior(self):
        return GeometryConfidence.prior(self.confidence)

    @property
    def current_driven(self):
        return self.feature_type in FeatureType.CURRENT_DRIVEN

    def supports(self, species, month=None):
        p = self.species_profiles.get(species)
        if not p:
            return False
        return True if month is None else p.in_season(month)

    def weight_for(self, species):
        p = self.species_profiles.get(species)
        return p.weight if p else 0.0

    def holds(self, species):
        p = self.species_profiles.get(species)
        return (p.holding if p and p.holding else self.holding_behavior) or ""

    def to_json(self):
        return {
            "id": self.id, "zone_id": self.zone_id, "name": self.name,
            "feature_type": self.feature_type,
            "feature_label": FeatureType.LABEL.get(self.feature_type, self.feature_type),
            "geometry": self.geometry.to_json() if self.geometry else None,
            "species_profiles": {k: v.to_json()
                                 for k, v in self.species_profiles.items()},
            "hydraulic_behavior": self.hydraulic_behavior,
            "hydraulic_label": HydraulicBehavior.LABEL.get(self.hydraulic_behavior),
            "holding_behavior": self.holding_behavior,
            "techniques": self.techniques, "source_refs": self.source_refs,
            "verification": asdict(self.verification),
            "notes": self.notes, "typical_minutes": self.typical_minutes,
            "confidence": self.confidence,
            "confidence_label": GeometryConfidence.LABEL.get(self.confidence),
            "location_evidence": self.location_evidence,
            "prior": self.prior,
            "current_driven": self.current_driven,
        }
