"""
The FishingFeature registry. §22-§26.

EVERY COORDINATE IN THIS FILE COMES FROM `caney/zones/registry.py`. Not one is typed in.
That is the whole design, and it is what makes §25 survivable in practice rather than only
at the type level: a feature's geometry is a named SUB-PART of a zone shape somebody
already verified — its head, its tail, a junction two zones agree on, or the whole area —
derived by the helpers below. There is no path through this module by which prose becomes
a pin, because there is no path by which a number enters it at all.

What a feature adds over its zone is the answer to "where in it". "Cordell Hull tailrace"
is a mile of river; "the outside seam below the dam, which needs the release to exist at
all, and dies twenty minutes after it stops" is a place and a schedule. That distinction
is what lets §26's hierarchy — species → zone → feature → segment — produce a materially
better plan than naming the zone alone, and it is what §89 tests.

CONFIDENCE IS INHERITED AND THEN DEMOTED. A sub-part is never known better than the whole
it was cut from, and usually worse: TWRA describing a reach does not describe which side
of it the seam is on. `_derive` enforces the demotion rather than trusting each entry to
remember, because an entry that forgot would be indistinguishable from one that knew.
"""
from ..domain.feature import (FeatureGeometry, FeatureSpeciesProfile, FeatureType,
                              FishingFeature, GeometryConfidence, HydraulicBehavior)
from ..domain.location import LocationEvidence, Verification
from .registry import ZONES, zone as _zone

#: The zone layer's evidence vocabulary, mapped into the feature layer's.
_FROM_ZONE = {
    LocationEvidence.VERIFIED_ACCESS: GeometryConfidence.OFFICIAL_GIS,
    LocationEvidence.VERIFIED_ZONE: GeometryConfidence.OSM_DERIVED,
    LocationEvidence.AGENCY_DESCRIBED_REACH: GeometryConfidence.AGENCY_DESCRIBED,
    LocationEvidence.MODELED_HABITAT: GeometryConfidence.MODELED,
    LocationEvidence.UNVERIFIED_CANDIDATE: GeometryConfidence.UNVERIFIED,
}

#: A sub-part is never known better than the shape it was cut from. One step down the
#: ORDER, floored at UNVERIFIED. The exception is `whole`, which IS the shape.
def _demote(level, steps=1):
    i = min(GeometryConfidence.rank(level) + steps,
            len(GeometryConfidence.ORDER) - 1)
    return GeometryConfidence.ORDER[i]


def _zone_confidence(zone_id):
    z = _zone(zone_id)
    lvl = z.geometry.evidence_level if z.geometry else LocationEvidence.UNVERIFIED_CANDIDATE
    return _FROM_ZONE.get(lvl, GeometryConfidence.UNVERIFIED)


def _points(zone_id):
    z = _zone(zone_id)
    return list(z.geometry.points) if z.geometry else []


def head(zone_id, note=""):
    """The upstream end of a zone corridor — its first two points."""
    pts = _points(zone_id)
    if len(pts) < 2:
        return whole(zone_id, note)
    return FeatureGeometry(kind="corridor", points=pts[:2],
                           confidence=_demote(_zone_confidence(zone_id)),
                           source="derived: head of %s" % zone_id, note=note)


def tail(zone_id, note=""):
    """The downstream end — its last two points."""
    pts = _points(zone_id)
    if len(pts) < 2:
        return whole(zone_id, note)
    return FeatureGeometry(kind="corridor", points=pts[-2:],
                           confidence=_demote(_zone_confidence(zone_id)),
                           source="derived: tail of %s" % zone_id, note=note)


def whole(zone_id, note=""):
    """The zone's own shape, at the zone's own confidence — nothing was narrowed."""
    z = _zone(zone_id)
    pts = _points(zone_id)
    kind = "area" if (z.geometry and z.geometry.kind == "area") else "corridor"
    if len(pts) < 2:
        # A zone that is a single verified point: the feature is that point, and it may
        # keep the point only because the zone earned it.
        conf = _zone_confidence(zone_id)
        if conf in GeometryConfidence.POINT_ALLOWED and len(pts) == 1:
            return FeatureGeometry(kind="point", points=pts, confidence=conf,
                                   source="derived: %s itself" % zone_id, note=note)
        return FeatureGeometry(kind="area", points=pts or [[0, 0]],
                               confidence=GeometryConfidence.UNVERIFIED,
                               source="derived: %s" % zone_id, note=note)
    return FeatureGeometry(kind=kind, points=pts, confidence=_zone_confidence(zone_id),
                           source="derived: all of %s" % zone_id, note=note)


def junction(zone_a, zone_b, note=""):
    """Where two zones meet. Both registries carry the coordinate, so it is corroborated.

    Returned as a short corridor spanning the two shapes' shared end rather than as a
    pin: two sources agreeing on a confluence's position still does not tell you which
    side of it the fish are on.
    """
    a, b = _points(zone_a), _points(zone_b)
    if not a or not b:
        return whole(zone_a, note)
    # The closest pair of endpoints between the two shapes.
    best, bd = None, None
    for pa in (a[0], a[-1]):
        for pb in (b[0], b[-1]):
            d = (pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2
            if bd is None or d < bd:
                best, bd = (pa, pb), d
    pts = [best[0], best[1]]
    if pts[0] == pts[1]:
        # The two zones share the exact coordinate — which happens where one zone IS the
        # dam the other starts at. Widen with a neighbouring point from whichever shape
        # has one, so this stays a corridor and does not become a disguised waypoint.
        nxt = None
        for shape in (a, b):
            for cand in shape:
                if cand != pts[0]:
                    nxt = cand
                    break
            if nxt:
                break
        if nxt is None:
            return whole(zone_a, note)
        pts = [pts[0], nxt]
    # The WEAKER of the two, not the stronger. A junction between a surveyed dam
    # coordinate and a reach somebody sketched is known as well as the sketch — taking
    # the better end would let one verified point launder the confidence of everything
    # it touches, which is the §25 failure wearing a different hat.
    conf = max((_zone_confidence(zone_a), _zone_confidence(zone_b)),
               key=GeometryConfidence.rank)
    return FeatureGeometry(kind="corridor", points=pts, confidence=conf,
                           source="derived: %s ∩ %s" % (zone_a, zone_b), note=note)


def _sp(species, holding, weight=1.0, months=None, evidence=(), heuristic=True):
    return FeatureSpeciesProfile(species=species, holding=holding, weight=weight,
                                 months=list(months or range(1, 13)),
                                 evidence=list(evidence), heuristic=heuristic)


def _f(fid, zone_id, name, ftype, geom, hydraulic, holding, species, minutes=45,
       techniques=(), sources=(), notes=""):
    return FishingFeature(
        id=fid, zone_id=zone_id, name=name, feature_type=ftype, geometry=geom,
        hydraulic_behavior=hydraulic, holding_behavior=holding,
        species_profiles={s.species: s for s in species},
        typical_minutes=minutes, techniques=list(techniques),
        source_refs=list(sources), notes=notes,
        verification=Verification(status="desk_verified",
                                  source="derived from the zone geometry it sits in"))


# ── the features ────────────────────────────────────────────────────────────
# Grouped by zone. Every `holding` line describes behaviour the zone registry or the
# seeded TWRA corpus already asserts; none introduces a new claim about where fish are.

def _build():
        return [
        # ── Cordell Hull tailwater · Carthage ────────────────────────────────────
        _f("cordell_dam_break", "cordell_tailwater", "Dam current break",
           FeatureType.DAM_CURRENT_BREAK, whole("cordell_tailwater"),
           HydraulicBehavior.NEEDS_CURRENT,
           "The boil directly below the units. Fish stack on the shear line where the "
           "release meets slack water, and scatter within the hour once it shuts down.",
           [_sp("striped_bass", "On the shear line, not in the boil", 1.0),
            _sp("smallmouth", "Off the edge of the break, in the softer water", 0.6)],
           minutes=35, notes="Dead without generation — the whole feature is the release."),

        _f("cordell_outside_seam", "cordell_tailwater", "Outside seam",
           FeatureType.TAILRACE_SEAM,
           junction("cordell_tailwater", "carthage_confluence",
                    "the head of the TWRA-described corridor below the dam"),
           HydraulicBehavior.BEST_ON_FALLING,
           "The seam that forms along the outside of the discharge as it spreads. Holds "
           "longer after shutdown than the boil does.",
           [_sp("striped_bass", "Along the current edge, working down as it softens", 0.95)],
           minutes=40),

        # ── Carthage confluence ─────────────────────────────────────────────────
        _f("carthage_caney_mouth", "carthage_confluence", "Caney Fork mouth",
           FeatureType.TRIBUTARY_MOUTH,
           junction("carthage_confluence", "caney_lower",
                    "where both zone corridors terminate — corroborated by two entries"),
           HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "Cold Caney water meeting the Cumberland. The thermal edge is the feature; it is "
           "sharpest while Center Hill is releasing and blurs within a few hours of shutdown.",
           [_sp("striped_bass", "On the temperature edge, usually the downstream side", 1.0,
                months=[5, 6, 7, 8, 9, 10]),
            _sp("smallmouth", "Off the seam, on the rock", 0.7)],
           minutes=55,
           notes="The summer striper refuge TWRA describes. Two dams drive it, not one."),

        _f("carthage_channel_swing", "carthage_confluence", "Channel swing below the mouth",
           FeatureType.CHANNEL_SWING, tail("carthage_confluence"),
           HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "The first bend below the confluence, where the channel pushes against the far "
           "bank and drops. Bait collects on the inside of the swing.",
           [_sp("striped_bass", "Deep on the outside, bait on the inside", 0.75)],
           minutes=45),

        # ── Caney Fork ──────────────────────────────────────────────────────────
        _f("caney_dam_break", "caney_upper", "Center Hill dam break",
           FeatureType.DAM_CURRENT_BREAK, head("caney_upper"),
           HydraulicBehavior.BLOWN_BY_CURRENT,
           "Immediately below the units. Excellent on minimum flow and unfishable — and "
           "unsafe to wade — once the units come on.",
           [_sp("trout", "In the slack behind the wall on low water", 0.9)],
           minutes=30,
           notes="The one feature where more current is strictly worse."),

        _f("caney_bettys_island_head", "caney_upper", "Betty's Island head",
           FeatureType.ISLAND_HEAD, tail("caney_upper"),
           HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "The split at the top of the island. Fish hold on the point of the divide and "
           "along both feeding lanes.",
           [_sp("trout", "On the divide, and in the first fifty yards of each lane", 0.85),
            _sp("smallmouth", "The lower third of the lanes, on rock", 0.5)],
           minutes=50),

        _f("caney_bettys_island_tail", "caney_middle", "Betty's Island tail",
           FeatureType.ISLAND_TAIL, head("caney_middle"),
           HydraulicBehavior.BEST_ON_FALLING,
           "Where the two lanes rejoin. The convergence seam holds fish as the water drops "
           "back after a release passes.",
           [_sp("trout", "On the convergence seam", 0.8)],
           minutes=45),

        _f("caney_stonewall_shoal", "caney_middle", "Stonewall shoal",
           FeatureType.SHOAL, tail("caney_middle"),
           HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "The broken water at the gauge reach. Wadeable on minimum flow; the arrival of a "
           "release is felt here before it is felt downstream.",
           [_sp("trout", "In the pockets and along the drop at the tail", 0.75),
            _sp("smallmouth", "The tailout, on the rock", 0.65)],
           minutes=50),

        _f("caney_lower_mouth", "caney_lower", "Lower Caney, Cumberland end",
           FeatureType.TRIBUTARY_MOUTH, tail("caney_lower"),
           HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "The last mile of the Caney before the Cumberland. Warmer than the tailwater, "
           "colder than the river, and the transition holds both fisheries.",
           [_sp("striped_bass", "Where the cold water fans out", 0.85,
                months=[5, 6, 7, 8, 9, 10]),
            _sp("trout", "The upper end, while the water stays cold", 0.55,
                months=[10, 11, 12, 1, 2, 3, 4]),
            _sp("smallmouth", "On the rock through the middle", 0.7)],
           minutes=55),

        # ── Old Hickory ─────────────────────────────────────────────────────────
        _f("oldhickory_tailrace_seam", "oldhickory_tailrace", "Old Hickory tailrace seam",
           FeatureType.TAILRACE_SEAM, head("oldhickory_tailrace"),
           HydraulicBehavior.NEEDS_CURRENT,
           "The seam below the units, twenty-five minutes from downtown. Entirely a "
           "generation feature.",
           [_sp("striped_bass", "On the seam, working the edge as it moves", 0.9),
            _sp("smallmouth", "The slack side, off the wall", 0.55)],
           minutes=40),

        _f("oldhickory_metro_riprap", "oldhickory_tailrace", "Metro reach riprap",
           FeatureType.RIPRAP, tail("oldhickory_tailrace"),
           HydraulicBehavior.CURRENT_INDIFFERENT,
           "Bank armouring through the Nashville reach. Fishes at any release and is the "
           "fallback when the dam is off.",
           [_sp("largemouth", "Tight to the rock, on the shaded side", 0.7),
            _sp("smallmouth", "The same rock, further out", 0.6)],
           minutes=60),

        _f("oldhickory_creek_mouths", "oldhickory_creek_arms", "Bledsoe / Station Camp mouths",
           FeatureType.CREEK_MOUTH, whole("oldhickory_creek_arms"),
           HydraulicBehavior.CURRENT_INDIFFERENT,
           "The creek mouths TWRA names in the mid-reservoir. Level and cover drive this, "
           "not discharge.",
           [_sp("largemouth", "On the first drop inside the mouth", 0.95),
            _sp("striped_bass", "Off the mouths, on bait, in the cool months", 0.6,
                months=[11, 12, 1, 2, 3, 4])],
           minutes=70,
           notes="An AREA. TWRA names the creeks; nothing published names the spots in them."),

        _f("oldhickory_embayment_grass", "oldhickory_embayments", "Embayment grass edges",
           FeatureType.GRASS_EDGE, whole("oldhickory_embayments"),
           HydraulicBehavior.CURRENT_INDIFFERENT,
           "The vegetated edges of the lower-reservoir embayments — the cover the river "
           "zones do not have.",
           [_sp("largemouth", "Along the outside edge of the grass", 1.0)],
           minutes=75),

        # ── Percy Priest ────────────────────────────────────────────────────────
        _f("priest_creek_mouths", "priest_creek_arms", "Spring / Fall Creek arms",
           FeatureType.CREEK_MOUTH, whole("priest_creek_arms"),
           HydraulicBehavior.CURRENT_INDIFFERENT,
           "The upper-reservoir creek arms. Thirty minutes from town and the closest real "
           "largemouth cover to Nashville.",
           [_sp("largemouth", "The first drop inside the arm, on wood", 0.95),
            _sp("smallmouth", "The rockier outside points", 0.5)],
           minutes=70),

        # ── Center Hill ─────────────────────────────────────────────────────────
        _f("centerhill_bluff_banks", "centerhill_shoreline", "Bluff banks",
           FeatureType.BLUFF_BANK, whole("centerhill_shoreline"),
           HydraulicBehavior.CURRENT_INDIFFERENT,
           "The rock walls TWRA describes. Deep water against the bank means fish can sit "
           "at any level without moving far.",
           [_sp("smallmouth", "Tight to the wall, on the shaded side", 0.9),
            _sp("largemouth", "The transitions where bluff meets slope", 0.6)],
           minutes=65),

        _f("centerhill_points", "centerhill_shoreline", "Main-lake points",
           FeatureType.POINT, whole("centerhill_shoreline"),
           HydraulicBehavior.CURRENT_INDIFFERENT,
           "Points off the main channel. The classic reservoir smallmouth position.",
           [_sp("smallmouth", "On the end, out to the channel drop", 0.85)],
           minutes=55),

        # ── Cordell Hull reservoir ──────────────────────────────────────────────
        _f("cordell_defeated_creek", "cordell_creek_arms", "Defeated Creek arm",
           FeatureType.CREEK_MOUTH, whole("cordell_creek_arms"),
           HydraulicBehavior.CURRENT_INDIFFERENT,
           "The reservoir arm above the dam.",
           [_sp("largemouth", "Inside the arm, on cover", 0.75),
            _sp("smallmouth", "The rocky outer third", 0.6)],
           minutes=65),

        _f("granville_creek_mouths", "cordell_granville_reach", "Granville creek mouths",
           FeatureType.CREEK_MOUTH, whole("cordell_granville_reach"),
           HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "The major creeks TWRA describes stripers using between Granville and Gainesboro.",
           [_sp("striped_bass", "At the mouths, on bait", 0.85)],
           minutes=60),

        # ── Cheatham ────────────────────────────────────────────────────────────
        _f("cheatham_tailrace_seam", "cheatham_tailrace", "Cheatham tailrace seam",
           FeatureType.TAILRACE_SEAM, head("cheatham_tailrace"),
           HydraulicBehavior.NEEDS_CURRENT,
           "The seam below Cheatham Dam. A generation feature on the lower Cumberland.",
           [_sp("striped_bass", "On the seam", 0.85),
            _sp("smallmouth", "The slack edge", 0.5)],
           minutes=45),

        # ── free-flowing smallmouth water ───────────────────────────────────────
        _f("duck_upper_shoals", "duck_upper", "Columbia shoals",
           FeatureType.SHOAL, whole("duck_upper"), HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "The shoal-and-pool sequence through the upper Duck.",
           [_sp("smallmouth", "At the head and tail of each shoal", 0.9)], minutes=60),

        _f("duck_middle_swings", "duck_middle", "Middle Duck channel swings",
           FeatureType.CHANNEL_SWING, whole("duck_middle"),
           HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "Bend pools with rock on the outside.",
           [_sp("smallmouth", "The outside of each swing", 0.85)], minutes=60),

        _f("duck_lower_swings", "duck_lower", "Lower Duck bends",
           FeatureType.CHANNEL_SWING, whole("duck_lower"),
           HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "Deeper, slower bends toward Centerville.",
           [_sp("smallmouth", "Outside bends, on wood and rock", 0.8),
            _sp("largemouth", "The slack inside, where it is soft", 0.45)], minutes=60),

        _f("buffalo_shoals", "buffalo_river", "Buffalo shoals",
           FeatureType.SHOAL, whole("buffalo_river"), HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "State Scenic River shoals — the clearest smallmouth water in the set.",
           [_sp("smallmouth", "Head and tail of the shoals", 0.9)], minutes=60),

        _f("harpeth_shoals", "harpeth_river", "Harpeth shoals",
           FeatureType.SHOAL, whole("harpeth_river"), HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "Close-in shoal water, thirty-five minutes out.",
           [_sp("smallmouth", "In the broken water and the tailouts", 0.8)], minutes=55),

        _f("stones_dam_break", "stones_river", "Priest dam break",
           FeatureType.DAM_CURRENT_BREAK, head("stones_river"),
           HydraulicBehavior.NEEDS_CURRENT,
           "Below Percy Priest Dam. Twenty minutes from town when the dam is on.",
           [_sp("striped_bass", "On the break", 0.7),
            _sp("smallmouth", "The edges", 0.6)], minutes=40),

        _f("elk_tims_ford_break", "elk_tims_ford", "Tims Ford dam break",
           FeatureType.DAM_CURRENT_BREAK, head("elk_tims_ford"),
           HydraulicBehavior.NEEDS_CURRENT,
           "Below Tims Ford. TVA generation, and the gauge is thirty miles down.",
           [_sp("trout", "In the slack on low water", 0.75),
            _sp("smallmouth", "Further down, on rock", 0.6)], minutes=45),

        _f("elk_alabama_swings", "elk_alabama", "Lower Elk bends",
           FeatureType.CHANNEL_SWING, whole("elk_alabama"),
           HydraulicBehavior.IMPROVES_WITH_CURRENT,
           "Free-flowing bend water below the state line.",
           [_sp("smallmouth", "Outside bends", 0.8)], minutes=60),

        _f("cumberland_ky_tailrace", "cumberland_ky", "Wolf Creek tailrace",
           FeatureType.TAILRACE_SEAM, head("cumberland_ky"),
           HydraulicBehavior.NEEDS_CURRENT,
           "Below Wolf Creek Dam. Routes weakly to the Burkesville gauge, so downstream "
           "timing here is approximate.",
           [_sp("trout", "On the seams", 0.85),
            _sp("striped_bass", "Off the seams in the warm months", 0.5,
                months=[5, 6, 7, 8, 9])], minutes=50),
    ]


#: Built on first use, not at import. Constructing 28 features means 28 trips into the
#: zone registry, and a Cloudflare Python Worker pays that on every cold isolate — where
#: CPU is the scarce resource and a request that never touches a feature should not pay
#: for one. `_cache` is module-scoped, so it is built once per isolate.
_CACHE = {"all": None}


def all_features():
    if _CACHE["all"] is None:
        _CACHE["all"] = _build()
    return list(_CACHE["all"])


def features_for_zone(zone_id):
    return [f for f in all_features() if f.zone_id == zone_id]


def features_for(zone_id, species, month=None):
    """The features in a zone that hold `species`, best first. §26."""
    out = [f for f in all_features()
           if f.zone_id == zone_id and f.supports(species, month)]
    out.sort(key=lambda f: (-f.weight_for(species), GeometryConfidence.rank(f.confidence)))
    return out


def feature(fid):
    for f in all_features():
        if f.id == fid:
            return f
    return None


def by_zone():
    out = {}
    for f in all_features():
        out.setdefault(f.zone_id, []).append(f)
    return out
