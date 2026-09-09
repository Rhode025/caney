"""
Create a GitHub issue for every roadmap ticket that does not have one, and write the new
issue numbers back into roadmap.json.

    python3 test/tools/make_issues.py --dry-run     list what WOULD be created
    python3 test/tools/make_issues.py --create      actually create them

THIS SCRIPT WRITES TO A LIVE REPOSITORY. It used to do that on a bare `python3
make_issues.py` with no confirmation and no argument parsing at all, which meant that
running it with `--help` — expecting usage text — silently created fifty-two issues and
rewrote roadmap.json. It now refuses to do anything without an explicit `--create`, prints
a dry run by default, and shows what it is about to do before it does it.
"""
import json, html, re, subprocess, sys, time
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROADMAP = os.path.join(ROOT, "roadmap.json")

ARGS = set(sys.argv[1:])
CREATE = "--create" in ARGS
if ARGS - {"--dry-run", "--create", "--labels"}:
    print(__doc__)
    raise SystemExit(0 if ({"--help", "-h"} & ARGS) else 2)

_r = subprocess.run(["git", "-C", ROOT, "remote", "get-url", "origin"],
                    capture_output=True, text=True)
REPO_HINT = (_r.stdout.strip() or "the configured origin") if _r.returncode == 0 \
    else "the configured origin"

R = json.load(open(ROADMAP))

def md(s):
    s = re.sub(r"<code>(.*?)</code>", r"`\1`", s)
    s = re.sub(r"<em>(.*?)</em>", r"*\1*", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)

def sh(args, check=True):
    p = subprocess.run(args, capture_output=True, text=True)
    if check and p.returncode: print("  !", " ".join(args[:4]), p.stderr.strip()[:150])
    return p

EPIC_COLOR = {"Freshness":"0a5ec2","Offline":"1e7a45","Accessibility":"8b6cef",
              "Wayfinding":"c2570a","Build & CI":"3a5a8c","Model validation":"0f766e",
              "Docs & system":"8a6524","RiverGuide":"7a3fa0","Research":"0f6b6b"}

# An epic with no colour here has no label, and `gh issue create` then fails on THAT ONE
# issue with a one-line warning that is easy to miss in a run of fifty. Two epics had been
# missing for a while before anyone noticed. Check up front instead.
_missing = sorted({t["epic"] for t in R["tickets"]} - set(EPIC_COLOR))
if _missing:
    print("STOP: these epics have no label colour in EPIC_COLOR: %s" % ", ".join(_missing))
    print("Add them, then re-run with --labels before --create.")
    sys.exit(2)
PRI_COLOR  = {"P0":"a62b17","P1":"b8791a","P2":"1f6fb2","P3":"6b7b8a"}
EFF_COLOR  = {"S":"e2e9ef","M":"cbd7e2","L":"b3c4d4"}

if "--labels" in sys.argv:
    for e,c in EPIC_COLOR.items(): sh(["gh","label","create",f"epic:{e}","--color",c,"--force","--description",f"Roadmap epic — {e}"])
    for p,c in PRI_COLOR.items():  sh(["gh","label","create",p,"--color",c,"--force","--description",f"Roadmap priority {p}"])
    for e,c in EFF_COLOR.items():  sh(["gh","label","create",f"effort:{e}","--color",c,"--force","--description",f"Nominal effort {e}"])
    sh(["gh","label","create","roadmap","--color","0a5ec2","--force","--description","From the 2026-08-23 QC & UX audit"])
    print("labels ready"); sys.exit()

# ONLY tickets that do not already have an issue. The original loop walked every ticket,
# so any second run duplicated all forty-three that already had one. Combined with there
# being no confirmation gate, one accidental invocation created a hundred-odd duplicates.
todo = [t for t in R["tickets"] if not t.get("issue")]
print("%d of %d tickets already have an issue; %d would be created."
      % (len(R["tickets"]) - len(todo), len(R["tickets"]), len(todo)))
for t in todo:
    print("  S%-3s %-12s %s" % (t["sprint"], t["key"], t["title"][:58]))
if not CREATE:
    print("\nDRY RUN — nothing was created, roadmap.json was not written.\n"
          "Re-run with --create to do it for real.")
    sys.exit(0)
if not todo:
    print("Nothing to create."); sys.exit(0)
print("\nCreating %d issues in %s…" % (len(todo), REPO_HINT))

created = []
for t in todo:
    title = f'S{t["sprint"]} · {t["key"]} — {t["title"]}'
    body = (
        f'**Sprint {t["sprint"]} · {t["epic"]} · {t["priority"]} · effort {t["effort"]}**\n\n'
        f'## Evidence\n\n{md(t["evidence"])}\n\n'
        f'## Done means\n\n' + "\n".join("- " + md(a) for a in t["done"]) + "\n\n"
        f'---\n<sub>From the QC & UX audit of {R["generated"]}. '
        f'Source of truth: `roadmap.json`. Board: `/roadmap.html` on the live site.</sub>\n'
    )
    labels = ["roadmap", f'epic:{t["epic"]}', t["priority"], f'effort:{t["effort"]}']
    p = sh(["gh","issue","create","--title",title,"--body",body,"--label",",".join(labels)])
    url = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
    num = url.rsplit("/",1)[-1] if url else None
    created.append({"sprint":t["sprint"], "key":t["key"], "issue":int(num) if num and num.isdigit() else None, "url":url})
    print(f'  #{num or "??"}  S{t["sprint"]:<2} {t["key"]}')
    time.sleep(0.35)

# write the issue numbers back into roadmap.json so page + board can link out
by = {c["key"]: c for c in created}
for t in R["tickets"]:
    c = by.get(t["key"])
    if c: t["issue"] = c["issue"]; t["issue_url"] = c["url"]
R["repo"] = "Rhode025/caney"
if CREATE:
    json.dump(R, open(ROADMAP, "w"), indent=1)
else:
    print("\nDRY RUN — nothing was created and roadmap.json was not written.\n"
          "Re-run with --create to do it for real.")
print(f'\ncreated {sum(1 for c in created if c["issue"])}/{len(created)} issues; roadmap.json updated with issue numbers')
