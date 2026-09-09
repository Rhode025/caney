"""
Where each piece of water gets its numbers. §26 — one table, not thirteen fetch blocks.

`hydrology_river` on a FishingZone indexes into this. Series names are the ones the
calibrated generators already use, so the planner and the river pages read the same
upstream objects (and, through sources/http.py, the same cached response).

unit_cfs is the per-turbine discharge used to convert a release into "units turning",
which is the number the striper model and the generation-on test actually use. Each is
the value already committed in the generator named beside it — moving one here without
moving it there would give the planner and the page different answers.
"""

CT = "America/Chicago"
ET = "America/New_York"

WATER = {
    "caney": {
        "name": "Caney Fork", "dam": "Center Hill Dam", "tailwater": True,
        "cwms_actual": "CETT1-CENTER_HILL.Flow.Ave.1Hour.1Hour.man-rev",
        "cwms_forecast": "Center Hill Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast",
        "office": "LRN",
        "usgs": "03424860", "usgs_label": "Caney Fork at Stonewall (USGS 03424860)",
        "usgs_mfd": 15.0,
        # briefing.py:155 units(cfs)=max(1,round((cfs-250)/3650)); gen when cfs>=800.
        # Copied, not re-derived — the page and the planner must call the same release
        # "two units" or the safety claims disagree with the page they link to.
        "unit_cfs": 3650, "unit_offset": 250, "gen_on": 800,
        "baseflow": 205,           # briefing.py CALIB_BASEFLOW, backtested
        "water_mph": 2.5, "mfd_stone": 15.0,
        "lat": 36.10, "lon": -85.83, "tz": CT,
    },
    "cordell": {
        "name": "Cumberland · Cordell Hull", "dam": "Cordell Hull Dam", "tailwater": True,
        "cwms_actual": "COHT1-CORDELL_HULL.Flow.Ave.1Hour.1Hour.man-rev",
        "cwms_forecast": "Cordell Hull Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast",
        "office": "LRN", "usgs": None,
        "unit_cfs": 8000, "gen_on": 4000,          # cordell.py UNIT_CFS
        "lat": 36.28, "lon": -85.95, "tz": CT,
        "note": "No USGS gauge on this reach at all — the USACE release IS the flow signal.",
    },
    "cumbnash": {
        "name": "Cumberland · Nashville", "dam": "Old Hickory Dam", "tailwater": True,
        "cwms_actual": "OHIT1-OLD_HICKORY.Flow.Ave.1Hour.1Hour.man-rev",
        "cwms_forecast": "Old Hickory Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast",
        "office": "LRN", "usgs": "03431500",
        "usgs_label": "Cumberland River at Nashville (USGS 03431500)",
        "unit_cfs": 6500, "gen_on": 3250,          # cumbnash.py OH_UNIT_CFS
        "lat": 36.17, "lon": -86.74, "tz": CT,
    },
    "cheatham": {
        "name": "Cumberland · Cheatham", "dam": "Cheatham Dam", "tailwater": True,
        "cwms_actual": "ASHT1-CHEATHAM.Flow.Ave.1Hour.1Hour.man-rev",
        "cwms_forecast": "Cheatham Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast",
        "office": "LRN", "usgs": None,
        "unit_cfs": 9000, "gen_on": 4500,          # cheatham.py UNIT_CFS
        "lat": 36.42, "lon": -87.30, "tz": CT,
    },
    "cumberland": {
        "name": "Cumberland KY", "dam": "Wolf Creek Dam", "tailwater": True,
        "cwms_actual": "WLCK2-WOLF_CREEK.Flow.Ave.1Hour.1Hour.man-rev",
        "cwms_forecast": "Wolf Creek Dam.Flow.Ave.1Hour.1Hour.celrn-cwms-forecast",
        "office": "LRN", "usgs": "03414100",
        "usgs_label": "Cumberland at Burkesville (USGS 03414100)", "usgs_mfd": 18.0,
        "unit_cfs": 6000, "gen_on": 3000,
        "lat": 36.87, "lon": -85.14, "tz": CT,
        "note": "Routes weakly (Wolf Creek→Burkesville r=0.30) — downstream timing is approximate.",
    },
    "stones": {
        "name": "Stones River", "dam": "J. Percy Priest Dam", "tailwater": True,
        "cwms_actual": None, "cwms_forecast": None, "office": "LRN",
        "usgs": "03430200", "usgs_label": "Stones River at US-70 near Donelson (USGS 03430200)",
        "unit_cfs": 3000, "gen_on": 1500,
        "lat": 36.185, "lon": -86.665, "tz": CT,
        "note": "The gauge sits in Cheatham backwater — stage here is not depth upstream.",
    },
    "elktn": {
        "name": "Elk · Tims Ford", "dam": "Tims Ford Dam", "tailwater": True,
        "cwms_actual": None, "cwms_forecast": None, "office": "LRN",
        "usgs": "03582000",
        "usgs_label": "Elk River above Fayetteville (USGS 03582000 — ~30 mi downstream, lagging)",
        "usgs_mfd": 30.0, "unit_cfs": 2000, "gen_on": 1000,
        "lat": 35.19, "lon": -86.28, "tz": CT,
        "note": "TVA generation, no CWMS feed here — the gauge lags the dam by hours.",
    },
    "elk": {
        "name": "Elk River (AL)", "dam": None, "tailwater": False,
        "cwms_actual": None, "cwms_forecast": None,
        "usgs": "03584600", "usgs_label": "Elk River at Prospect, TN (USGS 03584600)",
        "lat": 34.902, "lon": -87.078, "tz": CT,
    },
    "duckup": {
        "name": "Duck · Upper", "dam": None, "tailwater": False,
        "usgs": "03599500", "usgs_label": "Duck River at Columbia (USGS 03599500)",
        "lat": 35.66, "lon": -87.09, "tz": CT,
    },
    "duckmid": {
        "name": "Duck · Middle", "dam": None, "tailwater": False,
        "usgs": "03599500", "usgs_label": "Duck River at Columbia (USGS 03599500)",
        "usgs_scale": 1.6, "lat": 35.70, "lon": -87.27, "tz": CT,
        "note": "No gauge on this reach — flow is interpolated Columbia↔Centerville (x2.33 median).",
    },
    "ducklow": {
        "name": "Duck · Lower", "dam": None, "tailwater": False,
        "usgs": "03601990", "usgs_label": "Duck River at Centerville (USGS 03601990)",
        "lat": 35.78, "lon": -87.40, "tz": CT,
    },
    "buffalo": {
        "name": "Buffalo River", "dam": None, "tailwater": False,
        "usgs": "03604000", "usgs_label": "Buffalo River near Lobelville (USGS 03604000)",
        "lat": 35.66, "lon": -87.81, "tz": CT,
    },
    "harpeth": {
        "name": "Harpeth River", "dam": None, "tailwater": False,
        "usgs": "03434500", "usgs_label": "Harpeth near Kingston Springs (USGS 03434500)",
        "lat": 36.12, "lon": -87.05, "tz": CT,
    },
}


def water_for(river_id):
    return WATER.get(river_id) or {}
