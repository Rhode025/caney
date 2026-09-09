"""
Geographic confidence, as a first-class value. §28–§33.

The failure this prevents: telling someone to "start on the downstream seam immediately
below the ledge" when the only thing we actually know is that an agency described a
twelve-mile reach as good striped-bass water. Both facts are useful; they are not the same
fact, and prose that treats them alike is the most expensive kind of wrong — it sends
somebody to a specific place that nothing verified.

So every zone and every access point carries a LocationEvidence level, the level maps to a
prior, and three things downstream read it:

  * `caney/planner/utility.py` multiplies window utility by a location factor, so a
    beautifully-scoring reach nobody has stood in loses to a slightly worse one that has
    been verified (§60);
  * `phrase_for()` grades the tactical language — precise, corridor, or hedged (§30);
  * the map legend and the confidence drawer render the levels distinctly (§32, §72).

THE NUMBERS ARE PRIORS, NOT MEASUREMENTS. They were chosen to order correctly and to make
the gap between "an agency named this reach" and "we inferred this from habitat" cost
something real. Nothing has calibrated them. `docs/GEOGRAPHY.md` says so, and the trip log
is what will eventually move them.
"""
from dataclasses import asdict, dataclass, field
from typing import List, Optional


class LocationEvidence:
    """How well we know WHERE, ordered strongest first."""

    VERIFIED_ACCESS = "VERIFIED_ACCESS"                # a published ramp/access coordinate
    VERIFIED_ZONE = "VERIFIED_ZONE"                    # the reach itself is mapped and checked
    AGENCY_DESCRIBED_REACH = "AGENCY_DESCRIBED_REACH"  # an agency named the reach, not the spot
    MODELED_HABITAT = "MODELED_HABITAT"                # inferred from current/structure/habitat
    UNVERIFIED_CANDIDATE = "UNVERIFIED_CANDIDATE"      # plausible, unchecked

    ORDER = (VERIFIED_ACCESS, VERIFIED_ZONE, AGENCY_DESCRIBED_REACH, MODELED_HABITAT,
             UNVERIFIED_CANDIDATE)

    #: Initial priors. Ordering is the load-bearing part; the exact values are not calibrated.
    PRIOR = {
        VERIFIED_ACCESS: 0.98,
        VERIFIED_ZONE: 0.95,
        AGENCY_DESCRIBED_REACH: 0.85,
        MODELED_HABITAT: 0.65,
        UNVERIFIED_CANDIDATE: 0.40,
    }

    LABEL = {
        VERIFIED_ACCESS: "Verified access",
        VERIFIED_ZONE: "Verified reach",
        AGENCY_DESCRIBED_REACH: "Agency-described reach",
        MODELED_HABITAT: "Modelled habitat",
        UNVERIFIED_CANDIDATE: "Unverified candidate",
    }

    EXPLAIN = {
        VERIFIED_ACCESS: "Published coordinates from the agency that owns the access.",
        VERIFIED_ZONE: "The reach itself is mapped and has been checked against a source.",
        AGENCY_DESCRIBED_REACH: ("An agency describes this stretch of water as holding the "
                                 "species. It named a reach, not a spot."),
        MODELED_HABITAT: ("Inferred from current, structure and habitat. Nobody has stood "
                          "here and confirmed it."),
        UNVERIFIED_CANDIDATE: "Plausible from the map alone. Treat it as a lead.",
    }

    #: Map rendering, so weak geography never looks like a surveyed pin (§32).
    STYLE = {
        VERIFIED_ACCESS: {"kind": "pin", "weight": 3, "opacity": 0.95, "dash": None},
        VERIFIED_ZONE: {"kind": "line", "weight": 6, "opacity": 0.80, "dash": None},
        AGENCY_DESCRIBED_REACH: {"kind": "line", "weight": 6, "opacity": 0.60, "dash": "10 6"},
        MODELED_HABITAT: {"kind": "area", "weight": 3, "opacity": 0.35, "dash": "4 6"},
        UNVERIFIED_CANDIDATE: {"kind": "area", "weight": 2, "opacity": 0.22, "dash": "2 8"},
    }

    @staticmethod
    def prior(level):
        return LocationEvidence.PRIOR.get(level, LocationEvidence.PRIOR[
            LocationEvidence.UNVERIFIED_CANDIDATE])


@dataclass
class Verification:
    """§33 — structured metadata so a zone can be upgraded as field knowledge improves."""
    status: str = "unverified"        # unverified | desk_verified | field_verified
    verified_by: str = ""
    verified_at: Optional[str] = None  # ISO date
    source: str = ""
    notes: str = ""

    def to_json(self):
        return asdict(self)


def derived_holding_water(reach_level):
    """What we may claim about the exact holding water, given what we know about the reach.

    A reach nobody has verified cannot support a modelled-habitat claim about a specific
    seam inside it — the model would be inferring structure on water we have not confirmed
    the shape of. So an unverified reach caps the tactical claim at the same level, which
    is what pushes its language into the hedged form (§30).
    """
    if reach_level in (LocationEvidence.VERIFIED_ACCESS, LocationEvidence.VERIFIED_ZONE,
                       LocationEvidence.AGENCY_DESCRIBED_REACH):
        return LocationEvidence.MODELED_HABITAT
    return LocationEvidence.UNVERIFIED_CANDIDATE


@dataclass
class LocationConfidence:
    """The composite geographic confidence for one zone, and what it is made of."""

    access: str = LocationEvidence.UNVERIFIED_CANDIDATE
    reach: str = LocationEvidence.UNVERIFIED_CANDIDATE
    holding_water: str = LocationEvidence.MODELED_HABITAT
    verification: Verification = field(default_factory=Verification)
    notes: str = ""

    # How much each part matters to a plan. Access is where you physically go, so it is
    # weighted highest; holding water is the tactical claim and is the part we are usually
    # least sure of, which is exactly why it must not be silently averaged away.
    WEIGHTS = {"access": 0.40, "reach": 0.35, "holding_water": 0.25}

    @property
    def value(self):
        """0..1."""
        p = LocationEvidence.prior
        return round(p(self.access) * self.WEIGHTS["access"] +
                     p(self.reach) * self.WEIGHTS["reach"] +
                     p(self.holding_water) * self.WEIGHTS["holding_water"], 4)

    @property
    def score(self):
        """0..100, for display beside opportunity and forecast confidence (§31)."""
        return round(self.value * 100, 1)

    @property
    def tactical_level(self):
        """Which of the three phrasings §30 permits."""
        h = LocationEvidence.prior(self.holding_water)
        if h >= 0.90:
            return "precise"
        if h >= 0.62:
            return "corridor"
        return "hedged"

    def rows(self):
        """§72 — the breakdown shown when the reader taps location confidence."""
        return [
            {"key": "access", "label": "Access", "level": self.access,
             "level_label": LocationEvidence.LABEL[self.access],
             "detail": LocationEvidence.EXPLAIN[self.access],
             "prior": LocationEvidence.prior(self.access)},
            {"key": "reach", "label": "Fishery reach", "level": self.reach,
             "level_label": LocationEvidence.LABEL[self.reach],
             "detail": LocationEvidence.EXPLAIN[self.reach],
             "prior": LocationEvidence.prior(self.reach)},
            {"key": "holding_water", "label": "Exact holding water",
             "level": self.holding_water,
             "level_label": LocationEvidence.LABEL[self.holding_water],
             "detail": LocationEvidence.EXPLAIN[self.holding_water],
             "prior": LocationEvidence.prior(self.holding_water)},
        ]

    def to_json(self):
        return {"access": self.access, "reach": self.reach,
                "holding_water": self.holding_water,
                "value": self.value, "score": self.score,
                "tactical_level": self.tactical_level,
                "verification": self.verification.to_json(),
                "notes": self.notes, "rows": self.rows()}


def phrase_parts(level, holds, zone_name, habitat=(), between=None):
    """§30 — (instruction, rationale), graded to what we actually know about WHERE.

    Split in two on purpose. The instruction is what a reader acts on and belongs in the
    itinerary's headline, so it has to stay short — the first version put the whole
    hedged paragraph in bold as a step title and it was four lines deep on a phone. The
    rationale is why, and belongs underneath in the reason line.

    `holds` is the zone's own description of where the fish sit. At `precise` it IS the
    instruction. At `corridor` the instruction becomes a stretch and `holds` becomes the
    read. At `hedged` the instruction says plainly that the exact water is not field
    verified, and `holds` is demoted to what the model expects.
    """
    h = (holds or "").strip().rstrip(".")
    first = (list(habitat) or [""])[0]
    if level == "precise":
        return ((h + "." if h else "Start on the %s at %s."
                 % (first or "primary structure", zone_name)), "")
    if level == "corridor":
        # Name the two ends only when the result stays readable as a step title. Two long
        # ramp names plus a habitat word ran to four lines on a phone, which is not an
        # instruction any more — it is a paragraph somebody has to parse mid-cast.
        if between and len(between[0]) + len(between[1]) <= 34:
            instruction = ("Work the %s corridor between %s and %s."
                           % (first or "current-break", between[0], between[1]))
        else:
            instruction = ("Work the %s corridor through %s rather than one spot."
                           % (first or "current-break", zone_name))
        return instruction, (("The read: " + h + ".") if h else "")
    return ("Cover this reach and read the water yourself — the exact holding water has "
            "not been field verified.",
            ("Species and habitat evidence supports the reach. What the model expects: "
             + h + ".") if h else
            "Species and habitat evidence supports the reach, but nothing has confirmed a "
            "spot inside it.")


def phrase_for(level, holds, zone_name, habitat=(), between=None):
    """The two parts as one sentence, for consumers that want one string."""
    a, b = phrase_parts(level, holds, zone_name, habitat, between)
    return (a + (" " + b if b else "")).strip()
