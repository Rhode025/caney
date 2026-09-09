"""
Door-to-water. §14, §18, §19.

The single largest behavioural change in 3.0, and the one the North Star turns on. Caney
2.1 answered "I can fish 6 to 10". A person does not have a fishing window; they have a
day. "I can leave at 5 and I need to be home by 11:30" is six and a half hours of LIFE, of
which the fishing is whatever survives the drive, the ramp, the run upriver, the run back,
the trailer and the drive home.

2.1 treated that gap as somebody else's problem. Asked for 5:00-11:30 it planned six and a
half hours on the water, which is not a hard plan to follow so much as an impossible one.

THE CORE IDEA: travel is a CONSTRAINT, evaluated per candidate, not a cost subtracted at
the end (§19). Each zone gets its own fishable envelope:

    earliest fishing  = depart_after + drive out + launch prep + run to the water
    latest fishing    = return_by - drive home (with slack) - loading - run back

and the opportunity search runs inside THAT, not inside the raw availability. Two things
fall out that are otherwise special cases:

  * §88 solves itself. A 96-scoring zone two hours away and an 88-scoring zone fifty-five
    minutes away are not competing on score; the far one has ninety minutes of envelope
    and the near one has four hours, the duration factor prices that, and the near one
    wins without a rule saying so. If the envelope closes entirely the zone is ELIMINATED,
    which is the honest answer — you cannot fish there today.
  * "Leave by 4:52" (§18) is a real output rather than a subtraction the reader performs.

THE ASYMMETRY THAT MATTERS: the outbound drive may use its nominal estimate, because being
early at a ramp costs nothing. The return leg is padded by its provenance (§17
Provenance.SLACK), because being late getting home is the failure this whole module exists
to prevent, and an estimated drive that is wrong by 20% must not be the reason.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..domain.zone import Craft
from ..routing.provider import Provenance, Route
from . import transitions

#: Minutes from parking the car to the first cast. UNCALIBRATED PRIORS — nothing in this
#: repo has timed them, and CAL-03 is the ticket to do it from real trips. They are
#: ordered by how much gear has to come off the vehicle, which is the part that is
#: obviously right even before anybody measures it.
LAUNCH_PREP_MINUTES = {
    Craft.WADE: 12.0,     # boots, waders, rig up, walk down
    Craft.KAYAK: 18.0,    # unload, carry, load gear, put in
    Craft.DRIFT: 25.0,    # ramp queue, launch, park the trailer, walk back
    Craft.POWER: 20.0,    # ramp queue, launch, park the trailer, walk back
    Craft.ANY: 15.0,
}

#: Minutes from the last cast to pulling out of the lot.
TAKEOUT_MINUTES = {
    Craft.WADE: 10.0,
    Craft.KAYAK: 20.0,
    Craft.DRIFT: 25.0,
    Craft.POWER: 20.0,
    Craft.ANY: 15.0,
}

#: Minutes on the water between the ramp and the first fishable feature, and back. Most
#: launches are not standing on the spot. Priors again, scaled by craft speed the same
#: way transitions.py scales its moves.
RUN_TO_WATER_MINUTES = {
    Craft.WADE: 5.0,
    Craft.KAYAK: 10.0,
    Craft.DRIFT: 8.0,
    Craft.POWER: 9.0,
    Craft.ANY: 7.0,
}

#: Crafts that arrive on a trailer, which is slower on the road and slower at the ramp.
TRAILERED = (Craft.POWER, Craft.DRIFT)

#: Below this many minutes of fishable envelope a trip is not worth taking, whatever the
#: water is doing. Matches the species minimum in utility.py — a plan that offers
#: forty minutes on the water after a two-hour drive is a plan nobody executes.
MIN_ENVELOPE_MINUTES = 45.0


@dataclass
class Leg:
    """One timed piece of the day. The BRIEF view renders these in order (§48)."""

    kind: str                 # depart | drive_out | prep | run_out | fish | move |
                              # run_back | takeout | drive_home | home
    label: str
    start: float
    end: float
    minutes: float
    detail: str = ""
    zone_id: str = ""
    provenance: str = Provenance.ESTIMATED

    def to_json(self):
        d = asdict(self)
        d["minutes"] = round(self.minutes, 1)
        d["start"] = round(self.start)
        d["end"] = round(self.end)
        return d


@dataclass
class Envelope:
    """When a given zone can actually be fished, given the day and where you start."""

    zone_id: str
    start: float                     # earliest possible first cast
    end: float                       # latest possible last cast
    drive_out: Optional[Route] = None
    drive_home: Optional[Route] = None
    launch: Optional[Dict[str, Any]] = None
    prep_minutes: float = 0.0
    takeout_minutes: float = 0.0
    run_minutes: float = 0.0
    #: Why the envelope is empty, when it is. Shown as the elimination reason (§30 step 2).
    reason: str = ""

    @property
    def minutes(self):
        return max(0.0, (self.end - self.start) / 60.0)

    @property
    def viable(self):
        return self.minutes >= MIN_ENVELOPE_MINUTES

    @property
    def overhead_minutes(self):
        """Everything that is not fishing. The number that makes a far zone lose."""
        out = (self.drive_out.minutes if self.drive_out else 0.0)
        home = (self.drive_home.slack_minutes if self.drive_home else 0.0)
        return out + home + self.prep_minutes + self.takeout_minutes + 2 * self.run_minutes

    def to_json(self):
        return {"zone_id": self.zone_id, "start": round(self.start),
                "end": round(self.end), "minutes": round(self.minutes),
                "viable": self.viable, "reason": self.reason,
                "drive_out": self.drive_out.to_json() if self.drive_out else None,
                "drive_home": self.drive_home.to_json() if self.drive_home else None,
                "launch": self.launch,
                "prep_minutes": self.prep_minutes,
                "takeout_minutes": self.takeout_minutes,
                "run_minutes": self.run_minutes,
                "overhead_minutes": round(self.overhead_minutes)}


@dataclass
class Availability:
    """§14 — the day, not the fishing window.

    `depart_after` / `return_by` are the door-to-door constraint. `fish_after` /
    `fish_before` are an optional extra narrowing for somebody who wants to leave early
    but not start fishing until light.
    """

    depart_after: float
    return_by: float
    fish_after: Optional[float] = None
    fish_before: Optional[float] = None
    #: True when the caller gave a fishing window rather than a door-to-door day, so the
    #: planner should not invent travel around it. Keeps 2.1's request shape working.
    window_only: bool = False

    @property
    def total_minutes(self):
        return (self.return_by - self.depart_after) / 60.0

    def clamp(self, start, end):
        lo = max(start, self.fish_after) if self.fish_after else start
        hi = min(end, self.fish_before) if self.fish_before else end
        return lo, hi

    def to_json(self):
        return {"depart_after": round(self.depart_after), "return_by": round(self.return_by),
                "fish_after": round(self.fish_after) if self.fish_after else None,
                "fish_before": round(self.fish_before) if self.fish_before else None,
                "window_only": self.window_only,
                "total_minutes": round(self.total_minutes)}


def _access_point(zone, craft):
    """The access a car would be aimed at, with coordinates. None when we have none."""
    serving = [a for a in zone.access if a.serves(craft)] or list(zone.access)
    with_coords = [a for a in serving if a.lat is not None and a.lon is not None]
    if with_coords:
        # Prefer a verified one — driving somebody to an unverified pin is the §25 failure
        # in its logistics form.
        with_coords.sort(key=lambda a: (not a.verified,))
        return with_coords[0]
    return serving[0] if serving else None


def envelope(zone, availability, origin, craft, routing, now=None):
    """The fishable envelope for one zone. §19.

    `origin` is (lat, lon) or None. With no origin there is no travel model, so the
    envelope IS the availability — which is exactly 2.1's behaviour, preserved for
    requests that give a fishing window rather than a day.
    """
    a, b = availability.clamp(availability.depart_after, availability.return_by)

    if availability.window_only or origin is None:
        return Envelope(zone_id=zone.id, start=a, end=b,
                        launch=_launch_json(_access_point(zone, craft)))

    acc = _access_point(zone, craft)
    if acc is None or acc.lat is None:
        return Envelope(zone_id=zone.id, start=a, end=a, launch=None,
                        reason="no access point with coordinates, so no drive can be "
                               "planned to this water")

    trailer = craft in TRAILERED
    out = routing.route(origin, (acc.lat, acc.lon), trailer=trailer,
                        origin_id=getattr(origin, "id", None), access_id=acc.id)
    back = routing.route((acc.lat, acc.lon), origin, trailer=trailer,
                         origin_id=getattr(origin, "id", None), access_id=acc.id)
    if out is None or back is None:
        return Envelope(zone_id=zone.id, start=a, end=a, launch=_launch_json(acc),
                        reason="no route could be established to this water")

    prep = LAUNCH_PREP_MINUTES.get(craft, LAUNCH_PREP_MINUTES[Craft.ANY])
    tout = TAKEOUT_MINUTES.get(craft, TAKEOUT_MINUTES[Craft.ANY])
    run = RUN_TO_WATER_MINUTES.get(craft, RUN_TO_WATER_MINUTES[Craft.ANY])

    start = availability.depart_after + (out.minutes + prep + run) * 60.0
    # The return leg carries its provenance's slack. Being early costs nothing; being
    # late is the failure.
    end = availability.return_by - (back.slack_minutes + tout + run) * 60.0
    start, end = availability.clamp(start, end)

    env = Envelope(zone_id=zone.id, start=start, end=max(start, end),
                   drive_out=out, drive_home=back, launch=_launch_json(acc),
                   prep_minutes=prep, takeout_minutes=tout, run_minutes=run)
    if not env.viable:
        env.reason = (
            "the day does not reach this water — %d minutes of driving, rigging and "
            "running leaves %d fishable minutes of the %d you have"
            % (round(env.overhead_minutes), round(env.minutes),
               round(availability.total_minutes)))
    return env


def _launch_json(acc):
    if acc is None:
        return None
    d = acc.to_json()
    return {"id": d.get("id"), "name": d.get("name"), "lat": d.get("lat"),
            "lon": d.get("lon"), "verified": d.get("verified"),
            "note": d.get("note"), "source": d.get("source"),
            "evidence": d.get("evidence"), "evidence_label": d.get("evidence_label")}


def legs(env, windows, moves, availability, craft, tz):
    """The full door-to-door timeline. §14, §18, §48.

    `windows` are the chosen OpportunityWindows in time order; `moves` the Transitions
    between them. Returns Legs covering every minute from leaving the house to getting
    back, which is what BRIEF renders and what the "leave by" clock reads off.
    """
    if not windows:
        return []
    out = []
    first, last = windows[0], windows[-1]

    if env.drive_out is not None:
        # Leave as late as the plan allows rather than as early as the day allows: nobody
        # wants to sit in a parking lot for forty minutes because the day started at five.
        run = env.run_minutes * 60.0
        prep = env.prep_minutes * 60.0
        drive = env.drive_out.minutes * 60.0
        launch_at = first.start - run
        prep_at = launch_at - prep
        depart_at = max(availability.depart_after, prep_at - drive)
        # If leaving that late would miss the window, leave when the day opens.
        if depart_at + drive + prep + run > first.start:
            depart_at = availability.depart_after
            prep_at = depart_at + drive
            launch_at = prep_at + prep

        out.append(Leg("depart", "Leave", depart_at, depart_at, 0.0,
                       detail=env.drive_out.detail,
                       provenance=env.drive_out.provenance))
        out.append(Leg("drive_out", "Drive", depart_at, depart_at + drive,
                       env.drive_out.minutes,
                       detail="%s to %s" % (
                           Provenance.LABEL.get(env.drive_out.provenance, ""),
                           (env.launch or {}).get("name", "the access")),
                       provenance=env.drive_out.provenance))
        out.append(Leg("prep", _prep_label(craft), prep_at, launch_at,
                       env.prep_minutes, zone_id=env.zone_id))
        out.append(Leg("run_out", "Run to the water", launch_at, first.start,
                       env.run_minutes, zone_id=env.zone_id))

    for i, w in enumerate(windows):
        out.append(Leg("fish", "Fish", w.start, w.end, w.duration_minutes,
                       zone_id=w.zone_id, detail=getattr(w, "why", "") or ""))
        if i < len(moves):
            m = moves[i]
            out.append(Leg("move", "Move", w.end, w.end + m.minutes * 60.0, m.minutes,
                           detail=m.detail, zone_id=m.to_zone, provenance=m.provenance))

    if env.drive_home is not None:
        run_back = env.run_minutes * 60.0
        tout = env.takeout_minutes * 60.0
        drive = env.drive_home.minutes * 60.0
        ramp_at = last.end + run_back
        leave_at = ramp_at + tout
        out.append(Leg("run_back", "Run back", last.end, ramp_at, env.run_minutes,
                       zone_id=last.zone_id))
        out.append(Leg("takeout", _takeout_label(craft), ramp_at, leave_at,
                       env.takeout_minutes, zone_id=last.zone_id))
        out.append(Leg("drive_home", "Drive home", leave_at, leave_at + drive,
                       env.drive_home.minutes,
                       detail=Provenance.LABEL.get(env.drive_home.provenance, ""),
                       provenance=env.drive_home.provenance))
        out.append(Leg("home", "Home", leave_at + drive, leave_at + drive, 0.0,
                       provenance=env.drive_home.provenance))
    return out


def _prep_label(craft):
    return {Craft.WADE: "Park and rig", Craft.KAYAK: "Unload and put in",
            Craft.DRIFT: "Launch and park the trailer",
            Craft.POWER: "Launch and park the trailer"}.get(craft, "Rig up")


def _takeout_label(craft):
    return {Craft.WADE: "Back to the car", Craft.KAYAK: "Take out and load",
            Craft.DRIFT: "Take out and trailer",
            Craft.POWER: "Take out and trailer"}.get(craft, "Load up")


def summary(legs_list):
    """The five times the hero block shows (§44): leave, launch, fish, off, home."""
    by = {l.kind: l for l in legs_list}
    fish = [l for l in legs_list if l.kind == "fish"]
    if not fish:
        return {}
    return {
        "leave": round(by["depart"].start) if "depart" in by else None,
        "launch": round(by["run_out"].start) if "run_out" in by else None,
        "fish_start": round(fish[0].start),
        "fish_end": round(fish[-1].end),
        "off_water": round(by["takeout"].end) if "takeout" in by else None,
        "home": round(by["home"].end) if "home" in by else None,
        "fishing_minutes": round(sum(l.minutes for l in fish)),
        "travel_minutes": round(sum(l.minutes for l in legs_list
                                    if l.kind in ("drive_out", "drive_home", "move",
                                                  "run_out", "run_back"))),
        "overhead_minutes": round(sum(l.minutes for l in legs_list
                                      if l.kind in ("prep", "takeout"))),
    }


def published():
    """Every constant, to the browser — CLAUDE.md's rule, and §7's contract."""
    return {"launch_prep_minutes": LAUNCH_PREP_MINUTES,
            "takeout_minutes": TAKEOUT_MINUTES,
            "run_to_water_minutes": RUN_TO_WATER_MINUTES,
            "min_envelope_minutes": MIN_ENVELOPE_MINUTES,
            "trailered": list(TRAILERED)}
