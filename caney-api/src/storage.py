"""
KV-backed storage for the API Worker. §33, §78.

§33 asks for D1 for plans and KV for short-lived cache. The deploy token this project has
returns 401 on the D1 API — it can create Workers and KV namespaces and cannot create
databases — so the D1 path is written and unreachable, and KV carries plans in the
meantime. That is a real limitation and it is recorded rather than hidden: KV is
eventually consistent and has no queries, so "list my last ten trips" is not available
until D1 is. Refresh and replay, which address a plan by id, work exactly the same on
either.

DEPLOYMENT.md holds the one permission that changes this.
"""
import json

from caney.api.storage import Store


class KVStore(Store):
    """Cloudflare KV. Async underneath, and the handler is synchronous — see the note."""

    name = "kv"

    #: Same reasoning as MemoryStore.TTL: a snapshot outlives its plan because a delta
    #: compares against it, and a session outlives both because somebody may log an
    #: outcome that evening.
    TTL = {"snapshot": 7 * 86400, "plan": 3 * 86400, "session": 30 * 86400}

    def __init__(self, kv, cache=None):
        self.kv = kv
        # The handler is synchronous by design — it is the same code the build and the
        # tests run. KV is async. Rather than colour the whole planner async for two
        # calls, the Worker PRELOADS the keys a request needs into this dict before
        # calling the handler, and writes are collected and flushed after. Requests are
        # addressed by id, so what to preload is always known in advance.
        self._read = dict(cache or {})
        self._writes = []
        self.STATS = {"gets": 0, "hits": 0, "puts": 0}

    def _k(self, kind, key):
        return "%s:%s" % (kind, key)

    def get(self, kind, key):
        self.STATS["gets"] += 1
        v = self._read.get(self._k(kind, key))
        if v is None:
            return None
        self.STATS["hits"] += 1
        return json.loads(v) if isinstance(v, str) else v

    def put(self, kind, key, value, ttl_seconds=None):
        self.STATS["puts"] += 1
        self._writes.append((self._k(kind, key), json.dumps(value, default=str),
                             ttl_seconds or self.TTL.get(kind, 86400)))
        return True

    def delete(self, kind, key):
        self._writes.append((self._k(kind, key), None, 0))
        return True

    def preload(self, k, raw):
        self._read[k] = raw

    def pending(self):
        return list(self._writes)

    def clear_pending(self):
        self._writes = []

    def stats(self):
        s = dict(self.STATS)
        s["backend"] = self.name
        s["durable"] = True
        s["queryable"] = False       # KV has no queries; D1 would add them
        return s
