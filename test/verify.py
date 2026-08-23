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
# roadmap.html is the audit + sprint board. Not a river, so RIVER_COMPONENTS skips it,
# but it must still pass tokens, links, switcher and day identity like every other page.
ALL_HTML = ["index.html", "roadmap.html"] + list(RIVER_FILES.values())

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

TABS = len(RIVERS) + 1          # HQ + every river; derived, never hardcoded
print("── switcher (HQ + %d rivers = %d tabs) ──" % (len(RIVERS), TABS))
for f in ALL_HTML:
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
idx = read("index.html") if os.path.exists(os.path.join(OUT, "index.html")) else ""
check("HQ has board/filter/sort", all(x in idx for x in ['id="board"', 'id="spf"', 'id="sort"']))

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
for f in ALL_HTML:
    p = os.path.join(OUT, f)
    if not os.path.exists(p): continue
    html = read(f)
    check("DATA goes through __rlRelabel: " + f,
          bool(re.search(r"const (?:DATA|D)=window\.__rlRelabel\(", html)),
          "render() must wrap the DATA blob so labels are stamped before any render call")
    check("day-identity runtime present: " + f, "window.__rlRelabel=" in html)
    # S1 / #1 — a stale page must not render values that only mean something today.
    check("stale-day seal present: " + f, "window.__rlSealClockKeyed=" in html)
    if f not in ("index.html", "roadmap.html"):
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

# A guard on the guard: if the walk stops finding rows (a refactor renames date/label), the
# checks above would pass vacuously — as an earlier regex version of this check did.
check("day-row scan found rows to check", _rowtotal >= 50, "only %d rows seen" % _rowtotal)

# Relative words must not be BAKED into prose Python emits — DAYLABEL_JS can rewrite day
# rows, but it cannot reach a sentence. Day rows themselves are exempt: their build-time
# label is a documented no-JS fallback that __rlRelabel overwrites.
_REL = re.compile(r'"[^"]*\b(?:Today|Tomorrow|Yesterday)\b[^"]*"')
for src in ["riverlib.py", "briefing.py", "cumberland.py", "duck.py", "buffalo.py",
            "harpeth.py", "hq.py"]:
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
