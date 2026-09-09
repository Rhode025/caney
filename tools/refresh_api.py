#!/usr/bin/env python3
"""
Rebuild the API's snapshot shards, from outside. §12.

    python3 tools/refresh_api.py [--api URL] [--token TOK] [--shards 3]

The Worker's own cron trigger is registered and does not run, and a self-addressed fetch
from inside the Worker does not land either. An external POST to /internal/rebuild does:
23 of 23 sources in 2.3 seconds, measured. The property that matters is that each call is
a separate invocation with its own CPU and subrequest budget — which is exactly what
`waitUntil` never provided and what the self-fetch failed to achieve.

Run from .github/workflows/refresh.yml every ten minutes, and by hand when needed.
stdlib only.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_API = "https://caney-api.steven-b9c.workers.dev"

#: Cloudflare's bot protection rejects Python-urllib's default agent with a 403 before the
#: request reaches the Worker. Found the hard way.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def token_from_wrangler():
    path = os.path.join(ROOT, "caney-api", "wrangler.toml")
    try:
        with open(path, encoding="utf-8") as fh:
            m = re.search(r'^INTERNAL_TOKEN\s*=\s*"([^"]+)"', fh.read(), re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def call(url, token, timeout=120):
    req = urllib.request.Request(url, data=b"", method="POST",
                                 headers={"X-Caney-Internal": token, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, {"raw": body[:200]}
    except Exception as e:                          # noqa: BLE001
        return 0, {"raw": "%s: %s" % (type(e).__name__, e)}


def health(api):
    req = urllib.request.Request(api.rstrip("/") + "/health", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:                               # noqa: BLE001
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=os.environ.get("CANEY_API", DEFAULT_API))
    ap.add_argument("--token", default=os.environ.get("CANEY_INTERNAL_TOKEN", ""))
    ap.add_argument("--shards", type=int, default=3)
    a = ap.parse_args()

    token = a.token or token_from_wrangler()
    if not token:
        print("no INTERNAL_TOKEN — pass --token or keep it in caney-api/wrangler.toml")
        return 2

    worst = 0
    for n in range(a.shards):
        # Cloudflare returns 1101/1102 — worker threw, resource limits — when a COLD
        # Python isolate cannot import the package and build inside its CPU budget. It is
        # transient by construction: the retry lands on the isolate the first attempt
        # warmed. Measured at roughly one in four cold calls, and essentially never twice.
        for attempt in range(3):
            status, body = call("%s/internal/rebuild?shard=%d"
                                % (a.api.rstrip("/"), n), token)
            if status == 200:
                break
            if attempt < 2:
                import time
                time.sleep(3 * (attempt + 1))
        pf = (body or {}).get("prefetch") or {}
        print("  shard %d -> HTTP %s  %s ok / %s failed of %s%s"
              % (n, status, pf.get("ok"), pf.get("failed"), pf.get("requested"),
                 "" if attempt == 0 else "  (after %d retries)" % attempt))
        if status != 200:
            print("     %s" % json.dumps(body)[:200])
            worst = 1
        elif pf.get("failed"):
            # Not fatal: the affected zones report unknown/stale and the confidence
            # penalty applies. Loud, because a source failing quietly is the thing this
            # whole codebase is built to prevent.
            print("     %d sources failed — those zones will read stale or unknown"
                  % pf["failed"])

    h = health(a.api)
    ages = [m.get("age_s") for m in (h.get("shards") or [])
            if m.get("present")]
    print("\n  zones %s | shard ages %s | tz %s | storage %s"
          % (h.get("zones"), ages, h.get("tz_backend"), h.get("storage")))
    return worst


if __name__ == "__main__":
    sys.exit(main())
