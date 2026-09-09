"""
Confidence — a separate number from score. §31.

Score answers "how good is this fishery for this species in this window, if the data is
right". Confidence answers "how much of that rests on something we actually measured".

They are deliberately not blended into one figure, because a reader deciding whether to
drive 70 minutes needs both. The RANKER blends them, once, explicitly, with a published
rule (`rank_key`), so the trade-off is inspectable instead of buried in a scorer.

The worked example from §31 falls out of this arithmetic:
    score 89 / confidence 42  (attractive fishery, no live water)  ranks BELOW
    score 84 / confidence 93  (slightly worse fishery, fully observed)
"""
from ..domain.observation import DataState

# What each signal is worth to confidence, and whether its absence is disqualifying.
SIGNALS = [
    ("flow",                0.16, "Flow"),
    ("stage",               0.06, "Stage"),
    ("generation",          0.14, "Dam release now"),
    ("generation_forecast", 0.16, "Release forecast"),
    ("water_temp",          0.12, "Water temperature"),
    ("weather",             0.14, "Hourly weather"),
    ("sun",                 0.04, "Sun times"),
    ("research",            0.10, "Sourced research"),
    ("model",               0.08, "Routing model"),
]

STATE_CREDIT = {DataState.KNOWN: 1.0, DataState.STALE: 0.45,
                DataState.UNKNOWN: 0.0, DataState.ERROR: 0.0}

MODEL_CREDIT = {"measured": 1.0, "reported": 0.7, "structural": 0.6, "unknown": 0.25}


def confidence(zone, snap, claims, window, forecast_days_out=0):
    """(0..100, [rows]) — rows are the evidence drawer's freshness table (§33, §57)."""
    rows, total, got = [], 0.0, 0.0

    def credit(key, weight, label, state, detail, url=""):
        nonlocal total, got
        c = STATE_CREDIT.get(state, 0.0)
        total += weight
        got += weight * c
        rows.append({"key": key, "label": label, "state": state, "weight": weight,
                     "detail": detail, "source_url": url})

    for key, weight, label in SIGNALS:
        if key in ("flow", "stage", "generation", "generation_forecast", "water_temp"):
            ob = getattr(snap, key)
            # A river with no dam is not penalised for having no release forecast: the
            # signal does not exist there, so it leaves the denominator entirely.
            if key in ("generation", "generation_forecast") and not zone.tailwater:
                continue
            credit(key, weight, label, ob.state, "%s · %s" % (ob.source or "—", ob.age_label()),
                   ob.source_url)
        elif key == "weather":
            n = len(snap.weather_window(*window))
            credit(key, weight, label,
                   DataState.KNOWN if n >= 2 else DataState.UNKNOWN,
                   "%d hourly rows inside the requested window" % n)
        elif key == "sun":
            credit(key, weight, label,
                   DataState.KNOWN if snap.sunrise.ok else DataState.UNKNOWN,
                   snap.sunrise.source or "—")
        elif key == "research":
            rel = [c for c in claims if (not c.location_ids or zone.id in c.location_ids)]
            best = max([c.confidence for c in rel], default=0.0)
            state = (DataState.KNOWN if best >= 0.45 else
                     DataState.STALE if rel else DataState.UNKNOWN)
            credit(key, weight, label, state,
                   "%d claim(s) for this water, best confidence %.2f" % (len(rel), best))
        elif key == "model":
            mc = snap.model_confidence or "unknown"
            total += weight
            got += weight * MODEL_CREDIT.get(mc, 0.25)
            rows.append({"key": key, "label": label, "state": mc, "weight": weight,
                         "detail": snap.model_note or
                                   ("routing model confidence: %s" % mc), "source_url": ""})

    base = 100.0 * (got / total) if total else 0.0

    # §5: a request beyond reliable forecasting is a SEASONAL EXPECTATION, not a forecast.
    # Confidence falls off, and the plan says so in its own words rather than implying
    # exact generation and weather certainty.
    horizon_penalty = 0.0
    if forecast_days_out >= 3:
        horizon_penalty = min(45.0, 12.0 * (forecast_days_out - 2))
        rows.append({"key": "horizon", "label": "Forecast horizon", "state": "stale",
                     "weight": 0.0,
                     "detail": "%d days out — seasonal expectation, not a forecast"
                               % forecast_days_out, "source_url": ""})
    return max(0.0, round(base - horizon_penalty, 1)), rows


def rank_key(score, conf):
    """The ONE published blend. §31.

    Confidence acts as a multiplier that can cost a candidate up to 35% of its score, so a
    fully-observed 84 beats an unobserved 89:
        89 * (0.65 + 0.35*0.42) = 71.0
        84 * (0.65 + 0.35*0.93) = 81.9
    """
    return score * (0.65 + 0.35 * (conf / 100.0))


def confidence_label(conf):
    if conf >= 78: return "HIGH CONFIDENCE"
    if conf >= 55: return "MODERATE CONFIDENCE"
    if conf >= 32: return "LOW CONFIDENCE"
    return "VERY LOW CONFIDENCE"
