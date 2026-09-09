"""
The fishing-zone registry. §11.

Geography, not web pages. A zone may span several legacy river pages, and a page may hold
several zones. `hydrology_river` names which calibrated generator supplies the water
numbers for the zone — that is the only link back to the old model, and it is one-way.

COORDINATES (§34). Every point here is either
  * a TWRA Boating & Fishing Access published ramp coordinate,
  * a USACE published project location, or
  * a channel position walked along the OSM waterway centreline,
all of which already exist verified in this repository (briefing.py `_COORDS`,
cordell.py's USACE tailwater pin). Nothing here was derived from prose. Where a source
only describes a reach — "Cordell Hull Dam downstream to the mouth of the Caney Fork" —
the zone stores a CORRIDOR between two verified endpoints, never an invented pin.
"""
from ..domain.location import LocationConfidence, LocationEvidence, Verification
from ..domain.zone import (FishingZone, Geometry, GeometryKind, AccessPoint,
                           SpeciesProfileRef, Craft, ZoneKind)
from ..species.profiles import STRIPED_BASS, SMALLMOUTH, LARGEMOUTH, TROUT

TWRA_ACCESS = "TWRA Boating & Fishing Access layer"
USACE = "USACE Nashville District (LRN) published project location"
OSM = "OpenStreetMap waterway centreline, walked to the access"
#: USGS publishes the surveyed position of every gauge, with an accuracy code and a datum,
#: from waterservices.usgs.gov/nwis/site. That VERIFIES A POSITION and nothing else — it
#: does not say a ramp exists there or that the public may launch. Access points anchored
#: this way therefore carry VERIFIED_ZONE, not VERIFIED_ACCESS, which is the difference
#: between "we know where this is" and "we know you can get on the water here".
USGS_SITE = "USGS site service (surveyed, NAD83)"

ALL = list(range(1, 13))
SUMMER = [6, 7, 8, 9]
SPRING = [3, 4, 5]
FALL = [9, 10, 11]
WINTER = [11, 12, 1, 2, 3]


def _ap(id, name, lat, lon, kinds, craft, note="", source=OSM, verified=True, mfd=None,
        evidence=""):
    """`evidence` overrides the default grade.

    Without it, `verified=True` grades as VERIFIED_ACCESS — "a published ramp coordinate".
    That is right for a TWRA access layer entry and WRONG for a USGS gauge position, which
    tells you exactly where a structure is and nothing whatever about whether the public
    may launch beside it. Passing VERIFIED_ZONE keeps that distinction, and it is the
    difference between "we know where this is" and "we know you can get on the water".
    """
    return AccessPoint(id=id, name=name, lat=lat, lon=lon, kinds=kinds, craft=craft,
                       note=note, source=source, verified=verified,
                       river_miles_from_dam=mfd, evidence=evidence)


_ZONES = [

    # ══ CANEY FORK — the calibrated tailwater, three reaches ═══════════════
    FishingZone(
        id="caney_upper", name="Upper Caney Fork",
        waterbody_ids=["caney"], waterbody_names=["Caney Fork River"],
        hydrology_river="caney", dam="Center Hill Dam", tailwater=True, mfd=6.0,
        drive="~70 min · east of Nashville", detail_page="caney.html",
        geometry=Geometry(GeometryKind.CORRIDOR,
                          [[36.10008, -85.83181], [36.13150, -85.80710],
                           [36.14760, -85.83970]], verified=True, source=OSM,
                          note="Center Hill Dam (Long Branch) to Betty's Island — mfd 0–9."),
        habitat=["minimum-flow flat", "riffle", "seam", "shelf", "tailout"],
        access=[
            _ap("caney_long_branch", "Long Branch", 36.10008, -85.83181,
                ["wade", "paddle", "ramp"], [Craft.WADE, Craft.KAYAK, Craft.DRIFT],
                "USACE recreation area at the dam.", USACE, mfd=0.0),
            _ap("caney_happy_hollow", "Happy Hollow", 36.13150, -85.80710,
                ["wade", "paddle", "ramp"], [Craft.WADE, Craft.KAYAK, Craft.DRIFT],
                "TWRA published ramp coordinate, off I-40.", TWRA_ACCESS, mfd=6.0),
            _ap("caney_bettys", "Betty's Island", 36.14760, -85.83970,
                ["wade", "paddle", "ramp"], [Craft.WADE, Craft.KAYAK, Craft.DRIFT],
                "TWRA published ramp coordinate — the flats.", TWRA_ACCESS, mfd=9.0),
            _ap("caney_lancaster", "Lancaster (Hwy 96)", 36.1189, -85.84255,
                ["wade"], [Craft.WADE], "Wade access only — no ramp.", OSM, mfd=2.5),
            _ap("caney_kirby", "Kirby Road", 36.146707, -85.863610, ["wade"], [Craft.WADE],
                "Roadside gravel lot, Elmwood. WADE ACCESS ONLY — no ramp.", OSM, mfd=8.0),
        ],
        species_profiles={
            TROUT: SpeciesProfileRef(
                TROUT, months=ALL, pattern="generation / wading model",
                habitat=["minimum-flow flat", "riffle", "seam", "shelf"],
                holds=("On the minimum-flow flats and the seam edges when the dam is off; "
                       "tight to the bank shelves and behind the shoals as it comes up."),
                move_to=["caney_middle", "caney_lower"], weight=1.0, heuristic=False,
                evidence=["twra_trout_stocking", "twra_trout_regs"]),
        },
        hazards=["Center Hill generation raises this reach fast — the exit bound is the "
                 "EARLIEST modelled arrival, never the typical one.",
                 "Wading gravel with a rising river behind you is how people drown here."],
        regs=("TWRA trout regulations, Center Hill Dam to the Cumberland: five trout in "
              "combination; brown trout one per day, 24-inch minimum."),
        notes="The deepest-modelled water in the repo: 80-event arrival backtest, 2.5 mph.",
    ),

    FishingZone(
        id="caney_middle", name="Middle Caney Fork",
        waterbody_ids=["caney"], waterbody_names=["Caney Fork River"],
        hydrology_river="caney", dam="Center Hill Dam", tailwater=True, mfd=12.0,
        drive="~75 min · east of Nashville", detail_page="caney.html",
        geometry=Geometry(GeometryKind.CORRIDOR,
                          [[36.14760, -85.83970], [36.19569, -85.91774]],
                          verified=True, source=OSM,
                          note="Betty's Island to Stonewall — mfd 9–15."),
        habitat=["seam", "shelf", "tailout", "undercut bank", "gravel shoal"],
        access=[
            # USGS 03424860 "CANEY FORK AT STONEWALL". The note always said this was the
            # gauge reach; the coordinate was 1.6 km from the gauge.
            _ap("caney_stonewall", "Stonewall", 36.18611, -85.90444,
                ["wade", "paddle", "ramp"], [Craft.WADE, Craft.KAYAK, Craft.DRIFT],
                "Gordonsville — the USGS gauge reach, at its surveyed position.",
                USGS_SITE, mfd=15.0, evidence=LocationEvidence.VERIFIED_ZONE),
            _ap("caney_bettys2", "Betty's Island", 36.14760, -85.83970,
                ["wade", "paddle", "ramp"], [Craft.WADE, Craft.KAYAK, Craft.DRIFT],
                "TWRA published ramp coordinate.", TWRA_ACCESS, mfd=9.0),
        ],
        species_profiles={
            TROUT: SpeciesProfileRef(
                TROUT, months=ALL, pattern="generation / wading model, longer lag",
                habitat=["seam", "gravel shoal", "undercut bank"],
                holds=("The long gravel runs and the undercut outside bends; the water gets "
                       "here two to three hours after it leaves the dam, which buys wade time."),
                move_to=["caney_lower"], weight=0.85, heuristic=False,
                evidence=["twra_trout_stocking"]),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=[5, 6, 7, 8, 9, 10], pattern="warm-reach smallmouth",
                habitat=["gravel shoal", "boulder seam"],
                holds="The lower gravel shoals as the trout water warms toward Stonewall.",
                weight=0.45, heuristic=True),
        },
        hazards=["Same release, later — the flow arrives here on a lag, so a wade window "
                 "that has closed upstream may still be open, and closes without warning."],
        regs="TWRA trout regulations apply to the whole Caney below Center Hill Dam.",
    ),

    FishingZone(
        id="caney_lower", name="Lower Caney Fork",
        waterbody_ids=["caney", "cordell"],
        waterbody_names=["Caney Fork River", "Cumberland River"],
        hydrology_river="caney", dam="Center Hill Dam", tailwater=True, mfd=22.0,
        drive="~65 min · Carthage", detail_page="caney.html",
        geometry=Geometry(GeometryKind.CORRIDOR,
                          [[36.19569, -85.91774], [36.23924, -85.9086],
                           [36.23816, -85.93415]], verified=True, source=OSM,
                          note="Stonewall to the Cumberland confluence at Carthage — mfd 15–24.5."),
        habitat=["confluence", "creek mouth", "ledge", "current seam", "thermal refuge"],
        access=[
            _ap("caney_s_carthage", "South Carthage (Bob Lowery ramp)", 36.23924, -85.9086,
                ["ramp"], [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Concrete ramp on the lower Caney.", OSM, mfd=22.0),
            _ap("caney_carthage_mouth", "Carthage — Cumberland mouth", 36.23816, -85.93415,
                ["ramp"], [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "At the confluence with the Cumberland.", OSM, mfd=24.5),
        ],
        species_profiles={
            # §3.2 exactly: the SAME water, two fisheries, different months and patterns.
            STRIPED_BASS: SpeciesProfileRef(
                STRIPED_BASS, months=SUMMER + [5, 10],
                pattern="seasonal current / thermal refuge pattern",
                habitat=["confluence", "thermal refuge", "current seam", "creek mouth"],
                holds=("The cold Caney discharge meeting the warm Cumberland — fish sit in "
                       "the cool plume within about two river miles of the mouth."),
                move_to=["carthage_confluence", "cordell_tailwater"], weight=0.9,
                heuristic=False, evidence=["twra_striper_caney_2mi"]),
            TROUT: SpeciesProfileRef(
                TROUT, months=[11, 12, 1, 2, 3, 4], pattern="cold-season downstream extent",
                habitat=["ledge", "creek mouth"],
                holds="Trout push this far down only while the whole reach stays cold.",
                weight=0.35, heuristic=True),
        },
        hazards=["Navigable water below Stonewall — barge and power-boat traffic at the "
                 "Cumberland confluence.",
                 "Center Hill AND Cordell Hull both change this water. Two dams, two schedules."],
        regs="TWRA trout regulations run to the Cumberland; TWRA statewide black bass limits.",
    ),

    # ══ §22 — THE CARTHAGE STRIPER CASE ════════════════════════════════════
    # The zone that the old river.species[] model could not express. cordell.py's
    # species line is "Smallmouth, white bass & panfish", so a striper request could
    # never reach this water. TWRA manages it as the concentration point for the
    # species. A zone, not a page, is what fixes that.
    FishingZone(
        id="carthage_confluence", name="Carthage Confluence Complex",
        waterbody_ids=["cordell", "caney"],
        waterbody_names=["Cumberland River", "Caney Fork River"],
        hydrology_river="cordell", dam="Cordell Hull Dam", tailwater=True, mfd=1.0,
        drive="~65 min · Carthage", detail_page="cordell.html",
        geometry=Geometry(
            GeometryKind.CORRIDOR,
            [[36.285278, -85.939722],   # USACE Cordell Hull Dam tailwater (LRN, CORT1)
             [36.24552, -85.9043],      # Cumberland channel above Carthage (OSM centreline)
             [36.23816, -85.93415]],    # Caney Fork mouth (OSM centreline)
            verified=True, source=USACE + " + " + OSM,
            note=("The corridor TWRA describes: “from Cordell Hull Dam downstream to the "
                  "mouth of the Caney Fork River.” Stored as a corridor between three "
                  "verified endpoints — the source names a reach, not a spot, so this "
                  "renders as a reach.")),
        habitat=["tailrace boil", "current seam", "confluence", "ledge", "creek mouth",
                 "wing dam", "thermal refuge"],
        access=[
            _ap("cordell_tailwater_ramp", "Cordell Hull Dam tailwater", 36.285278, -85.939722,
                ["ramp"], [Craft.POWER, Craft.DRIFT],
                "USACE tailwater access below the lock and dam at Carthage (LRN, CORT1). "
                "Strong current when they generate; stay off the dam.", USACE, mfd=0.0),
            _ap("carthage_caney_mouth", "Carthage — Caney Fork mouth", 36.23816, -85.93415,
                ["ramp"], [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Ramp at the Caney Fork / Cumberland confluence.", OSM, mfd=8.0),
        ],
        species_profiles={
            STRIPED_BASS: SpeciesProfileRef(
                STRIPED_BASS, months=ALL,
                pattern="spring spawning/current · summer current+thermal · fall forage",
                habitat=["tailrace boil", "current seam", "confluence", "thermal refuge"],
                holds=("With the dam running: the boil, both seams beside it, and the first "
                       "ledge below. With it off: the Caney Fork mouth and the cool plume."),
                move_to=["caney_lower", "cordell_tailwater"], weight=1.0, heuristic=False,
                evidence=["twra_striper_cordell_to_caney", "twra_striper_may_carthage",
                          "twra_striper_forage", "twra_coa_tailwater"]),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=[3, 4, 5, 9, 10, 11], pattern="rocky-bank / ledge pattern",
                habitat=["ledge", "bluff bank", "current break"],
                holds="Rock ledges and bluff banks either side of the channel.",
                weight=0.55, heuristic=False, evidence=["twra_smb_cordell"]),
        },
        hazards=["Generation turns the current on fast below the lock and dam — stay off "
                 "the boil and respect the pull.",
                 "Commercial barge traffic runs the navigation channel.",
                 "Submerged wing dams and rock ledges — idle unfamiliar water."],
        regs=("Tennessee licence. Striped bass and black bass per TWRA statewide limits; "
              "verify current TWRA Region 2/3 regulations."),
        notes=("The zone that proves the model: TWRA calls this the striped-bass "
               "concentration, the page that owns the water does not list the species."),
    ),

    FishingZone(
        id="cordell_tailwater", name="Cordell Hull Tailrace",
        waterbody_ids=["cordell"], waterbody_names=["Cumberland River"],
        hydrology_river="cordell", dam="Cordell Hull Dam", tailwater=True, mfd=0.2,
        drive="~70 min · Carthage", detail_page="cordell.html",
        geometry=Geometry(GeometryKind.POINT, [[36.285278, -85.939722]], verified=True,
                          source=USACE, note="USACE Cordell Hull Dam tailwater, LRN CORT1."),
        habitat=["tailrace boil", "current seam", "wing dam", "ledge"],
        access=[
            _ap("cordell_tailwater_ramp2", "Cordell Hull Dam tailwater", 36.285278, -85.939722,
                ["ramp"], [Craft.POWER, Craft.DRIFT],
                "USACE tailwater access below the lock and dam.", USACE, mfd=0.0),
        ],
        species_profiles={
            STRIPED_BASS: SpeciesProfileRef(
                STRIPED_BASS, months=ALL, pattern="current-dependent tailrace pattern",
                habitat=["tailrace boil", "current seam"],
                holds="The boil and the first seam below it, whenever units are turning.",
                move_to=["carthage_confluence", "caney_lower"], weight=0.95,
                heuristic=False, evidence=["twra_striper_cordell_to_caney", "twra_coa_tailwater"]),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="tailrace ledge pattern",
                habitat=["ledge", "wing dam"], holds="Deep on the ledges below the discharge.",
                weight=0.6, heuristic=False, evidence=["twra_smb_cordell"]),
        },
        hazards=["The tailrace is the most dangerous water in this zone set when they "
                 "generate. Stay well clear of the discharge."],
        regs="TWRA statewide limits; verify current Region 3 regulations.",
    ),

    FishingZone(
        id="cordell_creek_arms", name="Cordell Hull Creek Arms",
        waterbody_ids=["cordell"], waterbody_names=["Cordell Hull Reservoir"],
        hydrology_river="cordell", dam="Cordell Hull Dam", tailwater=False,
        drive="~75 min · Defeated Creek", detail_page="cordell.html",
        geometry=Geometry(GeometryKind.CORRIDOR,
                          [[36.285278, -85.939722], [36.3272, -85.8117]],
                          verified=False, source="OSM waterway centreline, reservoir arm",
                          note=("Reservoir arm above the dam — an AREA, not a pin. TWRA "
                                "describes creeks, stump beds and fallen trees on flats "
                                "in 2–8 ft of water without naming coordinates.")),
        habitat=["backwater", "creek arm", "laydown", "wood", "flooded bank",
                 "vegetation", "stump flat"],
        access=[
            _ap("cordell_defeated", "Defeated Creek area", 36.3272, -85.8117, ["ramp"],
                [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Reservoir arm access above the dam. Coordinates approximate to the arm, "
                "not to a verified ramp — treat as an area.",
                "OSM, unverified against TWRA access layer", verified=False),
        ],
        species_profiles={
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=ALL, pattern="cover / stump-flat pattern",
                habitat=["stump flat", "laydown", "wood", "creek arm", "vegetation"],
                holds=("Creeks, stump beds and fallen trees on flats in 2–8 feet — TWRA's "
                       "own description of this fishery."),
                weight=0.95, heuristic=False, evidence=["twra_lmb_cordell"]),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=SPRING + FALL, pattern="rocky-bank pattern",
                habitat=["bluff bank", "boulder seam"],
                holds="Rocky banks from Defeated Creek to the dam.",
                weight=0.7, heuristic=False, evidence=["twra_smb_cordell"]),
        },
        hazards=["Standing timber and stumps on the flats — idle unfamiliar water."],
        regs="TWRA statewide black bass limits.",
    ),

    # ══ CUMBERLAND · NASHVILLE (Old Hickory tailwater) ═════════════════════
    FishingZone(
        id="oldhickory_tailrace", name="Old Hickory Tailwater",
        waterbody_ids=["cumbnash"], waterbody_names=["Cumberland River"],
        hydrology_river="cumbnash", dam="Old Hickory Dam", tailwater=True, mfd=0.5,
        drive="~25 min · Nashville", detail_page="cumbnash.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[36.2966, -86.6539], [36.17, -86.74]],
                          verified=False, source="OSM waterway centreline",
                          note="Old Hickory Dam down the Nashville metro reach."),
        habitat=["tailrace boil", "current seam", "wing dam", "ledge", "creek mouth"],
        access=[
            _ap("cumbnash_metro", "Nashville metro ramps", 36.17, -86.74, ["ramp"],
                [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Metro reach ramps. Not individually verified to RIVER_SPEC §2.",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            STRIPED_BASS: SpeciesProfileRef(
                STRIPED_BASS, months=WINTER + [4, 5],
                pattern="Nov–Mar below-dam pattern, spring run",
                habitat=["tailrace boil", "current seam", "wing dam"],
                holds="Below Old Hickory Dam Nov–Mar; up toward the dam on the spring run.",
                move_to=["carthage_confluence"], weight=0.85, heuristic=False,
                evidence=["twra_striper_oldhickory_winter"]),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="ledge / wing-dam pattern",
                habitat=["ledge", "wing dam", "bluff bank"],
                holds="Deep on the wing dams and rock ledges through the metro reach.",
                weight=0.7, heuristic=True),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=ALL, pattern="bank cover / creek arm",
                habitat=["laydown", "wood", "creek arm", "boat dock"],
                holds="Laydowns, docks and the creek arms off the main channel.",
                weight=0.6, heuristic=True),
        },
        hazards=["Barge traffic in the navigation channel.",
                 "Submerged wing dams through the metro reach."],
        regs="TWRA statewide limits.",
    ),

    FishingZone(
        id="cheatham_tailrace", name="Cheatham Tailwater",
        waterbody_ids=["cheatham"], waterbody_names=["Cumberland River"],
        hydrology_river="cheatham", dam="Cheatham Dam", tailwater=True, mfd=0.5,
        drive="~55 min · Ashland City", detail_page="cheatham.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[36.3211, -87.2225], [36.42, -87.3]],
                          verified=False, source="OSM waterway centreline",
                          note="Cheatham Dam downstream into the lower Cumberland."),
        habitat=["tailrace boil", "current seam", "ledge", "creek mouth"],
        access=[
            _ap("cheatham_tw", "Cheatham Dam tailwater", 36.3211, -87.2225, ["ramp"],
                [Craft.POWER, Craft.DRIFT],
                "USACE Cheatham Lock & Dam tailwater vicinity. Not verified to §2.",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            STRIPED_BASS: SpeciesProfileRef(
                STRIPED_BASS, months=WINTER + SUMMER,
                pattern="current-dependent tailrace pattern",
                habitat=["tailrace boil", "current seam"],
                holds="The boil and seams when Cheatham is generating.",
                move_to=["oldhickory_tailrace"], weight=0.7, heuristic=True),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="ledge pattern",
                habitat=["ledge", "bluff bank"], holds="Rock ledges below the dam.",
                weight=0.6, heuristic=True),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=ALL, pattern="backwater / wood",
                habitat=["backwater", "laydown", "wood", "creek arm"],
                holds="The sloughs and laydowns off the main channel.",
                weight=0.55, heuristic=True),
        },
        hazards=["Lock and dam traffic; strong tailrace current under generation."],
        regs="TWRA statewide limits.",
    ),

    # ══ DUCK / BUFFALO / HARPETH — free-flowing smallmouth ═════════════════
    FishingZone(
        id="duck_upper", name="Upper Duck (Columbia)",
        waterbody_ids=["duckup"], waterbody_names=["Duck River"],
        hydrology_river="duckup", drive="~55 min · Columbia", detail_page="duckup.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[35.66, -87.09], [35.70, -87.27]],
                          verified=False, source="OSM waterway centreline",
                          note="Columbia to Williamsport — 19.6 mi."),
        habitat=["gravel shoal", "limestone pool", "boulder seam", "current break",
                 "bluff bank"],
        access=[
            _ap("duckup_columbia", "Columbia access", 35.66, -87.09, ["wade", "paddle", "ramp"],
                [Craft.WADE, Craft.KAYAK, Craft.DRIFT],
                "TWRA lists 30 free public access sites on the Duck; individual ramps are "
                "not verified to §2 here.", "OSM, unverified", verified=False),
        ],
        species_profiles={
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="shoal / pool river pattern",
                habitat=["gravel shoal", "limestone pool", "boulder seam", "current break"],
                holds=("The heads and tails of the shoals, boulder seams and the deep "
                       "limestone pools between them."),
                move_to=["duck_middle", "duck_lower"], weight=1.0, heuristic=False,
                evidence=["twra_duck_smb", "twra_duck_bigfalls"]),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=[5, 6, 7, 8, 9], pattern="slack-pocket pattern",
                habitat=["laydown", "wood", "backwater"],
                holds="Out of the current, in the wood and the slow pockets.",
                weight=0.4, heuristic=True),
        },
        hazards=["Strainers and logjams on the bends.", "Skinny at summer level — the "
                 "shoals will stop a boat before they stop a wader."],
        regs="Creel limit 5/day largemouth, smallmouth and spotted bass combined.",
    ),

    FishingZone(
        id="duck_middle", name="Middle Duck (Williamsport–Leatherwood)",
        waterbody_ids=["duckmid"], waterbody_names=["Duck River"],
        hydrology_river="duckmid", drive="~60 min", detail_page="duckmid.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[35.70, -87.27], [35.78, -87.40]],
                          verified=False, source="OSM waterway centreline",
                          note="Williamsport to Leatherwood — 18.9 mi, no gauge of its own."),
        habitat=["gravel shoal", "boulder seam", "bluff bank", "ledge"],
        access=[
            _ap("duckmid_williamsport", "Williamsport", 35.70, -87.27, ["paddle", "ramp"],
                [Craft.KAYAK, Craft.DRIFT, Craft.POWER],
                "Jet-boat ramp reach. Not verified to §2.", "OSM, unverified", verified=False),
        ],
        species_profiles={
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="shoal / pool river pattern",
                habitat=["gravel shoal", "boulder seam", "ledge"],
                holds="Shoal edges and the bluff-bank ledges.",
                move_to=["duck_lower"], weight=0.85, heuristic=False,
                evidence=["twra_duck_smb"]),
        },
        hazards=["No gauge on this reach — every water number here is interpolated.",
                 "Strainers and logjams on the bends."],
        regs="Creel limit 5/day black bass combined. TDEC mercury advisory Buffalo→I-40.",
    ),

    FishingZone(
        id="duck_lower", name="Lower Duck (Centerville)",
        waterbody_ids=["ducklow"], waterbody_names=["Duck River"],
        hydrology_river="ducklow", drive="~75 min · Centerville",
        detail_page="ducklow.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[35.78, -87.40], [35.83, -87.55]],
                          verified=False, source="OSM waterway centreline",
                          note="Leatherwood to Centerville — 21.3 mi, the only forecast reach."),
        habitat=["gravel shoal", "ledge", "bluff bank", "creek mouth"],
        access=[
            _ap("ducklow_centerville", "Centerville", 35.78, -87.40, ["ramp", "paddle"],
                [Craft.POWER, Craft.KAYAK, Craft.DRIFT],
                "The only Duck reach with a published forward forecast (NWPS CNVT1).",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="big-water shoal pattern",
                habitat=["gravel shoal", "ledge", "creek mouth"],
                holds="The deeper shoal runs and the creek mouths.", weight=0.8,
                heuristic=False, evidence=["twra_duck_smb"]),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=[4, 5, 6, 7, 8, 9, 10], pattern="wood / slack pattern",
                habitat=["laydown", "wood", "backwater", "creek arm"],
                holds="Laydowns and the slow creek arms out of the main push.",
                weight=0.5, heuristic=True),
        },
        hazards=["Strainers and logjams.", "Biggest, deepest water of the three reaches."],
        regs="Creel limit 5/day black bass combined. TDEC mercury advisory Buffalo→I-40.",
    ),

    FishingZone(
        id="buffalo_river", name="Buffalo River",
        waterbody_ids=["buffalo"], waterbody_names=["Buffalo River"],
        hydrology_river="buffalo", drive="~90 min · Lobelville",
        detail_page="buffalo.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[35.66, -87.81], [35.75, -87.75]],
                          verified=False, source="OSM waterway centreline",
                          note="Topsy to the Duck confluence — State Scenic River."),
        habitat=["gravel shoal", "boulder seam", "bluff bank", "bedrock ledge"],
        access=[
            _ap("buffalo_lobelville", "Lobelville / Linden liveries", 35.66, -87.81,
                ["paddle", "wade"], [Craft.KAYAK, Craft.WADE],
                "Canoe liveries at Linden and Lobelville. Not verified to §2.",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="free-flowing shoal pattern",
                habitat=["gravel shoal", "boulder seam", "bedrock ledge"],
                holds="Shoal lips, boulder seams and the head of every bedrock run.",
                weight=0.95, heuristic=False, evidence=["tdec_buffalo"]),
        },
        hazards=["No dam anywhere on the Buffalo — nothing buffers a rain event. It rises "
                 "fast and drops fast.",
                 "Strainers, logjams and deadfall on the bends, worst after high water."],
        regs="Creel limit 5/day black bass combined.",
    ),

    FishingZone(
        id="harpeth_river", name="Harpeth River",
        waterbody_ids=["harpeth"], waterbody_names=["Harpeth River"],
        hydrology_river="harpeth", drive="~35 min · Kingston Springs",
        detail_page="harpeth.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[36.12, -87.05], [36.18, -87.15]],
                          verified=False, source="OSM waterway centreline",
                          note="Hwy 100 to the Cumberland confluence — State Scenic River."),
        habitat=["gravel shoal", "limestone ledge", "bluff bank", "current break"],
        access=[
            _ap("harpeth_narrows", "Narrows of the Harpeth", 36.12, -87.05,
                ["paddle", "wade"], [Craft.KAYAK, Craft.WADE],
                "Harpeth River State Park. Portage the neck — the tunnel is a historic "
                "structure, not a boat route.", "OSM, unverified", verified=False),
        ],
        species_profiles={
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="low-gradient shoal pattern",
                habitat=["gravel shoal", "limestone ledge", "current break"],
                holds="The shoal lips and the ledge drops on the outside bends.",
                weight=0.8, heuristic=True),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=[5, 6, 7, 8, 9], pattern="slow-pool wood pattern",
                habitat=["laydown", "wood", "backwater"],
                holds="The long slow pools, tight to the wood.", weight=0.45,
                heuristic=True),
        },
        hazards=["No dam anywhere on the Harpeth — it comes up fast after rain and drops "
                 "slowly.", "The Narrows tunnel is a historic structure, not a boat route."],
        regs="Creel limit 5/day black bass combined.",
    ),

    # ══ STONES / ELK / CUMBERLAND KY ═══════════════════════════════════════
    FishingZone(
        id="stones_river", name="Stones River (Priest tailwater)",
        waterbody_ids=["stones"], waterbody_names=["Stones River"],
        hydrology_river="stones", dam="J. Percy Priest Dam", tailwater=True, mfd=1.0,
        drive="~20 min · Donelson", detail_page="stones.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[36.1509, -86.6236], [36.185, -86.665]],
                          verified=False, source="OSM waterway centreline",
                          note="Priest Dam down to the Cumberland."),
        habitat=["tailrace", "current seam", "ledge", "backwater", "wood"],
        access=[
            # USGS 03430200 "STONES RIVER AT US HWY 70 NEAR DONELSON, TN" — the same
            # structure this access is named for, published 2.9 km from the coordinate
            # that was here. It is worth correcting because this is the point a plan
            # sends somebody to, and because the routing estimate is computed from it.
            # Honesty about the size of the win: for this particular access the drive
            # estimate did NOT move — 25 minutes either way once rounded to five — so the
            # gain is in where you are told to go, not in when you are told to leave.
            _ap("stones_donelson", "Stones River at US-70", 36.18648, -86.63276,
                ["bank", "paddle", "ramp"], [Craft.KAYAK, Craft.DRIFT, Craft.POWER, Craft.WADE],
                "The US-70 bridge reach, at the USGS gauge. Position surveyed; nothing "
                "published says the public may launch here.", USGS_SITE, verified=True,
                evidence=LocationEvidence.VERIFIED_ZONE),
        ],
        species_profiles={
            TROUT: SpeciesProfileRef(
                TROUT, months=[11, 12, 1, 2, 3], pattern="winter put-and-take stocking",
                habitat=["tailrace", "current seam"],
                holds="Below the dam through the cold months while the stockings hold.",
                weight=0.5, heuristic=False, evidence=["twra_trout_stocking"]),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=[4, 5, 6, 7, 8, 9, 10], pattern="urban ledge pattern",
                habitat=["ledge", "current seam"], holds="Ledges below the tailrace.",
                weight=0.5, heuristic=True),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=ALL, pattern="backwater / wood pattern",
                habitat=["backwater", "wood", "laydown", "vegetation"],
                holds=("The Cheatham-pool backwater below the tailrace — slow, woody and "
                       "out of any current."),
                weight=0.7, heuristic=True),
        },
        hazards=["Priest generation turns the tailrace on with little warning.",
                 "The gauge sits in Cheatham backwater — stage here is not depth upstream."],
        regs="TWRA statewide limits; trout regulations apply during the stocked season.",
    ),

    FishingZone(
        id="elk_tims_ford", name="Elk River — Tims Ford Tailwater",
        waterbody_ids=["elktn"], waterbody_names=["Elk River"],
        hydrology_river="elktn", dam="Tims Ford Dam", tailwater=True, mfd=1.0,
        drive="~90 min · Winchester", detail_page="elktn.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[35.2168, -86.2694], [35.19, -86.28]],
                          verified=False, source="OSM waterway centreline",
                          note="Tims Ford Dam downstream toward Fayetteville."),
        habitat=["riffle", "seam", "gravel shoal", "undercut bank"],
        access=[
            _ap("elktn_tailwater", "Tims Ford tailwater", 35.2168, -86.2694,
                ["wade", "paddle"], [Craft.WADE, Craft.KAYAK],
                "Tailwater access below Tims Ford Dam. Not verified to §2.",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            TROUT: SpeciesProfileRef(
                TROUT, months=ALL, pattern="TVA generation / wading model",
                habitat=["riffle", "seam", "gravel shoal"],
                holds="The riffle heads and the seams while the dam is off.",
                weight=0.85, heuristic=False, evidence=["twra_trout_stocking"]),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=[6, 7, 8, 9, 10], pattern="warm-reach pattern",
                habitat=["gravel shoal", "boulder seam"],
                holds="Downstream where the release warms.", weight=0.5, heuristic=True),
        },
        hazards=["TVA generation — the gauge is ~30 miles downstream and lags badly. "
                 "Call TVA before you get in."],
        regs="TWRA trout regulations on the tailwater.",
    ),

    FishingZone(
        id="elk_alabama", name="Elk River — Alabama (Wheeler)",
        waterbody_ids=["elk"], waterbody_names=["Elk River"],
        hydrology_river="elk", drive="~2 h · Prospect", detail_page="elk.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[34.902, -87.078], [34.85, -87.10]],
                          verified=False, source="OSM waterway centreline"),
        habitat=["gravel shoal", "bluff bank", "creek mouth", "wood"],
        access=[
            _ap("elk_prospect", "Prospect", 34.902, -87.078, ["paddle", "ramp"],
                [Craft.KAYAK, Craft.DRIFT, Craft.POWER],
                "Not verified to §2.", "OSM, unverified", verified=False),
        ],
        species_profiles={
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="free-flowing shoal pattern",
                habitat=["gravel shoal", "bluff bank"],
                holds="Shoal edges and the bluff banks.", weight=0.75, heuristic=True),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=[4, 5, 6, 7, 8, 9, 10], pattern="backwater / wood",
                habitat=["backwater", "wood", "laydown", "vegetation", "creek arm"],
                holds="Wheeler backwater — vegetation, wood and the creek arms.",
                weight=0.75, heuristic=True),
        },
        hazards=["Strainers and deadfall.", "Alabama licence below the state line."],
        regs="Alabama regulations below the state line; verify before you fish.",
    ),

    FishingZone(
        id="cumberland_ky", name="Cumberland KY — Wolf Creek Tailwater",
        waterbody_ids=["cumberland"], waterbody_names=["Cumberland River"],
        hydrology_river="cumberland", dam="Wolf Creek Dam", tailwater=True, mfd=3.0,
        drive="~2¼ h · Burkesville KY", detail_page="cumberland.html",
        geometry=Geometry(GeometryKind.CORRIDOR, [[36.8672, -85.1461], [36.87, -85.14]],
                          verified=False, source="OSM waterway centreline",
                          note="Wolf Creek Dam downstream past Burkesville."),
        habitat=["riffle", "seam", "shelf", "gravel shoal", "tailout"],
        access=[
            # RENAMED, not moved. This point is 21 km from Burkesville and sits at Wolf
            # Creek Dam — which is right for a zone whose mfd is 3.0, so the coordinate
            # was fine and the label was not. USGS 03414100 is the Burkesville gauge at
            # 36.78675, -85.36522, and it is a different place from this one.
            _ap("cumberland_burkesville", "Wolf Creek Dam tailwater", 36.8672, -85.1461,
                ["ramp", "paddle", "wade"], [Craft.DRIFT, Craft.KAYAK, Craft.POWER, Craft.WADE],
                "Below the dam, three river miles above the Burkesville gauge. "
                "Not verified to §2.", "OSM, unverified", verified=False),
        ],
        species_profiles={
            TROUT: SpeciesProfileRef(
                TROUT, months=ALL, pattern="trophy tailwater, generation-gated",
                habitat=["riffle", "seam", "shelf", "tailout"],
                holds="The shelves and seams; this is a drift-boat river when they run.",
                weight=0.95, heuristic=True),
            STRIPED_BASS: SpeciesProfileRef(
                STRIPED_BASS, months=[6, 7, 8, 9], pattern="summer refuge in the cold release",
                habitat=["thermal refuge", "current seam"],
                holds="Downstream where the cold release meets warmer water.",
                weight=0.35, heuristic=True),
        },
        hazards=["Wolf Creek generation raises this river fast and far.",
                 "Kentucky licence required."],
        regs="Kentucky regulations; verify KDFWR trout limits before you fish.",
    ),
]

# ══ §35, §36 · STILLWATER — the cover water largemouth actually live in ═════
#
# The 2.0 zone set was river-shaped, so largemouth had almost nowhere to be: they were
# made to compete inside current-oriented reaches, which is not where they are. These
# zones are creek arms, embayments and shoreline — described by TWRA, and each one an
# AREA or CORRIDOR because an agency naming an embayment is not the same as a surveyed
# spot. Their access coordinates are approximate to the embayment and are marked so.
#
# They also carry the §34 striper work: TWRA describes a WINTER striper concentration in
# the lower Old Hickory embayments and a SPRING one in the Cordell Hull creeks between
# Granville and Gainesboro. Modelling stripers only at Carthage was overfitting one case.

_STILLWATER = [

    FishingZone(
        id="oldhickory_creek_arms", name="Old Hickory Creek Arms",
        waterbody_ids=["cumbnash"], waterbody_names=["Old Hickory Reservoir"],
        hydrology_river="oldhickory_lake", dam="Old Hickory Dam", tailwater=False,
        drive="~45 min · Gallatin", detail_page="cumbnash.html",
        geometry=Geometry(GeometryKind.AREA,
                          [[36.3760, -86.3300], [36.3200, -86.4400], [36.2900, -86.6000],
                           [36.3400, -86.5200]],
                          verified=False, source="OSM embayment outlines, approximate",
                          evidence=LocationEvidence.AGENCY_DESCRIBED_REACH,
                          note=("TWRA names Bledsoe, Spencer and Station Camp Creek in the "
                                "middle section and Drakes Creek and Shutes Branch "
                                "downstream. This polygon spans those arms; it is not a "
                                "survey of any of them.")),
        habitat=["creek arm", "grass bed", "vegetation", "laydown", "wood", "riprap",
                 "flat", "boat dock", "point"],
        access=[
            _ap("oldhickory_bledsoe", "Bledsoe Creek area", 36.3760, -86.3300, ["ramp"],
                [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Embayment access near Gallatin. Coordinates are approximate to the arm, "
                "not to a verified ramp.", "OSM, unverified against the TWRA access layer",
                verified=False),
            _ap("oldhickory_drakes", "Drakes Creek area", 36.2960, -86.5900, ["ramp"],
                [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Downstream embayment near Hendersonville. Approximate.",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=ALL, pattern="grass and hard-cover embayment pattern",
                habitat=["grass bed", "vegetation", "laydown", "wood", "riprap", "flat",
                         "boat dock", "creek arm"],
                holds=("Matted grass edges in 3-5 ft, and any hard structure mixed into "
                       "the grass. TWRA maintains forty fish-attractor sites on this "
                       "reservoir."),
                weight=0.95, heuristic=False, evidence=["twra_oh_lmb_grass"]),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=SPRING + FALL + [12, 1, 2],
                pattern="riprap and point pattern",
                habitat=["riprap", "point", "bluff bank"],
                holds="Riprap banks and the points at the mouths of the arms.",
                weight=0.55, heuristic=True),
        },
        hazards=["Standing timber and stumps in the backs of the arms.",
                 "Barge traffic in the main channel; the arms are off it."],
        regs="Largemouth bass 14-inch minimum on Old Hickory. TWRA statewide otherwise.",
        kind=ZoneKind.CREEK_ARM,
    ),

    FishingZone(
        id="oldhickory_embayments", name="Lower Old Hickory Embayments",
        waterbody_ids=["cumbnash"], waterbody_names=["Old Hickory Reservoir"],
        hydrology_river="oldhickory_lake", dam="Old Hickory Dam", tailwater=False,
        drive="~35 min · Hendersonville", detail_page="cumbnash.html",
        geometry=Geometry(GeometryKind.AREA,
                          [[36.3050, -86.6100], [36.2800, -86.6600], [36.2950, -86.7000],
                           [36.3200, -86.6400]],
                          verified=False, source="OSM embayment outlines, approximate",
                          evidence=LocationEvidence.AGENCY_DESCRIBED_REACH,
                          note=("The lower-reservoir embayments TWRA describes as the "
                                "winter striped-bass concentration. An area, not a spot.")),
        habitat=["backwater", "creek arm", "flat", "point", "channel swing", "riprap"],
        access=[
            _ap("oldhickory_shutes", "Shutes Branch area", 36.3050, -86.6100, ["ramp"],
                [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Lower-reservoir embayment access. Approximate to the arm.",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            STRIPED_BASS: SpeciesProfileRef(
                STRIPED_BASS, months=[12, 1, 2, 3],
                pattern="winter embayment concentration",
                habitat=["backwater", "creek arm", "flat", "channel swing"],
                holds=("Fish concentrate in the lower-reservoir embayments from December "
                       "through the winter, following bait off the main channel."),
                move_to=["oldhickory_tailrace"], weight=0.85, heuristic=False,
                evidence=["twra_oh_striper_winter_embayments"]),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=ALL, pattern="embayment cover pattern",
                habitat=["laydown", "wood", "riprap", "boat dock", "flat"],
                holds="Docks, riprap and the wood in the backs of the pockets.",
                weight=0.75, heuristic=False, evidence=["twra_oh_lmb_grass"]),
        },
        hazards=["Shallow flats and stumps in the backs of the embayments."],
        regs="Largemouth bass 14-inch minimum. Striped bass per TWRA statewide limits.",
        kind=ZoneKind.BACKWATER,
    ),

    FishingZone(
        id="priest_creek_arms", name="Percy Priest Creek Arms",
        waterbody_ids=["stones"], waterbody_names=["J. Percy Priest Reservoir"],
        hydrology_river="priest_lake", dam="J. Percy Priest Dam", tailwater=False,
        drive="~30 min · Smyrna / Hermitage", detail_page="stones.html",
        geometry=Geometry(GeometryKind.AREA,
                          [[36.1400, -86.4600], [36.0300, -86.4900], [36.0100, -86.5600],
                           [36.1000, -86.5900]],
                          verified=False, source="OSM embayment outlines, approximate",
                          evidence=LocationEvidence.AGENCY_DESCRIBED_REACH,
                          note=("TWRA names Spring and Fall Creek in the upper reservoir, "
                                "Stewart Creek near mid-lake and Suggs Creek in the lower "
                                "reservoir. This polygon spans them.")),
        habitat=["creek arm", "flat", "point", "laydown", "wood", "riprap", "channel swing",
                 "boat dock"],
        access=[
            _ap("priest_stewart", "Stewart Creek area", 36.0450, -86.4900, ["ramp"],
                [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Mid-lake embayment access. Approximate to the arm, not a verified ramp.",
                "OSM, unverified", verified=False),
            _ap("priest_suggs", "Suggs Creek area", 36.1050, -86.5500, ["ramp"],
                [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Lower-reservoir embayment access. Approximate.",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=ALL, pattern="embayment / fish-attractor pattern",
                habitat=["creek arm", "laydown", "wood", "flat", "point", "boat dock"],
                holds=("The Spring, Fall, Stewart and Suggs Creek embayments. TWRA "
                       "maintains about 132 fish-attractor sites here, and largemouth use "
                       "them year round — hardest from late November through April in "
                       "6-15 ft."),
                weight=0.95, heuristic=False, evidence=["twra_priest_lmb"]),
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=SPRING + FALL, pattern="point and riprap pattern",
                habitat=["point", "riprap", "bluff bank"],
                holds="Main-lake points and the riprap.", weight=0.5, heuristic=True),
        },
        hazards=["Heavy recreational traffic on summer weekends — this is a metro lake."],
        regs="TWRA statewide black bass limits; verify Priest exceptions before you fish.",
        kind=ZoneKind.CREEK_ARM,
    ),

    FishingZone(
        id="centerhill_shoreline", name="Center Hill Rocky Shoreline",
        waterbody_ids=["caney"], waterbody_names=["Center Hill Reservoir"],
        hydrology_river="centerhill_lake", dam="Center Hill Dam", tailwater=False,
        drive="~75 min · Smithville", detail_page="caney.html",
        geometry=Geometry(GeometryKind.AREA,
                          [[36.1000, -85.8300], [36.0200, -85.7300], [35.9400, -85.6600],
                           [35.9800, -85.8200]],
                          verified=False, source="OSM shoreline, approximate",
                          evidence=LocationEvidence.AGENCY_DESCRIBED_REACH,
                          note=("TWRA describes 'miles of rocky shoreline, points, and "
                                "bluff areas'. This polygon spans the main lake; it names "
                                "no spot because the source names no spot.")),
        habitat=["bluff bank", "point", "riprap", "ledge", "laydown", "creek arm"],
        access=[
            _ap("centerhill_hurricane", "Hurricane Bridge area", 36.0200, -85.7900,
                ["ramp"], [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Main-lake access. Approximate — not verified against the TWRA layer.",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            SMALLMOUTH: SpeciesProfileRef(
                SMALLMOUTH, months=ALL, pattern="highland-reservoir rock pattern",
                habitat=["bluff bank", "point", "ledge", "riprap"],
                holds=("Miles of rocky shoreline, points and bluff ends — TWRA's own "
                       "description of the habitat here."),
                weight=0.85, heuristic=False, evidence=["twra_centerhill"]),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=ALL, pattern="year-round bank and pocket pattern",
                habitat=["laydown", "wood", "creek arm", "boat dock", "point"],
                holds="The pockets and the wood between the bluff ends.",
                weight=0.7, heuristic=False, evidence=["twra_centerhill"]),
        },
        hazards=["Deep, clear, steep water — sudden wind on a big highland lake.",
                 "Winter drawdown moves the ramps."],
        regs="TWRA statewide black bass limits.",
        kind=ZoneKind.BANK,
    ),

    FishingZone(
        id="cordell_granville_reach", name="Cordell Hull — Granville to Gainesboro",
        waterbody_ids=["cordell"], waterbody_names=["Cordell Hull Reservoir"],
        hydrology_river="cordell_lake", dam="Cordell Hull Dam", tailwater=False,
        drive="~90 min · Granville", detail_page="cordell.html",
        geometry=Geometry(GeometryKind.CORRIDOR,
                          [[36.2870, -85.7550], [36.3200, -85.6900], [36.3540, -85.6640]],
                          verified=False, source="OSM channel centreline",
                          evidence=LocationEvidence.AGENCY_DESCRIBED_REACH,
                          note=("TWRA: striped bass use the major creeks from Granville to "
                                "Gainesboro during spring. A reach between two towns — "
                                "stored as the corridor the source describes.")),
        habitat=["creek arm", "channel swing", "point", "flat", "bluff bank"],
        access=[
            _ap("cordell_granville", "Granville area", 36.2870, -85.7550, ["ramp"],
                [Craft.POWER, Craft.DRIFT, Craft.KAYAK],
                "Upper-reservoir access. Approximate to the town, not a verified ramp.",
                "OSM, unverified", verified=False),
        ],
        species_profiles={
            STRIPED_BASS: SpeciesProfileRef(
                STRIPED_BASS, months=[3, 4, 5, 6],
                pattern="spring creek-mouth staging above the dam",
                habitat=["creek arm", "channel swing", "point"],
                holds=("The major creeks between Granville and Gainesboro through the "
                       "spring, and up toward Celina as the summer heat pushes fish to the "
                       "coolest water."),
                move_to=["cordell_tailwater"], weight=0.8, heuristic=False,
                evidence=["twra_cordell_striper_creeks"]),
            LARGEMOUTH: SpeciesProfileRef(
                LARGEMOUTH, months=ALL, pattern="stump-flat and wood pattern",
                habitat=["creek arm", "laydown", "wood", "flat"],
                holds="Creeks, stump beds and fallen trees on flats in 2-8 ft.",
                weight=0.85, heuristic=False, evidence=["twra_lmb_cordell"]),
        },
        hazards=["Standing timber on the flats — idle unfamiliar water.",
                 "Long run from the nearest verified ramp."],
        regs="TWRA statewide limits; verify Region 3 exceptions.",
        kind=ZoneKind.RESERVOIR_ARM,
    ),
]

_ZONES.extend(_STILLWATER)

ZONES = {z.id: z for z in _ZONES}


def zone(zid):
    z = ZONES.get(zid)
    if z is None:
        raise KeyError("no fishing zone %r" % (zid,))
    return z


def all_zones():
    return list(_ZONES)


def zones_for_species(species, month=None):
    """Candidate generation input. Geography first — page species tags take no part."""
    return [z for z in _ZONES if z.supports_species(species, month)]


def validate():
    """Structural checks the test suite pins."""
    from ..species.profiles import SPECIES
    bad = []
    seen = set()
    for z in _ZONES:
        if z.id in seen:
            bad.append("duplicate zone id %s" % z.id)
        seen.add(z.id)
        if not z.access:
            bad.append("%s has no access points" % z.id)
        if not z.species_profiles:
            bad.append("%s has no species profiles" % z.id)
        for sp in z.species_profiles:
            if sp not in SPECIES:
                bad.append("%s references unknown species %r" % (z.id, sp))
        if z.geometry and not z.geometry.points:
            bad.append("%s has a geometry with no points" % z.id)
        for a in z.access:
            if a.verified and (a.lat is None or a.lon is None):
                bad.append("%s access %s claims verified with no coordinates" % (z.id, a.id))
    for sp in SPECIES:
        if not zones_for_species(sp):
            bad.append("no zone supports species %s" % sp)
    return bad


# ── §28-§33 · geographic confidence, declared per zone ──────────────────────
#
# Derived confidence (from the access points and the geometry) is the default and is
# usually right. These are the zones where we know something the derivation cannot see:
# that TWRA describes a reach without naming a spot, that a USACE project location is a
# published coordinate, or that a shape came off an OSM centreline and nobody has stood on
# it. `verification` is the §33 hook — status/by/at/source/notes — so a zone can be
# upgraded from a phone at the ramp without touching any other file.
#
# THE PRIORS ARE NOT CALIBRATED. See docs/GEOGRAPHY.md.

_A = LocationEvidence.VERIFIED_ACCESS
_Z = LocationEvidence.VERIFIED_ZONE
_R = LocationEvidence.AGENCY_DESCRIBED_REACH
_M = LocationEvidence.MODELED_HABITAT
_U = LocationEvidence.UNVERIFIED_CANDIDATE

_LOCATION = {
    "caney_upper": LocationConfidence(
        access=_A, reach=_Z, holding_water=_M,
        verification=Verification(status="desk_verified", verified_by="repo",
                                  verified_at="2026-08-01",
                                  source="TWRA Boating & Fishing Access layer + OSM centreline",
                                  notes=("Happy Hollow and Betty's Island are TWRA published "
                                         "ramp coordinates; mfd values are guide-verified and "
                                         "backtested against the Stonewall gauge.")),
        notes="The best-known water in the repo."),
    "caney_middle": LocationConfidence(
        access=_A, reach=_Z, holding_water=_M,
        verification=Verification(status="desk_verified", verified_by="repo",
                                  verified_at="2026-08-01", source="TWRA + OSM centreline")),
    "caney_lower": LocationConfidence(
        access=_Z, reach=_R, holding_water=_M,
        verification=Verification(status="desk_verified", verified_by="repo",
                                  verified_at="2026-09-09",
                                  source="TWRA Old Hickory page describes the lower Caney reach"),
        notes="TWRA names the reach — within two river miles of the mouth — not a spot."),
    "carthage_confluence": LocationConfidence(
        access=_A, reach=_R, holding_water=_M,
        verification=Verification(status="desk_verified", verified_by="repo",
                                  verified_at="2026-09-09",
                                  source="USACE LRN project location + TWRA reach description",
                                  notes=("TWRA: 'from Cordell Hull Dam downstream to the mouth "
                                         "of the Caney Fork River'. A reach, not a spot.")),
        notes="Access is a published USACE coordinate; the fishery is an agency-described reach."),
    "cordell_tailwater": LocationConfidence(
        access=_A, reach=_Z, holding_water=_M,
        verification=Verification(status="desk_verified", verified_by="repo",
                                  verified_at="2026-09-09", source="USACE LRN (CORT1)")),
    "cordell_creek_arms": LocationConfidence(
        access=_U, reach=_R, holding_water=_M,
        verification=Verification(status="unverified",
                                  source="TWRA describes the fishery; the ramp is unverified"),
        notes=("TWRA describes creeks, stump beds and fallen trees on 2-8 ft flats. The "
               "fishery is agency-described; the access coordinate is not.")),
    "oldhickory_tailrace": LocationConfidence(access=_U, reach=_R, holding_water=_M,
        notes="TWRA describes the below-dam winter fishery; the metro ramps are unverified."),
    "cheatham_tailrace": LocationConfidence(access=_U, reach=_U, holding_water=_U),
    "duck_upper": LocationConfidence(access=_U, reach=_R, holding_water=_M,
        notes="TWRA describes the Old Stone Fort gorge and Big Falls pool by name."),
    "duck_middle": LocationConfidence(access=_U, reach=_U, holding_water=_U),
    "duck_lower": LocationConfidence(access=_U, reach=_U, holding_water=_U),
    "buffalo_river": LocationConfidence(access=_U, reach=_R, holding_water=_M,
        notes="TDEC describes the river; the liveries are named but not coordinate-verified."),
    "harpeth_river": LocationConfidence(access=_U, reach=_U, holding_water=_U),
    # Access is _Z, not _A. USGS 03430200 publishes the surveyed position of the US-70
    # structure this access is named for, so we now know WHERE it is to the metre — and
    # still have nothing published saying the public may launch beside it. Reach and
    # holding water stay unverified: a surveyed point does not map a reach.
    "stones_river": LocationConfidence(
        access=_Z, reach=_U, holding_water=_U,
        verification=Verification(status="desk_verified", verified_by="repo",
                                  verified_at="2026-09-09",
                                  source="USGS site service, gauge 03430200 (NAD83)",
                                  notes=("The coordinate that was here sat 2.9 km from the "
                                         "gauge it was named after. The drive estimate did "
                                         "not move at five-minute rounding; what moved is "
                                         "where the plan points.")),
        notes="Position surveyed; public access unpublished; the reach is still a guess."),
    "elk_tims_ford": LocationConfidence(access=_U, reach=_U, holding_water=_U),
    "elk_alabama": LocationConfidence(access=_U, reach=_U, holding_water=_U),
    "cumberland_ky": LocationConfidence(access=_U, reach=_U, holding_water=_U),
}

# ── §36 · what KIND of water each zone is ──────────────────────────────────
_KIND = {
    "caney_upper": ZoneKind.TAILRACE,
    "caney_middle": ZoneKind.RIVER_REACH,
    "caney_lower": ZoneKind.CONFLUENCE,
    "carthage_confluence": ZoneKind.CONFLUENCE,
    "cordell_tailwater": ZoneKind.TAILRACE,
    "cordell_creek_arms": ZoneKind.CREEK_ARM,
    "oldhickory_tailrace": ZoneKind.TAILRACE,
    "cheatham_tailrace": ZoneKind.TAILRACE,
    "duck_upper": ZoneKind.RIVER_REACH,
    "duck_middle": ZoneKind.RIVER_REACH,
    "duck_lower": ZoneKind.RIVER_REACH,
    "buffalo_river": ZoneKind.RIVER_REACH,
    "harpeth_river": ZoneKind.RIVER_REACH,
    "stones_river": ZoneKind.TAILRACE,
    "elk_tims_ford": ZoneKind.TAILRACE,
    "elk_alabama": ZoneKind.RIVER_REACH,
    "cumberland_ky": ZoneKind.TAILRACE,
}

for _zid, _lc in _LOCATION.items():
    if _zid in ZONES:
        ZONES[_zid].location = _lc
for _zid, _k in _KIND.items():
    if _zid in ZONES:
        ZONES[_zid].kind = _k
