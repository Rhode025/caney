#!/usr/bin/env python3
"""
Is the deployed API running the code in this repo? §72.

    python3 tools/check_deployed.py [--strict]

The planner package is VENDORED into the Worker at deploy time, and deploy.yml publishes
Pages only — the Worker needs a separate `workers.yml -f action=deploy-api` dispatch. So a
change under caney/ lives in master and not in production until somebody remembers, and
nothing caught that. It happened: the pre-dawn horizon fix was committed, green in CI, and
absent from the live API for twenty minutes.

`--strict` exits non-zero on drift. Without it, it reports and exits 0, which is the right
default for a post-deploy step that should not fail a good Pages publish.

stdlib only.
"""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_API = "https://caney-api.steven-b9c.workers.dev"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

#: Changes under these paths reach production only through a Worker deploy.
WORKER_PATHS = ("caney/", "caney-api/")


def head_sha():
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def changed_since(sha):
    """Files under WORKER_PATHS changed between `sha` and HEAD."""
    if not sha or sha == "unknown":
        return None
    r = subprocess.run(["git", "diff", "--name-only", sha, "HEAD"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return [f for f in r.stdout.split() if f.startswith(WORKER_PATHS)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    try:
        req = urllib.request.Request(a.api.rstrip("/") + "/health",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            h = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:                          # noqa: BLE001
        print("could not reach %s: %s" % (a.api, e))
        return 1 if a.strict else 0

    live = str(h.get("build_sha") or "unknown")
    here = head_sha()
    print("deployed: %s" % live[:12])
    print("repo HEAD: %s" % here[:12])

    if live == "unknown":
        print("the worker does not report a build SHA — redeploy to start stamping it")
        return 0
    if live.startswith(here[:12]) or here.startswith(live[:12]):
        print("in sync")
        return 0

    drifted = changed_since(live)
    if drifted is None:
        print("DRIFT: the deployed commit is not in this clone, so the diff cannot be read")
        return 1 if a.strict else 0
    if not drifted:
        print("the deployed commit differs but nothing under %s changed — "
              "a Worker deploy is not needed" % ", ".join(WORKER_PATHS))
        return 0
    print("DRIFT: %d file(s) the Worker serves have changed since it was deployed:"
          % len(drifted))
    for f in drifted[:12]:
        print("   %s" % f)
    print("")
    print("   gh workflow run workers.yml -f action=deploy-api")
    return 1 if a.strict else 0


if __name__ == "__main__":
    sys.exit(main())
