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


def _objects(text):
    """Yield top-level JSON objects from a stream that may be PRETTY-PRINTED.

    `wrangler tail --format json` emits multi-line objects, not one per line. The first
    version of this read line by line, found nothing that started with "{", and reported
    "events seen: NONE" — while the raw log plainly contained `"outcome": "exception"`.
    That nearly produced the wrong conclusion for the third time in this investigation: a
    broken parser and an idle scheduler look identical in a summary.

    Brace counting, skipping braces inside strings.
    """
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                chunk = text[start:i + 1]
                try:
                    yield json.loads(chunk)
                except ValueError:
                    pass
                start = None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/tail.log"
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError as e:
        print("no tail log at %s (%s)" % (path, e))
        return 2

    kinds = collections.Counter()
    outcomes = collections.Counter()
    errors = []
    for d in _objects(raw):
        if "outcome" not in d and "event" not in d:
            continue
        ev = d.get("event") or {}
        if "cron" in ev or ev.get("scheduledTime"):
            kind = "scheduled"
        elif ev.get("request"):
            kind = "fetch"
        else:
            kind = "other"
        kinds[kind] += 1
        outcomes[d.get("outcome") or "?"] += 1
        msgs = []
        for m in (d.get("logs") or []):
            for part in (m.get("message") or []):
                msgs.append(str(part))
        for x in (d.get("exceptions") or []):
            msgs.append(str(x))
        # The useful line in a Python traceback is the one naming the error.
        for m in msgs:
            if ("Error" in m or "Exception" in m) and "Traceback" not in m:
                errors.append((kind, m[:300]))

    print("events seen: %s" % (dict(kinds) or "NONE"))
    print("outcomes:    %s" % (dict(outcomes) or "NONE"))
    if errors:
        print("")
        print("errors (deduplicated):")
        seen = set()
        for kind, m in errors:
            key = m[:120]
            if key in seen:
                continue
            seen.add(key)
            print("  [%s] %s" % (kind, m))

    if not kinds:
        print("")
        print("NOTHING PARSED. Either no invocations occurred in this window, or the")
        print("stream format changed — check the raw log before concluding the former.")
    elif not kinds.get("scheduled"):
        print("")
        print("%d invocation(s), NONE of them scheduled. The cron is not invoking the"
              % sum(kinds.values()))
        print("worker in this window.")
    return 0
if __name__ == "__main__":
    sys.exit(main())
