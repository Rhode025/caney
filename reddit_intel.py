#!/usr/bin/env python3
"""
reddit_intel.py — mine public Reddit for river-fishing intel, the terms-compliant way.

Uses Reddit's OFFICIAL API (OAuth2, application-only "client_credentials" grant) — the same
API third-party apps use. It only READS public posts; it does NOT log in as you, join/subscribe,
vote, comment, or take any account action. Reddit's unauthenticated .json is now 403-blocked, so
the free registered-app path is both the working AND the sanctioned way to do this.

ONE-TIME SETUP (2 min, free):
  1. Log in at https://www.reddit.com/prefs/apps  → "create another app…"
  2. Type: "script".  name: caney-river-intel.  redirect uri: http://localhost (unused).
  3. Copy the client id (under the app name) and the secret.
  4. Put them where this script can read them, either:
       export REDDIT_CLIENT_ID=xxxx  REDDIT_CLIENT_SECRET=yyyy  REDDIT_USERNAME=your_uname
     or drop a git-ignored file  reddit_creds.json  next to this script:
       {"client_id":"xxxx","client_secret":"yyyy","username":"your_uname"}

Then:  python3 reddit_intel.py            # mine + write out/intel/reddit.json + print a digest
Re-run anytime (or on a cron) — it remembers what it's already seen and flags what's NEW.

Rate-limited and low-volume (a handful of requests). Non-commercial personal use.
"""
import json, os, sys, time, urllib.request, urllib.parse, datetime, base64

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "out", "intel"); os.makedirs(OUTDIR, exist_ok=True)
SEEN_PATH = os.path.join(HERE, "reddit_seen.json")
OUT_PATH = os.path.join(OUTDIR, "reddit.json")

# ── what counts as intel, per river ──────────────────────────────────────────
# Reddit search query per river (quoted phrases match exactly). Broad all-of-Reddit search
# catches r/flyfishing, r/troutfishing, r/smallmouthbass, r/Tennessee, r/kentucky, etc. at once.
RIVERS = {
    "caney":      {"name": "Caney Fork",   "q": '"Caney Fork" OR "Center Hill Dam"'},
    "duck":       {"name": "Duck River",   "q": '"Duck River" (smallmouth OR fishing OR float OR fish)'},
    "buffalo":    {"name": "Buffalo River", "q": '"Buffalo River" Tennessee (smallmouth OR fishing OR float OR canoe)'},
    "harpeth":    {"name": "Harpeth River", "q": '"Harpeth River" (smallmouth OR fishing OR float OR canoe OR Narrows)'},
    "cumberland": {"name": "Cumberland KY", "q": '"Wolf Creek Dam" OR ("Cumberland River" (trout OR tailwater OR generation))'},
    "elk":        {"name": "Elk River",    "q": '"Elk River" (smallmouth OR Wheeler OR Alabama OR Prospect OR fishing OR jet)'},
    "elktn":      {"name": "Elk · Tims Ford", "q": '"Tims Ford" OR ("Elk River" Tennessee (trout OR tailwater OR fishing))'},
    "stones":     {"name": "Stones River", "q": '"Stones River" OR ("Percy Priest" (fishing OR tailrace OR "white bass"))'},
    "cumbnash":   {"name": "Cumberland · Nashville", "q": '("Cumberland River" (Nashville OR "Old Hickory" OR striper OR "Shelby Bottoms"))'},
    "cheatham":   {"name": "Cumberland · Cheatham", "q": '"Cheatham Dam" OR ("Cumberland River" (Clarksville OR "Ashland City"))'},
    "cordell":    {"name": "Cumberland · Cordell Hull", "q": '"Cordell Hull" OR ("Cumberland River" Carthage)'},
}
# only keep posts from subreddits that are actually about fishing/the region (cuts noise)
KEEP_SUBS_HINT = ("fish", "fly", "trout", "bass", "angl", "tenness", "kentuck", "nashville", "outdoor", "troutzone")
FRESH_DAYS = 120          # ignore anything older than this
PER_QUERY  = 25           # results per search
UA = "caney-river-intel/0.2 (personal, non-commercial)"

def load_creds():
    cid = os.environ.get("REDDIT_CLIENT_ID"); sec = os.environ.get("REDDIT_CLIENT_SECRET")
    uname = os.environ.get("REDDIT_USERNAME", "")
    p = os.path.join(HERE, "reddit_creds.json")
    if (not cid or not sec) and os.path.exists(p):
        c = json.load(open(p)); cid = cid or c.get("client_id"); sec = sec or c.get("client_secret"); uname = uname or c.get("username", "")
    return cid, sec, uname

def get_token(cid, sec):
    auth = base64.b64encode(("%s:%s" % (cid, sec)).encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request("https://www.reddit.com/api/v1/access_token", data=body,
        headers={"Authorization": "Basic " + auth, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)["access_token"]

def search(token, q, ua):
    qs = urllib.parse.urlencode({"q": q, "sort": "new", "t": "year", "limit": PER_QUERY,
                                 "type": "link", "raw_json": 1})
    req = urllib.request.Request("https://oauth.reddit.com/search?" + qs,
        headers={"Authorization": "Bearer " + token, "User-Agent": ua})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r).get("data", {}).get("children", [])

def clean(txt, n=220):
    txt = " ".join((txt or "").split())
    return txt[:n] + ("…" if len(txt) > n else "")

def main():
    cid, sec, uname = load_creds()
    if not cid or not sec:
        print(__doc__); print("!! No Reddit app credentials found — see SETUP above."); return 2
    ua = UA + (" by /u/%s" % uname if uname else "")
    try:
        token = get_token(cid, sec)
    except Exception as e:
        print("token error (check your client id/secret):", e); return 1

    seen = {}
    if os.path.exists(SEEN_PATH):
        try: seen = json.load(open(SEEN_PATH))
        except: seen = {}
    now = time.time(); cutoff = now - FRESH_DAYS * 86400
    digest = {}
    for rid, cfg in RIVERS.items():
        posts, ids = [], set()
        try:
            children = search(token, cfg["q"], ua)
        except Exception as e:
            print("search warn (%s): %s" % (rid, e)); children = []
        for c in children:
            p = c["data"]
            if p["id"] in ids or p["created_utc"] < cutoff: continue
            sub = p["subreddit"].lower()
            if not any(h in sub for h in KEEP_SUBS_HINT): continue   # keep it to fishing/region subs
            ids.add(p["id"])
            posts.append({
                "id": p["id"], "sub": p["subreddit"], "title": p["title"],
                "author": p.get("author", ""), "score": p.get("score", 0),
                "comments": p.get("num_comments", 0),
                "date": datetime.datetime.utcfromtimestamp(p["created_utc"]).strftime("%Y-%m-%d"),
                "url": "https://www.reddit.com" + p["permalink"],
                "snippet": clean(p.get("selftext", "")),
                "new": p["id"] not in seen,
            })
        posts.sort(key=lambda x: x["date"], reverse=True)
        digest[rid] = {"name": cfg["name"], "posts": posts,
                       "new": sum(1 for x in posts if x["new"]), "total": len(posts)}
        time.sleep(2)   # be polite to the API

    # persist "seen" so re-runs flag only genuinely new items
    for r in digest.values():
        for p in r["posts"]: seen[p["id"]] = p["date"]
    json.dump(seen, open(SEEN_PATH, "w"))
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    json.dump({"updated": stamp, "rivers": digest}, open(OUT_PATH, "w"), indent=1)

    # console digest
    print("Reddit river intel · %s\n" % stamp)
    for rid, r in digest.items():
        print("── %s — %d recent (%d new) ──" % (r["name"], r["total"], r["new"]))
        for p in r["posts"][:6]:
            flag = "🆕 " if p["new"] else "   "
            print("  %sr/%-15s %s ▲%-4d 💬%-3d %s" % (flag, p["sub"], p["date"], p["score"], p["comments"], p["title"][:64]))
        if not r["posts"]: print("   (nothing fresh)")
        print()
    print("wrote", OUT_PATH)
    return 0

if __name__ == "__main__":
    sys.exit(main())
