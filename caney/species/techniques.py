"""
The conventional-tackle half of the technique model. §20, §21.

`caney/species/profiles.py` carries the fly presentations and always did. This file is its
counterpart, and the two are selected between by TackleMethod rather than one being the
default and the other an afterthought.

WHY THIS IS A SEPARATE FILE. Every species profile in this repo was written fly-first,
because the product was fly-first. Bolting a `lure` key onto those tables would have
produced fly logic wearing lure vocabulary — the retrieve descriptions, the depth rules
and the switch triggers are genuinely different, and a swimbait fished "dead drift, mend
upstream" is not advice. The two tables share a SHAPE, not an implementation.

The keys match profiles.py exactly (`default`, `heavy_current`, `slack`, `low_light`), so
the condition logic in segments.py chooses a key once and either table can answer it.
That symmetry is load-bearing: it means adding a condition adds it to both methods, and a
key present in one table and missing from the other fails a test rather than silently
falling back to fly.

CONTENT POLICY. `test/verify.py` enforces a fly-only vocabulary on the river reference
pages, and that policy stands — the river pages are a fly product. The planner is not, as
of §20, and the check is scoped accordingly rather than deleted.
"""
from ..domain.method import TackleMethod

#: Shape of every entry, checked by test_species.py so the two tables cannot drift.
FIELDS = ("primary_lure", "primary_size", "primary_color", "line", "leader",
          "presentation", "depth", "retrieve", "target_structure")

CONVENTIONAL = {
    "striped_bass": {
        "default": {
            "primary_lure": "Soft-plastic swimbait on a jighead",
            "primary_size": "5-6 in, 3/8-3/4 oz",
            "primary_color": "Pearl or smoke — match the shad",
            "line": "20 lb braid",
            "leader": "25 lb fluorocarbon, 3 ft",
            "presentation": "Cast across and let it swing down with the current",
            "depth": "Mid-column, counting it down",
            "retrieve": "Slow and steady — let the current do the work",
            "target_structure": "Current seams and the edges of breaks",
        },
        "heavy_current": {
            "primary_lure": "Heavy bucktail or a big paddle-tail",
            "primary_size": "6-8 in, 1-2 oz",
            "primary_color": "White or chartreuse where it is pushing hard",
            "line": "30 lb braid",
            "leader": "30 lb fluorocarbon, short",
            "presentation": "Cast up-current and stay in contact as it comes back",
            "depth": "Deep — get under the push",
            "retrieve": "Lift and drop, keeping the line tight",
            "target_structure": "The shear line where the release meets slack water",
        },
        "slack": {
            "primary_lure": "Flutter spoon or a deep jig",
            "primary_size": "1-2 oz",
            "primary_color": "Chrome or white",
            "line": "20 lb braid",
            "leader": "20 lb fluorocarbon",
            "presentation": "Vertical over marked fish, or a long count-down cast",
            "depth": "Down to the thermocline or the bait",
            "retrieve": "Yo-yo it — the fall is the bite",
            "target_structure": "Bait balls, channel edges, the deepest water nearby",
        },
        "low_light": {
            "primary_lure": "Topwater walking bait",
            "primary_size": "5-7 in",
            "primary_color": "Bone or clear",
            "line": "30 lb braid",
            "leader": "30 lb monofilament — mono floats",
            "presentation": "Long casts across flats and seams, worked back",
            "depth": "On top",
            "retrieve": "Walk it, and do not set until you feel weight",
            "target_structure": "Shallow flats next to deep water; surface activity",
        },
    },
    "smallmouth": {
        "default": {
            "primary_lure": "Tube or a Ned-style soft plastic",
            "primary_size": "3-4 in, 1/8-3/8 oz",
            "primary_color": "Green pumpkin or brown",
            "line": "10 lb braid",
            "leader": "8-10 lb fluorocarbon",
            "presentation": "Cast upstream and drag it back with the current",
            "depth": "On the bottom",
            "retrieve": "Drag and pause — most bites come on the pause",
            "target_structure": "Rock, current breaks, the edge of the shoal",
        },
        "heavy_current": {
            "primary_lure": "Heavier football jig",
            "primary_size": "3/8-1/2 oz",
            "primary_color": "Brown or crawfish",
            "line": "12 lb braid",
            "leader": "12 lb fluorocarbon",
            "presentation": "Cast up-current, keep contact, let it tumble",
            "depth": "Hard on the bottom",
            "retrieve": "Short hops, staying in touch",
            "target_structure": "Behind boulders and on the soft side of the seam",
        },
        "slack": {
            "primary_lure": "Drop-shot",
            "primary_size": "3 in worm, 3/16 oz",
            "primary_color": "Natural — green pumpkin, watermelon",
            "line": "8 lb braid",
            "leader": "6-8 lb fluorocarbon",
            "presentation": "Vertical or a short cast to visible rock",
            "depth": "A foot off the bottom",
            "retrieve": "Shake it in place; move it slowly",
            "target_structure": "Deeper rock, bluff ends, the outside of the bend",
        },
        "low_light": {
            "primary_lure": "Walking topwater or a small popper",
            "primary_size": "3-4 in",
            "primary_color": "Bone or shad",
            "line": "10 lb braid",
            "leader": "10 lb monofilament",
            "presentation": "Across the shoal and the tailout",
            "depth": "On top",
            "retrieve": "Steady walk with pauses over rock",
            "target_structure": "Shoal heads and tailouts, shallow rock",
        },
    },
    "largemouth": {
        "default": {
            "primary_lure": "Texas-rigged soft plastic",
            "primary_size": "5-7 in, 1/4-3/8 oz",
            "primary_color": "Green pumpkin or black-blue in stain",
            "line": "15 lb fluorocarbon",
            "leader": "none — straight through",
            "presentation": "Pitch to cover and let it fall on a slack line",
            "depth": "In the cover, on the bottom",
            "retrieve": "Lift, fall, wait. The fall is the bite",
            "target_structure": "Wood, grass edges, the first drop inside a creek mouth",
        },
        "heavy_current": {
            "primary_lure": "Squarebill crankbait",
            "primary_size": "2-3 in",
            "primary_color": "Shad or crawfish",
            "line": "15 lb fluorocarbon",
            "leader": "none",
            "presentation": "Cast to the bank and crank it into the rock",
            "depth": "3-6 ft, deflecting",
            "retrieve": "Steady, with a hesitation off every deflection",
            "target_structure": "Riprap and current-washed banks",
        },
        "slack": {
            "primary_lure": "Jig with a craw trailer",
            "primary_size": "3/8-1/2 oz",
            "primary_color": "Black-blue or green pumpkin",
            "line": "17 lb fluorocarbon",
            "leader": "none",
            "presentation": "Pitch to isolated cover and work it slowly",
            "depth": "Bottom, in the thickest cover you can reach",
            "retrieve": "Crawl it, with long pauses",
            "target_structure": "Laydowns, stumps, the inside grass line",
        },
        "low_light": {
            "primary_lure": "Buzzbait or a hollow-body frog",
            "primary_size": "3/8 oz / 4 in",
            "primary_color": "Black at night, white at dawn",
            "line": "40 lb braid over grass",
            "leader": "none",
            "presentation": "Over and along the grass edge",
            "depth": "On top",
            "retrieve": "Steady over open water; walk it in the holes",
            "target_structure": "Grass edges, shallow flats next to a drop",
        },
    },
    "trout": {
        "default": {
            "primary_lure": "In-line spinner",
            "primary_size": "1/16-1/8 oz",
            "primary_color": "Silver or gold — silver in clear water",
            "line": "6 lb monofilament",
            "leader": "4 lb fluorocarbon",
            "presentation": "Cast across and slightly up, swing it through the run",
            "depth": "Mid-column",
            "retrieve": "Just fast enough to keep the blade turning",
            "target_structure": "Seams, the head of the run, the edge of the shelf",
        },
        "heavy_current": {
            "primary_lure": "Heavier spoon or a weighted spinner",
            "primary_size": "1/8-1/4 oz",
            "primary_color": "Gold or brass",
            "line": "8 lb monofilament",
            "leader": "6 lb fluorocarbon",
            "presentation": "Quarter it upstream and let it get down before it swings",
            "depth": "Deep — the fish will not come up through it",
            "retrieve": "Slow, staying in contact",
            "target_structure": "The soft water behind rock, and the bank seam",
        },
        "slack": {
            "primary_lure": "Small soft plastic or a micro jig",
            "primary_size": "1-2 in, 1/32-1/16 oz",
            "primary_color": "Natural or white",
            "line": "4 lb monofilament",
            "leader": "4 lb fluorocarbon, long",
            "presentation": "Cast and let it sink, then move it in small increments",
            "depth": "Near the bottom in the deeper pools",
            "retrieve": "Twitch and pause",
            "target_structure": "Pool bottoms, undercut banks, the deepest slot",
        },
        "low_light": {
            "primary_lure": "Small jerkbait or a floating minnow",
            "primary_size": "2-3 in",
            "primary_color": "Rainbow or brown trout pattern",
            "line": "6 lb monofilament",
            "leader": "5 lb fluorocarbon",
            "presentation": "Cast to the bank and work it out over the drop",
            "depth": "Top two feet",
            "retrieve": "Twitch, twitch, pause",
            "target_structure": "Shallow tailouts and bank seams at first and last light",
        },
    },
}


def for_method(species, key, method):
    """The technique table entry for one species/condition/method, or None.

    Returns None for FLY so the caller uses `profiles.py`, which is the source of truth
    for fly and always was — this module never mirrors it.
    """
    if method == TackleMethod.FLY:
        return None
    table = CONVENTIONAL.get(species) or {}
    return dict(table.get(key) or table.get("default") or {}) or None


def prefer_conventional(method, species, key, stillwater=False):
    """Which method to SHOW when the user said 'either'. §20.

    Not a coin flip and not fly-by-default. The rule is about what the water rewards:
    reservoir cover and heavy tailrace current are where conventional tackle genuinely
    does something a fly rod cannot — reach depth quickly, and cover a lot of water — and
    largemouth in grass is the clearest case of all. Everywhere else the fly answer is at
    least as good and is the one this repo has actually calibrated, so it wins the tie.
    """
    if method == TackleMethod.FLY:
        return False
    if method == TackleMethod.CONVENTIONAL:
        return True
    if species == "largemouth":
        return True
    if key == "heavy_current":
        return True
    return bool(stillwater and key == "slack")


def available(species):
    return sorted(CONVENTIONAL.get(species, {}))
