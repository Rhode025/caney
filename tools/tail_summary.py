#!/usr/bin/env python3
"""
Summarise `wrangler tail --format json` output. Diagnostic for #165.

    npx wrangler tail --format json | tee /tmp/tail.log
    python3 tools/tail_summary.py /tmp/tail.log

In a file rather than inlined in the workflow because an indented heredoc inside a YAML
block scalar does not work — bash will not see the terminator and Python will not accept
the indentation. That mistake already broke one workflow in this repo; twice would be
careless.

The question it answers: when a scheduled invocation does not happen, is the scheduler
failing to invoke the worker, or invoking it and dying? Those look identical from outside
and need different fixes. A `scheduled` event in the stream means invoked; its absence
across two cron windows means not invoked.
"""
import collections
import json
import sys


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/tail.log"
    kinds = collections.Counter()
    rows = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                ev = d.get("event") or {}
                if "cron" in ev or ev.get("scheduledTime"):
                    kind = "scheduled"
                elif ev.get("request"):
                    kind = "fetch"
                else:
                    kind = "other"
                kinds[kind] += 1
                rows.append((kind, d.get("outcome"),
                             [str(x)[:200] for x in (d.get("exceptions") or [])],
                             [str(m.get("message"))[:200] for m in (d.get("logs") or [])]))
    except OSError as e:
        print("no tail log at %s (%s)" % (path, e))
        return 2

    print("events seen: %s" % (dict(kinds) or "NONE"))
    for kind, outcome, exc, logs in rows[:30]:
        print("  %-10s outcome=%s" % (kind, outcome))
        for e in exc:
            print("     exception: %s" % e)
        for l in logs[:3]:
            print("     log: %s" % l)

    if not kinds.get("scheduled"):
        print("")
        print("NO SCHEDULED EVENT in this window.")
        print("The scheduler is not invoking the worker at all — this is not a handler")
        print("that runs and fails. A handler that ran would appear here with an outcome,")
        print("and one that threw would appear with an exception.")
    else:
        bad = [r for r in rows if r[0] == "scheduled" and r[1] != "ok"]
        print("")
        print("%d scheduled invocation(s), %d of them not ok." % (kinds["scheduled"], len(bad)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
