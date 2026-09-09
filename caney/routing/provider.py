"""
RoutingProvider — how long it takes to get there. §17, §18, §19.

Caney 2.1 knew how long it takes to move BETWEEN two pieces of water by boat
(`caney/planner/transitions.py`). It did not know how long it takes to get to the water
from your house, which is why its answer to "I can leave at 5 and must be home by 11:30"
was to plan six and a half hours of fishing.

Three answers this must give, and they are not the same problem:

    origin  -> launch     driving, with a trailer or not
    launch  -> launch     driving between accesses (a bank move, or a shuttle)
    takeout -> origin     driving home, at a different time of day

THE HIERARCHY IS THE POINT (§17):

    1. a real routing provider, when one is configured        provenance="routed"
    2. a route somebody measured and wrote down               provenance="known"
    3. geographic estimate                                    provenance="estimated"
    4. nothing                                                returns None

Level 3 is where this file could most easily lie. Straight-line distance times a fudge
factor is not a drive time, and dressing it up as "47 minutes" invites somebody to leave
at 4:52 for a 5:39 launch on the strength of arithmetic over two decimal degrees. So the
estimate is deliberately COARSE — rounded to five minutes, carrying a low confidence and
a provenance the UI is required to show — and §19's constraint solver treats an estimated
return as needing more slack than a routed one. Precision we do not have is not free to
invent; it is the specific thing that makes somebody late.
"""
import math
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple


class Provenance:
    ROUTED = "routed"          # a routing service answered
    KNOWN = "known"            # a measured, recorded route
    ESTIMATED = "estimated"    # geography plus a road factor
    UNKNOWN = "unknown"

    ALL = (ROUTED, KNOWN, ESTIMATED, UNKNOWN)
    LABEL = {ROUTED: "Routed", KNOWN: "Measured", ESTIMATED: "Estimated",
             UNKNOWN: "Unknown"}

    #: Confidence prior for each. Uncalibrated; ordering is what matters.
    CONFIDENCE = {ROUTED: 0.92, KNOWN: 0.85, ESTIMATED: 0.55, UNKNOWN: 0.0}

    #: §19 — how much slack the return leg needs, as a multiplier on the drive. An
    #: estimated drive that is wrong by 20% must not be the reason somebody misses a
    #: hard deadline, so an estimate buys more buffer than a routed answer.
    SLACK = {ROUTED: 1.08, KNOWN: 1.10, ESTIMATED: 1.25, UNKNOWN: 1.40}


@dataclass
class Route:
    minutes: float
    miles: Optional[float] = None
    provenance: str = Provenance.ESTIMATED
    provider: str = ""
    observed_at: float = field(default_factory=time.time)
    detail: str = ""

    @property
    def confidence(self):
        return Provenance.CONFIDENCE.get(self.provenance, 0.0)

    @property
    def slack_minutes(self):
        """Minutes to budget for this leg, including the buffer its provenance earns."""
        return self.minutes * Provenance.SLACK.get(self.provenance, 1.4)

    def to_json(self):
        d = asdict(self)
        d["confidence"] = round(self.confidence, 3)
        d["provenance_label"] = Provenance.LABEL.get(self.provenance, self.provenance)
        d["slack_minutes"] = round(self.slack_minutes, 1)
        return d


# ── geography ───────────────────────────────────────────────────────────────

EARTH_MILES = 3958.7613


def haversine_miles(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_MILES * math.asin(min(1.0, math.sqrt(h)))


# ── the estimate's constants ────────────────────────────────────────────────
# Fitted, not guessed: `analysis/road_factor.py` regresses the `drive` string on all 22
# FishingZones ("~70 min · east of Nashville", "~2¼ h · Burkesville KY") against the
# great-circle distance from Nashville to each zone's primary access. Those strings were
# written from a real map when each zone was researched, which makes them the only
# door-to-water ground truth this repo has.
#
#     minutes = OVERHEAD_MINUTES + straight_line_miles * MINUTES_PER_STRAIGHT_MILE
#
# MAE 4.8 min, RMSE 5.3 min, bias 0.0 min over the 22 points. Re-derive with
# `python3 analysis/road_factor.py`.
#
# TWO parameters, not four. The obvious formulation — a road-sinuosity factor times an
# average speed — is NOT IDENTIFIABLE from this data: only the ratio appears, so any
# (factor, mph) pair on one line fits equally well and the first attempt at this fit
# happily reported a road factor of 0.86, which would mean roads shorter than straight
# lines. Quoting two numbers where the data supports one is precisely the manufactured
# precision §17 forbids, so the model carries the single slope it can actually measure.
MINUTES_PER_STRAIGHT_MILE = 1.12

#: Getting out of the house, off the interstate and into a parking lot. The fitted
#: intercept (16.2), rounded. Applies once per leg, both directions.
OVERHEAD_MINUTES = 16.0

#: For display only, and marked as such wherever it is shown: at 1.12 min per straight
#: mile, a 1.25x road factor implies roughly 67 mph average. Illustrative — see above.
IMPLIED_ROAD_FACTOR = 1.25
IMPLIED_AVG_MPH = 67.0

#: A boat on a trailer is slower and cannot take every shortcut. UNCALIBRATED — the zone
#: `drive` strings were not recorded per craft, so nothing in this repo separates a
#: trailered drive from a car one. A prior, and MOVE-02 is the ticket to measure it.
TRAILER_PENALTY = 1.12

#: Estimates are rounded to this, so nothing reads as more precise than it is.
ESTIMATE_ROUNDING_MINUTES = 5.0


class RoutingProvider:
    name = "abstract"

    def route(self, origin, destination, trailer=False, depart_at=None):
        """`Route` or None. None means "cannot answer", never "zero minutes"."""
        raise NotImplementedError


class NullRoutingProvider(RoutingProvider):
    """Answers nothing. The honest provider when no origin is known."""

    name = "none"

    def route(self, origin, destination, trailer=False, depart_at=None):
        return None


class GeographicRoutingProvider(RoutingProvider):
    """Great-circle distance, a road factor and an average speed. Deliberately coarse."""

    name = "geographic"

    def route(self, origin, destination, trailer=False, depart_at=None):
        if not origin or not destination:
            return None
        if origin[0] is None or destination[0] is None:
            return None
        straight = haversine_miles(origin, destination)
        minutes = OVERHEAD_MINUTES + straight * MINUTES_PER_STRAIGHT_MILE
        if trailer:
            minutes *= TRAILER_PENALTY
        minutes = round(minutes / ESTIMATE_ROUNDING_MINUTES) * ESTIMATE_ROUNDING_MINUTES
        return Route(minutes=max(ESTIMATE_ROUNDING_MINUTES, minutes),
                     miles=round(straight * IMPLIED_ROAD_FACTOR, 1),
                     provenance=Provenance.ESTIMATED, provider=self.name,
                     detail="%.0f mi straight line, fitted from 22 mapped zone drives"
                            % straight)


class ConfiguredRoutingProvider(RoutingProvider):
    """Routes somebody actually drove and wrote down. §17 level 2.

    Keyed by (origin_id, access_id). Origin ids come from the saved-origin list; a custom
    lat/lon has no id and therefore never hits this table, which is correct — a measured
    route from a place you have never left from does not exist.
    """

    name = "configured"

    def __init__(self, table=None):
        self.table = dict(table or KNOWN_DRIVES)

    def route(self, origin_id, access_id, trailer=False, depart_at=None):
        row = self.table.get((origin_id, access_id))
        if row is None:
            return None
        minutes = row["minutes"] * (TRAILER_PENALTY if trailer else 1.0)
        return Route(minutes=round(minutes, 1), miles=row.get("miles"),
                     provenance=Provenance.KNOWN, provider=self.name,
                     detail=row.get("detail", ""))


class HttpRoutingProvider(RoutingProvider):
    """A real routing service, when CANEY_ROUTING_ENDPOINT names one. §17 level 1.

    Expects an OSRM-shaped response, which is what both a self-hosted OSRM and most
    proxies in front of commercial routers emit. Any failure returns None so the chain
    falls through to the estimate — a routing outage must never fail a plan.
    """

    name = "http"

    def __init__(self, endpoint=None, timeout=6):
        self.endpoint = endpoint or os.environ.get("CANEY_ROUTING_ENDPOINT") or ""
        self.timeout = timeout

    @property
    def enabled(self):
        return bool(self.endpoint)

    def route(self, origin, destination, trailer=False, depart_at=None):
        if not self.enabled or not origin or not destination:
            return None
        from ..sources.http import cached_json
        url = "%s/%s,%s;%s,%s?overview=false" % (
            self.endpoint.rstrip("/"), origin[1], origin[0],
            destination[1], destination[0])
        data, err = cached_json(url, ttl=3600, timeout=self.timeout, retries=1,
                                key="route:%s:%s" % (origin, destination))
        if not data or err:
            return None
        try:
            leg = (data.get("routes") or [])[0]
            minutes = float(leg["duration"]) / 60.0
            miles = float(leg["distance"]) / 1609.344
        except Exception:                       # noqa: BLE001 — a bad shape is no answer
            return None
        if trailer:
            minutes *= TRAILER_PENALTY
        return Route(minutes=round(minutes, 1), miles=round(miles, 1),
                     provenance=Provenance.ROUTED, provider=self.name,
                     detail="routing service")


class ChainRoutingProvider(RoutingProvider):
    """§17's hierarchy, in order, first non-None wins."""

    name = "chain"

    def __init__(self, http=None, configured=None, geographic=None):
        self.http = http if http is not None else HttpRoutingProvider()
        self.configured = configured if configured is not None else ConfiguredRoutingProvider()
        self.geographic = geographic if geographic is not None else GeographicRoutingProvider()

    def route(self, origin, destination, trailer=False, depart_at=None,
              origin_id=None, access_id=None):
        if self.http is not None and getattr(self.http, "enabled", False):
            r = self.http.route(origin, destination, trailer, depart_at)
            if r is not None:
                return r
        if origin_id and access_id and self.configured is not None:
            r = self.configured.route(origin_id, access_id, trailer, depart_at)
            if r is not None:
                return r
        if self.geographic is not None:
            return self.geographic.route(origin, destination, trailer, depart_at)
        return None

    def describe(self):
        return {"http": getattr(self.http, "enabled", False),
                "configured": len(getattr(self.configured, "table", {})),
                "geographic": self.geographic is not None,
                "minutes_per_straight_mile": MINUTES_PER_STRAIGHT_MILE,
                "overhead_minutes": OVERHEAD_MINUTES,
                "trailer_penalty": TRAILER_PENALTY,
                "estimate_rounding_minutes": ESTIMATE_ROUNDING_MINUTES,
                "slack": Provenance.SLACK}


#: Measured drives. Empty rather than fabricated: every entry here must be a drive
#: somebody actually made and timed, and inventing plausible-looking rows would defeat
#: the entire point of separating KNOWN from ESTIMATED. MOVE-02 in the roadmap is the
#: ticket to fill it in from real trips.
KNOWN_DRIVES: Dict[Tuple[str, str], Dict[str, Any]] = {}


def build_provider():
    return ChainRoutingProvider()
