"""
The hydrology model. §27, §28.

The strangler target: pure, validated model logic extracted from riverlib.py so that both
the planner and the legacy page generators consume ONE implementation, and so the planner
carries no dependency on a 2,100-line module full of blocking fetches and HTML helpers.

    arrival.py   release travel time to a river mile, with its uncertainty spread
    wading.py    measured wade/float thresholds per reach
    striper.py   the striped-bass day grade the river pages show

MIGRATION ORDER (§29): Caney first, then Cordell, Cumberland, Duck, the rest. Each step is
extract the pure logic, PROVE EXACT OUTPUT EQUIVALENCE, switch the old page to the shared
model, delete the duplicated constants. Steps two and four are the ones that get skipped
under time pressure, and skipping them is how two implementations of one number appear.

Nothing here fetches. Nothing here renders.
"""
from .arrival import ARRIVAL_STAGES, arrival_window   # noqa: F401
from .striper import STRIPER_SEASON, striper_read     # noqa: F401
from .wading import WATER_MODEL                       # noqa: F401
