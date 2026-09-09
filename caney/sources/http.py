"""
The one place the product talks to the internet. §26.

Thirteen generators each implemented their own fetch-with-retry; this is the replacement
for the new code. Two properties that matter:

  * DEDUPE. Two zones on the same dam ask for the same CWMS series. The in-process memo
    means one request, not two, and the disk cache means none at all on a rebuild inside
    the TTL. §56: centralise repeated source requests before parallelising anything.
  * FAILURE IS A VALUE. A dead upstream returns (None, error-string), never an exception
    and never an empty structure that reads as "zero". Callers turn that into
    Observation.error(), which is visible in the freshness strip.

stdlib only, as everywhere else in this repo.
"""
import json
import os
import time
import urllib.error
import urllib.request
import threading

CACHE_DIR = os.environ.get(
    "CANEY_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), ".cache", "sources"))

UA = {"User-Agent": "caney-planner/2.0 (+https://caney.pages.dev)"}

_MEMO = {}
_LOCK = threading.Lock()
STATS = {"hits_memo": 0, "hits_disk": 0, "fetches": 0, "failures": 0, "bytes": 0,
         "seconds": 0.0}


def _path(key):
    import hashlib
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, h[:2], h + ".json")


def cached_json(url, ttl=900, timeout=45, retries=2, key=None, headers=None):
    """(data, error). `error` is a string when data is None; both are never truthy at once."""
    k = key or url
    now = time.time()

    with _LOCK:
        m = _MEMO.get(k)
    if m and now - m[0] < ttl:
        with _LOCK:
            STATS["hits_memo"] += 1
        return m[1], None

    p = _path(k)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                blob = json.load(fh)
            if now - blob.get("at", 0) < ttl:
                STATS["hits_disk"] += 1
                with _LOCK:
                    _MEMO[k] = (blob["at"], blob["data"])
                return blob["data"], None
        except Exception:
            pass

    t0 = time.time()
    data, err = None, None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            STATS["bytes"] += len(raw)
            data = json.loads(raw.decode("utf-8", "replace"))
            err = None
            break
        except Exception as e:                       # noqa: BLE001 — every failure is data
            err = "%s: %s" % (type(e).__name__, e)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    STATS["seconds"] += time.time() - t0
    STATS["fetches"] += 1

    if data is None:
        STATS["failures"] += 1
        # Serve a stale disk copy rather than nothing — the caller sees the age and
        # decides. Silence is worse than an old number that admits its age.
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    blob = json.load(fh)
                return blob["data"], "stale:" + (err or "fetch failed")
            except Exception:
                pass
        return None, err or "fetch failed"

    with _LOCK:
        _MEMO[k] = (now, data)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"at": now, "url": url, "data": data}, fh)
        os.replace(tmp, p)
    except Exception:
        pass
    return data, None


def stats():
    return dict(STATS)
