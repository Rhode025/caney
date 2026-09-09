#!/usr/bin/env python3
"""
Fit the driving-estimate constants in caney/routing/provider.py. §17.

CLAUDE.md: "Calibration constants carry their provenance in the comment above them."
This is that provenance, and it is re-runnable:

    python3 analysis/road_factor.py

The calibration set is the `drive` string on every FishingZone — "~70 min · east of
Nashville", "~2¼ h · Burkesville KY" — written when each zone was researched, against a
real map, from one origin (Nashville). Twenty-two points is small and they are rounded to
five or fifteen minutes, so this fit settles the SHAPE of the estimate, not a precise
travel-time model. That is the right ambition: §17 says an estimate must be labelled an
estimate, and a two-parameter fit over rounded map lookups is exactly that.

The model is deliberately the simplest thing that can work:

    minutes = OVERHEAD_MINUTES + straight_line_miles * MINUTES_PER_STRAIGHT_MILE

Two parameters, because two is all this data identifies. Writing it as a road-sinuosity
factor times an average speed looks more physical and is not: only the ratio appears in
the residuals, so any (factor, mph) pair on one line fits equally well. The first run of
this fit, with speed pinned at 46 mph, duly reported a road factor of 0.86 — roads
shorter than straight lines. Reporting two numbers where the data supports one is the
false precision §17 exists to prevent.

Not part of the build. stdlib only.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from caney.routing.provider import haversine_miles   # noqa: E402
from caney.zones.registry import all_zones                    # noqa: E402

#: Where the `drive` strings were measured from.
NASHVILLE = (36.1627, -86.7816)

_FRACTION = {"¼": 0.25, "½": 0.5, "¾": 0.75}


def parse_drive(s):
    """'~70 min' -> 70.0 ; '~2¼ h' -> 135.0 ; anything else -> None."""
    if not s:
        return None
    s = s.split("·")[0].strip().lstrip("~").strip()
    m = re.match(r"^(\d+)\s*min", s)
    if m:
        return float(m.group(1))
    m = re.match(r"^(\d+)\s*([¼½¾]?)\s*h", s)
    if m:
        return (float(m.group(1)) + _FRACTION.get(m.group(2), 0.0)) * 60.0
    return None


def sample():
    rows = []
    for z in all_zones():
        minutes = parse_drive(z.drive)
        acc = [a for a in z.access if a.lat is not None and a.lon is not None]
        if minutes is None or not acc:
            continue
        # The access a car would actually be aimed at: the first listed is the primary.
        miles = haversine_miles(NASHVILLE, (acc[0].lat, acc[0].lon))
        rows.append((z.id, miles, minutes))
    return rows


def fit(rows):
    """Ordinary least squares. minutes = intercept + slope * straight_line_miles."""
    n = len(rows)
    sx = sum(r[1] for r in rows)
    sy = sum(r[2] for r in rows)
    sxx = sum(r[1] * r[1] for r in rows)
    sxy = sum(r[1] * r[2] for r in rows)
    denom = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return intercept, slope


def report():
    rows = sample()
    overhead, slope = fit(rows)
    print("calibration points: %d   origin: Nashville %s\n" % (len(rows), NASHVILLE))
    print("  %-26s %7s %8s %9s %8s" % ("zone", "mi", "stated", "fitted", "err"))
    errs = []
    for zid, miles, stated in sorted(rows, key=lambda r: r[1]):
        pred = overhead + miles * slope
        errs.append(pred - stated)
        print("  %-26s %7.1f %8.0f %9.0f %+8.0f" % (zid, miles, stated, pred, pred - stated))
    mae = sum(abs(e) for e in errs) / len(errs)
    rmse = (sum(e * e for e in errs) / len(errs)) ** 0.5
    bias = sum(errs) / len(errs)
    print("\n  MINUTES_PER_STRAIGHT_MILE  %.3f" % slope)
    print("  OVERHEAD_MINUTES           %.1f" % overhead)
    print("  (illustrative only: %.2f road factor implies %.0f mph average)"
          % (1.25, 1.25 * 60.0 / slope))
    print("  MAE %.1f min   RMSE %.1f min   bias %+.1f min" % (mae, rmse, bias))
    print("\n  worst: %s" % ", ".join(
        "%s %+.0f" % (r[0], overhead + r[1] * slope - r[2])
        for r in sorted(rows, key=lambda r: -abs(overhead + r[1] * slope - r[2]))[:3]))
    return overhead, slope, mae


if __name__ == "__main__":
    report()
