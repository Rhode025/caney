#!/usr/bin/env python3
"""
bot.py -> out/bot.json — the corpus the RiverGuide chat bot answers from.

One record per river, normalised from two places that already exist: the status card
(out/status/<id>.json, authoritative for now/today/week) and the built page's DATA blob
(the fly matrix, tips, hatch calendar and access points, which live only in the page).

Why a separate file rather than pointing the bot at the pages: the bot pays per token.
A page is 50-210 KB of HTML and CSS wrapped around a few hundred bytes of answer. This is
the answer without the wrapper, and it is sliceable — a question about one river's flies
should not ship thirteen rivers' weeks.

THIRD-PARTY DEPENDENCIES: none required. `headroom-ai` is used ONLY if it is importable,
to write an additional compressed copy; the site build never depends on it and never fails
without it (CLAUDE.md invariant: the build is stdlib-only). See compress_corpus().
"""
import json, os, re, sys, glob, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import riverlib

OUT = os.path.join(HERE, "out")
SITE = "https://caney.pages.dev"


def page_data(river_id):
    """The DATA blob out of a built page. verify.py pins this same shape, so a rename
    that would silently empty the bot's corpus fails the build first."""
    p = os.path.join(OUT, river_id + ".html")
    if not os.path.exists(p):
        return {}
    h = open(p, encoding="utf-8").read()
    m = re.search(r"const (?:DATA|D)=window\.__rlRelabel\(", h)
    if not m:
        return {}
    s, depth = m.end(), 0
    for j in range(s, len(h)):
        if h[j] == "{":
            depth += 1
        elif h[j] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(h[s:j + 1])
                except Exception:
                    return {}
    return {}


def fly_now(D):
    """What to tie on right now — already computed at build time by the clarity x light
    matrix, so the bot never has to reason its way to a fly."""
    f = D.get("flysel") or {}
    now = f.get("now") or {}
    if not now:
        return None
    return {
        "clarity": now.get("clarity"),
        "light": now.get("light"),
        "fly": now.get("fly"),
        "rig": f.get("rig"),
        "box": [{"name": b[0], "sizes": b[1], "job": b[2]}
                for b in (f.get("boxinv") or []) if len(b) >= 3][:8],
        "sources": f.get("sources"),
    }


def hatch_now(D):
    """Only the forage that is actually on this month — the other eleven columns are
    noise to a bot answering about today."""
    H = D.get("hatch") or {}
    month = D.get("month")
    rows = []
    for r in (H.get("rows") or []):
        m = r.get("m") or []
        if month and len(m) >= month and m[month - 1]:
            rows.append({"name": r.get("name"), "pattern": r.get("pattern"),
                         "intensity": m[month - 1]})
    rows.sort(key=lambda r: -r["intensity"])
    return rows


def access(D):
    pts = D.get("points") or D.get("access") or []
    out = []
    for p in pts:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        out.append({k: v for k, v in {
            "name": p.get("name"),
            "types": p.get("types"),
            "info": (p.get("info") or p.get("note") or "")[:220] or None,
            "lat": p.get("lat"), "lon": p.get("lon"),
            "mfd": p.get("mfd"), "rm": p.get("rm"),
        }.items() if v not in (None, "", [])})
    return out[:12]


def tips(D):
    out = []
    for t in (D.get("tips") or [])[:6]:
        if isinstance(t, (list, tuple)) and len(t) >= 2:
            out.append(str(t[1])[:300])
        elif isinstance(t, str):
            out.append(t[:300])
    return out


def build():
    rivers = []
    for r in riverlib.RIVERS:
        rid = r["id"]
        sp = os.path.join(OUT, "status", rid + ".json")
        if not os.path.exists(sp):
            print("  ! no status card:", rid)
            continue
        S = json.load(open(sp))
        D = page_data(rid)
        days = S.get("days") or {}

        # The honesty layer. Every river states how its numbers were arrived at, so the bot
        # can qualify an answer instead of sounding equally sure about a backtested tailwater
        # and a river whose constants have never been validated (issue #30).
        wm = (riverlib.WATER_MODEL or {}).get(rid) or {}
        _, _, conf = riverlib.wade_float(rid, 500)

        rivers.append({k: v for k, v in {
            "id": rid,
            "name": r.get("name"),
            "emoji": r.get("emoji"),
            "url": SITE + "/" + r.get("file", rid + ".html"),
            "species": S.get("species"),
            "kind": S.get("kind"),
            "drive": S.get("drive"),
            "built": S.get("built"),
            "now": S.get("now"),
            "weather": S.get("wx"),
            "today": days.get("today"),
            "tomorrow": days.get("tomorrow"),
            "week": S.get("week"),
            "fly": fly_now(D),
            "hatchNow": hatch_now(D),
            "tips": tips(D),
            "access": access(D),
            "solunar": D.get("solunar"),
            "waterModel": {"how": wm.get("src"), "confidence": conf} if wm else None,
        }.items() if v not in (None, [], {})})

    now = datetime.datetime.now(datetime.timezone.utc)
    corpus = {
        "built": int(now.timestamp()),
        "builtIso": now.isoformat(timespec="seconds"),
        "site": SITE,
        "region": "Middle Tennessee / south-central Kentucky / north Alabama",
        # Read by the bot's system prompt. These are the rules the pages themselves follow,
        # restated for a model that will be tempted to be helpful about a number it should
        # not touch.
        "rules": [
            "Generation schedules, wade windows, arrival times and flow numbers are safety "
            "information. Quote them exactly as given or say you do not know. Never restate, "
            "round, average or infer one.",
            "Every reading is from the build time above, not live. If it is more than a few "
            "hours old, say so before answering.",
            "A river whose waterModel.confidence is not 'measured' carries estimated numbers. "
            "Say which when it matters.",
            "Link the river's url so the reader can check the live page.",
        ],
        "rivers": rivers,
    }
    return corpus


def compress_corpus(corpus):
    """Optional second copy, compressed by headroom (github.com/headroomlabs-ai/headroom).

    Two things learned the hard way and worth keeping written down:

    1. The npm package does NOT compress. headroom-ai@0.36.5 for JS is a ~10 KB client that
       returns {compressed: false, tokensBefore: 0} and passes the payload through untouched,
       despite its README. Only the PYTHON package carries the compressors — which is why
       this runs at build time and not in the Worker, where there is no Python.
    2. headroom protects user messages (`router:protected:user_message`). Data inside one is
       left alone. It has to be presented as a TOOL RESULT to be compressed at all — hence
       the shape below, which is also how the bot sends it.

    Measured on this corpus: about 30% of tokens. Absent headroom, this is a no-op and the
    bot uses the full copy; the build never depends on it.
    """
    try:
        import headroom
    except ImportError:
        print("  headroom not installed — skipping compressed copy (bot uses bot.json)")
        return None
    payload = json.dumps(corpus, separators=(",", ":"))
    msgs = [
        {"role": "system", "content": "You answer questions about river fishing conditions."},
        {"role": "user", "content": "What is fishing well right now?"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "get_conditions", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": payload},
    ]
    try:
        r = headroom.compress(msgs)
    except Exception as e:
        print("  headroom failed (%s) — using the full copy" % e)
        return None
    tool = next((m for m in r.messages if m.get("role") == "tool"), None)
    if not tool or not isinstance(tool.get("content"), str):
        print("  headroom returned nothing usable — using the full copy")
        return None
    saved = getattr(r, "tokens_saved", 0) or 0
    before = getattr(r, "tokens_before", 0) or 0
    pct = (saved / before * 100) if before else 0
    print("  headroom: %s -> %s tokens (%.1f%% saved)" % (f"{before:,}", f"{before-saved:,}", pct))
    return {"content": tool["content"],
            "tokensBefore": before, "tokensAfter": before - saved, "transforms": r.transforms_applied}


if __name__ == "__main__":
    corpus = build()
    p = os.path.join(OUT, "bot.json")
    json.dump(corpus, open(p, "w"), separators=(",", ":"))
    size = os.path.getsize(p)
    print("wrote %s | %d rivers | %s KB (~%s tokens)"
          % (p, len(corpus["rivers"]), f"{size//1024:,}", f"{size//4:,}"))

    c = compress_corpus(corpus)
    if c:
        json.dump(c, open(os.path.join(OUT, "bot.min.json"), "w"), separators=(",", ":"))
        print("wrote out/bot.min.json")
