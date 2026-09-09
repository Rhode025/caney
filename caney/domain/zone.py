"""
FishingZone — a piece of water you can fish, independent of which web page owns it.

§3.1/§3.2. The old model was `river.species[]`, which is wrong in two directions at once:

  * cordell.py's species line reads "Smallmouth, white bass & panfish", so a striped-bass
    request can never surface the Cordell Hull tailwater — even though TWRA manages the
    Cordell Hull → Caney Fork confluence as striped-bass water.
  * the same geographic water fishes as different fisheries in different months. The lower
    Caney is a trout page and a summer striper refuge; those are not the same opportunity
    and must not share one score.

So a zone is geography, and a SpeciesProfile attaches to a zone with its own seasonal
months, habitat notes and technique bias. A zone may span several river pages, and a river
page may contain several zones.

Coordinates rule (§34): a zone stores EITHER verified point access (from USACE/USGS/OSM
data already verified in this repo) OR a corridor described by its endpoints. Prose that
says "the dam downstream to the Caney Fork mouth" becomes a corridor, never a fake pin.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


class Craft:
    ANY = "any"
    WADE = "wade"
    KAYAK = "kayak"
    DRIFT = "drift"
    POWER = "power"

    ALL = (ANY, WADE, KAYAK, DRIFT, POWER)
    LABEL = {ANY: "Any", WADE: "Wade", KAYAK: "Kayak", DRIFT: "Drift boat",
             POWER: "Power boat / jet"}


class GeometryKind:
    POINT = "point"        # a verified single location (a ramp, a dam tailrace)
    CORRIDOR = "corridor"  # a reach between two verified endpoints
    AREA = "area"          # a polygon


@dataclass
class Geometry:
    kind: str = GeometryKind.CORRIDOR
    points: List[List[float]] = field(default_factory=list)   # [[lat, lon], …]
    verified: bool = False
    source: str = ""
    note: str = ""

    def centroid(self):
        if not self.points:
            return None
        return [round(sum(p[0] for p in self.points) / len(self.points), 6),
                round(sum(p[1] for p in self.points) / len(self.points), 6)]

    def to_json(self):
        d = asdict(self)
        d["centroid"] = self.centroid()
        return d


@dataclass
class AccessPoint:
    id: str
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    kinds: List[str] = field(default_factory=list)      # ramp / wade / paddle / bank
    craft: List[str] = field(default_factory=list)      # Craft.* this access serves
    note: str = ""
    source: str = ""                                    # who verified the coordinates
    verified: bool = False
    river_miles_from_dam: Optional[float] = None        # mfd, for arrival routing

    def serves(self, craft):
        return craft == Craft.ANY or craft in self.craft

    def to_json(self):
        return asdict(self)


@dataclass
class SpeciesProfileRef:
    """How one species uses one zone. The seasonal/behavioural half of the zone model."""
    species: str
    months: List[int] = field(default_factory=lambda: list(range(1, 13)))
    pattern: str = ""                 # "spring spawning/current", "summer thermal refuge", …
    habitat: List[str] = field(default_factory=list)
    holds: str = ""                   # where the fish actually sit, in guide language
    move_to: List[str] = field(default_factory=list)   # zone ids to shift to, in order
    weight: float = 1.0               # zone's intrinsic suitability for the species, 0..1
    evidence: List[str] = field(default_factory=list)  # ResearchClaim ids backing this
    heuristic: bool = True            # False once a Tier A/B source backs it

    def in_season(self, month):
        return month in self.months

    def to_json(self):
        return asdict(self)


@dataclass
class FishingZone:
    id: str
    name: str
    waterbody_ids: List[str] = field(default_factory=list)   # legacy river page ids
    waterbody_names: List[str] = field(default_factory=list)
    geometry: Optional[Geometry] = None
    access: List[AccessPoint] = field(default_factory=list)
    habitat: List[str] = field(default_factory=list)
    species_profiles: Dict[str, SpeciesProfileRef] = field(default_factory=dict)
    source_refs: List[str] = field(default_factory=list)
    # which legacy river page's hydrology drives this zone's water numbers
    hydrology_river: str = ""
    # miles from the controlling dam at the zone's fishing centre — arrival routing
    mfd: Optional[float] = None
    dam: str = ""
    tailwater: bool = False
    drive: str = ""
    detail_page: str = ""             # the encyclopedia page to link to (§48)
    regs: str = ""
    hazards: List[str] = field(default_factory=list)
    notes: str = ""

    # ── eligibility (§6, §30 step 2) ────────────────────────────────────────
    def craft_options(self):
        out = []
        for a in self.access:
            for c in a.craft:
                if c not in out:
                    out.append(c)
        return out

    def supports_craft(self, craft):
        """Eligibility GATE, not a score. Never recommend wading a non-wadeable reach."""
        if craft == Craft.ANY:
            return True
        return craft in self.craft_options()

    def access_for(self, craft):
        return [a for a in self.access if a.serves(craft)]

    def supports_species(self, species, month=None):
        p = self.species_profiles.get(species)
        if not p:
            return False
        return True if month is None else p.in_season(month)

    def to_json(self):
        return {
            "id": self.id, "name": self.name,
            "waterbody_ids": self.waterbody_ids, "waterbody_names": self.waterbody_names,
            "geometry": self.geometry.to_json() if self.geometry else None,
            "access": [a.to_json() for a in self.access],
            "habitat": self.habitat,
            "species_profiles": {k: v.to_json() for k, v in self.species_profiles.items()},
            "source_refs": self.source_refs,
            "hydrology_river": self.hydrology_river, "mfd": self.mfd, "dam": self.dam,
            "tailwater": self.tailwater, "drive": self.drive,
            "detail_page": self.detail_page, "regs": self.regs, "hazards": self.hazards,
            "notes": self.notes,
            "craft": self.craft_options(),
        }
