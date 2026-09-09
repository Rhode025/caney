#!/usr/bin/env python3
"""
The planner test suite.

    python3 test/planner/run.py

No network, no clock dependence, no third-party packages, AND NO BUILD. Everything here
runs against hand-built fixtures, so a failure means the code changed — never that the
river did.

The no-build part is a contract, not an accident: CI runs this suite FIRST, before the
sixty-second build, so a broken scorer fails in seconds. A check that needs `out/` must
call `harness.skip()` and name where the same invariant is enforced after the build —
`test/verify.py` — rather than failing. Two checks did fail on a clean checkout the first
time this ran in CI, which is how that rule got written down.
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
import test_hydrology as H                       # noqa: E402
import test_opportunity as O                     # noqa: E402
import test_research as R                        # noqa: E402
import test_species as S                         # noqa: E402
import test_v3 as V3                             # noqa: E402
import test_zones as Z                           # noqa: E402

if __name__ == "__main__":
    harness.run([
        D.test_observations, D.test_claims, D.test_weights,
        Z.test_registry, Z.test_carthage_zone, Z.test_craft_gating,
        G.test_golden_releases, G.test_warmwater_bands, G.test_wade_gate,
        H.run,
        O.test_peak_beats_average, O.test_minimum_durations, O.test_move_beats_stay,
        O.test_move_not_worth_it, O.test_location_confidence, O.test_transitions,
        O.test_safety_overrides_opportunity, O.test_zone_kinds,
        S.test_carthage_stripers, S.test_caney_trout_wade, S.test_trout_power_boat,
        S.test_smallmouth_bands, S.test_largemouth_can_win, S.test_confidence_beats_score,
        R.test_provider_is_optional, R.test_query_generation, R.test_claim_extraction,
        R.test_cache, R.test_seed_corpus, R.test_research_changes_ranking,
        R.test_stale_research, R.test_research_offline,
        A.test_no_unknown_as_zero, A.test_no_inline_assets,
        A.test_browser_engine_holds_no_model, A.test_layering, A.test_repo_hygiene,
        A.test_observability,
        # ── Caney 3.0 · §87-§93's golden scenarios ─────────────────────────
        V3.test_door_to_door, V3.test_best_water_too_far,
        V3.test_feature_selection, V3.test_plan_delta, V3.test_source_failure,
        V3.test_research_unavailable, V3.test_api_contract, V3.test_sessions,
        V3.test_snapshot_is_replayable, V3.test_method, V3.test_routing_is_honest,
    ])
