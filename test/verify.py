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

RIVERS = ["caney", "cumbnash", "stones", "duck", "elktn", "cumberland", "elk", "cheatham", "cordell"]
# Derived, never hand-maintained: a hand-written copy of this map silently skipped
# cheatham.html and cordell.html from every per-file check for one release.
RIVER_FILES = {r: r + ".html" for r in RIVERS}
ALL_HTML = ["index.html"] + list(RIVER_FILES.values())

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

print()
if _fail:
    print("\033[31mFAILED %d check(s):\033[0m %s" % (len(_fail), "; ".join(_fail)))
    sys.exit(1)
print("\033[32mALL STATIC CHECKS PASSED\033[0m")
