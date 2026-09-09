"""
PlanSession and PlanDelta — the plan as a thing that runs, and the plan as a thing that
changes underneath you. §9, §10, §11, §56.

Caney 2.1 had a boolean. `onwater = true` was enough when the product was a report you
read before leaving, because there were only two states worth distinguishing: looking at
it, and not. A live guide has more, and they are not decoration — each one changes which
question the app should be answering and which refresh cadence is honest:

    DRAFT       composing constraints; nothing computed
    READY       a plan exists and the user has not committed to it
    EN_ROUTE    committed and travelling; the useful question is "will I make the window"
    AT_LAUNCH   arrived; "rig for what, and how long until it starts"
    ON_WATER    fishing; "what do I do NOW, and when do I move"
    COMPLETED   ended normally; the outcome loop opens
    ABORTED     ended early; the outcome loop opens with a different first question

Storing that as one boolean would force every consumer to re-derive the state from clock
arithmetic, and they would each derive it slightly differently.

PLANDELTA (§10, §11) answers one question: has anything changed that should change what
you DO? Not "has anything changed" — gauges move constantly and a product that says PLAN
CHANGED every five minutes teaches people to ignore it. The thresholds below are the
whole design. They are published constants for the same reason the utility constants are
(CLAUDE.md): the browser must never re-decide materiality on its own, and a number this
consequential should not be buried in a comparison.
"""
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class PlanState:
    DRAFT = "DRAFT"
    READY = "READY"
    EN_ROUTE = "EN_ROUTE"
    AT_LAUNCH = "AT_LAUNCH"
    ON_WATER = "ON_WATER"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"

    ALL = (DRAFT, READY, EN_ROUTE, AT_LAUNCH, ON_WATER, COMPLETED, ABORTED)

    #: States in which the trip is live and conditions must be watched (§12).
    ACTIVE = (EN_ROUTE, AT_LAUNCH, ON_WATER)
    #: States from which nothing further happens.
    TERMINAL = (COMPLETED, ABORTED)

    LABEL = {DRAFT: "Draft", READY: "Ready", EN_ROUTE: "En route", AT_LAUNCH: "At launch",
             ON_WATER: "On water", COMPLETED: "Completed", ABORTED: "Aborted"}

    #: Legal transitions. A trip may be abandoned from anywhere, may not resume once
    #: terminal, and may skip AT_LAUNCH (people put in and start fishing).
    NEXT = {
        DRAFT: (READY, ABORTED),
        READY: (EN_ROUTE, AT_LAUNCH, ON_WATER, DRAFT, ABORTED),
        EN_ROUTE: (AT_LAUNCH, ON_WATER, ABORTED),
        AT_LAUNCH: (ON_WATER, ABORTED),
        ON_WATER: (COMPLETED, ABORTED),
        COMPLETED: (),
        ABORTED: (),
    }

    #: How often to re-check while active (§12). Seconds. On the water the generation
    #: schedule is what moves; en route the drive estimate is.
    REFRESH_SECONDS = {EN_ROUTE: 600, AT_LAUNCH: 420, ON_WATER: 300}

    @staticmethod
    def can(frm, to):
        return to in PlanState.NEXT.get(frm, ())


class Materiality:
    INFORMATIONAL = "informational"   # true, recorded, not shown unprompted
    NOTABLE = "notable"               # shown in "what changed", does not interrupt
    MATERIAL = "material"             # the plan changed; interrupt

    ORDER = (INFORMATIONAL, NOTABLE, MATERIAL)

    @staticmethod
    def rank(m):
        try:
            return Materiality.ORDER.index(m)
        except ValueError:
            return 0


class Threshold:
    """What counts as a change worth acting on. §10, §11.

    Every number here is a judgement about human behaviour, not about hydrology, and none
    is calibrated. They were chosen so that the alerts a person gets in a morning are the
    ones they would have wanted a text message about. docs/PLANNER.md records the
    reasoning; the trip log is what should eventually move them.
    """

    #: A generation start or stop moving by more than this changes when you fish and where.
    #: Twenty minutes is roughly one move between adjacent features — below it the plan
    #: absorbs the shift, above it the plan is wrong.
    GENERATION_SHIFT_MINUTES = 20.0

    #: Discharge. Proportional, because 200 cfs means something different on the Caney
    #: than on the Cumberland at Nashville.
    FLOW_CHANGE_FRACTION = 0.25

    #: Stage, in feet. Absolute, because this is the number that decides whether you can
    #: stand up.
    STAGE_CHANGE_FEET = 0.5

    #: SAFETY IS ASYMMETRIC AND THIS IS THE MOST IMPORTANT LINE IN THE FILE. A safe-exit
    #: time moving LATER is good news and merely notable. Moving EARLIER by even a few
    #: minutes is material every time, because the person is standing in the river acting
    #: on the old number. Never make these one symmetric threshold.
    SAFE_EXIT_EARLIER_MINUTES = 5.0
    SAFE_EXIT_LATER_MINUTES = 30.0

    #: A move time inside the itinerary shifting.
    MOVE_SHIFT_MINUTES = 15.0

    #: The window's own quality. Points on the 0-100 opportunity scale.
    OPPORTUNITY_POINTS = 8.0

    #: Drive time, for the "leave by" clock (§18).
    DRIVE_SHIFT_MINUTES = 12.0

    @staticmethod
    def published():
        """Emitted to the client so nothing re-decides materiality locally (§11)."""
        return {k: getattr(Threshold, k) for k in dir(Threshold)
                if k.isupper() and not k.startswith("_")}


@dataclass
class DeltaChange:
    field_name: str
    label: str
    was: Any = None
    now: Any = None
    was_label: str = ""
    now_label: str = ""
    materiality: str = Materiality.INFORMATIONAL
    why: str = ""
    zone_id: str = ""

    def to_json(self):
        d = asdict(self)
        d["field"] = d.pop("field_name")
        return d


class DeltaVerdict:
    UNCHANGED = "UNCHANGED"
    MATERIAL_CHANGE = "MATERIAL_CHANGE"


@dataclass
class PlanDelta:
    """§10, §11 — the structured answer to "is my plan still right?"."""

    verdict: str = DeltaVerdict.UNCHANGED
    checked_at: float = field(default_factory=time.time)
    from_snapshot: str = ""
    to_snapshot: str = ""
    changes: List[DeltaChange] = field(default_factory=list)
    #: One sentence a person can act on. §56 — "Generation ended 43 minutes early. Move to
    #: the Caney confluence now." Empty when nothing material moved.
    headline: str = ""
    #: The itinerary difference, when the plan itself moved rather than just its inputs.
    was_itinerary: Optional[Dict[str, Any]] = None
    now_itinerary: Optional[Dict[str, Any]] = None
    #: Set when the new plan is available to swap in.
    new_plan_id: str = ""

    @property
    def material(self):
        return any(c.materiality == Materiality.MATERIAL for c in self.changes)

    def finalise(self):
        self.verdict = (DeltaVerdict.MATERIAL_CHANGE if self.material
                        else DeltaVerdict.UNCHANGED)
        if self.material and not self.headline:
            first = next(c for c in self.changes
                         if c.materiality == Materiality.MATERIAL)
            self.headline = first.why or first.label
        return self

    def to_json(self):
        return {"verdict": self.verdict, "checked_at": self.checked_at,
                "from_snapshot": self.from_snapshot, "to_snapshot": self.to_snapshot,
                "changes": [c.to_json() for c in self.changes],
                "headline": self.headline,
                "was_itinerary": self.was_itinerary, "now_itinerary": self.now_itinerary,
                "new_plan_id": self.new_plan_id,
                "thresholds": Threshold.published()}


@dataclass
class PlanSession:
    """§9 — a plan being executed."""

    id: str = ""
    plan_id: str = ""
    snapshot_id: str = ""
    state: str = PlanState.DRAFT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None       # when START TRIP was tapped
    ended_at: Optional[float] = None
    #: [(epoch, from, to, reason)] — the audit trail, so a trip's shape is reconstructable.
    history: List[Dict[str, Any]] = field(default_factory=list)
    #: The last delta shown to the user, so the banner is not re-raised on every poll.
    last_delta: Optional[Dict[str, Any]] = None
    last_checked_at: Optional[float] = None
    #: §68 — filled at the end, four taps.
    outcome: Optional[Dict[str, Any]] = None
    notes: str = ""

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = "sess_" + uuid.uuid4().hex[:12]

    @property
    def active(self):
        return self.state in PlanState.ACTIVE

    @property
    def terminal(self):
        return self.state in PlanState.TERMINAL

    def refresh_seconds(self):
        """§12 — how long until this session should re-check. None when it should not."""
        return PlanState.REFRESH_SECONDS.get(self.state)

    def transition(self, to, reason="", at=None):
        if not PlanState.can(self.state, to):
            raise ValueError("a session may not go from %s to %s" % (self.state, to))
        at = at or time.time()
        self.history.append({"at": at, "from": self.state, "to": to, "reason": reason})
        if to == PlanState.EN_ROUTE and self.started_at is None:
            self.started_at = at
        if to in PlanState.TERMINAL:
            self.ended_at = at
        self.state = to
        self.updated_at = at
        return self

    def to_json(self):
        d = asdict(self)
        d["active"] = self.active
        d["terminal"] = self.terminal
        d["state_label"] = PlanState.LABEL.get(self.state, self.state)
        d["refresh_seconds"] = self.refresh_seconds()
        return d

    @staticmethod
    def from_json(d):
        return PlanSession(**{k: v for k, v in d.items()
                              if k in PlanSession.__dataclass_fields__})
