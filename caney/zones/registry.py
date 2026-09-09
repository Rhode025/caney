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
from ..domain.zone import (FishingZone, Geometry, GeometryKind, AccessPoint,
                           SpeciesProfileRef, Craft)
from ..species.profiles import STRIPED_BASS, SMALLMOUTH, LARGEMOUTH, TROUT

TWRA_ACCESS = "TWRA Boating & Fishing Access layer"
USACE = "USACE Nashville District (LRN) published project location"
OSM = "OpenStreetMap waterway centreline, walked to the access"

ALL = list(range(1, 13))
SUMMER = [6, 7, 8, 9]
SPRING = [3, 4, 5]
FALL = [9, 10, 11]
WINTER = [11, 12, 1, 2, 3]


def _ap(id, name, lat, lon, kinds, craft, note="", source=OSM, verified=True, mfd=None):
    return AccessPoint(id=id, name=name, lat=lat, lon=lon, kinds=kinds, craft=craft,
                       note=note, source=source, verified=verified,
                       river_miles_from_dam=mfd)


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
            _ap("caney_stonewall", "Stonewall", 36.19569, -85.91774,
                ["wade", "paddle", "ramp"], [Craft.WADE, Craft.KAYAK, Craft.DRIFT],
                "Gordonsville — the USGS gauge reach.", OSM, mfd=15.0),
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
            _ap("stones_donelson", "Stones River at US-70", 36.185, -86.665,
                ["bank", "paddle", "ramp"], [Craft.KAYAK, Craft.DRIFT, Craft.POWER, Craft.WADE],
                "Metro access. Not verified to §2.", "OSM, unverified", verified=False),
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
            _ap("cumberland_burkesville", "Burkesville", 36.8672, -85.1461,
                ["ramp", "paddle", "wade"], [Craft.DRIFT, Craft.KAYAK, Craft.POWER, Craft.WADE],
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
