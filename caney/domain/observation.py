"""
Observation — one measured or modelled value, with its state, provenance and age.

THE RULE THIS TYPE EXISTS TO ENFORCE: unknown is not zero.

`value or 0` is how a missing Center Hill release forecast becomes "0 cfs", which becomes
"minimum flow", which becomes "wade all day", which puts someone in the river during a
two-unit release. Every number that reaches a plan carries a DataState saying whether it
was actually observed. Arithmetic on an unknown yields an unknown; it never yields 0.
"""
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


class DataState:
    KNOWN = "known"      # observed or modelled from observations, inside its freshness budget
    STALE = "stale"      # was observed, but older than the budget for this kind of value
    UNKNOWN = "unknown"  # never obtained — the source has no reading for this
    ERROR = "error"      # the source was reached and failed, or returned nonsense

    ALL = (KNOWN, STALE, UNKNOWN, ERROR)
    #: states in which a value may be shown as a number at all
    NUMERIC = (KNOWN, STALE)


@dataclass
class Observation:
    """A single value plus everything needed to decide how much to trust it."""
    value: Any = None
    unit: str = ""
    state: str = DataState.UNKNOWN
    observed_at: Optional[float] = None   # epoch seconds the reading describes
    fetched_at: Optional[float] = None    # epoch seconds we obtained it
    source: str = ""                      # human name, e.g. "USACE CWMS (LRN)"
    source_url: str = ""
    confidence: float = 0.0               # 0..1, how much the planner may lean on it
    note: str = ""

    # ── constructors ────────────────────────────────────────────────────────
    @classmethod
    def known(cls, value, unit="", source="", source_url="", observed_at=None,
              confidence=0.9, note=""):
        if value is None:
            return cls.unknown(unit, source, note="value was None")
        return cls(value=value, unit=unit, state=DataState.KNOWN,
                   observed_at=observed_at, fetched_at=time.time(), source=source,
                   source_url=source_url, confidence=confidence, note=note)

    @classmethod
    def unknown(cls, unit="", source="", note=""):
        return cls(value=None, unit=unit, state=DataState.UNKNOWN,
                   fetched_at=time.time(), source=source, confidence=0.0, note=note)

    @classmethod
    def error(cls, unit="", source="", note=""):
        return cls(value=None, unit=unit, state=DataState.ERROR,
                   fetched_at=time.time(), source=source, confidence=0.0, note=note)

    @classmethod
    def stale(cls, value, unit="", source="", source_url="", observed_at=None,
              confidence=0.4, note=""):
        if value is None:
            return cls.unknown(unit, source, note=note or "stale with no value")
        return cls(value=value, unit=unit, state=DataState.STALE,
                   observed_at=observed_at, fetched_at=time.time(), source=source,
                   source_url=source_url, confidence=confidence, note=note)

    # ── queries ─────────────────────────────────────────────────────────────
    @property
    def ok(self) -> bool:
        """True when there is a real number here. The ONLY gate that may precede use."""
        return self.state in DataState.NUMERIC and self.value is not None

    def age_s(self, now=None) -> Optional[float]:
        # `or` would treat epoch 0 as missing. Explicit None checks only — this file
        # exists precisely to stop falsy-means-absent bugs.
        t = self.observed_at if self.observed_at is not None else self.fetched_at
        if t is None:
            return None
        return max(0.0, (now if now is not None else time.time()) - t)

    def age_label(self, now=None) -> str:
        """'8 min ago' / '3 h ago' / '14 days old' / 'unknown'. Never a bare 'updated'."""
        if not self.ok:
            return "unknown"
        a = self.age_s(now)
        if a is None:
            return "unknown"
        m = a / 60.0
        if m < 1:      return "just now"
        if m < 90:     return "%d min ago" % round(m)
        h = m / 60.0
        if h < 36:     return "%d h ago" % round(h)
        return "%d days old" % round(h / 24.0)

    def or_else(self, default):
        """The explicit, greppable replacement for `value or 0`.

        Callers must name the fallback at the call site, so a reviewer can see whether
        substituting it is safe. There is deliberately no zero default."""
        return self.value if self.ok else default

    def require(self, why=""):
        """Value or raise. Use where proceeding without the number is unsafe."""
        if not self.ok:
            raise UnknownValue("%s is %s%s" % (self.source or "value", self.state,
                                               (" — " + why) if why else ""))
        return self.value

    def with_staleness(self, budget_s, now=None):
        """Demote KNOWN → STALE once past the freshness budget for this kind of value."""
        if self.state != DataState.KNOWN:
            return self
        a = self.age_s(now)
        if a is None or a <= budget_s:
            return self
        return Observation(value=self.value, unit=self.unit, state=DataState.STALE,
                           observed_at=self.observed_at, fetched_at=self.fetched_at,
                           source=self.source, source_url=self.source_url,
                           confidence=self.confidence * 0.45,
                           note=(self.note + " " if self.note else "") +
                                "older than the %s budget for this value" % _dur(budget_s))

    def to_json(self):
        d = asdict(self)
        d["age_label"] = self.age_label()
        return d


class UnknownValue(Exception):
    """Raised by Observation.require(). Caught by the planner and turned into a SKIP."""


def _dur(s):
    if s < 3600:  return "%d-minute" % round(s / 60)
    if s < 86400: return "%d-hour" % round(s / 3600)
    return "%d-day" % round(s / 86400)


# Freshness budgets by kind of value (seconds). Section 57: no single generic "updated".
FRESHNESS_BUDGET = {
    "flow":        3 * 3600,
    "stage":       3 * 3600,
    "generation":  2 * 3600,
    "release_forecast": 6 * 3600,
    "water_temp":  12 * 3600,
    "weather":     3 * 3600,
    "lake_elev":   24 * 3600,
    "research_report": 21 * 86400,
    "research_management": 400 * 86400,
    "regulation":  400 * 86400,
}


def budget_for(kind):
    return FRESHNESS_BUDGET.get(kind, 6 * 3600)
