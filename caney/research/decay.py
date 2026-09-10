"""
How fast a claim's influence decays. §24, §62.

ONE TABLE, TWO CONSUMERS. This is the canonical copy; `research-worker/src/decay.json` is
generated from it by `tools/emit_decay.py` and imported by `claims.js`, and
`test_research.py` fails if the two drift. Python owns the numbers for the same reason
CLAUDE.md gives for every other calibrated constant: a value that lives in two places gets
edited in one.

WHY THIS FILE EXISTS. Until now the two halves of the research system disagreed badly about
decay, and in both directions at once. Python applied a single step curve to every claim
type — 1.0 within a week, then 0.9, 0.75, 0.55, floor 0.35 — while the worker had these
sixteen per-type curves. Measured at five years old:

    a FISHING REPORT    python 0.350   here 0.050   python was 7x too generous
    a HABITAT note      python 0.350   here 0.700   python gave it half its worth

At one month old the fishing report was 18x over-weighted. A guide's Tuesday report and an
electrofishing survey are not the same kind of fact, and one curve for both makes the
perishable one go stale far too slowly and the structural one far too fast.

It was latent rather than live — the research worker does not yet feed the planner — which
is exactly why it is worth fixing before RES-03 switches research on.

    ttl_seconds     when we would go looking again
    half_life_days  how fast influence decays in the meantime
    floor           what the claim is always worth, however old

THE NUMBERS ARE JUDGEMENTS, NOT MEASUREMENTS, like every other prior in this repo. What is
defensible is the ORDERING and the shape: a report has a five-day half-life and almost no
floor; a regulation does not decay in influence at all because it is either current or
wrong, but carries a short TTL because it must be rechecked.
"""

#: Canonical. Keep in sync with research-worker/src/decay.json via tools/emit_decay.py.
DECAY = {
    "recent_report":         {"ttl_seconds": 12 * 3600,   "half_life_days": 5,      "floor": 0.05},
    "creel_result":          {"ttl_seconds": 30 * 86400,  "half_life_days": 400,    "floor": 0.45},
    "generation_response":   {"ttl_seconds": 21 * 86400,  "half_life_days": 900,    "floor": 0.60},
    "current_response":      {"ttl_seconds": 28 * 86400,  "half_life_days": 1200,   "floor": 0.65},
    "thermal_refuge":        {"ttl_seconds": 28 * 86400,  "half_life_days": 1200,   "floor": 0.65},
    "seasonal_distribution": {"ttl_seconds": 28 * 86400,  "half_life_days": 1500,   "floor": 0.65},
    "migration":             {"ttl_seconds": 28 * 86400,  "half_life_days": 1500,   "floor": 0.65},
    "time_of_day":           {"ttl_seconds": 28 * 86400,  "half_life_days": 1500,   "floor": 0.60},
    "weather_response":      {"ttl_seconds": 28 * 86400,  "half_life_days": 1500,   "floor": 0.60},
    "forage":                {"ttl_seconds": 45 * 86400,  "half_life_days": 1100,   "floor": 0.55},
    "habitat":               {"ttl_seconds": 90 * 86400,  "half_life_days": 2200,   "floor": 0.70},
    "species_presence":      {"ttl_seconds": 90 * 86400,  "half_life_days": 2200,   "floor": 0.70},
    "technique":             {"ttl_seconds": 60 * 86400,  "half_life_days": 900,    "floor": 0.40},
    "stocking":              {"ttl_seconds": 14 * 86400,  "half_life_days": 500,    "floor": 0.35},
    "survey":                {"ttl_seconds": 180 * 86400, "half_life_days": 1800,   "floor": 0.45},
    # Regulations do not decay in INFLUENCE — they are either current or they are wrong —
    # but they must be rechecked, so the TTL is short and the floor is high.
    "regulation":            {"ttl_seconds": 7 * 86400,   "half_life_days": 100000, "floor": 0.95},
}

DEFAULT = {"ttl_seconds": 21 * 86400, "half_life_days": 900, "floor": 0.5}

#: The seed corpus said `seasonal_location` where the worker said `seasonal_distribution`.
#: The same concept under two names is the same divergence this file exists to end, so the
#: old spelling is aliased rather than silently falling through to DEFAULT — which is what
#: it was doing, and which cost three TWRA claims a third of their weight.
ALIASES = {
    "seasonal_location": "seasonal_distribution",
}


def decay_for(claim_type):
    return DECAY.get(ALIASES.get(claim_type, claim_type), DEFAULT)


def recency(claim_type, age_days):
    """0..1 — how much a claim of this type, this old, still counts.

    Identical arithmetic to `claims.js::recency`, which a test pins.
    """
    d = decay_for(claim_type)
    v = 0.5 ** (max(0.0, float(age_days)) / float(d["half_life_days"]))
    return max(d["floor"], min(1.0, v))


def recency_for(claim_type, published_at, today=None):
    """Recency from a publication date, or the type's FLOOR when there is no date.

    The floor is the honest answer for an undated claim, and it is per-type for a reason:
    an undated fishing report is worth almost nothing as a current report (0.05), while an
    undated habitat description is still a habitat description (0.70). The previous
    behaviour returned a flat 0.5 for both, which over-credited the report and
    under-credited the agency fact — and 22 of the 23 seeded claims have no publication
    date, so that flat 0.5 was what nearly the whole corpus was scored on.
    """
    if not published_at:
        return decay_for(claim_type)["floor"]
    import datetime as dt
    try:
        d = dt.date.fromisoformat(str(published_at)[:10])
    except (TypeError, ValueError):
        return decay_for(claim_type)["floor"]
    days = ((today or dt.date.today()) - d).days
    return recency(claim_type, days)


def ttl_seconds(claim_type):
    return decay_for(claim_type)["ttl_seconds"]
