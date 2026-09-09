#!/usr/bin/env python3
"""
The planner test suite.

    python3 test/planner/run.py

No network, no clock dependence, no third-party packages. Everything here runs against
hand-built fixtures, so a failure means the code changed — never that the river did.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import harness                                   # noqa: E402
import test_architecture as A                    # noqa: E402
import test_domain as D                          # noqa: E402
import test_golden as G                          # noqa: E402
import test_research as R                        # noqa: E402
import test_species as S                         # noqa: E402
import test_zones as Z                           # noqa: E402

if __name__ == "__main__":
    harness.run([
        D.test_observations, D.test_claims, D.test_weights,
        Z.test_registry, Z.test_carthage_zone, Z.test_craft_gating,
        G.test_golden_releases, G.test_warmwater_bands, G.test_wade_gate,
        S.test_carthage_stripers, S.test_caney_trout_wade, S.test_trout_power_boat,
        S.test_smallmouth_bands, S.test_largemouth_can_win, S.test_confidence_beats_score,
        R.test_provider_is_optional, R.test_query_generation, R.test_claim_extraction,
        R.test_cache, R.test_seed_corpus,
        A.test_no_unknown_as_zero, A.test_no_inline_assets,
        A.test_browser_engine_holds_no_model, A.test_layering, A.test_repo_hygiene,
        A.test_observability,
    ])
