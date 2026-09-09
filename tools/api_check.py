#!/usr/bin/env python3
"""
Check the deployed API. §72.

    python3 tools/api_check.py                 health + shard freshness
    python3 tools/api_check.py --plan          also run one plan end to end
    python3 tools/api_check.py --quiet-shards  one line, for watching in a loop

Exists because I hand-rolled this probe about fifteen times during the 3.0 deployment and
got it subtly wrong twice. Two details it gets right that an ad-hoc curl does not:

  * IT RETRIES. Cloudflare returns 1101/1102 — worker threw, resource limits — when a cold
    Python isolate cannot finish inside its CPU budget, roughly one cold call in four.
    A check without a retry reports a healthy service as down, which is exactly what
    happened during a final verification pass.
  * IT SENDS A BROWSER USER-AGENT. Cloudflare's bot protection answers Python-urllib's
    default with 403 before the request reaches the Worker, so the failure looks like an
    auth problem and is not one.

stdlib only.
"""
import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API = "https://caney-api.steven-b9c.workers.dev"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
RETRIES = 3


def call(url, body=None, timeout=120):
    """(status, obj). Retries 5xx and network errors; a 4xx is returned as-is."""
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(RETRIES):
        req = urllib.request.Request(
            url, data=data, method="POST" if data is not None else "GET",
            headers={"User-Agent": UA, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code < 500 or attempt == RETRIES - 1:
                try:
                    return e.code, json.loads(raw)
                except ValueError:
                    return e.code, {"raw": raw[:200]}
        except Exception:                            # noqa: BLE001
            if attempt == RETRIES - 1:
                return 0, {"raw": "unreachable"}
        time.sleep(2 * (attempt + 1))
    return 0, {"raw": "unreachable"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--plan", action="store_true", help="also run one plan end to end")
    ap.add_argument("--quiet-shards", action="store_true", help="one line, for loops")
    a = ap.parse_args()

    st, h = call(a.api.rstrip("/") + "/health")
    if st != 200:
        print("health %s: %s" % (st, json.dumps(h)[:160]))
        return 1

    shards = h.get("shards") or []
    ages = [round(x.get("age_s") or -1) for x in shards if x.get("present")]
    last = h.get("last_build_start") or {}

    if a.quiet_shards:
        print("  %s  last why=%-5s age=%-5s  shard ages=%s"
              % (time.strftime("%H:%M:%S"), last.get("why"),
                 round(last.get("age_s") or -1), ages))
        return 0

    print("health: zones=%s  tz=%s  storage=%s  research=%s"
          % (h.get("zones"), h.get("tz_backend"), h.get("storage"),
             h.get("research_status")))
    print("last build: why=%s  %ss ago" % (last.get("why"), round(last.get("age_s") or -1)))
    bad = 0
    for x in shards:
        pf = x.get("prefetch") or {}
        failed = pf.get("failed") or 0
        bad += failed
        print("  shard %s  age=%-7s %s ok / %s failed of %s"
              % (x.get("shard"), round(x.get("age_s") or -1), pf.get("ok"),
                 failed, pf.get("requested")))
    if bad:
        print("  %d sources failed — those zones read stale or unknown, and the "
              "confidence penalty applies" % bad)

    if a.plan:
        d = dt.datetime.now().astimezone() + dt.timedelta(days=1)
        lo = d.replace(hour=6, minute=0, second=0, microsecond=0)
        hi = d.replace(hour=12, minute=0, second=0, microsecond=0)
        t0 = time.time()
        st, env = call(a.api.rstrip("/") + "/api/v3/plan", {
            "species": "striped_bass", "craft": "power", "method": "either",
            "availability": {"depart_after": lo.isoformat(), "return_by": hi.isoformat()},
            "origin": {"lat": 36.1627, "lon": -86.7816}})
        el = time.time() - t0
        if st != 200:
            print("\nplan %s in %.1fs: %s" % (st, el, json.dumps(env)[:180]))
            return 1
        r = env["recommendation"]
        s = (env.get("logistics") or {}).get("summary") or {}
        fmt = lambda t: (dt.datetime.fromtimestamp(t).strftime("%-I:%M %p")   # noqa: E731
                         if t else "—")
        print("\nplan 200 in %.1fs -> %s" % (el, r["location"]["name"]))
        print("  leave %s  fish %s-%s  home %s  %s confidence"
              % (fmt(s.get("leave")), fmt(s.get("fish_start")), fmt(s.get("fish_end")),
                 fmt(s.get("home")), env["confidence_label"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
