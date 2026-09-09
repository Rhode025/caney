# Geographic confidence

The failure this exists to prevent: telling somebody to *"start on the downstream seam
immediately below the ledge"* when the only thing we actually know is that an agency
described a twelve-mile reach as good striped-bass water.

Both are useful facts. They are not the same fact, and prose that treats them alike is the
most expensive kind of wrong — it sends a person to a specific place that nothing verified.

---

## 1. Evidence levels (§29)

`caney/domain/location.py`. Ordered strongest first; the priors are **initial priors, not
calibrated measurements**, and the ordering is the load-bearing part.

| level | prior | what it means |
|---|---|---|
| `VERIFIED_ACCESS` | 0.98 | published coordinates from the agency that owns the access |
| `VERIFIED_ZONE` | 0.95 | the reach is mapped and checked against a source |
| `AGENCY_DESCRIBED_REACH` | 0.85 | an agency describes the stretch. It named a reach, not a spot |
| `MODELED_HABITAT` | 0.65 | inferred from current, structure and habitat. Nobody has stood here |
| `UNVERIFIED_CANDIDATE` | 0.40 | plausible from the map alone. A lead |

A zone's `LocationConfidence` has three parts, weighted:

```
access 0.40   +   reach 0.35   +   holding_water 0.25
```

Access is weighted highest because it is where you physically go. Holding water is the
tactical claim and the part we are usually least sure of — which is exactly why it must not
be silently averaged away.

**Derivation is capped.** An unverified reach cannot support a modelled-habitat claim about
a specific seam inside it: the model would be inferring structure on water we have not
confirmed the shape of. `derived_holding_water()` enforces that, and it is what pushes weak
zones into hedged language.

---

## 2. It costs the candidate something (§60)

Window utility multiplies by `L = 0.75 + 0.25 × location_confidence`. So:

```
score 92, location confidence 0.35   →   utility 72.7
score 87, location confidence 0.95   →   utility 81.1     ← wins
```

A beautifully-scoring reach nobody has stood in loses to a slightly worse one that has been
verified. The penalty is deliberately **bounded** — it cannot flip an enormous gap, because
a 99 on unverified water really is better than a 70 on a mapped ramp.

---

## 3. The language changes with the evidence (§30)

`phrase_for(level, …)`:

| tactical level | what the plan says |
|---|---|
| `precise` | *"The boil and both seams beside it."* |
| `corridor` | *"Work the tailrace-boil corridor between the dam and the Caney mouth."* |
| `hedged` | *"This reach is supported by species and habitat evidence, but the exact holding water has not been field verified — cover it and read the water yourself."* |

`test/verify.py` asserts the last one structurally: **a zone whose tactical level is
`hedged` must not emit precise tactical language**, for any species, in any build.

---

## 4. The map says it too (§32)

`web/planner/map.js` styles geometry by evidence level, and the legend names the
distinction:

| level | rendering |
|---|---|
| verified access | solid pin, heavy |
| verified reach | solid line |
| agency-described reach | **dashed** corridor |
| modelled habitat | **dotted** area, low opacity |
| unverified candidate | faint dotted area |

Multi-zone plans are numbered `1 → 2 → 3` to match the itinerary (§73).

An unverified access point is drawn hollow and dashed. Solid means somebody published the
coordinate.

---

## 5. Current state of the registry

22 zones. Verified geography is concentrated where the repo has done the work:

| zone | access | reach | score |
|---|---|---|---|
| `caney_upper`, `caney_middle` | verified (TWRA layer) | verified (OSM + guide-verified mfd) | 88.7 |
| `cordell_tailwater` | verified (USACE LRN) | verified | 88.7 |
| `carthage_confluence` | verified (USACE LRN) | agency-described (TWRA) | 85.2 |
| `caney_lower` | verified reach | agency-described | 84.0 |
| the reservoir and creek-arm zones | unverified | agency-described | 62.0 |
| everything else | unverified | unverified | 40.0 |

The 40s are honest, and they cost those zones real utility. **Verifying access coordinates
against the TWRA Boating & Fishing Access layer is the highest-value data work left in this
repo** — it would move a dozen zones from 40 to 85+ and change rankings.

---

## 6. Upgrading a zone (§33)

Every zone carries a `Verification` record:

```python
verification=Verification(
    status="desk_verified",          # unverified | desk_verified | field_verified
    verified_by="repo",
    verified_at="2026-09-09",
    source="TWRA Boating & Fishing Access layer + OSM centreline",
    notes="Happy Hollow and Betty's Island are TWRA published ramp coordinates.")
```

To upgrade one:

1. Get the coordinate from an authority, or stand on it.
2. Set the `AccessPoint`'s `evidence` to `VERIFIED_ACCESS` and `verified=True`, with the
   `source` naming who verified it.
3. Set the zone's `LocationConfidence` in `_LOCATION` and fill in the `Verification`.
4. `python3 test/planner/run.py` — `test_zones` checks that a zone claiming verification
   has coordinates and cites a source.

Nothing requires human verification to operate. The system is designed to work honestly
with weak geography and to get better as the geography improves.

---

## 7. Zone kinds (§36)

Not every fishing opportunity is a river reach:

```
river_reach · tailrace · confluence · reservoir_arm · creek_arm · backwater
flat · point · shoal · ledge · bank · riprap · grass_bed
```

`ZoneKind.STILLWATER` marks the ones whose fishing is driven by cover and level rather than
current — and `segments.technique_for` reads it, so a creek arm gets a cover presentation
rather than a seam presentation.

This is what gave largemouth somewhere to be. See `docs/SCORING.md` §Species coverage.
