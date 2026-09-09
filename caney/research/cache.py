"""
Research cache. §21.

Keyed by (species, geographic candidate, date bucket, query family) exactly as specified,
with a TTL chosen by INFORMATION TYPE rather than one global number — a weekly fishing
report and a species management page do not go stale at the same rate.

Stored on disk as JSON so a rebuild inside the TTL costs nothing, and so `refreshed_at`
can be shown to the reader (§21, §57).
"""
import hashlib
import json
import os
import time

TTL = {
    "live":        15 * 60,          # direct live instrument data — minutes
    "report":      12 * 3600,        # weekly fishing reports — 6-24 h
    "regulation":  7 * 86400,        # regulations — days
    "management":  28 * 86400,       # species management pages — weeks
    "survey":      120 * 86400,      # historical surveys — months
}
DEFAULT_TTL = TTL["report"]

DIR = os.environ.get(
    "CANEY_RESEARCH_CACHE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), ".cache", "research"))


def key(species, candidate, date_bucket, family):
    raw = "|".join(str(x) for x in (species, candidate, date_bucket, family))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def date_bucket(epoch, family):
    """How coarse the date has to be before two requests share an answer."""
    if family in ("report", "live"):
        return time.strftime("%Y-%m-%d", time.localtime(epoch))
    if family == "regulation":
        return time.strftime("%Y-W%W", time.localtime(epoch))
    return time.strftime("%Y-%m", time.localtime(epoch))


def _path(k):
    return os.path.join(DIR, k[:2], k + ".json")


def get(k, family="report"):
    p = _path(k)
    if not os.path.exists(p):
        return None, None
    try:
        with open(p, encoding="utf-8") as fh:
            blob = json.load(fh)
    except Exception:
        return None, None
    age = time.time() - blob.get("at", 0)
    if age > TTL.get(family, DEFAULT_TTL):
        return None, blob.get("at")
    return blob.get("data"), blob.get("at")


def put(k, data, family="report"):
    p = _path(k)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"at": time.time(), "family": family, "data": data}, fh)
        os.replace(tmp, p)
    except Exception:
        pass
    return data


def last_refreshed():
    """(epoch, count) across the whole cache — for the 'research last refreshed' line."""
    newest, n = None, 0
    for root, _dirs, files in os.walk(DIR):
        for f in files:
            if not f.endswith(".json"):
                continue
            n += 1
            try:
                t = os.path.getmtime(os.path.join(root, f))
                newest = t if newest is None else max(newest, t)
            except OSError:
                pass
    return newest, n
