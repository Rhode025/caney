"""
Model versions. §53, §54.

Every plan records which models produced it, so a result stored today is still
interpretable after the weights move. Bump the relevant one whenever you change:

    PLANNER_VERSION        the utility function, the window search, the itinerary search
    SPECIES_MODEL_VERSION  the weight table or a species profile rule
    ZONE_MODEL_VERSION     the zone registry, zone kinds, or location confidence
    RESEARCH_VERSION       the seed corpus, the tiers, or the decay curves

The trip log freezes these alongside the prediction (§50), and the scoreboard groups by
them — which is the only way a calibration result stays meaningful once the model moves.
"""

PLANNER_VERSION = "2.1.0"
SPECIES_MODEL_VERSION = "2.1.0"
ZONE_MODEL_VERSION = "2.1.0"
RESEARCH_VERSION = "2.1.0"


def versions():
    return {"planner": PLANNER_VERSION, "species_model": SPECIES_MODEL_VERSION,
            "zone_model": ZONE_MODEL_VERSION, "research": RESEARCH_VERSION}
