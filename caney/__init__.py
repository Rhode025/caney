"""
caney — the species-first fishing oracle.

The package that answers "I want to fish for X on DATE from A to B — what do I do?"

Layering, outermost first. Nothing may import from a layer above it:

    sources/    upstream fetch + normalise (USGS, CWMS, Open-Meteo, NWPS)
    domain/     value objects with no I/O — Observation, FishingZone, FishingPlan,
                SafetyClaim, ResearchClaim, RiverSnapshot
    species/    declarative species behaviour + scoring weights
    zones/      the fishing-zone registry (geography, not web pages)
    research/   the research provider abstraction, claim extraction, cache, seed corpus
    planner/    candidate generation, scoring, confidence, timeline, plan assembly
    render/     HTML/JSON emission — the ONLY layer allowed to know about presentation

The legacy per-river generators (briefing.py, duck.py, …) and riverlib.py are NOT part of
this package and are not rewritten: their hydrology is calibrated and backtested. The
planner consumes them through sources/snapshots.py rather than replacing them.

See docs/ARCHITECTURE.md.
"""
__version__ = "2.0.0"
