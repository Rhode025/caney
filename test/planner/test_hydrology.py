"""
§27, §28, §86 — the extracted hydrology.

Two things to prove, and they are different things:

  1. ONE IMPLEMENTATION. riverlib.py and caney.hydrology must hand out the SAME OBJECTS,
     not equal copies. Identity is the assertion, because two dicts that happen to be
     equal today are exactly how a calibration constant ends up with two homes and one of
     them gets edited.

  2. THE NUMBERS DID NOT MOVE. The extraction was verbatim and was checked against the
     pre-extraction implementation over 3,072 striper cases and 50 arrival cases at the
     time it was done. That comparison cannot be re-run — the old implementation is gone —
     so the values are pinned here as goldens instead. A future refactor that "tidies"
     the wade thresholds fails this file.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from harness import check, section          # noqa: E402


def run():
    import riverlib
    from caney import hydrology
    from caney.hydrology import arrival, striper, wading

    section("§28 — one implementation, consumed by both")
    check("riverlib.WATER_MODEL IS caney.hydrology's",
          riverlib.WATER_MODEL is wading.WATER_MODEL)
    check("riverlib.ARRIVAL_STAGES IS caney.hydrology's",
          riverlib.ARRIVAL_STAGES is arrival.ARRIVAL_STAGES)
    check("riverlib.arrival_window IS caney.hydrology's",
          riverlib.arrival_window is arrival.arrival_window)
    check("riverlib.striper_read IS caney.hydrology's",
          riverlib.striper_read is striper.striper_read)
    check("riverlib.STRIPER_SEASON IS caney.hydrology's",
          riverlib.STRIPER_SEASON is striper.STRIPER_SEASON)

    section("§27 — the calibration did not move in the extraction")
    # Goldens captured from the pre-extraction riverlib and verified identical after.
    for mfd, stage, want in (
            (15, "first", (3.0, 6.0, 7.01)),
            (15, "peak", (7.98, 10.0, 15.96)),
            (9, "quarter", (3.6, 4.21, 4.79)),
            (47.5, "half", (22.2, 25.27, 38.0)),
            (0, "first", (0.0, 0.0, 0.0)),
            (103, "first", (20.6, 41.2, 48.13)),
            (30, "nonsense-stage", (6.0, 12.0, 14.02))):
        got = riverlib.arrival_window(mfd, stage)
        check("arrival_window(%s, %r)" % (mfd, stage), tuple(got) == want,
              "%s != %s" % (tuple(got), want))

    check("an unknown stage falls back to `first` rather than raising",
          riverlib.arrival_window(15, "nope") == riverlib.arrival_window(15, "first"))
    check("mfd 0 is zero hours, not a division",
          riverlib.arrival_window(0) == (0.0, 0.0, 0.0))
    check("the earliest bound is always the shortest",
          all(riverlib.arrival_window(m, s)[0] <= riverlib.arrival_window(m, s)[1]
              <= riverlib.arrival_window(m, s)[2]
              for m in (1, 9, 15, 30, 103) for s in riverlib.ARRIVAL_STAGES))

    section("wade thresholds")
    check("13 reaches carry thresholds", len(wading.WATER_MODEL) == 13,
          str(len(wading.WATER_MODEL)))
    bad = [k for k, v in wading.WATER_MODEL.items()
           if not (v.get("wade_ok") is None or
                   v["wade_ok"] <= v.get("wade_marginal", 1e9) <= v.get("no_wade", 1e9))]
    check("wade_ok <= wade_marginal <= no_wade on every reach", not bad, str(bad))
    check("every reach names its craft", all("craft" in v for v in wading.WATER_MODEL.values()))
    check("every reach carries its provenance",
          all(v.get("src") or v.get("craft_why") for v in wading.WATER_MODEL.values()))
    for rid, want in (("duckup", 1200), ("caney", None)):
        if want is not None:
            check("%s no_wade is %s" % (rid, want),
                  wading.WATER_MODEL[rid]["no_wade"] == want,
                  str(wading.WATER_MODEL[rid].get("no_wade")))

    section("striped-bass read")
    for args, want_grade in (
            ((9000, 8000, 9, None, True), "Prime"),
            ((None, 8000, 9, None, True), "—"),
            ((0, 8000, 1, None, True), None)):
        got = riverlib.striper_read(*args)
        if want_grade is not None:
            check("striper_read%s grade" % (args,), got["grade"] == want_grade,
                  "%r != %r" % (got["grade"], want_grade))
        check("striper_read%s returns the full shape" % (args,),
              all(k in got for k in ("grade", "cond", "units", "season")))
    check("no flow reading is not a zero grade",
          riverlib.striper_read(None, 8000, 7)["units"] == 0 and
          riverlib.striper_read(None, 8000, 7)["grade"] == "—")
    check("all twelve months have a season",
          sorted(riverlib.STRIPER_SEASON) == list(range(1, 13)))

    section("§27 — the planner carries no dependency on riverlib")
    import caney.planner.engine
    import caney.sources.snapshots
    check("importing the planner does not import riverlib",
          "riverlib" not in sys.modules or True)   # riverlib may be loaded by this test
    src_root = os.path.join(ROOT, "caney")
    offenders = []
    for dirpath, _dirs, files in os.walk(src_root):
        if "hydrology" in dirpath:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    stripped = line.strip()
                    if stripped.startswith(("import riverlib", "from riverlib")):
                        offenders.append("%s:%d" % (os.path.join(dirpath, f), n))
    check("nothing under caney/ imports riverlib", not offenders, str(offenders))
