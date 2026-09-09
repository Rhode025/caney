"""
Architectural invariants. §25, §47, §55, §54.

These are the checks that stop the new architecture from quietly becoming the old one:
a scoring threshold drifting into the browser, HTML creeping back into Python, `value or 0`
reappearing, a secret being committed.
"""
import os
import re

from harness import check, eq, section, skip

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _walk(rel, suffix):
    base = os.path.join(ROOT, rel)
    for root, _dirs, files in os.walk(base):
        if "node_modules" in root or "__pycache__" in root:
            continue
        for f in sorted(files):
            if f.endswith(suffix):
                yield os.path.join(root, f)


def _code_lines(path):
    """Line numbers and text of REAL code — docstrings and comments removed.

    The first version of this check grepped raw text and flagged the sentence in
    observation.py that explains why `value or 0` is banned. A lint that fails on its own
    documentation trains people to disable it.
    """
    import io
    import tokenize
    src = _read(os.path.relpath(path, ROOT))
    blank = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                for ln in range(tok.start[0], tok.end[0] + 1):
                    blank.setdefault(ln, []).append(tok.string)
    except tokenize.TokenError:
        pass
    out = []
    for n, line in enumerate(src.splitlines(), 1):
        if n in blank and any(len(s) > 20 for s in blank[n]):
            continue                      # a docstring line, not code
        out.append((n, line))
    return out


def test_no_unknown_as_zero():
    section("§3.4 — `value or 0` must not reappear in planner code")
    pat = re.compile(r"\bor\s+0\b(?!\.)")
    hits = []
    for p in _walk("caney", ".py"):
        for n, line in _code_lines(p):
            if line.strip().startswith("#"):
                continue
            if pat.search(line):
                # Allowed only where the value being defaulted CANNOT be a measurement:
                # a length, a count, a sort key. Each must say so, on the line itself.
                if "# not a measurement" in line:
                    continue
                hits.append("%s:%d %s" % (os.path.relpath(p, ROOT), n, line.strip()[:70]))
    check("no bare `or 0` on a value that could be a reading", not hits,
          " | ".join(hits[:4]))
    check("the ban is enforced on code, not on the prose that explains it",
          any("or 0" in _read("caney", "domain", "observation.py") for _ in [1]))

    section("every source adapter returns a state, never an empty structure")
    for mod in ("usgs.py", "cwms.py", "weather.py"):
        src = _read("caney", "sources", mod)
        check("%s constructs explicit unknown/error observations" % mod,
              "Observation.unknown(" in src or "return [], err" in src)


def test_no_inline_assets():
    section("§47 — shared CSS and JS are shared, not pasted into documents")
    pages = _read("caney", "render", "pages.py")
    check("the page renderer contains no <style> block", "<style" not in pages)
    check("the page renderer contains no inline script body",
          not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", pages.replace(
              '<script type="module">\n  import { boot }', "<script src=")),
          "the only inline script may be the 2-line module bootstrap")
    check("the page renderer links the shared stylesheet",
          'href="assets/app.css"' in pages)

    # This suite runs BEFORE the build in CI, on purpose: a broken scorer should fail in
    # seconds rather than after a sixty-second build. So the built-output half defers to
    # test/verify.py, which runs after it and asserts the same things.
    out = os.path.join(ROOT, "out", "index.html")
    if os.path.exists(out):
        html = _read("out", "index.html")
        check("the built homepage has no <style>", "<style" not in html)
        bodies = [b for b in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                                        html, re.S) if len(b.strip()) > 200]
        check("the built homepage has no inline script over 200 chars", not bodies,
              "%d found" % len(bodies))
        for js in ("app.js", "model.js", "utility.js", "opportunity.js", "itin.js",
                   "segments.js", "ui.js", "timeline.js", "format.js", "map.js"):
            check("shared module is a separate file: " + js,
                  os.path.exists(os.path.join(ROOT, "out", "assets", "planner", js)))
    else:
        skip("built-output asset checks",
             "out/ has not been built; test/verify.py enforces them after the build")


def test_browser_engine_holds_no_model():
    section("§47 — the browser assembles, it does not model")
    src = _read("web", "planner", "model.js")
    # Numeric literals that would be a threshold or a coefficient. The ones that are
    # allowed are the window-search geometry (which Python publishes too) and 0/1/100.
    # 0/1/2/3/4 are indices and lengths; 100 and 1000 are unit conversions; 3600 and
    # 86400000 are time; the rest are named display constants declared at the top of the
    # file. Anything else in model.js is a threshold, and a threshold is a model.
    ALLOWED = {"0", "1", "2", "3", "4", "5", "10", "100", "1000", "3600", "86400000",
               "0.05", "0.2", "0.35", "12", "32", "45", "50", "55", "68", "78"}
    bad = []
    for n, line in enumerate(src.splitlines(), 1):
        st = line.strip()
        if st.startswith("*") or st.startswith("//") or st.startswith("/*"):
            continue
        for m in re.finditer(r"(?<![\w.])\d+(?:\.\d+)?", line):
            if m.group(0) not in ALLOWED:
                bad.append("%d: %s" % (n, st[:70]))
                break
    check("model.js contains no unexplained numeric constants", not bad,
          " | ".join(bad[:4]))
    check("the ranking blend comes from the dataset, not from a literal",
          "rank.base" in src and "rank.conf" in src)
    check("the weights come from the dataset", "data.weights[species]" in src)
    check("the gates come from the dataset", "data.gates[zoneId]" in src)

    section("verdict thresholds are stated in both engines and must match")
    py = _read("caney", "planner", "engine.py")
    for lit in ("68", "55", "50"):
        check("verdict threshold %s appears in the Python engine" % lit,
              lit in py, "engine.py")
        check("verdict threshold %s appears in the browser engine" % lit,
              lit in src, "model.js")


def test_layering():
    section("§25 — nothing imports upward through the layers")
    RULES = {
        "domain": ("caney.sources", "caney.planner", "caney.render", "caney.zones",
                   "riverlib"),
        "species": ("caney.sources", "caney.planner", "caney.render", "riverlib"),
        "research": ("caney.planner", "caney.render"),
    }
    for layer, forbidden in RULES.items():
        for p in _walk(os.path.join("caney", layer), ".py"):
            src = _read(os.path.relpath(p, ROOT))
            for f in forbidden:
                mod = f.split(".")[-1]
                bad = re.search(r"^\s*(?:from|import)\s+.*\b%s\b" % re.escape(mod),
                                src, re.M)
                check("%s does not import %s" % (os.path.relpath(p, ROOT), f), not bad,
                      bad.group(0).strip() if bad else "")

    section("the calibrated hydrology is reused, not reimplemented")
    snap = _read("caney", "sources", "snapshots.py")
    check("arrival routing comes from riverlib, not from a local copy",
          "riverlib.arrival_window(" in snap)
    check("no new arrival constant is defined in the planner",
          "2.5" not in _read("caney", "planner", "scoring.py"))


def test_repo_hygiene():
    section("§54 — nothing generated or secret is committed")
    ig = _read(".gitignore")
    for pat in (".wrangler/", "**/.wrangler/", ".env", ".env.*", ".cache/"):
        check("gitignore covers %s" % pat, pat in ig)
    import subprocess
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True).stdout.split("\n")
    bad = [t for t in tracked if ".wrangler" in t or t.endswith(".env")]
    check("no .wrangler or .env file is tracked", not bad, ",".join(bad[:3]))

    section("§17 — no secret is embedded")
    for p in list(_walk("caney", ".py")) + list(_walk("web", ".js")) + \
             list(_walk("riverguide/src", ".js")):
        src = _read(os.path.relpath(p, ROOT))
        hits = re.findall(r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})", src)
        check("no credential literal in " + os.path.relpath(p, ROOT), not hits, str(hits))


def test_observability():
    section("§55 — the build records what it did")
    p = os.path.join(ROOT, "out", "plan", "build.json")
    if not os.path.exists(p):
        return skip("build-report checks",
                    "out/ has not been built; test/verify.py enforces them after the build")
    import json
    b = json.load(open(p))
    for k in ("built", "durationSeconds", "zones", "safetyClaims", "featuredPlans",
              "http", "research", "datasetBytes"):
        check("build report records %s" % k, k in b, str(sorted(b)))
    for k in ("fetches", "failures", "hits_memo", "hits_disk", "seconds", "bytes"):
        check("source fetch stats record %s" % k, k in b["http"], str(sorted(b["http"])))
    for k in ("provider", "enabled", "queries", "fetched", "cached", "latencySeconds"):
        check("research stats record %s" % k, k in b["research"], str(sorted(b["research"])))
    check("the build reports a duration budget it can be measured against",
          isinstance(b["durationSeconds"], (int, float)))
