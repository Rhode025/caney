"""§11, §22 — the fishing-zone knowledge model."""
from harness import check, eq, section

from caney.domain.zone import Craft, GeometryKind
from caney.species.profiles import SPECIES
from caney.zones.registry import ZONES, all_zones, validate, zones_for_species


def test_registry():
    section("§11 — the zone registry is structurally sound")
    eq("validate() finds no issues", validate(), [])
    check("every species has somewhere to fish",
          all(zones_for_species(sp) for sp in SPECIES))
    for z in all_zones():
        check("%s names its hydrology river" % z.id, bool(z.hydrology_river))
        check("%s has at least one access point" % z.id, bool(z.access))
        check("%s links a drill-down page" % z.id, bool(z.detail_page))
        for a in z.access:
            check("%s/%s declares which craft it serves" % (z.id, a.id), bool(a.craft))
            if a.verified:
                check("%s/%s cites who verified its coordinates" % (z.id, a.id),
                      bool(a.source))

    section("§34 — coordinates are verified or the zone says they are not")
    for z in all_zones():
        if not z.geometry:
            continue
        check("%s geometry declares verification" % z.id,
              isinstance(z.geometry.verified, bool))
        check("%s geometry cites a source" % z.id, bool(z.geometry.source))
        if not z.geometry.verified:
            check("%s unverified geometry is a corridor or area, not a point" % z.id,
                  z.geometry.kind != GeometryKind.POINT, z.geometry.kind)
        for a in z.access:
            if not a.verified:
                check("%s/%s says its coordinates are unverified" % (z.id, a.id),
                      "unverified" in (a.source or "").lower() or
                      "not verified" in (a.note or "").lower(),
                      "%s / %s" % (a.source, a.note[:40]))


def test_carthage_zone():
    section("§22 — the Carthage striper case exists as GEOGRAPHY")
    z = ZONES["carthage_confluence"]
    check("the zone spans two river pages",
          set(z.waterbody_ids) >= {"cordell", "caney"}, str(z.waterbody_ids))
    check("it holds striped bass", "striped_bass" in z.species_profiles)
    check("its striper profile is not a heuristic",
          not z.species_profiles["striped_bass"].heuristic)
    check("it cites the TWRA evidence ids",
          len(z.species_profiles["striped_bass"].evidence) >= 3,
          str(z.species_profiles["striped_bass"].evidence))
    check("it is stored as a corridor between verified endpoints, not a pin",
          z.geometry.kind == GeometryKind.CORRIDOR and len(z.geometry.points) >= 2,
          z.geometry.kind)
    check("the corridor says WHY it is a corridor",
          "reach" in (z.geometry.note or "").lower(), z.geometry.note[:80])
    check("its USACE endpoint is the published dam location",
          [36.285278, -85.939722] in z.geometry.points, str(z.geometry.points[0]))

    section("§3.1 — a page's species label takes no part in this")
    import riverlib
    label = riverlib.RIVER_CONFIG["cordell"]["species"]
    check("the cordell page still does not advertise striped bass",
          "striped" not in label.lower(), label)
    check("and the zone model finds it anyway",
          "carthage_confluence" in [x.id for x in zones_for_species("striped_bass", 9)])

    section("§3.2 — the same water is different fisheries in different months")
    lower = ZONES["caney_lower"]
    check("the lower Caney is striper water in summer",
          lower.supports_species("striped_bass", 7))
    check("and trout water in winter", lower.supports_species("trout", 1))
    check("and NOT striper water in January",
          not lower.supports_species("striped_bass", 1))
    check("and NOT trout water in July", not lower.supports_species("trout", 7))
    check("the two profiles describe different patterns",
          lower.species_profiles["striped_bass"].pattern !=
          lower.species_profiles["trout"].pattern)


def test_craft_gating():
    section("§6 — craft is an eligibility gate")
    up = ZONES["caney_upper"]
    check("the upper Caney can be waded", up.supports_craft(Craft.WADE))
    check("the upper Caney is not power-boat water", not up.supports_craft(Craft.POWER))
    cc = ZONES["carthage_confluence"]
    check("the Carthage confluence is not wadeable", not cc.supports_craft(Craft.WADE))
    check("it is power-boat water", cc.supports_craft(Craft.POWER))
    check("'any' matches every zone", all(z.supports_craft(Craft.ANY) for z in all_zones()))
    for z in all_zones():
        for c in z.craft_options():
            check("%s lists an access that serves %s" % (z.id, c),
                  bool(z.access_for(c)))
