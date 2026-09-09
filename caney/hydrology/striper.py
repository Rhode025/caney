"""
The striped-bass read. §27.

MOVED VERBATIM FROM riverlib.py, including the TWRA and guide-report seasonality it
encodes. The planner's species model scores stripers through `caney/species/profiles.py`;
this is the older, coarser grade that the river pages display, and the two are kept
separate on purpose — one is a page component and one is a scoring input, and merging
them would make a display change a model change.

riverlib.py imports it back from here (§28).
"""
# ── STRIPED BASS MODEL (Cumberland tailraces) ────────────────────────────────
# Sourced, not invented. Every threshold below traces to one of:
#
#  BIOLOGY. Striped bass seek thermal refuge once surface water passes ~70 F; occupied
#  refuges hold <=22 C (72 F) with dissolved oxygen >5 mg/L, and adults select 16-22 C
#  (61-72 F). 75 F is approaching their upper tolerance. A bottom-release tailrace IS that
#  refuge in summer, which is why the fish stack there when it is hot.
#  (Coutant/TVA thermal-refuge literature; TWRA and FWC summaries.)
#
#  CURRENT. Stripers hold on current seams and below current breaks, darting into swift
#  water for disoriented baitfish. Summer fishing "peaks when water is released for
#  generation" — generation is the trigger, not the obstacle. More than one generator makes
#  the river genuinely dangerous for small craft, which is a boating limit, not a fish limit.
#
#  SEASON (Cumberland-specific, TWRA + guide reports).
#    Nov-Mar  upper Cheatham, immediately below Old Hickory Dam, is the prime stretch
#    Apr-May  spring run; trophy fish upper Old Hickory near Carthage and at Cordell Hull
#    Jun-Sep  tailrace thermal refuge; generation-dependent
#    Oct      transition, fish follow bait down
#
#  NOTE ON TECHNIQUE: sources describe this fishery largely in conventional-tackle terms
#  (swimbaits, live gizzard shad on downlines). This project is fly-only by policy
#  (RIVER_SPEC, enforced by verify.py), so the same presentations are expressed as fly
#  equivalents: sink-tips, big articulated baitfish patterns, Deceivers and Clousers.
#  The WHERE and WHEN come from the sources; only the HOW is translated.
#
#  FISH. Average 25-30 lb, 40-50 lb common, Tennessee record 65 lb from this system.
#  Guides attribute the size to fish "fighting the current all day".
#
# What is NOT claimed: a cfs number above which stripers stop feeding. No source supports
# one, and the sources that discuss heavy generation describe a BOATING limit. So high flow
# degrades the fishing verdict only through the boating penalty, never on the fish's behalf.

STRIPER_SEASON = {
    1:  ("winter",  "below Old Hickory Dam is the prime stretch Nov-Mar"),
    2:  ("winter",  "below Old Hickory Dam is the prime stretch Nov-Mar"),
    3:  ("winter",  "tail of the Nov-Mar window; fish still stacked below the dam"),
    4:  ("spring",  "spring run building; trophy fish move up toward the dams"),
    5:  ("spring",  "peak trophy month on the upper pool and at Cordell Hull"),
    6:  ("summer",  "heat pushes fish to the tailrace for cool, oxygenated water"),
    7:  ("summer",  "thermal refuge is the whole game — fish the tailrace when they generate"),
    8:  ("summer",  "thermal refuge is the whole game — fish the tailrace when they generate"),
    9:  ("summer",  "still refuge-bound until the lake turns over"),
    10: ("fall",    "transition; fish follow bait downstream as the water cools"),
    11: ("winter",  "below Old Hickory Dam is the prime stretch Nov-Mar"),
    12: ("winter",  "below Old Hickory Dam is the prime stretch Nov-Mar"),
}

def striper_read(cfs, unit_cfs, month, water_f=None, at_dam=True):
    """Grade a striped-bass day from flow, season and (where known) water temperature.

    Returns dict: grade, col, cond, note, where, technique, units, season.
    """
    season, snote = STRIPER_SEASON.get(month, ("summer", ""))
    units = 0 if not cfs else max(0, round(cfs / unit_cfs))

    # Current is the trigger. No generation means no seam, no concentrated bait.
    if cfs is None:
        return {"grade": "—", "col": "#94a3b1", "cond": "No data", "units": 0, "season": season,
                "note": "no release data", "where": "", "technique": ""}
    if units == 0:
        base = ("Slack", "Slow", "#f2a832",
                "No generation — nothing pinning bait. The seam is gone and so are the fish.",
                "Work deep ledges, channel edges and creek mouths and wait for the horn.",
                "Sinking line and a big baitfish pattern worked slow along the ledge; cover water until you find them.")
    elif units == 1:
        base = ("1 unit", "Good", "#7db85a",
                "One unit turning — a seam is forming and bait is starting to stack.",
                "Fish the seam edge and the first break below the discharge.",
                "Swing a large Deceiver or Clouser across the seam on an intermediate line; hang it in the break.")
    elif units <= 3:
        base = ("%d units" % units, "Prime", "#28c76f",
                "Heavy generation — this is when the tailrace fishes best.",
                "Right in the tailrace: the boil, the seams either side, the first ledge below.",
                "Heavy sink-tip and a big articulated baitfish pattern straight through the seam; let it swing.")
    else:
        base = ("%d units" % units, "Good", "#f2a832",
                "Very heavy water — fish are there but boat handling is the limiting factor.",
                "Stay off the boil; work the outside seams and the slack behind structure.",
                "Fast-sinking head to hold under the push; spot-lock well clear of the discharge and cast to the edge.")
    cond, grade, col, note, where, tech = base

    # Summer is when the tailrace matters most: it is the thermal refuge.
    # Summer upgrades a fishable day, but never overrides the very-heavy case: that verdict
    # is capped by boat handling, and the refuge argument says nothing about boat handling.
    if season == "summer" and 1 <= units <= 3:
        grade, col = "Prime", "#28c76f"
        note += " Summer refuge: the cool bottom-release water is why they are here at all."
    if season == "summer" and units == 0:
        note += " In summer heat with no current the refuge stops working — expect a slow day."
    if season == "winter" and at_dam:
        note += " Nov-Mar this stretch immediately below the dam is the one to be on."
    if season == "spring":
        note += " Spring run: the biggest fish of the year move up toward the dam now."

    if water_f is not None:
        if water_f >= 75:
            note += " Water at %d F is past their comfort — they will be tight to the coldest water." % round(water_f)
        elif 61 <= water_f <= 72:
            note += " Water at %d F sits in their preferred 61-72 F band." % round(water_f)
    return {"grade": grade, "col": col, "cond": cond, "units": units, "season": season,
            "season_note": snote, "note": note, "where": where, "technique": tech}
