"""
SourceRuntime — where the bytes come from. §30, §31, §32.

The planner asks for a URL and gets back `(data, error)`. It has never known, and must
never learn, whether that came from urllib, a Worker `fetch`, a disk cache or a fixture.
Caney 3.0 needs that separation to be real rather than aspirational, because the runtime
the API executes in cannot make a blocking call at all:

    BuildSourceRuntime    urllib + a disk cache. The build box and the tests.
    WorkerSourceRuntime   a pure lookup over a store the Worker filled CONCURRENTLY
                          before calling the planner. Never blocks; a miss is an error
                          value, not a fetch and not a zero.
    FixtureSourceRuntime  recorded responses from disk. Deterministic tests, no network.
    RecordingSourceRuntime wraps another runtime and remembers every request made.

The last one is the reason this design holds together. A Worker cannot discover what to
prefetch by starting to plan — the first blocking call would already have failed. It needs
the request set UP FRONT. Rather than hand-maintain that list beside the fetch code and
watch it drift, the build runs the real snapshot builder under a recorder and emits the
manifest it actually produced (`out/plan/sources.json`). A source added to `cwms.py` with
no thought for the Worker still appears in the manifest, because the recorder saw it.

§32 is why the manifest is keyed by hydrology river: a striped-bass request in September
touches four rivers, and fetching the trout gauges too would be slower and ruder to USGS
for no gain.
"""
import json
import os
import threading
import time


class SourceRequest:
    """One upstream call, described well enough for a different runtime to make it."""

    __slots__ = ("key", "url", "ttl", "headers")

    def __init__(self, key, url, ttl=900, headers=None):
        self.key, self.url, self.ttl = key, url, float(ttl)
        self.headers = dict(headers or {})

    def to_json(self):
        return {"key": self.key, "url": self.url, "ttl": self.ttl,
                "headers": self.headers}

    @staticmethod
    def from_json(d):
        return SourceRequest(d["key"], d["url"], d.get("ttl", 900), d.get("headers"))

    def __repr__(self):
        return "SourceRequest(%r)" % self.key


class SourceRuntime:
    """The interface. `get_json` returns `(data, error)` and NEVER raises.

    Both halves are never truthy at once, and `(None, None)` is not a legal answer —
    callers turn an error string into `Observation.error`, and turning None into a
    silent empty structure is the failure this whole layer exists to prevent.
    """

    name = "abstract"

    #: Does loading rivers on a thread pool buy anything? True where get_json performs
    #: I/O that can overlap; False where it is a dictionary lookup. It is not merely an
    #: optimisation flag — Pyodide has no threads at all, so a runtime that says True
    #: inside a Worker takes the request down with "can't start new thread".
    concurrent = True

    def get_json(self, url, ttl=900, timeout=45, retries=2, key=None, headers=None):
        raise NotImplementedError

    def stats(self):
        return {}


# ────────────────────────────────────────────────────────────────────────────
# build
# ────────────────────────────────────────────────────────────────────────────

class BuildSourceRuntime(SourceRuntime):
    """urllib, an in-process memo and a disk cache. The behaviour Caney 2.x shipped.

    Two properties carried over unchanged, because both were load-bearing:
    deduplication (two zones on one dam make one CWMS call) and stale-serving (a dead
    upstream yields the old value tagged `stale:`, never silence).
    """

    name = "build"

    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir or os.environ.get(
            "CANEY_CACHE_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), ".cache", "sources"))
        self._memo = {}
        self._lock = threading.Lock()
        self.STATS = {"hits_memo": 0, "hits_disk": 0, "fetches": 0, "failures": 0,
                      "bytes": 0, "seconds": 0.0}

    def _path(self, key):
        import hashlib
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, h[:2], h + ".json")

    def get_json(self, url, ttl=900, timeout=45, retries=2, key=None, headers=None):
        import urllib.error
        import urllib.request
        k = key or url
        now = time.time()

        with self._lock:
            m = self._memo.get(k)
        if m and now - m[0] < ttl:
            with self._lock:
                self.STATS["hits_memo"] += 1
            return m[1], None

        p = self._path(k)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    blob = json.load(fh)
                if now - blob.get("at", 0) < ttl:
                    self.STATS["hits_disk"] += 1
                    with self._lock:
                        self._memo[k] = (blob["at"], blob["data"])
                    return blob["data"], None
            except Exception:                       # noqa: BLE001
                pass

        t0 = time.time()
        data, err = None, None
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(url, headers={**UA, **(headers or {})})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read()
                self.STATS["bytes"] += len(raw)
                data = json.loads(raw.decode("utf-8", "replace"))
                err = None
                break
            except Exception as e:                  # noqa: BLE001 — every failure is data
                err = "%s: %s" % (type(e).__name__, e)
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
        self.STATS["seconds"] += time.time() - t0
        self.STATS["fetches"] += 1

        if data is None:
            self.STATS["failures"] += 1
            if os.path.exists(p):
                try:
                    with open(p, encoding="utf-8") as fh:
                        blob = json.load(fh)
                    return blob["data"], "stale:" + (err or "fetch failed")
                except Exception:                   # noqa: BLE001
                    pass
            return None, err or "fetch failed"

        with self._lock:
            self._memo[k] = (now, data)
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"at": now, "url": url, "data": data}, fh)
            os.replace(tmp, p)
        except Exception:                           # noqa: BLE001
            pass
        return data, None

    def stats(self):
        return dict(self.STATS)


UA = {"User-Agent": "caney-planner/3.0 (+https://caney.pages.dev)"}


# ────────────────────────────────────────────────────────────────────────────
# worker
# ────────────────────────────────────────────────────────────────────────────

class WorkerSourceRuntime(SourceRuntime):
    """A pure lookup. The Worker fetched everything already, or it did not.

    `put` accepts the two outcomes a prefetch can have and nothing else. A key that was
    never prefetched returns an error naming itself, which surfaces as an `Observation`
    in the freshness strip — the planner then plans around a missing signal, which is a
    thing it already knows how to do. What it must never do is quietly proceed as though
    the value were zero, so there is no default here and no fallback fetch.
    """

    name = "worker"
    #: Everything was fetched before the planner ran. There is no I/O left to overlap,
    #: and no threads to overlap it with.
    concurrent = False

    def __init__(self):
        self._store = {}
        self.STATS = {"hits": 0, "misses": 0, "errors": 0, "prefetched": 0}

    def put(self, key, data=None, error=None):
        if (data is None) == (error is None):
            raise ValueError(
                "prefetch result for %r must be exactly one of data or error" % key)
        self._store[key] = (data, error)
        self.STATS["prefetched"] += 1

    def get_json(self, url, ttl=900, timeout=45, retries=2, key=None, headers=None):
        k = key or url
        if k not in self._store:
            self.STATS["misses"] += 1
            return None, ("not prefetched: %s — the request planner did not include this "
                          "source, so nothing fetched it" % k)
        data, err = self._store[k]
        if err:
            self.STATS["errors"] += 1
        else:
            self.STATS["hits"] += 1
        return data, err

    def stats(self):
        return dict(self.STATS)


# ────────────────────────────────────────────────────────────────────────────
# fixtures
# ────────────────────────────────────────────────────────────────────────────

class FixtureSourceRuntime(SourceRuntime):
    """Recorded responses on disk, addressed by the same key the live runtimes use."""

    name = "fixture"
    concurrent = False

    def __init__(self, root, strict=True):
        self.root, self.strict = root, bool(strict)
        self.STATS = {"hits": 0, "misses": 0}

    def _path(self, key):
        import hashlib
        return os.path.join(self.root,
                            hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json")

    def get_json(self, url, ttl=900, timeout=45, retries=2, key=None, headers=None):
        k = key or url
        p = self._path(k)
        if not os.path.exists(p):
            self.STATS["misses"] += 1
            if self.strict:
                return None, "no fixture recorded for %s" % k
            return None, "fixture miss"
        self.STATS["hits"] += 1
        with open(p, encoding="utf-8") as fh:
            blob = json.load(fh)
        return blob.get("data"), blob.get("error")

    def save(self, key, url, data, error=None):
        os.makedirs(self.root, exist_ok=True)
        p = self._path(key)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"key": key, "url": url, "data": data, "error": error}, fh)

    def stats(self):
        return dict(self.STATS)


# ────────────────────────────────────────────────────────────────────────────
# recorder
# ────────────────────────────────────────────────────────────────────────────

class RecordingSourceRuntime(SourceRuntime):
    """Wraps a runtime and remembers every request, in order, deduplicated by key.

    This is what makes the Worker's prefetch manifest derived rather than declared.
    `label()` groups subsequent requests under a hydrology river so §32 can fetch a
    subset; requests made outside any label land under `""` and are always fetched.
    """

    name = "recording"

    @property
    def concurrent(self):
        return getattr(self.inner, "concurrent", True)

    def __init__(self, inner):
        self.inner = inner
        self.requests = {}          # key -> SourceRequest
        self.groups = {}            # label -> [key]
        self._lock = threading.Lock()
        # The snapshot builder loads rivers on a thread pool, so a single shared label
        # attribute would interleave: Caney's CWMS request would be recorded under
        # whichever river happened to set the label last. Per-thread, therefore.
        self._local = threading.local()

    @property
    def _label(self):
        return getattr(self._local, "label", "")

    def label(self, name):
        rt = self

        class _Ctx:
            def __enter__(self_inner):
                self_inner.prev = rt._label
                rt._local.label = name
                return rt

            def __exit__(self_inner, *a):
                rt._local.label = self_inner.prev
                return False
        return _Ctx()

    def get_json(self, url, ttl=900, timeout=45, retries=2, key=None, headers=None):
        k = key or url
        with self._lock:
            self.requests[k] = SourceRequest(k, url, ttl, headers)
            g = self.groups.setdefault(self._label, [])
            if k not in g:
                g.append(k)
        return self.inner.get_json(url, ttl, timeout, retries, key, headers)

    def manifest(self):
        """{groups: {river: [key]}, requests: {key: SourceRequest json}}."""
        return {"groups": {k: list(v) for k, v in self.groups.items()},
                "requests": {k: r.to_json() for k, r in self.requests.items()}}

    def stats(self):
        return self.inner.stats()


# ────────────────────────────────────────────────────────────────────────────
# the installed runtime
# ────────────────────────────────────────────────────────────────────────────

_CURRENT = None


def current():
    global _CURRENT
    if _CURRENT is None:
        _CURRENT = BuildSourceRuntime()
    return _CURRENT


def install(runtime):
    """Swap the runtime. Returns the previous one so a caller can restore it."""
    global _CURRENT
    prev = _CURRENT
    _CURRENT = runtime
    return prev


class using:
    """`with using(rt):` — install for a block, restore afterwards even on error."""

    def __init__(self, runtime):
        self.runtime, self._prev = runtime, None

    def __enter__(self):
        self._prev = install(self.runtime)
        return self.runtime

    def __exit__(self, *a):
        install(self._prev)
        return False
