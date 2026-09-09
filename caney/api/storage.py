"""
Where plans, snapshots and sessions live. §33, §78.

Three stores, not one, because the three things have genuinely different lifetimes and
access patterns and putting them in one bucket makes at least two of them wrong:

    snapshots   write-once, read on refresh and replay, content-addressed, LARGE
    plans       write-once, read often while a trip is live, small
    sessions    read-modify-write on every state change, tiny, hot

§16 constrains what may be kept. A saved origin is the user's; a snapshot needs the
ROUTING ANSWER (how long the drive was) to explain a plan later, but it does not need the
coordinates that produced it, and storing them would build the travel-history database
§16 says not to build. `redact_origin` is applied on the way in, once, so no caller has to
remember.

The abstract Store here is what the handler talks to. Concrete backends are supplied by
whatever is hosting it: MemoryStore below for tests and the dev server, KV and D1 inside
the Worker. Nothing in `caney/` imports a Cloudflare binding.
"""
import json
import time


def redact_origin(obj):
    """§16 — keep the answer, drop the address.

    A plan must be able to say "the drive was 70 minutes, estimated" months later. It must
    not be able to say where you live. Coordinates become a coarse grid cell (~11 km),
    enough to tell two trips apart and useless for finding anybody.

    It reaches the NESTED copies, which is the part that matters. An envelope carries the
    origin in three places — `request.origin`, `logistics.origin` and the top level — and
    a redactor that cleaned only the top level would have been a privacy control that
    looked like it worked.
    """
    if not isinstance(obj, dict):
        return obj

    def cell(o):
        if isinstance(o, (list, tuple)) and len(o) == 2 and o[0] is not None:
            return [round(float(o[0]), 1), round(float(o[1]), 1)]
        if isinstance(o, dict) and o.get("lat") is not None:
            return [round(float(o["lat"]), 1), round(float(o["lon"]), 1)]
        return None

    def walk(d):
        if isinstance(d, list):
            return [walk(x) for x in d]
        if not isinstance(d, dict):
            return d
        out = {}
        for k, v in d.items():
            if k == "origin":
                c = cell(v)
                out["origin"] = None
                if c:
                    out["origin_cell"] = c
            else:
                out[k] = walk(v)
        return out

    return walk(obj)


class Store:
    """Key-value with a TTL. Deliberately the smallest interface that works."""

    name = "abstract"

    def get(self, kind, key):
        raise NotImplementedError

    def put(self, kind, key, value, ttl_seconds=None):
        raise NotImplementedError

    def delete(self, kind, key):
        raise NotImplementedError

    def stats(self):
        return {}


class MemoryStore(Store):
    """In-process. The dev server, the tests, and a Worker cold start before KV binds."""

    name = "memory"

    #: Defaults chosen from what each thing is FOR, not from a cache intuition.
    #: A snapshot outlives its plan because a delta compares against it. A session
    #: outlives both because somebody may finish a trip and log the outcome that evening.
    TTL = {"snapshot": 7 * 86400, "plan": 3 * 86400, "session": 30 * 86400}

    def __init__(self, max_entries=2000):
        self._d = {}
        self.max_entries = max_entries
        self.STATS = {"gets": 0, "hits": 0, "puts": 0, "evictions": 0}

    def _k(self, kind, key):
        return "%s/%s" % (kind, key)

    def get(self, kind, key):
        self.STATS["gets"] += 1
        row = self._d.get(self._k(kind, key))
        if not row:
            return None
        if row[0] and row[0] < time.time():
            self._d.pop(self._k(kind, key), None)
            return None
        self.STATS["hits"] += 1
        return json.loads(row[1])

    def put(self, kind, key, value, ttl_seconds=None):
        ttl = ttl_seconds if ttl_seconds is not None else self.TTL.get(kind, 86400)
        self.STATS["puts"] += 1
        if len(self._d) >= self.max_entries:
            # Oldest-expiry first. Crude, and correct for a process that is not the
            # durable copy of anything.
            oldest = sorted(self._d.items(),
                            key=lambda kv: kv[1][0] or 0)[:64]  # not a measurement
            for k, _ in oldest:
                self._d.pop(k, None)
                self.STATS["evictions"] += 1
        self._d[self._k(kind, key)] = (time.time() + ttl if ttl else None,
                                       json.dumps(value, default=str))
        return True

    def delete(self, kind, key):
        return self._d.pop(self._k(kind, key), None) is not None

    def stats(self):
        s = dict(self.STATS)
        s["entries"] = len(self._d)
        s["backend"] = self.name
        return s


class NullStore(Store):
    """Stores nothing and says so. What the API uses when no binding is configured.

    Not an error: a plan is fully usable without being stored, it simply cannot be
    refreshed by id afterwards. The handler reports `storage: "none"` so the client
    disables the refresh affordance rather than offering a button that 404s.
    """

    name = "none"

    def get(self, kind, key):
        return None

    def put(self, kind, key, value, ttl_seconds=None):
        return False

    def delete(self, kind, key):
        return False

    def stats(self):
        return {"backend": self.name, "durable": False}
