"""
Model versions. §53, §54, §79.

Every plan records which models produced it, so a result stored today is still
interpretable after the weights move. Bump the relevant one whenever you change:

    PLANNER_VERSION        the utility function, the window search, the itinerary search,
                           the logistics constraint solver
    SPECIES_MODEL_VERSION  the weight table, a species profile rule, or a technique table
    ZONE_MODEL_VERSION     the zone registry, zone kinds, features, or location confidence
    RESEARCH_VERSION       the seed corpus, the tiers, or the decay curves
    HYDROLOGY_VERSION      the arrival model, the wade thresholds, the routing constants

The trip log freezes these alongside the prediction (§50), and the scoreboard groups by
them — which is the only way a calibration result stays meaningful once the model moves.

WHAT 3.0 DID AND DID NOT MOVE. §67 is explicit that 3.0 must not change the scoring
formula merely because the version number changed, and it did not: `utility.py`'s weights,
the peak/cubic/floor split, the duration saturation and `profiles.py::WEIGHTS` are
byte-for-byte what 2.1 shipped. What moved is the SEARCH — the window optimiser now runs
inside a per-candidate travel envelope rather than over the raw availability — and that
changes which windows are considered, so PLANNER_VERSION moves. A stored 2.1 result and a
3.0 result are not comparable as calibration evidence, and pretending otherwise by
leaving the version alone would quietly poison the first real outcome sample.

RESEARCH_VERSION deliberately stays at 2.1.0: nothing in the corpus, the tiers or the
decay curves changed. Bumping every number together because "it is a new release" is how
version fields stop carrying information.
"""

PLANNER_VERSION = "3.0.0"
SPECIES_MODEL_VERSION = "3.0.0"
ZONE_MODEL_VERSION = "3.0.0"
RESEARCH_VERSION = "2.1.0"
HYDROLOGY_VERSION = "3.0.0"

#: The API's wire schema. Separate from the models: a schema change breaks clients, a
#: model change breaks comparisons, and they move for different reasons.
SCHEMA_VERSION = "3.0"


def versions():
    return {"planner": PLANNER_VERSION, "species_model": SPECIES_MODEL_VERSION,
            "zone_model": ZONE_MODEL_VERSION, "research": RESEARCH_VERSION,
            "hydrology": HYDROLOGY_VERSION, "schema": SCHEMA_VERSION}
