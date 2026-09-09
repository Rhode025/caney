"""
RiverSnapshot — everything known about one piece of water at one moment. §24.

No HTML, no CSS, no presentation of any kind. The web UI, RiverGuide and the tests all
read this; none of them scrapes a generated page. Values are Observations, so "we don't
know the release forecast" and "the release forecast is zero" are different objects.
"""
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .observation import Observation, DataState, budget_for


@dataclass
class RiverSnapshot:
    zone_id: str = ""
    river_id: str = ""                       # legacy generator that owns the hydrology
    taken_at: float = field(default_factory=time.time)

    # ── water (§29) ─────────────────────────────────────────────────────────
    flow: Observation = field(default_factory=Observation.unknown)
    stage: Observation = field(default_factory=Observation.unknown)
    flow_trend: Observation = field(default_factory=Observation.unknown)
    stage_trend: Observation = field(default_factory=Observation.unknown)
    generation: Observation = field(default_factory=Observation.unknown)     # cfs released
    generation_on: Observation = field(default_factory=Observation.unknown)  # bool
    generation_forecast: Observation = field(default_factory=Observation.unknown)  # [(epoch,cfs)]
    water_temp: Observation = field(default_factory=Observation.unknown)
    lake_elevation: Observation = field(default_factory=Observation.unknown)
    clarity: Observation = field(default_factory=Observation.unknown)
    recent_rain_in: Observation = field(default_factory=Observation.unknown)

    # ── weather (§28), hourly across the horizon ────────────────────────────
    weather_hours: List[Dict[str, Any]] = field(default_factory=list)
    weather_daily: Dict[str, Any] = field(default_factory=dict)
    tz_name: str = "America/Chicago"
    sunrise: Observation = field(default_factory=Observation.unknown)
    sunset: Observation = field(default_factory=Observation.unknown)

    # ── model predictions & uncertainty (§3.5) ──────────────────────────────
    arrival: Dict[str, Any] = field(default_factory=dict)   # {earliest,typical,latest,...}
    model_confidence: str = "unknown"       # measured | reported | structural | unknown
    model_note: str = ""

    lunar: Dict[str, Any] = field(default_factory=dict)
    access: List[Dict[str, Any]] = field(default_factory=list)
    research: List[Dict[str, Any]] = field(default_factory=list)
    biological_context: Dict[str, Any] = field(default_factory=dict)
    safety_claim_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # ── freshness (§57) ─────────────────────────────────────────────────────
    def freshness(self):
        """Per-signal ages. There is deliberately no single 'updated' timestamp."""
        rows = []
        for label, kind, ob in (
                ("Water", "flow", self.flow),
                ("Stage", "stage", self.stage),
                ("Generation", "generation", self.generation),
                ("Generation forecast", "release_forecast", self.generation_forecast),
                ("Water temperature", "water_temp", self.water_temp),
                ("Lake elevation", "lake_elev", self.lake_elevation)):
            if ob.state == DataState.UNKNOWN and not ob.source:
                continue
            rows.append({"label": label, "state": ob.state, "age": ob.age_label(),
                         "source": ob.source, "source_url": ob.source_url})
        if self.weather_hours:
            w = self.weather_hours[0].get("_fetched_at")
            rows.append({"label": "Weather", "state": "known",
                         "age": Observation(fetched_at=w, state=DataState.KNOWN,
                                            value=1).age_label() if w else "unknown",
                         "source": "Open-Meteo / NWS", "source_url": ""})
        return rows

    def apply_freshness_budgets(self, now=None):
        """Demote anything past its budget. Called once, after loading, before scoring."""
        for name, kind in (("flow", "flow"), ("stage", "stage"),
                           ("generation", "generation"),
                           ("generation_forecast", "release_forecast"),
                           ("water_temp", "water_temp"),
                           ("lake_elevation", "lake_elev")):
            ob = getattr(self, name)
            setattr(self, name, ob.with_staleness(budget_for(kind), now))
        return self

    #: Injected by the sources layer (see caney/sources/snapshots.localize). The domain
    #: layer may not import upward, and computing sun times and moon phase needs both the
    #: weather adapter and the lunar model — so localisation is a function OVER a snapshot,
    #: not a method ON one. test_architecture.test_layering pins that.

    def weather_at(self, epoch):
        """The hourly weather row covering `epoch`, or None. Never the day's average."""
        best, bd = None, None
        for h in self.weather_hours:
            d = abs(h.get("epoch", 0) - epoch)
            if bd is None or d < bd:
                best, bd = h, d
        return best if (bd is not None and bd <= 5400) else None

    def weather_window(self, start, end):
        """§28 — weather for the USER'S window, not for 'today'."""
        return [h for h in self.weather_hours if start <= h.get("epoch", 0) <= end]

    @staticmethod
    def from_json(d):
        """Rebuild a snapshot from its own JSON. §12, §33.

        The API Worker does not build snapshots on the request path — 22 zones of
        hydrology is far more work than answering one question, and doing it per request
        exceeded the platform's limits on the second call. A scheduled build writes them
        to KV and requests rehydrate here.

        The round trip must be LOSSLESS for the Observation states in particular:
        `known`/`stale`/`unknown`/`error` are the whole basis of the freshness strip and
        of the confidence penalty, and a rehydrate that flattened them to plain values
        would restore the exact failure this codebase is built to prevent.
        """
        s = RiverSnapshot(
            zone_id=d.get("zone_id", ""), river_id=d.get("river_id", ""),
            taken_at=d.get("taken_at") or time.time())
        for k in ("flow", "stage", "flow_trend", "stage_trend", "generation",
                  "generation_on", "generation_forecast", "water_temp",
                  "lake_elevation", "clarity", "recent_rain_in", "sunrise", "sunset"):
            setattr(s, k, Observation.from_json(d.get(k) or {}))
        s.weather_hours = d.get("weather_hours") or []
        s.weather_daily = d.get("weather_daily") or {}
        s.tz_name = d.get("tz_name") or "America/Chicago"
        s.arrival = d.get("arrival") or {}
        s.model_confidence = d.get("model_confidence", "unknown")
        s.model_note = d.get("model_note", "")
        s.lunar = d.get("lunar") or {}
        s.access = d.get("access") or []
        s.research = d.get("research") or []
        s.biological_context = d.get("biological_context") or {}
        s.safety_claim_ids = d.get("safety_claim_ids") or []
        s.errors = d.get("errors") or []
        return s

    def to_json(self):
        out = {"zone_id": self.zone_id, "river_id": self.river_id,
               "tz_name": self.tz_name, "weather_daily": self.weather_daily,
               "taken_at": self.taken_at, "arrival": self.arrival,
               "model_confidence": self.model_confidence, "model_note": self.model_note,
               "lunar": self.lunar, "access": self.access, "research": self.research,
               "biological_context": self.biological_context,
               "safety_claim_ids": self.safety_claim_ids,
               "weather_hours": self.weather_hours,
               "freshness": self.freshness(), "errors": self.errors}
        for k in ("flow", "stage", "flow_trend", "stage_trend", "generation",
                  "generation_on", "generation_forecast", "water_temp", "lake_elevation",
                  "clarity", "recent_rain_in", "sunrise", "sunset"):
            out[k] = getattr(self, k).to_json()
        return out
