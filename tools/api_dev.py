#!/usr/bin/env python3
"""
The Caney API, served locally. §5, §98.

    python3 tools/api_dev.py [--port 8787] [--fast]

Same handler, same router and same planner the Cloudflare Worker runs — only the
transport differs. That is what makes it useful for more than convenience: the shadow
comparison in §5 and the API contract tests in §86 run against this, so a difference
between the two deployments is a difference in the Worker's plumbing and never in the
model.

Snapshots are built once at startup and reused, because the source layer's TTLs already
handle freshness and rebuilding per request would hammer four public agencies during a
test run. `--fast` skips live research entirely.

stdlib only.
"""
import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from caney.api import router                              # noqa: E402
from caney.api.handler import Context                     # noqa: E402
from caney.api.storage import MemoryStore                 # noqa: E402
from caney.domain.planning import ResearchStatus          # noqa: E402
from caney.research.corpus import claims_for              # noqa: E402
from caney.sources.http import stats as source_stats      # noqa: E402
from caney.sources.snapshots import build_all             # noqa: E402
from caney.zones.registry import all_zones                # noqa: E402

STATE = {"ctx": None, "built_at": 0.0}
REBUILD_AFTER = 900.0


def build_context(store, fast=False):
    now = time.time()
    snaps, book = build_all(now=now, horizon_days=3)
    import datetime as dt
    from caney.tz import zone as tzf
    month = dt.datetime.fromtimestamp(now, tzf()).month
    claims = {}
    for z in all_zones():
        for sp in z.species_profiles:
            claims[(z.id, sp)] = claims_for(sp, month=month, zone_ids=[z.id])
    return Context(snapshots=snaps, book=book, claims_by_zone=claims, store=store,
                   research_status=(ResearchStatus.DISABLED if fast
                                    else ResearchStatus.CACHED),
                   source_stats=source_stats(), now=now)


def context(store, fast):
    now = time.time()
    if STATE["ctx"] is None or now - STATE["built_at"] > REBUILD_AFTER:
        STATE["ctx"] = build_context(store, fast)
        STATE["built_at"] = now
    STATE["ctx"].now = now
    return STATE["ctx"]


class Handler(BaseHTTPRequestHandler):
    server_version = "caney-api-dev"
    store = None
    fast = False
    origins = ("*",)

    def _send(self, status, obj, origin=""):
        raw = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in router.cors_headers(origin, self.origins).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in router.cors_headers(self.headers.get("Origin", ""),
                                        self.origins).items():
            self.send_header(k, v)
        self.end_headers()

    def _handle(self, body=None):
        origin = self.headers.get("Origin", "")
        try:
            status, obj = router.route(self.command, self.path.split("?")[0], body,
                                       context(self.store, self.fast))
        except Exception as e:                          # noqa: BLE001
            import traceback
            traceback.print_exc()
            status, obj = 500, {"error": {"message": "%s: %s" % (type(e).__name__, e),
                                          "status": 500, "code": "internal_error"}}
        self._send(status, obj, origin)

    do_GET = do_HEAD = lambda self: self._handle()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError as e:
            return self._send(400, {"error": {"message": "invalid JSON: %s" % e,
                                              "status": 400, "code": "bad_request"}},
                              self.headers.get("Origin", ""))
        self._handle(body)

    do_PATCH = do_POST

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.address_string(), fmt % args))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--fast", action="store_true", help="skip live research")
    a = ap.parse_args()

    Handler.store = MemoryStore()
    Handler.fast = a.fast
    print("building snapshots…", file=sys.stderr)
    context(Handler.store, a.fast)
    print("caney api on http://%s:%d%s/  (health: /health)"
          % (a.host, a.port, router.PREFIX), file=sys.stderr)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
