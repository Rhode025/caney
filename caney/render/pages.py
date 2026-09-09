"""
HTML emission. §47, §48.

The ONLY module in the package that knows about markup, and it is deliberately thin: the
page is a shell with an empty result region, and every byte of CSS and JS is a `<link>` or
a `<script type=module src=…>` to a shared file under out/assets/. Nothing is inlined.

That is the §47 non-negotiable, stated as a property the test suite checks: the emitted
page carries no style block and no script body beyond the two-line module bootstrap.
test/planner/test_architecture.py fails the build if one appears.
"""
import json
import os
import time

NAV = [
    ("index.html", "Plan"),
    ("rivers.html", "Rivers"),
    ("roadmap.html", "Roadmap"),
]

HEAD = """<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#0d141c" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#eef2f6" media="(prefers-color-scheme: light)">
<meta name="description" content="{desc}">
<title>{title}</title>
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🌊</text></svg>">
<link rel="apple-touch-icon" href="assets/icon-192.png">
<link rel="stylesheet" href="assets/app.css">
</head><body>
<a class="skip-link" href="#main">Skip to the planner</a>
<div class="app">
"""

TOPNAV = """<nav class="topnav" aria-label="Primary">
  <div class="links">{links}</div>
  <button id="theme" type="button" aria-label="Cycle colour theme">◐ Auto</button>
</nav>
"""

PICKER = """<div id="banner" class="banner warn" hidden role="status"></div>

<div class="eyebrow">Caney · Middle Tennessee</div>
<h1>What do you want to catch?</h1>
<p class="cap">Pick a fish and a time. One answer, with the evidence behind it.</p>

<main id="main" class="pick-panel">
  <section aria-labelledby="h-species">
    <h2 id="h-species" class="sr-only">Species</h2>
    <div class="speciespick" id="species" role="group" aria-label="Target species"></div>
  </section>

  <section aria-labelledby="h-when">
    <h2 id="h-when">When can you fish?</h2>
    <div class="chips" id="times" role="group" aria-label="Time window"></div>
    <div class="custom" id="custom">
      <div class="field"><label for="c-date">Date</label><input id="c-date" type="date"></div>
      <div class="field"><label for="c-start">From</label><input id="c-start" type="time"></div>
      <div class="field"><label for="c-end">To</label><input id="c-end" type="time"></div>
    </div>
    <p class="tiny" id="windowecho" data-clock></p>
  </section>

  <section aria-labelledby="h-craft">
    <h2 id="h-craft">How are you fishing?</h2>
    <div class="chips" id="crafts" role="group" aria-label="Craft"></div>
    <p class="tiny">Craft is a gate, not a preference: a reach you cannot wade is removed
    from a wade plan, never merely ranked lower.</p>
  </section>

  <button class="cta" id="go" type="button" disabled>FIND MY BEST PLAN</button>
  <p class="tiny" id="gohint" role="status">Pick a species to enable this.</p>
</main>

<div id="live" aria-live="polite" class="sr-only"></div>

<div class="plan-panel">
  <div id="result" aria-busy="false" aria-live="polite"></div>
  <div class="chips" style="margin-top:16px">
    <button class="btn primary" id="startplan" type="button" hidden>START THIS PLAN</button>
    <button class="btn" id="ics" type="button">Add alarms to my phone (.ics)</button>
  </div>
</div>

<div class="onwater-panel" id="onwater"></div>
"""

FOOT = """<footer class="foot">
<p id="built">Loading…</p>
<p>Public data only · USACE CWMS · USGS · NOAA/NWS · Open-Meteo · TWRA · OpenStreetMap.
Fishing advice is a heuristic; water numbers are instrument readings and say how old they are.
<b>Verify the release schedule before you get in the water.</b></p>
<p>The river encyclopedia is still here: <a href="rivers.html">every river, in detail →</a></p>
</footer>
</div>
<script type="module">
  import { boot } from "./assets/planner/app.js";
  boot();
</script>
</body></html>
"""


def write_pages(out_dir, data, now=None):
    now = now or time.time()
    links = "".join('<a href="%s"%s>%s</a>' % (href, ' class="on"' if href == "index.html" else "", label)
                    for href, label in NAV)
    html = (HEAD.format(title="Caney — what do you want to catch?",
                        desc=("Species-first fishing planner for Middle Tennessee. Pick a "
                              "fish and a time; get one evidence-backed plan with the water, "
                              "the weather, the timeline and the sources behind it."))
            + TOPNAV.format(links=links)
            + PICKER
            + FOOT)
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)

    # A stable deep link for the result view. Same shell — the planner is one page and the
    # state lives in the hash, so this never becomes a second implementation.
    with open(os.path.join(out_dir, "plan.html"), "w", encoding="utf-8") as fh:
        fh.write(html.replace('<a href="index.html" class="on">',
                              '<a href="index.html" class="on">'))

    from .icons import write as write_icons
    write_icons(os.path.join(out_dir, "assets"))
    return path
