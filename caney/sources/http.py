"""
The one place the product asks for bytes. §26, §30.

Thirteen generators each implemented their own fetch-with-retry; this is the replacement
for the new code. Two properties that matter:

  * DEDUPE. Two zones on the same dam ask for the same CWMS series. One request, not two,
    and none at all on a rebuild inside the TTL. §56: centralise repeated source requests
    before parallelising anything.
  * FAILURE IS A VALUE. A dead upstream returns (None, error-string), never an exception
    and never an empty structure that reads as "zero". Callers turn that into
    Observation.error(), which is visible in the freshness strip.

Caney 3.0 moved the mechanism into `runtime.py` and left this module as the seam every
adapter calls. `cached_json` no longer knows how bytes arrive — on the build box it is
urllib and a disk cache; inside the API Worker it is a lookup over responses fetched
concurrently before the planner ran; in tests it is a fixture directory. Adapters did not
change, which was the point of putting the seam here in 2.0.

stdlib only, as everywhere else in this repo.
"""
from .runtime import (BuildSourceRuntime, FixtureSourceRuntime,  # noqa: F401
                      RecordingSourceRuntime, SourceRequest, SourceRuntime,
                      WorkerSourceRuntime, current, install, using)

#: Kept for callers that referenced them directly before 3.0.
UA = {"User-Agent": "caney-planner/3.0 (+https://caney.pages.dev)"}


def cached_json(url, ttl=900, timeout=45, retries=2, key=None, headers=None):
    """(data, error). `error` is a string when data is None; both are never truthy at once."""
    return current().get_json(url, ttl=ttl, timeout=timeout, retries=retries,
                              key=key, headers=headers)


def stats():
    """Fetch counters for the build report. Shape varies by runtime; the keys the build
    report pins are always present, because `verify.py` checks for them."""
    s = dict(current().stats())
    for k in ("hits_memo", "hits_disk", "fetches", "failures", "bytes"):
        s.setdefault(k, 0)
    s.setdefault("seconds", 0.0)
    s["runtime"] = current().name
    return s


#: Back-compat for anything that reached into the module global. The build runtime owns
#: the counters now, so this reads through rather than being a second copy of them.
class _Stats(dict):
    def __getitem__(self, k):
        return stats().get(k, 0)

    def get(self, k, default=None):
        return stats().get(k, default)

    def keys(self):
        return stats().keys()

    def items(self):
        return stats().items()

    def __iter__(self):
        return iter(stats())

    def __len__(self):
        return len(stats())

    def __repr__(self):
        return repr(stats())


STATS = _Stats()
