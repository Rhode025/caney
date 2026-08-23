import json, html, re, subprocess, sys, time
R = json.load(open("/Users/stevenrhodes/caney/roadmap.json"))

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
              "Docs & system":"8a6524"}
PRI_COLOR  = {"P0":"a62b17","P1":"b8791a","P2":"1f6fb2","P3":"6b7b8a"}
EFF_COLOR  = {"S":"e2e9ef","M":"cbd7e2","L":"b3c4d4"}

if "--labels" in sys.argv:
    for e,c in EPIC_COLOR.items(): sh(["gh","label","create",f"epic:{e}","--color",c,"--force","--description",f"Roadmap epic — {e}"])
    for p,c in PRI_COLOR.items():  sh(["gh","label","create",p,"--color",c,"--force","--description",f"Roadmap priority {p}"])
    for e,c in EFF_COLOR.items():  sh(["gh","label","create",f"effort:{e}","--color",c,"--force","--description",f"Nominal effort {e}"])
    sh(["gh","label","create","roadmap","--color","0a5ec2","--force","--description","From the 2026-08-23 QC & UX audit"])
    print("labels ready"); sys.exit()

created = []
for t in R["tickets"]:
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
json.dump(R, open("/Users/stevenrhodes/caney/roadmap.json","w"), indent=1)
print(f'\ncreated {sum(1 for c in created if c["issue"])}/{len(created)} issues; roadmap.json updated with issue numbers')
