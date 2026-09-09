"""
Declarative species behaviour + the scoring weights. §12, §13.

Two hard rules.

1. WEIGHTS ARE CONFIG, NOT LOGIC. `WEIGHTS[species]` is a plain dict summing to 100, and
   the scorer multiplies a 0..1 component fit by the weight. Recalibrating means editing a
   number here — never touching planner/scoring.py. test/planner/test_weights.py pins the
   published table so a silent drift fails the build.

2. EVERY BIOLOGICAL RULE CARRIES PROVENANCE. `Evidence.SOURCED` rules name the agency
   document behind them; everything else is explicitly `Evidence.HEURISTIC` — guide craft
   and angling convention, useful and unvalidated. Nothing is allowed to be neither.
   The repo's calibration-provenance invariant (CLAUDE.md), applied to biology.
"""

STRIPED_BASS = "striped_bass"
SMALLMOUTH = "smallmouth"
LARGEMOUTH = "largemouth"
TROUT = "trout"

SPECIES = (STRIPED_BASS, SMALLMOUTH, LARGEMOUTH, TROUT)

# Four glyphs that stay distinguishable at 30px in the dark, which is the size and the
# light the chooser is actually used in. Coloured circles read as status dots, not fish.
DISPLAY = {
    STRIPED_BASS: {"label": "Stripers", "full": "Striped bass", "emoji": "🐟",
                   "accent": "#2f6d94"},
    SMALLMOUTH:   {"label": "Smallmouth", "full": "Smallmouth bass", "emoji": "🐠",
                   "accent": "#8a6a2f"},
    LARGEMOUTH:   {"label": "Largemouth", "full": "Largemouth bass", "emoji": "🐡",
                   "accent": "#2f7a45"},
    TROUT:        {"label": "Trout", "full": "Trout", "emoji": "🎣", "accent": "#0a5ec2"},
}


class Evidence:
    SOURCED = "sourced"      # a Tier A/B document says this
    HEURISTIC = "heuristic"  # angling convention; plausible, unvalidated


# ── §13. The published weight table. Each column sums to 100. ───────────────
WEIGHTS = {
    STRIPED_BASS: {
        "current":   25,   # current / generation
        "thermal":   20,   # water temperature / thermal fit
        "seasonal":  15,   # seasonal geographic pattern
        "research":  15,   # recent primary research
        "forage":    10,   # forage / habitat
        "light":      7,   # time-of-day / light
        "weather":    5,
        "moon":       3,
    },
    SMALLMOUTH: {
        "flow":      20,   # flow level / trend
        "thermal":   15,   # water temperature / season
        "clarity":   15,
        "habitat":   15,
        "weather":   10,   # weather / cloud / wind
        "research":  10,
        "current":    7,
        "access":     5,   # access / craft
        "moon":       3,
    },
    LARGEMOUTH: {
        "thermal":   20,   # water temperature / season
        "habitat":   20,   # habitat / cover
        "level":     15,   # water level / trend
        "weather":   15,
        "forage":    15,   # forage / recent reports
        "light":      7,
        "current":    5,
        "moon":       3,
    },
    TROUT: {
        "generation": 30,  # generation / flow / wade timing
        "thermal":    20,  # water temperature / dissolved O2
        "hatch":      15,  # hatch / forage
        "clarity":    10,
        "weather":     8,  # weather / light
        "research":    7,
        "access":      7,  # access / craft
        "moon":        3,
    },
}

COMPONENT_LABEL = {
    "current": "Current / generation", "thermal": "Thermal suitability",
    "seasonal": "Seasonal location", "research": "Recent research evidence",
    "forage": "Forage / structure", "light": "Time of day / light",
    "weather": "Weather", "moon": "Moon / solunar", "flow": "Flow level / trend",
    "clarity": "Clarity", "habitat": "Habitat", "access": "Access / craft",
    "level": "Water level / trend", "generation": "Generation / wade timing",
    "hatch": "Hatch / forage",
}

# Lunar is capped hard (§14): a perfect solunar window may never rescue bad water. The
# scorer additionally refuses to let moon alone lift a plan out of SKIP.
MOON_MAX_SHARE = 0.03


class SpeciesProfile:
    def __init__(self, key, **kw):
        self.key = key
        self.__dict__.update(kw)

    def season_of(self, month):
        for name, months in self.seasons.items():
            if month in months:
                return name
        return "unknown"

    def to_json(self):
        d = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        d["display"] = DISPLAY[self.key]
        d["weights"] = WEIGHTS[self.key]
        return d


SPECIES_PROFILES = {

    STRIPED_BASS: SpeciesProfile(
        STRIPED_BASS,
        seasons={"winter": [11, 12, 1, 2, 3], "spring": [4, 5],
                 "summer": [6, 7, 8, 9], "fall": [10]},
        # Temperature band: TWRA striped-bass management describes summer thermal stress
        # driving fish to cool, oxygenated tailrace water. The 61-72 F preferred band is
        # already used by riverlib.striper_read and is retained here unchanged.
        temp_f={"lethal_hi": 80, "stress_hi": 75, "prefer": [61, 72], "prefer_lo": 50,
                "slow_lo": 44},
        temp_evidence=Evidence.SOURCED,
        temp_source="TWRA striped bass management — summer thermal refuge below dams",
        # Current is the trigger, not a modifier. No generation = no seam = no stacked bait.
        current={"needs": True, "ideal_units": [1, 3], "slack_penalty": 0.72,
                 "heavy_units": 4},
        current_evidence=Evidence.SOURCED,
        current_source="TWRA / USACE tailrace striper pattern; riverlib.striper_read backtest",
        clarity={"prefer": ["stained", "clear"], "muddy_penalty": 0.4},
        clarity_evidence=Evidence.HEURISTIC,
        light={"best": ["dawn", "dusk", "night"], "worst": ["midday_bright"],
               "low_light_bonus": 1.0, "midday_bright": 0.45},
        light_evidence=Evidence.SOURCED,
        light_source="TWRA summer pattern — early / low-light windows under current",
        weather={"pressure_drop_bonus": 0.15, "wind_ideal_mph": [4, 14],
                 "storm_abort": True},
        weather_evidence=Evidence.HEURISTIC,
        forage=["gizzard shad", "threadfin shad", "skipjack herring", "alewife"],
        forage_evidence=Evidence.SOURCED,
        forage_source="TWRA reservoir forage surveys — shad-dominated Cumberland system",
        habitat=["tailrace boil", "current seam", "wing dam", "ledge", "confluence",
                 "creek mouth", "thermal refuge"],
        spawn={"months": [4, 5], "behaviour":
               "spring run pushes the largest fish up toward the dams; current-oriented"},
        spawn_evidence=Evidence.SOURCED,
        spawn_source="TWRA striped bass spring run guidance",
        thermal_refuge={"months": [6, 7, 8, 9],
                        "behaviour": "cold bottom-release tailrace water is the whole game"},
        time_of_day={"summer": ["dawn", "first two hours of light", "dusk"],
                     "winter": ["mid-morning through afternoon"]},
        moon={"weight": "weak", "note": "solunar majors nudge a good window, never make one"},
        techniques={
            "default": {"primary_fly": "Baitfish streamer (Deceiver)", "primary_size": "#2/0–1/0",
                        "primary_color": "white/gray", "backup_fly": "Clouser Minnow",
                        "backup_size": "#1/0–2", "line": "intermediate",
                        "leader": "7½ ft 0X–1X, 16 lb", "presentation": "swing across the seam",
                        "depth": "2–6 ft under the surface film", "retrieve": "long strips, pause on the swing"},
            "heavy_current": {"primary_fly": "Articulated baitfish", "primary_size": "6 in",
                              "primary_color": "white/gray", "backup_fly": "Big Deceiver",
                              "backup_size": "#3/0", "line": "fast sink-tip (250–350 gr)",
                              "leader": "5 ft 20 lb", "presentation": "quarter down and let it swing through the boil",
                              "depth": "6–12 ft", "retrieve": "slow figure-eight on the hang"},
            "slack": {"primary_fly": "Clouser Minnow", "primary_size": "#1/0",
                      "primary_color": "chartreuse/white", "backup_fly": "Woolly Bugger",
                      "backup_size": "#4", "line": "full sink",
                      "leader": "6 ft 12 lb", "presentation": "count down along the ledge",
                      "depth": "12–20 ft", "retrieve": "slow strip, long pauses"},
            "low_light": {"primary_fly": "Gurgler / big popper", "primary_size": "#2/0",
                          "primary_color": "white", "backup_fly": "Deceiver",
                          "backup_size": "#1/0", "line": "floating",
                          "leader": "9 ft 1X", "presentation": "wake it across the seam",
                          "depth": "surface", "retrieve": "steady wake, no pause"},
        },
    ),

    SMALLMOUTH: SpeciesProfile(
        SMALLMOUTH,
        seasons={"winter": [12, 1, 2], "spring": [3, 4, 5], "summer": [6, 7, 8],
                 "fall": [9, 10, 11]},
        temp_f={"lethal_hi": 90, "stress_hi": 84, "prefer": [65, 78], "prefer_lo": 55,
                "slow_lo": 48},
        temp_evidence=Evidence.HEURISTIC,
        current={"needs": False, "ideal_units": [0, 1], "slack_penalty": 0.9},
        current_evidence=Evidence.HEURISTIC,
        # Flow, not current, is the smallmouth variable on a free-flowing river: too low
        # and the fish are spooky in skinny water, too high and it is unfishable.
        # Penalties, not scores: fit = 1 - penalty. The first version shipped
        # blown_penalty 0.1, which scored a blown-out river 0.9 — higher than prime. The
        # golden band fixture (test/planner/test_golden.py) exists because of that.
        # Low water still fishes on a Middle Tennessee shoal river — clear, skinny and
        # spooky, but catchable. High, pushy water takes the fishable edges away, so it is
        # penalised harder than low. Ordering pinned by test_golden.test_warmwater_bands.
        flow={"prefer": "prime", "low_penalty": 0.40, "high_penalty": 0.50,
              "blown_penalty": 0.88},
        flow_evidence=Evidence.SOURCED,
        flow_source="USGS field-measurement wade thresholds (riverlib.WATER_MODEL)",
        clarity={"prefer": ["clear", "stained"], "muddy_penalty": 0.25},
        clarity_evidence=Evidence.HEURISTIC,
        light={"best": ["dawn", "dusk", "overcast"], "worst": ["midday_bright"],
               "low_light_bonus": 0.95, "midday_bright": 0.55},
        light_evidence=Evidence.HEURISTIC,
        weather={"pressure_drop_bonus": 0.2, "wind_ideal_mph": [3, 12], "storm_abort": True},
        weather_evidence=Evidence.HEURISTIC,
        forage=["crayfish", "sculpin", "hellgrammite", "shiner", "madtom"],
        forage_evidence=Evidence.SOURCED,
        forage_source="TWRA stream smallmouth diet studies",
        habitat=["gravel shoal", "current break", "boulder seam", "ledge", "bluff bank",
                 "wood", "eddy line"],
        spawn={"months": [4, 5], "behaviour": "gravel-bed spawn; leave bedding fish alone"},
        spawn_evidence=Evidence.SOURCED,
        spawn_source="TWRA black bass spawn timing, Middle Tennessee",
        thermal_refuge={"months": [7, 8], "behaviour": "spring seeps and deeper shoal runs"},
        time_of_day={"summer": ["dawn", "last hour"], "fall": ["all day under cloud"]},
        moon={"weight": "weak", "note": "minor influence on a river fishery"},
        techniques={
            "default": {"primary_fly": "Crayfish pattern", "primary_size": "#4–6",
                        "primary_color": "olive/brown", "backup_fly": "Woolly Bugger",
                        "backup_size": "#6", "line": "floating",
                        "leader": "9 ft 3X", "presentation": "dead-drift into the shoal, then crawl",
                        "depth": "on the bottom", "retrieve": "short hops"},
            "heavy_current": {"primary_fly": "Weighted sculpin", "primary_size": "#2",
                              "primary_color": "olive", "backup_fly": "Clouser",
                              "backup_size": "#4", "line": "sink-tip",
                              "leader": "6 ft 2X", "presentation": "swing the seam edge",
                              "depth": "3–6 ft", "retrieve": "steady with a stall"},
            "slack": {"primary_fly": "Popper", "primary_size": "#6",
                      "primary_color": "chartreuse", "backup_fly": "Crayfish",
                      "backup_size": "#6", "line": "floating", "leader": "9 ft 3X",
                      "presentation": "tight to the bank and the boulder shade",
                      "depth": "surface", "retrieve": "pop, long pause"},
            "low_light": {"primary_fly": "Popper", "primary_size": "#4",
                          "primary_color": "black", "backup_fly": "Woolly Bugger",
                          "backup_size": "#4", "line": "floating", "leader": "9 ft 2X",
                          "presentation": "across the shoal lip", "depth": "surface",
                          "retrieve": "wake it"},
        },
    ),

    LARGEMOUTH: SpeciesProfile(
        LARGEMOUTH,
        seasons={"winter": [12, 1, 2], "spring": [3, 4, 5], "summer": [6, 7, 8],
                 "fall": [9, 10, 11]},
        temp_f={"lethal_hi": 92, "stress_hi": 88, "prefer": [68, 82], "prefer_lo": 58,
                "slow_lo": 50},
        temp_evidence=Evidence.HEURISTIC,
        current={"needs": False, "ideal_units": [0, 0], "slack_penalty": 1.0,
                 "current_penalty": 0.55},
        current_evidence=Evidence.HEURISTIC,
        # Largemouth want the water OFF the main current: backwaters, sloughs, wood.
        flow={"prefer": "stable", "rising_bonus": 0.1, "falling_penalty": 0.25},
        flow_evidence=Evidence.HEURISTIC,
        clarity={"prefer": ["stained", "clear"], "muddy_penalty": 0.5},
        clarity_evidence=Evidence.HEURISTIC,
        light={"best": ["dawn", "dusk", "overcast"], "worst": ["midday_bright"],
               "low_light_bonus": 0.9, "midday_bright": 0.6},
        light_evidence=Evidence.HEURISTIC,
        weather={"pressure_drop_bonus": 0.25, "wind_ideal_mph": [2, 10], "storm_abort": True},
        weather_evidence=Evidence.HEURISTIC,
        forage=["bluegill", "gizzard shad", "crayfish", "frog"],
        forage_evidence=Evidence.HEURISTIC,
        habitat=["backwater", "slough", "laydown", "wood", "vegetation", "boat dock",
                 "creek arm", "flooded bank"],
        spawn={"months": [4, 5], "behaviour": "shallow bed spawn in protected pockets"},
        spawn_evidence=Evidence.SOURCED,
        spawn_source="TWRA black bass spawn timing, Middle Tennessee",
        thermal_refuge={"months": [7, 8], "behaviour": "shade and deeper creek arms midday"},
        time_of_day={"summer": ["first light", "last light"], "spring": ["afternoon warm-up"]},
        moon={"weight": "weak", "note": "spawn timing only; not a daily driver"},
        techniques={
            "default": {"primary_fly": "Deer-hair popper", "primary_size": "#2",
                        "primary_color": "chartreuse/white", "backup_fly": "Bunny leech",
                        "backup_size": "#1/0", "line": "floating",
                        "leader": "7½ ft 12 lb", "presentation": "tight to wood and vegetation edges",
                        "depth": "surface to 2 ft", "retrieve": "pop, long pause"},
            "heavy_current": {"primary_fly": "Bunny leech", "primary_size": "#1/0",
                              "primary_color": "black/blue", "backup_fly": "Clouser",
                              "backup_size": "#1", "line": "sink-tip",
                              "leader": "6 ft 12 lb", "presentation": "behind the current break, in the slack",
                              "depth": "4–8 ft", "retrieve": "slow strips"},
            "slack": {"primary_fly": "Deer-hair popper", "primary_size": "#2",
                      "primary_color": "black", "backup_fly": "Bunny leech",
                      "backup_size": "#1/0", "line": "floating", "leader": "7½ ft 12 lb",
                      "presentation": "into the pocket, let the rings die",
                      "depth": "surface", "retrieve": "twitch, wait"},
            "low_light": {"primary_fly": "Black bunny leech", "primary_size": "#1/0",
                          "primary_color": "black", "backup_fly": "Popper",
                          "backup_size": "#2", "line": "floating", "leader": "7½ ft 12 lb",
                          "presentation": "parallel to the laydown", "depth": "1–3 ft",
                          "retrieve": "slow, steady"},
        },
    ),

    TROUT: SpeciesProfile(
        TROUT,
        seasons={"winter": [12, 1, 2], "spring": [3, 4, 5], "summer": [6, 7, 8],
                 "fall": [9, 10, 11]},
        # A bottom-release tailwater holds a narrow band year round; the risk is the
        # generation, not the temperature. Upper bound matters on the free-flowing reaches.
        temp_f={"lethal_hi": 75, "stress_hi": 68, "prefer": [48, 62], "prefer_lo": 40,
                "slow_lo": 36},
        temp_evidence=Evidence.SOURCED,
        temp_source="TWRA trout management — tailwater cold-water release",
        current={"needs": False, "ideal_units": [0, 0], "slack_penalty": 1.0},
        current_evidence=Evidence.SOURCED,
        current_source="riverlib WATER_MODEL / Center Hill release routing backtest",
        flow={"prefer": "minimum", "wade_gate": True},
        flow_evidence=Evidence.SOURCED,
        flow_source="USGS field measurements + 80-event Center Hill arrival backtest",
        clarity={"prefer": ["clear"], "muddy_penalty": 0.3},
        clarity_evidence=Evidence.HEURISTIC,
        light={"best": ["overcast", "dawn", "dusk"], "worst": ["midday_bright"],
               "low_light_bonus": 0.85, "midday_bright": 0.7},
        light_evidence=Evidence.HEURISTIC,
        weather={"pressure_drop_bonus": 0.1, "wind_ideal_mph": [0, 8], "storm_abort": True},
        weather_evidence=Evidence.HEURISTIC,
        forage=["midge", "sulphur", "caddis", "scud", "sowbug", "black fly", "terrestrial"],
        forage_evidence=Evidence.SOURCED,
        forage_source="Caney Fork hatch calendar (riverlib HATCH data, guide-sourced)",
        habitat=["minimum-flow flat", "riffle", "seam", "shelf", "spring seep",
                 "tailout", "undercut bank"],
        spawn={"months": [10, 11], "behaviour": "brown trout redds — do not wade the gravel"},
        spawn_evidence=Evidence.SOURCED,
        spawn_source="TWRA trout regulations / redd protection guidance",
        thermal_refuge={"months": [7, 8],
                        "behaviour": "the cold release IS the refuge; below-dam reaches only"},
        time_of_day={"summer": ["first three hours", "the hour before generation"],
                     "winter": ["late morning through mid-afternoon"]},
        moon={"weight": "weak", "note": "negligible on a tailwater; generation dominates"},
        techniques={
            "default": {"primary_fly": "Zebra midge", "primary_size": "#18–22",
                        "primary_color": "black/silver", "backup_fly": "Pheasant tail",
                        "backup_size": "#18", "line": "floating",
                        "leader": "9–12 ft 6X", "presentation": "dead-drift under an indicator",
                        "depth": "12–24 in off the bottom", "retrieve": "none — drift"},
            "heavy_current": {"primary_fly": "Woolly Bugger", "primary_size": "#8",
                              "primary_color": "olive", "backup_fly": "Sculpin",
                              "backup_size": "#6", "line": "sink-tip",
                              "leader": "6 ft 3X", "presentation": "swing the edges from the bank",
                              "depth": "2–4 ft", "retrieve": "short strips on the swing"},
            "slack": {"primary_fly": "Zebra midge", "primary_size": "#20",
                      "primary_color": "black", "backup_fly": "Scud",
                      "backup_size": "#16", "line": "floating", "leader": "12 ft 6X",
                      "presentation": "sight-fish the minimum-flow flats",
                      "depth": "6–18 in", "retrieve": "none — drift"},
            "low_light": {"primary_fly": "Sulphur emerger", "primary_size": "#16",
                          "primary_color": "pale yellow", "backup_fly": "Elk hair caddis",
                          "backup_size": "#16", "line": "floating", "leader": "12 ft 6X",
                          "presentation": "across and slightly down to rising fish",
                          "depth": "film", "retrieve": "none — drift"},
        },
    ),
}


def profile(species):
    p = SPECIES_PROFILES.get(species)
    if p is None:
        raise KeyError("no species profile for %r (have %s)" % (species, list(SPECIES)))
    return p


def weights_for(species):
    w = WEIGHTS.get(species)
    if w is None:
        raise KeyError("no weights for %r" % (species,))
    return dict(w)


def validate():
    """Every weight column sums to 100 and every component has a label. Called by tests."""
    bad = []
    for sp, w in WEIGHTS.items():
        total = sum(w.values())
        if total != 100:
            bad.append("%s weights sum to %s, not 100" % (sp, total))
        for k in w:
            if k not in COMPONENT_LABEL:
                bad.append("%s: component %r has no label" % (sp, k))
        if w.get("moon", 0) > 3:
            bad.append("%s: moon weight %s exceeds the §14 cap of 3" % (sp, w["moon"]))
    for sp, p in SPECIES_PROFILES.items():
        for attr in ("temp", "current", "clarity", "light", "weather"):
            if not getattr(p, attr + "_evidence", None):
                bad.append("%s: %s rule has no evidence classification" % (sp, attr))
    return bad
