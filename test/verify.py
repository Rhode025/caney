#!/usr/bin/env python3
"""
Static QA for the river tool — no browser, no network. Checks the BUILT site in out/
against the invariants we keep hand-verifying: token completeness, link integrity, the
switcher, required components per page, the fly-only content policy, and the HQ status
contract. Run test/run.sh first (it regenerates), or run this against an existing out/.

Exit 0 = all pass, 1 = one or more failures.
"""
import os, re, json, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
STATUS = os.path.join(OUT, "status")

RIVERS = ["caney", "cumbnash", "stones", "duckup", "duckmid", "ducklow", "buffalo", "harpeth",
          "elktn", "cumberland", "elk", "cheatham", "cordell"]
# Derived, never hand-maintained: a hand-written copy of this map silently skipped
# cheatham.html and cordell.html from every per-file check for one release.
RIVER_FILES = {r: r + ".html" for r in RIVERS}
# index.html is the species-first planner (Caney 2.0). rivers.html is the old HQ board,
# now the reference layer behind it (§48). roadmap.html is the audit + sprint board.
# None of the three is a river, so RIVER_COMPONENTS skips them, but rivers.html and
# roadmap.html must still pass tokens, links, switcher and day identity like every other
# page. index.html is exempt from the switcher check: it has its own nav and is the root
# of the hierarchy rather than a peer of it.
ALL_HTML = ["index.html", "rivers.html", "roadmap.html"] + list(RIVER_FILES.values())
SWITCHER_HTML = ["rivers.html", "roadmap.html"] + list(RIVER_FILES.values())

# fly-only: these must never appear in output (baitfish = a fly's imitation target, allowed)
FORBIDDEN = re.compile(
    r"\b(catfish|sauger|crappie|lure|swimbait|spinnerbait|rattlebait|jerkbait|roadrunner|"
    r"bucktail|jigging|jig|spoon|drop-shot|tube|crankbait)\b", re.I)
FORBIDDEN_OK = re.compile(r"baitfish", re.I)   # allow 'baitfish streamer'
REMOVED_SPECIES = {"Catfish", "Sauger", "Crappie"}
EXPECTED_SPECIES = {"Trout", "Striped bass", "Smallmouth", "Largemouth", "White bass", "Panfish"}
# component anchors every RIVER page must carry (HQ is exempt — different layout).
# Each entry is a tuple of acceptable ids — Caney is bespoke and renders the solunar
# feeding component under id="feed" where the templated rivers use id="sol".
RIVER_COMPONENTS = [
    ('id="lmap"',),                 # live map
    ('id="sol"', 'id="feed"'),      # solunar / moon feeding
    ('id="hatch"',),                # hatch / forage calendar
    ('id="flysel"',),               # fly selection matrix
    ('id="mooncal"',),              # moon calendar
    ('id="log"',),                  # catch log
    ('id="chatterSec"',),           # river chatter (self-hiding)
]

_fail = []
def check(name, cond, detail=""):
    (print("  \033[32m✓\033[0m " + name) if cond
     else (_fail.append(name), print("  \033[31m✗\033[0m %s%s" % (name, (" — " + detail) if detail else ""))))

def read(f):
    with open(os.path.join(OUT, f), encoding="utf-8") as fh:
        return fh.read()

print("── files & tokens ──")
for f in ALL_HTML:
    p = os.path.join(OUT, f)
    if not os.path.exists(p):
        check("exists: " + f, False, "missing — run test/run.sh to build"); continue
    html = read(f)
    check("exists: " + f, True)
    toks = sorted(set(re.findall(r"__[A-Z][A-Z_]+__", html)))
    check("no leftover tokens: " + f, not toks, ",".join(toks))

print("── links resolve ──")
for f in ALL_HTML:
    if not os.path.exists(os.path.join(OUT, f)):
        continue
    html = read(f)
    targets = sorted(set(re.findall(r'href="([a-z]+\.html)"', html)))
    missing = [t for t in targets if not os.path.exists(os.path.join(OUT, t))]
    check("links resolve: " + f, not missing, "missing " + ",".join(missing))

TABS = len(RIVERS) + 2         # Plan + Rivers + every river; derived, never hardcoded
print("── switcher (Plan + Rivers + %d rivers = %d tabs) ──" % (len(RIVERS), TABS))
for f in SWITCHER_HTML:
    if not os.path.exists(os.path.join(OUT, f)):
        continue
    html = read(f)
    m = re.search(r'<div class="switch">(.*?)</div>', html, re.S)
    n = len(re.findall(r"<a\b", m.group(1))) if m else 0
    check("switcher %d tabs: %s" % (TABS, f), n == TABS, "found %d" % n)

print("── required components per river page ──")
for rid, f in RIVER_FILES.items():
    if not os.path.exists(os.path.join(OUT, f)):
        continue
    html = read(f)
    missing = [alts[0] for alts in RIVER_COMPONENTS if not any(a in html for a in alts)]
    check("components: " + f, not missing, "missing " + ",".join(missing))
riv = read("rivers.html") if os.path.exists(os.path.join(OUT, "rivers.html")) else ""
check("river board has board/filter/sort",
      all(x in riv for x in ['id="board"', 'id="spf"', 'id="sort"']))

print("── fly-only content policy ──")
for f in ALL_HTML:
    if not os.path.exists(os.path.join(OUT, f)):
        continue
    html = read(f)
    bad = [m.group(0) for m in FORBIDDEN.finditer(html)
           if not FORBIDDEN_OK.match(html[max(0, m.start() - 4):m.end() + 4])]
    # 'baitfish' contains no forbidden token; guard is just belt-and-suspenders
    bad = sorted(set(w.lower() for w in bad))
    check("fly-only (no gear/species): " + f, not bad, "found " + ",".join(bad))

print("── HQ status contract ──")
cards = {}
for jf in glob.glob(os.path.join(STATUS, "*.json")):
    rid = os.path.basename(jf)[:-5]
    try:
        cards[rid] = json.load(open(jf))
    except Exception as e:
        check("valid JSON: " + rid, False, str(e))
check("all %d status cards present" % len(RIVERS), set(cards) == set(RIVERS),
      "have " + ",".join(sorted(cards)))
for rid, c in cards.items():
    ok = (isinstance(c.get("species"), list) and c.get("name") and c.get("file")
          and isinstance(c.get("now"), dict)
          and all(k in c["now"] for k in ("grade", "cond", "col"))
          and isinstance(c.get("week"), list) and 1 <= len(c["week"]) <= 7
          and all(all(k in w for k in ("grade", "col", "ico", "hi", "pop")) for w in c["week"]))
    check("status schema: " + rid, ok)

# HQ day contract (the board renders these directly, so a missing field is a blank card)
for rid, c in cards.items():
    days = c.get("days") or {}
    ok = set(days) >= {"today", "tomorrow"}
    check("day state present: " + rid, ok, "have " + ",".join(sorted(days)))
    for when, d in days.items():
        shape = (isinstance(d.get("vessel"), dict) and isinstance(d.get("clarity"), dict)
                 and isinstance(d.get("level"), dict)
                 and all(k in d["vessel"] for k in ("kind", "label", "col", "ico"))
                 and all(k in d["level"] for k in ("kind", "label", "col")))
        check("day shape: %s/%s" % (rid, when), shape)
        cv = d.get("curve")
        if cv is not None:
            good = (isinstance(cv.get("vals"), list) and len(cv["vals"]) == 24
                    and cv.get("src") in ("forecast", "observed")
                    and any(x is not None for x in cv["vals"]))
            check("curve shape: %s/%s" % (rid, when), good,
                  "len=%s src=%s" % (len(cv.get("vals") or []), cv.get("src")))
# every river in the wade/float model must carry a source for its numbers
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_rl", os.path.join(ROOT, "riverlib.py"))
_rl = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_rl)
check("water model covers every river", set(_rl.WATER_MODEL) == set(RIVERS),
      "missing " + ",".join(sorted(set(RIVERS) - set(_rl.WATER_MODEL))))
for _rid, _m in _rl.WATER_MODEL.items():
    check("water model cites a source: " + _rid, bool(_m.get("src")) and len(_m["src"]) > 40)
    _w, _f, _c = _rl.wade_float(_rid, 500)
    check("wade_float returns a confidence: " + _rid,
          _c in ("measured", "reported", "structural", "unknown"), repr(_c))
# A river with no wade threshold must never produce a guessed wade verdict. Stones now
# returns "n/a" rather than "unknown" — stronger, because the craft set settles it: you
# do not wade this reach, so there is nothing to be uncertain about.
check("stones never returns a guessed wade verdict",
      _rl.wade_float("stones", 300)[0] in ("n/a", "unknown"),
      _rl.wade_float("stones", 300)[0])

# A unit count and a flow reading must never be paired unless they come from the SAME
# measurement. cumbnash carries both an Old Hickory release and a USGS gauge 25 mi
# downstream that differ by thousands of cfs; pairing them produced "1 unit / 15,700 cfs",
# which is internally impossible (15,700 would be 2.4 units).
for _rid in ("cumbnash", "cheatham", "cordell"):
    _n = (cards.get(_rid, {}).get("now") or {})
    _cond, _det = _n.get("cond", ""), _n.get("detail", "")
    import re as _re
    _um = _re.match(r"(\d+)\s*units?", _cond)
    if _um:
        _units = int(_um.group(1))
        # every cfs figure quoted alongside must either be attributed, or be consistent
        _um2 = _re.search(r'"relUnit"\s*:\s*(\d+)', open(os.path.join(OUT, _rid + ".html")).read())
        _unit_cfs = int(_um2.group(1)) if _um2 else 6500
        for _v in [int(x.replace(",", "")) for x in _re.findall(r"([\d,]+)\s*cfs", _det)]:
            _implied = round(_v / _unit_cfs)
            _ok = (_implied == _units) or ("release" in _det and "at " in _det)
            check("unit count and flow are from the same source or attributed: %s" % _rid, _ok,
                  "%r vs %r" % (_cond, _det))
    if "release" in _det and "cfs" in _det:
        check("release figure is labelled as a release: " + _rid, "cfs release" in _det, _det)

# the three Cumberland tailraces are striped-bass pages: the grade must come from the
# sourced striper model, and heavy water must never be graded Prime on the fish's behalf
# (that verdict is capped by boat handling, which the summer refuge argument cannot override)
for _rid in ("cumbnash", "cheatham", "cordell"):
    _c = cards.get(_rid, {})
    check("striper page targets only striped bass: " + _rid,
          _c.get("species") == ["Striped bass"], str(_c.get("species")))
for _u, _cfs in ((1, 6500), (2, 13000), (3, 19500)):
    _r = _rl.striper_read(_cfs, 6500, 7)
    check("summer generation grades Prime at %d units" % _u, _r["grade"] == "Prime", _r["grade"])
_hi = _rl.striper_read(40000, 6500, 7)
check("very heavy water is not graded Prime on the fish's behalf", _hi["grade"] != "Prime", _hi["grade"])
check("very heavy water names boat handling as the limit", "boat" in _hi["note"].lower(), _hi["note"][:60])
_slack = _rl.striper_read(0, 6500, 7)
check("no generation is graded down", _slack["grade"] in ("Slow", "Fair"), _slack["grade"])
check("every striper read says where to fish", all(
    _rl.striper_read(q, 6500, m).get("where") for q in (0, 6500, 20000) for m in (1, 5, 7, 10)))
check("winter note names the Nov-Mar stretch",
      "Nov-Mar" in _rl.striper_read(13000, 6500, 1)["note"], "")
check("spring note names the run",
      "Spring run" in _rl.striper_read(13000, 6500, 5)["note"], "")

# craft is user-stated ground truth and must gate every verdict: the board must never
# suggest a vessel a river does not take, whatever the flow says.
_CRAFT_SPEC = {"caney": {"wade", "float", "boat"}, "duckup": {"boat", "wade"}, "duckmid": {"boat"}, "ducklow": {"boat"}, "buffalo": {"paddle", "wade"}, "harpeth": {"paddle", "wade"}, "cumbnash": {"boat"},
               "cumberland": {"boat", "wade"}, "elktn": {"kayak", "wade"}, "stones": {"boat"}}
for _rid, _want in _CRAFT_SPEC.items():
    check("craft set matches the stated spec: " + _rid,
          set(_rl.WATER_MODEL[_rid].get("craft") or []) == _want,
          "have " + ",".join(sorted(_rl.WATER_MODEL[_rid].get("craft") or [])))
for _rid, _m in _rl.WATER_MODEL.items():
    _c = set(_m.get("craft") or [])
    check("craft set is non-empty and explained: " + _rid, bool(_c) and bool(_m.get("craft_why")))
    # sweep flows; a craft the river does not have must never be offered
    for _q in (50, 250, 600, 1500, 5000, 20000):
        _w, _f, _ = _rl.wade_float(_rid, _q)
        if not (_c & {"wade", "kayak"}):
            check("never offers wading on a boat-only river: %s@%s" % (_rid, _q), _w == "n/a", _w)
        if not (_c & {"boat", "float"}):
            check("never offers a boat where there is none: %s@%s" % (_rid, _q), _f == "n/a", _f)
_k, _lbl, _why, _ = _rl.craft_label("elktn", 260)
check("kayak-only river is labelled as such", "Kayak" in _lbl, _lbl)

# a river with no forward flow forecast must SAY so rather than render an empty card
for rid in ("elk", "elktn", "stones"):
    d = (cards.get(rid, {}).get("days") or {}).get("tomorrow", {})
    check("no-forecast river is explicit: " + rid,
          d.get("curve") is None and "forecast" in (d.get("headline") or "").lower(),
          repr(d.get("headline")))

species = set(s for c in cards.values() for s in c.get("species", []))
check("species == expected set", species == EXPECTED_SPECIES,
      "extra=%s missing=%s" % (species - EXPECTED_SPECIES, EXPECTED_SPECIES - species))
check("removed species absent", not (species & REMOVED_SPECIES), str(species & REMOVED_SPECIES))

# grade-map completeness: every grade emitted must be weighted by the HQ sorter
gw_src = open(os.path.join(ROOT, "hq.py")).read()
gm = re.search(r"const GW=\{([^}]+)\}", gw_src)
gw_keys = set(re.findall(r"(\w+):", gm.group(1))) | {"—"} if gm else set()
emitted = set()
for c in cards.values():
    emitted.add(c["now"]["grade"])
    emitted |= set(w["grade"] for w in c["week"])
check("HQ grade-map covers all emitted grades", emitted <= gw_keys,
      "unhandled " + ",".join(emitted - gw_keys))

print("── deploy freshness endpoint (#2) ──")
# The watchdog runs outside this repo and reads only this file. If its shape drifts, the
# watchdog goes blind in exactly the silent way the 2026-08-21 outage went unnoticed — so
# the contract is pinned here rather than in the Worker, which cannot fail the build.
_sp = os.path.join(OUT, "site.json")
if not os.path.exists(_sp):
    check("site.json exists", False, "hq.py must write the watchdog's endpoint")
else:
    _s = json.load(open(_sp))
    check("site.json has a numeric build epoch", isinstance(_s.get("built"), int))
    check("site.json counts the rivers", _s.get("rivers") == len(RIVERS),
          "says %s, registry has %d" % (_s.get("rivers"), len(RIVERS)))
    check("site.json reports the oldest river", _s.get("oldestRiver") in RIVERS,
          str(_s.get("oldestRiver")))
    check("site.json reports how far behind it is",
          isinstance(_s.get("oldestRiverAgeSec"), int) and _s["oldestRiverAgeSec"] >= 0)
    check("every river card carries its own build epoch",
          all(isinstance(c.get("built"), int) for c in cards.values()),
          ",".join(r for r, c in cards.items() if not isinstance(c.get("built"), int)))

print("── bot corpus (RiverGuide) ──")
# The bot answers from out/bot.json alone. It is assembled from the status cards AND from
# each page's DATA blob, so a rename in either place would silently empty it — the bot would
# then answer confidently from a corpus with no conditions in it. Pin the shape here.
_bp = os.path.join(OUT, "bot.json")
if not os.path.exists(_bp):
    check("bot.json exists", False, "bot.py must run at the end of the build")
else:
    _b = json.load(open(_bp))
    _rv = {r["id"]: r for r in _b.get("rivers", [])}
    check("bot corpus covers every river", set(_rv) == set(RIVERS),
          "missing " + ",".join(sorted(set(RIVERS) - set(_rv))))
    check("bot corpus states its safety rules", len(_b.get("rules") or []) >= 3)
    check("bot corpus is timestamped", isinstance(_b.get("built"), int))
    for _k in ("now", "week"):
        _bad = [r for r, c in _rv.items() if not c.get(_k)]
        check("every river has %s: bot corpus" % _k, not _bad, ",".join(_bad))
    # The fly answer is the single most-asked thing and the most easily lost, since it comes
    # from the page rather than the status card.
    _nofly = [r for r, c in _rv.items() if not (c.get("fly") or {}).get("fly")]
    check("every river has a current fly", not _nofly, ",".join(_nofly))
    _noacc = [r for r, c in _rv.items() if not c.get("access")]
    check("every river has access points", not _noacc, ",".join(_noacc))

print("── day identity: no build-time relative time (RIVER_SPEC §0) ──")
# The 2026-08-23 regression: deploys stopped for two days and every page kept calling
# Friday's data "Today", because day rows carried a label but no date identity. These
# checks keep that impossible: every row must ship an `iso`, and the reader's clock —
# not the build's — must decide what the label says.
_MD = re.compile(r"^\d{1,2}/\d{1,2}$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def data_blob(html):
    """The page's DATA object, parsed. Brace-matched rather than regexed — day rows nest
    (wx, byCraft), so a flat [^{}] pattern silently matches nothing and passes vacuously."""
    m = re.search(r"const (?:DATA|D)=window\.__rlRelabel\(", html)
    if not m: return None
    i, depth = m.end(), 0
    for j in range(i, len(html)):
        if html[j] == "{": depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                try: return json.loads(html[i:j + 1])
                except Exception: return None
    return None

def day_rows(o, acc=None):
    """Every object that looks like a day row: has a label and an 'M/D' date."""
    acc = [] if acc is None else acc
    if isinstance(o, list):
        for v in o: day_rows(v, acc)
    elif isinstance(o, dict):
        if "label" in o and _MD.match(str(o.get("date", ""))): acc.append(o)
        for v in o.values(): day_rows(v, acc)
    return acc

_rowtotal = 0
# index.html is the planner (Caney 2.0). It meets the SAME invariant by a different, and
# stronger, mechanism: no time is formatted at build time at all — the dataset ships
# epochs, and web/planner/format.js labels them against the reader's clock. So it is
# checked below by its own contract instead of the __rlRelabel one.
for f in [x for x in ALL_HTML if x != "index.html"]:
    p = os.path.join(OUT, f)
    if not os.path.exists(p): continue
    html = read(f)
    check("DATA goes through __rlRelabel: " + f,
          bool(re.search(r"const (?:DATA|D)=window\.__rlRelabel\(", html)),
          "render() must wrap the DATA blob so labels are stamped before any render call")
    check("day-identity runtime present: " + f, "window.__rlRelabel=" in html)
    # S1 / #1 — a stale page must not render values that only mean something today.
    check("stale-day seal present: " + f, "window.__rlSealClockKeyed=" in html)
    if f not in ("rivers.html", "roadmap.html"):
        # Every river page carries at least one clock-keyed container for the seal to find.
        # Without one, a stale build would show live-looking numbers with nothing to blank.
        clock = re.findall(r'id="(nowstrip|now|arrival|best|feed|sol)"|data-clock', html)
        check("has a clock-keyed surface to seal: " + f, bool(clock),
              "no #now/#nowstrip/#sol/#feed container — the seal has nothing to act on")

    D = data_blob(html)
    check("DATA parses: " + f, D is not None)
    if D is None: continue
    # Every day ROW must carry an iso. Without one __rlRelabel cannot reach it and its label
    # stays frozen at build time — which is exactly how Friday's data came to say "Today".
    rows = day_rows(D); _rowtotal += len(rows)
    bad = [r for r in rows if not _ISO.match(str(r.get("iso", "")))]
    check("every day row carries an iso: %s (%d rows)" % (f, len(rows)), not bad,
          "%d without iso, e.g. label=%r date=%r" %
          (len(bad), bad[0].get("label"), bad[0].get("date")) if bad else "")
    if "todayIso" in D or "today" in D or "todayLabel" in D:
        check("page headline carries todayIso: " + f, _ISO.match(str(D.get("todayIso", ""))),
              "needed so the headline date follows the reader's clock, not the build's")

print("── planner (Caney 2.0) ──")
_pd = os.path.join(OUT, "plan", "data.json")
if not os.path.exists(_pd):
    check("plan/data.json exists", False, "planner.py must run in build.sh")
else:
    _P = json.load(open(_pd))
    _idx = read("index.html")

    # §4 — the homepage asks the product's question and offers the four species.
    check("homepage asks what to catch", "What do you want to catch?" in _idx)
    for _w in ("id=\"species\"", "id=\"times\"", "id=\"crafts\"", "id=\"go\""):
        check("planner shell has " + _w, _w in _idx)
    check("primary CTA is FIND MY BEST PLAN", "FIND MY BEST PLAN" in _idx)
    for _sp in ("striped_bass", "smallmouth", "largemouth", "trout"):
        check("species in dataset: " + _sp, _sp in _P["species"])
        check("weights sum to 100: " + _sp, sum(_P["weights"][_sp].values()) == 100,
              str(sum(_P["weights"][_sp].values())))
        check("moon is capped at 3 points: " + _sp, _P["weights"][_sp].get("moon", 0) <= 3)

    # §47 — shared CSS and JS are actually shared: the shell links them, never inlines them.
    check("homepage inlines no <style>", "<style" not in _idx)
    _inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", _idx, re.S)
    _bodies = [b for b in _inline if len(b.strip()) > 200]
    check("homepage inlines no script body", not _bodies,
          "%d inline script(s) over 200 chars" % len(_bodies))
    check("homepage links the shared stylesheet", 'href="assets/app.css"' in _idx)
    for _js in ("app.js", "model.js", "ui.js", "timeline.js", "format.js", "map.js"):
        check("shared module shipped: " + _js,
              os.path.exists(os.path.join(OUT, "assets", "planner", _js)))

    # RIVER_SPEC §0 applied to the planner: no formatted clock time in the emitted HTML.
    _clock = re.findall(r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)\b", _idx)
    check("no build-time clock string on the homepage", not _clock, ",".join(_clock[:3]))
    check("day labelling is client-side",
          "dayLabel" in open(os.path.join(OUT, "assets", "planner", "format.js"),
                             encoding="utf-8").read())

    # §22 — the Carthage striper case must exist as GEOGRAPHY, not as a page species tag.
    _cc = _P["zones"].get("carthage_confluence")
    check("carthage_confluence zone exists", bool(_cc))
    if _cc:
        check("carthage_confluence holds striped bass",
              "striped_bass" in _cc["species_profiles"])
        check("carthage_confluence spans Cordell AND the Caney",
              set(_cc["waterbody_ids"]) >= {"cordell", "caney"}, str(_cc["waterbody_ids"]))
        check("carthage_confluence is a corridor, not an invented pin",
              (_cc["geometry"] or {}).get("kind") == "corridor",
              str((_cc["geometry"] or {}).get("kind")))
        _ev = _P["evidence"].get("carthage_confluence|striped_bass") or []
        check("carthage striper case carries sourced evidence", len(_ev) >= 3,
              "%d claims" % len(_ev))
        # 2.1: an evidence row is {id, confidence} — the confidence is per zone, because
        # a claim is worth more at the water it names than at the water it does not.
        for _row in _ev:
            _cid = _row["id"] if isinstance(_row, dict) else _row
            _cl = _P["claims"].get(_cid) or {}
            check("every research claim has a source URL", bool(_cl.get("source_url")),
                  _cid)
            if isinstance(_row, dict):
                check("evidence carries a per-zone confidence: " + _cid,
                      isinstance(_row.get("confidence"), (int, float)), str(_row))

    # §3.3 / §20 — safety claims are minted from instruments and carry their bound.
    _bad_bound = [c["id"] for c in _P["safety"] if c["bound"] not in
                  ("earliest", "typical", "latest", "measured")]
    check("every safety claim declares its bound", not _bad_bound, ",".join(_bad_bound[:3]))
    _exits = [c for c in _P["safety"] if c["kind"] == "safe_exit"]
    check("every safe-exit claim uses the conservative bound",
          all(c["bound"] == "earliest" for c in _exits),
          ",".join(c["id"] for c in _exits if c["bound"] != "earliest"))
    _num = [c["id"] for c in _P["safety"]
            if c["kind"] in ("flow", "stage", "generation_start", "generation_stop",
                             "safe_exit", "release_arrival") and not c["numbers"]]
    check("numeric safety claims list their licensed numbers", not _num, ",".join(_num[:3]))

    # §3.4 — unknown is never zero.
    for _zid, _z in _P["zones"].items():
        for _k, _o in _z["water"].items():
            if _o["state"] in ("unknown", "error"):
                check("unknown water value is not a number: %s.%s" % (_zid, _k),
                      _o["value"] is None, repr(_o["value"]))

    # §3.5 — modelled arrival ships a distribution, never a single time.
    for _zid, _z in _P["zones"].items():
        _a = (_z.get("arrival") or {}).get("first")
        if _a:
            check("arrival ships early/typical/late: " + _zid,
                  set(_a) == {"earliest_h", "typical_h", "latest_h"} and
                  _a["earliest_h"] <= _a["typical_h"] <= _a["latest_h"], str(_a))

    # ── Caney 2.1 ──────────────────────────────────────────────────────
    # §6, §7 — the window utility constants are published, not written twice.
    _U = _P.get("utility") or {}
    for _k in ("wPeak", "wCubic", "wFloor", "idealMinutes", "dBase", "dSpan",
               "shortPenalty", "cBase", "cSpan", "lBase", "lSpan",
               "transitionCostPerMin", "idleCostFactor", "breadthBonus",
               "complexityPenalty", "sampleMinutes", "minDuration"):
        check("utility constant published: " + _k, _k in _U, str(sorted(_U)))
    check("the quality mixture sums to 1",
          abs(_U.get("wPeak", 0) + _U.get("wCubic", 0) + _U.get("wFloor", 0) - 1) < 1e-9,
          str([_U.get("wPeak"), _U.get("wCubic"), _U.get("wFloor")]))
    check("the peak term dominates the mixture (§7)",
          _U.get("wPeak", 0) > _U.get("wCubic", 0) and _U.get("wPeak", 0) > _U.get("wFloor", 0))
    for _sp in ("striped_bass", "smallmouth", "largemouth", "trout"):
        check("minimum practical duration published: " + _sp,
              (_U.get("minDuration") or {}).get(_sp, 0) >= 60,
              str(_U.get("minDuration")))
    check("duration saturates rather than paying forever",
          _U.get("dBase", 0) + _U.get("dSpan", 0) <= 1.0 + 1e-9)

    # §4 — the hourly opportunity series both engines optimise over.
    check("hourly opportunity series shipped", bool(_P.get("hourly")),
          str(len(_P.get("hourly") or {})))
    for _k, _h in (_P.get("hourly") or {}).items():
        check("hourly series is anchored and dense: " + _k,
              _h.get("t0") and _h.get("step") == 3600 and len(_h.get("values") or []) >= 48,
              str(len(_h.get("values") or [])))
        break

    # §11, §12 — the transition graph, per craft, with provenance on every edge.
    _T = _P.get("transitions") or {}
    check("a transition graph exists for every craft",
          set(_T) == {"any", "wade", "kayak", "drift", "power"}, str(sorted(_T)))
    for _craft, _edges in _T.items():
        for _k, _e in list(_edges.items())[:200]:
            check("transition declares provenance: %s %s" % (_craft, _k),
                  _e.get("provenance") in ("known", "estimated", "unknown"),
                  str(_e.get("provenance")))
            check("transition has a positive cost: %s %s" % (_craft, _k),
                  isinstance(_e.get("minutes"), (int, float)) and _e["minutes"] > 0,
                  str(_e.get("minutes")))
    check("a wading angler gets far fewer moves than a power boat",
          len(_T.get("wade", {})) < len(_T.get("power", {})),
          "%d vs %d" % (len(_T.get("wade", {})), len(_T.get("power", {}))))

    # §28-§33 — geographic confidence is first class, and honest.
    for _zid, _z in _P["zones"].items():
        _lc = _z.get("location_confidence") or {}
        check("zone declares location confidence: " + _zid,
              isinstance(_lc.get("score"), (int, float)) and 0 <= _lc["score"] <= 100,
              str(_lc.get("score")))
        check("it names its three parts: " + _zid, len(_lc.get("rows") or []) == 3)
        check("it declares a tactical level: " + _zid,
              _lc.get("tactical_level") in ("precise", "corridor", "hedged"),
              str(_lc.get("tactical_level")))
        check("zone declares its kind: " + _zid, bool(_z.get("kind")))
        _geo = _z.get("geometry") or {}
        if _geo:
            check("geometry declares its evidence level: " + _zid,
                  _geo.get("evidence") in _P["locationEvidence"]["order"],
                  str(_geo.get("evidence")))
        # §30 — weak geography must NOT produce precise tactical language. The check is
        # on the INSTRUCTION half: the rationale may describe what the model expects, but
        # the sentence the reader acts on must say it is unverified.
        for _sp2, _parts in (_z.get("holds_parts") or {}).items():
            if _lc.get("tactical_level") == "hedged":
                check("hedged geography hedges its instruction: %s/%s" % (_zid, _sp2),
                      "not been field verified" in _parts[0], _parts[0][:80])
            if _lc.get("tactical_level") == "corridor":
                check("corridor geography gives a stretch, not a spot: %s/%s" % (_zid, _sp2),
                      "corridor" in _parts[0].lower(), _parts[0][:80])

    # §35, §36 — largemouth has cover water, and not every zone is a river reach.
    _kinds = {z.get("kind") for z in _P["zones"].values()}
    check("more than one kind of water is modelled", len(_kinds) >= 5, str(sorted(_kinds)))
    _lm_still = [z for z in _P["zones"].values()
                 if "largemouth" in (z.get("species_profiles") or {}) and z.get("stillwater")]
    check("largemouth has stillwater zones to compete in", len(_lm_still) >= 3,
          str([z["id"] for z in _lm_still]))

    # §34 — stripers are modelled in every month, across more than one system.
    _sb = [z for z in _P["zones"].values()
           if "striped_bass" in (z.get("species_profiles") or {})]
    _months = set()
    for _z in _sb:
        _months |= set(_z["species_profiles"]["striped_bass"]["months"])
    check("striper zones cover every month", _months == set(range(1, 13)),
          str(sorted(set(range(1, 13)) - _months)))
    check("striper zones span several systems",
          len({z["river"] for z in _sb}) >= 4, str({z["river"] for z in _sb}))

    # §53 — every plan is stamped with the models that produced it.
    for _k in ("planner", "species_model", "zone_model", "research"):
        check("model version published: " + _k, bool((_P.get("versions") or {}).get(_k)),
              str(_P.get("versions")))

    # §55 — the parity fixture covers all four layers.
    _pp = os.path.join(OUT, "plan", "parity.json")
    if os.path.exists(_pp):
        _PA = json.load(open(_pp))
        for _layer in ("cases", "windows", "subwindows", "itineraries"):
            check("parity fixture covers " + _layer, len(_PA.get(_layer) or []) > 0,
                  str(len(_PA.get(_layer) or [])))

    check("dataset carries the published rank formula",
          abs(_P["rank"]["base"] + _P["rank"]["conf"] - 1.0) < 1e-9, str(_P["rank"]))
    check("planner reports research state", "provider" in _P.get("research", {}))
    check("PWA manifest shipped", os.path.exists(os.path.join(OUT, "manifest.webmanifest")))
    check("service worker shipped", os.path.exists(os.path.join(OUT, "sw.js")))
    check("leaflet bundled locally (offline maps)",
          os.path.exists(os.path.join(OUT, "assets", "leaflet.js")))
    check("parity fixture shipped for the browser engine",
          os.path.exists(os.path.join(OUT, "plan", "parity.json")))

# A guard on the guard: if the walk stops finding rows (a refactor renames date/label), the
# checks above would pass vacuously — as an earlier regex version of this check did.
check("day-row scan found rows to check", _rowtotal >= 50, "only %d rows seen" % _rowtotal)

# Relative words must not be BAKED into prose Python emits — DAYLABEL_JS can rewrite day
# rows, but it cannot reach a sentence. Day rows themselves are exempt: their build-time
# label is a documented no-JS fallback that __rlRelabel overwrites.
_REL = re.compile(r'"[^"]*\b(?:Today|Tomorrow|Yesterday)\b[^"]*"')
for src in ["riverlib.py", "briefing.py", "cumberland.py", "duck.py", "buffalo.py",
            "harpeth.py", "hq.py", "planner.py", "caney/render/pages.py"]:
    txt = open(os.path.join(ROOT, src), encoding="utf-8").read()
    hits = []
    for ln, line in enumerate(txt.splitlines(), 1):
        s = line.strip()
        if s.startswith("#") or '"Today" if' in line or "'Today'" in line:
            continue          # comments, and the documented row-label fallback
        for m in _REL.finditer(line):
            g = m.group(0)
            # Markup is exempt: a static control like <button data-v="today">Today</button>
            # is a VIEW label the client repaints against its own clock, not baked data.
            if "<" in g or ">" in g:
                continue
            if len(g) > 12:               # a bare "Today" key/label is fine; prose is not
                hits.append("%s:%d" % (src, ln))
    check("no relative time baked into prose: " + src, not hits, ", ".join(hits[:3]))

print()
if _fail:
    print("\033[31mFAILED %d check(s):\033[0m %s" % (len(_fail), "; ".join(_fail)))
    sys.exit(1)
print("\033[32mALL STATIC CHECKS PASSED\033[0m")
