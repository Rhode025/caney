"""
What it costs to move. §11, §12.

A move must be paid for. Without a transition model the optimiser will happily send someone
thirty-five minutes across the county for three points of score, which is not what a guide
would do and not what the utility function should reward.

PROVENANCE, IN PRIORITY ORDER (§11). Every estimate says which of these it is, and the UI
shows it:

    known      a configured, real route between two zones on the same water
    estimated  great-circle distance × a mode factor. Honest, and labelled.
    unknown    no route we can justify. The move is not offered.

CRAFT AWARENESS (§12). A power boat can run a navigable pool a wading angler cannot walk;
a wading angler can cross a shoal a jet boat has to go around; a road reposition needs a
launch and a takeout at both ends. `transition()` returns None when the move is impossible
for the craft, which removes it from the search rather than pricing it.
"""
import math
from dataclasses import asdict, dataclass
from typing import Optional

from ..domain.zone import Craft

#: Average speeds, in miles per hour, per movement mode. Priors, not measurements.
SPEED_MPH = {
    "boat_downstream": 18.0,
    "boat_upstream": 12.0,
    "paddle_downstream": 4.0,
    "paddle_upstream": 1.5,
    "drift_downstream": 5.0,
    "wade_bank": 1.6,
    "road": 32.0,        # county roads with a ramp at each end, not interstate
}

#: Fixed overhead in minutes: securing rods, motoring off plane, trailering, parking.
OVERHEAD_MIN = {
    "boat_downstream": 4.0, "boat_upstream": 4.0,
    "paddle_downstream": 3.0, "paddle_upstream": 3.0,
    "drift_downstream": 4.0,
    "wade_bank": 2.0,
    "road": 14.0,        # take out, trailer, drive, launch again
}

#: Straight-line distance is shorter than any real route. These inflate it, per mode.
SINUOSITY = {"water": 1.25, "road": 1.45}

#: Moves longer than this are never offered — at that point it is two trips, not a move.
MAX_TRANSITION_MIN = 55.0


@dataclass
class Transition:
    from_zone: str
    to_zone: str
    minutes: float
    mode: str
    provenance: str            # known | estimated | unknown
    detail: str = ""
    miles: Optional[float] = None

    def to_json(self):
        d = asdict(self)
        d["minutes"] = round(self.minutes, 1)
        if self.miles is not None:
            d["miles"] = round(self.miles, 2)
        return d


#: §11 "manual configuration" — routes we actually know, keyed (from, to), symmetric unless
#: both directions are listed. Minutes are the whole move, overhead included.
KNOWN_ROUTES = {
    # The Carthage circuit. The Cordell Hull tailwater and the Caney Fork mouth are ~8
    # river miles apart on continuously navigable water; a bass boat runs it in about a
    # quarter of an hour with the current, a little more against it.
    ("cordell_tailwater", "carthage_confluence"): (12.0, "boat_downstream",
        "8 river miles of continuously navigable Cumberland, running downstream."),
    ("carthage_confluence", "cordell_tailwater"): (16.0, "boat_upstream",
        "8 river miles back up to the dam, against the release."),
    ("carthage_confluence", "caney_lower"): (10.0, "boat_upstream",
        "Up into the Caney Fork mouth from the confluence — navigable, no lock."),
    ("caney_lower", "carthage_confluence"): (8.0, "boat_downstream",
        "Down the lower Caney to the Cumberland confluence."),
    ("cordell_tailwater", "caney_lower"): (20.0, "boat_downstream",
        "Down the Cumberland past Carthage and up into the Caney mouth."),
    ("caney_lower", "cordell_tailwater"): (24.0, "boat_upstream",
        "Out of the Caney mouth and back up to the dam."),
    # The Caney trout reaches. Wading between them is a drive, not a walk: the access
    # points are county roads and there is no continuous bank.
    ("caney_upper", "caney_middle"): (18.0, "road",
        "Long Branch or Happy Hollow to Betty's Island / Stonewall by road."),
    ("caney_middle", "caney_upper"): (18.0, "road",
        "Back upstream to the dam reaches by road."),
    ("caney_middle", "caney_lower"): (16.0, "road",
        "Stonewall down to the South Carthage ramp by road."),
    ("caney_lower", "caney_middle"): (16.0, "road", "Back up to Stonewall by road."),
    # Cordell Hull reservoir arms sit above the dam; from the tailwater that is a lock or
    # a trailer, so it is a road reposition however you cut it.
    ("cordell_tailwater", "cordell_creek_arms"): (26.0, "road",
        "Trailer around the dam — there is no boat route from tailwater to reservoir."),
    ("cordell_creek_arms", "cordell_tailwater"): (26.0, "road",
        "Trailer back below the dam."),
    ("carthage_confluence", "cordell_creek_arms"): (32.0, "road",
        "Trailer from Carthage up around the dam to the reservoir arms."),
    # Duck reaches, by road between ramps.
    ("duck_upper", "duck_middle"): (24.0, "road", "Columbia to Williamsport by road."),
    ("duck_middle", "duck_upper"): (24.0, "road", "Williamsport back to Columbia."),
    ("duck_middle", "duck_lower"): (26.0, "road", "Williamsport to Centerville by road."),
    ("duck_lower", "duck_middle"): (26.0, "road", "Centerville back to Williamsport."),
}

#: Which movement modes each craft can use.
CRAFT_MODES = {
    Craft.POWER: ("boat_downstream", "boat_upstream", "road"),
    Craft.DRIFT: ("drift_downstream", "boat_downstream", "road"),
    Craft.KAYAK: ("paddle_downstream", "paddle_upstream", "road"),
    Craft.WADE: ("wade_bank", "road"),
    Craft.ANY: ("boat_downstream", "boat_upstream", "drift_downstream",
                "paddle_downstream", "paddle_upstream", "wade_bank", "road"),
}


def haversine_miles(a, b):
    r = 3958.8
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2 +
         math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _centre(zone):
    if zone.geometry and zone.geometry.points:
        return zone.geometry.centroid()
    for a in zone.access:
        if a.lat is not None:
            return [a.lat, a.lon]
    return None


def transition(from_zone, to_zone, craft, snaps=None):
    """Transition | None. None means the move is impossible for this craft (§12)."""
    if from_zone.id == to_zone.id:
        return Transition(from_zone.id, to_zone.id, 0.0, "none", "known", "Same zone.", 0.0)

    modes = CRAFT_MODES.get(craft, CRAFT_MODES[Craft.ANY])

    # Both ends must actually serve the craft, or there is nowhere to get in or out.
    if not (from_zone.supports_craft(craft) and to_zone.supports_craft(craft)):
        return None

    key = (from_zone.id, to_zone.id)
    if key in KNOWN_ROUTES:
        minutes, mode, detail = KNOWN_ROUTES[key]
        if mode not in modes:
            # The known route uses a mode this craft does not have. A road reposition is
            # the universal fallback, but only where both ends have a road access.
            if "road" in modes and _road_capable(from_zone) and _road_capable(to_zone):
                mode, detail = "road", detail + " (by road for this craft.)"
                minutes = max(minutes, 20.0)
            else:
                return None
        if minutes > MAX_TRANSITION_MIN:
            return None
        return Transition(from_zone.id, to_zone.id, minutes, mode, "known", detail)

    # No configured route. Estimate, and say so.
    a, b = _centre(from_zone), _centre(to_zone)
    if a is None or b is None:
        return None
    straight = haversine_miles(a, b)

    same_water = bool(set(from_zone.waterbody_ids) & set(to_zone.waterbody_ids))
    water_modes = [m for m in modes if m != "road"]
    if same_water and water_modes and not (from_zone.tailwater ^ to_zone.tailwater):
        mode = water_modes[0]
        miles = straight * SINUOSITY["water"]
    elif "road" in modes and _road_capable(from_zone) and _road_capable(to_zone):
        mode = "road"
        miles = straight * SINUOSITY["road"]
    else:
        return None

    minutes = OVERHEAD_MIN[mode] + (miles / SPEED_MPH[mode]) * 60.0
    if minutes > MAX_TRANSITION_MIN:
        return None
    return Transition(
        from_zone.id, to_zone.id, minutes, mode, "estimated",
        "Estimated from %0.1f straight-line miles × %s sinuosity — no verified route."
        % (straight, "water" if mode != "road" else "road"),
        miles)


def _road_capable(zone):
    """A road reposition needs somewhere to take out and somewhere to put back in."""
    return any(("ramp" in (a.kinds or []) or "wade" in (a.kinds or []) or
                "paddle" in (a.kinds or []) or "bank" in (a.kinds or []))
               for a in zone.access)


def build_graph(zones, craft):
    """{(from, to): Transition} for every move this craft can make. Small by construction."""
    out = {}
    for f in zones:
        for t in zones:
            if f.id == t.id:
                continue
            tr = transition(f, t, craft)
            if tr is not None:
                out[(f.id, t.id)] = tr
    return out
