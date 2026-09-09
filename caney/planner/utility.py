"""
The window utility function. §6, §7, §14.

WHY THIS EXISTS. Caney 2.0 ranked a candidate by the MEAN of its hourly scores across the
user's whole availability. That is the wrong objective, and §3 gives the counterexample:

    Candidate A   6:30  96   7:00  95   7:30  92   8:00  63 …  9:30  52
    Candidate B   6:30  77   7:00  77   7:30  78   8:00  76 …  9:30  75

A mean prefers B. But the right answer is "fish A hard from 6:30 to 7:45, then move,
switch, or stop." The user's availability is a CONSTRAINT, not a requirement to fish every
minute of it.

So utility is computed over a WINDOW, and the formula is deliberately small enough to state
in full:

    U  =  Q × D × C × L  −  transition  −  staleness

    Q  quality, 0..100, peak-weighted:
         Q = 0.50·peak + 0.28·cubic_mean + 0.22·floor
         peak       mean of the top third of the samples (at least one)
         cubic_mean 100·(mean((s/100)³))^(1/3) — a power mean, so a 95 counts for more
                    than a 70 in a way an arithmetic mean never does (§7)
         floor      the worst sample in the window. This is the term that stops a great
                    hour being averaged together with three dead ones and still winning:
                    extending A's window into its 52 costs it 0.22 × 43 points.

    D  duration factor, 0.72 … 1.00:
         D = 0.72 + 0.28 · min(1, minutes / IDEAL_MINUTES)
         × SHORT_PENALTY if minutes < the species minimum practical duration (§5)
         It SATURATES at IDEAL. Fishing longer than about two and a half hours does not
         keep buying utility, which is what stops the optimiser from padding a peak window
         with mediocre hours to farm duration.

    C  forecast-confidence factor  = 0.70 + 0.30 · confidence/100
    L  location-confidence factor  = 0.75 + 0.25 · location_confidence  (§28, §60)

    transition   minutes of travel × TRANSITION_COST_PER_MIN, charged to the itinerary
    staleness    a flat penalty when the driving observations are stale rather than known

WHAT THE CONSTANTS ARE. Priors, chosen so the four mandatory regression scenarios (§57,
§58, §59, §60) come out the way the brief says they must, and so that the ordering is
stable under small perturbations. Nothing here is calibrated against outcomes yet; the
trip log and the scoreboard exist to change that. Every constant is published to the
browser in `data.json` so `web/planner/utility.js` computes the identical number, and
`test/planner/test_parity.mjs` fails on a disagreement larger than 0.05.
"""
import math

#: Quality mixture. Sums to 1.0.
W_PEAK = 0.50
W_CUBIC = 0.28
W_FLOOR = 0.22

#: Duration.
IDEAL_MINUTES = 150.0
D_BASE = 0.72
D_SPAN = 0.28
SHORT_PENALTY = 0.35        # applied below the species minimum practical duration

#: Confidence factors.
C_BASE, C_SPAN = 0.70, 0.30
L_BASE, L_SPAN = 0.75, 0.25

#: Itinerary costs and credits.
TRANSITION_COST_PER_MIN = 0.22      # utility points per minute of travel
IDLE_COST_FACTOR = 0.15             # waiting is cheaper than travelling, not free
COMPLEXITY_PENALTY = 1.5            # per extra zone beyond the first (§14)
STALE_PENALTY = 4.0                 # flat, when the driving water reading is stale

#: Credit for a day that contains SEVERAL genuinely good windows rather than one.
#:
#: This exists because the duration factor deliberately saturates: a bite window is a bite
#: window, and letting raw minutes keep paying is exactly what lets the optimiser pad a
#: peak with dead hours (§57). But a day that gets ninety minutes at 95 AND two hours at
#: 90 really is better than either alone, and without this the optimiser could never say
#: so. It is scaled by the mean quality of the segments, so stitching a good window to a
#: bad one earns nothing.
BREADTH_BONUS = 6.0

#: The sampling grid a window is evaluated on. Both engines use it.
SAMPLE_MINUTES = 15

#: §5 — minimum practical durations, in minutes. Config, per species.
MIN_DURATION = {
    "striped_bass": 60,
    "smallmouth": 75,
    "largemouth": 75,
    "trout": 60,
}
DEFAULT_MIN_DURATION = 60

#: A window shorter than the minimum is allowed only if it is exceptional (§5).
EXCEPTIONAL_QUALITY = 88.0


def min_duration(species):
    return MIN_DURATION.get(species, DEFAULT_MIN_DURATION)


def quality(samples):
    """Peak-weighted quality of a list of 0..100 scores."""
    xs = [float(s) for s in samples if s is not None]
    if not xs:
        return 0.0
    n = max(1, len(xs) // 3)
    peak = sum(sorted(xs, reverse=True)[:n]) / n
    cubic = 100.0 * (sum((x / 100.0) ** 3 for x in xs) / len(xs)) ** (1.0 / 3.0)
    floor = min(xs)
    return round(W_PEAK * peak + W_CUBIC * cubic + W_FLOOR * floor, 4)


def duration_factor(minutes, species):
    """Saturating, with a hard penalty below the species minimum practical duration."""
    m = max(0.0, float(minutes))
    d = D_BASE + D_SPAN * min(1.0, m / IDEAL_MINUTES)
    if m < min_duration(species):
        d *= SHORT_PENALTY
    return round(d, 6)


def confidence_factor(confidence):
    return round(C_BASE + C_SPAN * max(0.0, min(100.0, float(confidence))) / 100.0, 6)


def location_factor(location_confidence):
    """`location_confidence` is 0..1 (LocationConfidence.value)."""
    return round(L_BASE + L_SPAN * max(0.0, min(1.0, float(location_confidence))), 6)


def window_utility(samples, minutes, species, confidence, location_confidence,
                   transition_minutes=0.0, stale=False):
    """The published formula, in one place. Returns (utility, parts)."""
    q = quality(samples)
    d = duration_factor(minutes, species)
    c = confidence_factor(confidence)
    l = location_factor(location_confidence)
    transition = TRANSITION_COST_PER_MIN * max(0.0, float(transition_minutes))
    stale_pen = STALE_PENALTY if stale else 0.0
    u = q * d * c * l - transition - stale_pen
    return round(u, 4), {
        "quality": q, "duration_factor": d, "confidence_factor": c,
        "location_factor": l, "transition": round(transition, 4),
        "staleness": stale_pen, "utility": round(u, 4),
    }


def sample_series(series_values, t0, step, start, end, sample_minutes=SAMPLE_MINUTES):
    """Sample an hourly score series across [start, end) by linear interpolation.

    Deterministic and trivially mirrorable: the grid is start, start+15min, … and each
    point is interpolated between the two bracketing hourly values. Both engines must walk
    the identical grid, so this is written to be boring rather than clever.
    """
    out = []
    if end <= start or not series_values:
        return out
    stepsec = sample_minutes * 60
    t = float(start)
    n = len(series_values)
    while t < end - 1:
        pos = (t - t0) / float(step)
        i = int(math.floor(pos))
        frac = pos - i
        if i < 0:
            v = series_values[0]
        elif i >= n - 1:
            v = series_values[n - 1]
        else:
            a, b = series_values[i], series_values[i + 1]
            v = a + (b - a) * frac
        out.append(round(float(v), 6))
        t += stepsec
    return out


def constants():
    """Published to the browser. §47 — a constant in model.js is a second model."""
    return {
        "wPeak": W_PEAK, "wCubic": W_CUBIC, "wFloor": W_FLOOR,
        "idealMinutes": IDEAL_MINUTES, "dBase": D_BASE, "dSpan": D_SPAN,
        "shortPenalty": SHORT_PENALTY,
        "cBase": C_BASE, "cSpan": C_SPAN, "lBase": L_BASE, "lSpan": L_SPAN,
        "transitionCostPerMin": TRANSITION_COST_PER_MIN,
        "idleCostFactor": IDLE_COST_FACTOR,
        "breadthBonus": BREADTH_BONUS,
        "complexityPenalty": COMPLEXITY_PENALTY,
        "stalePenalty": STALE_PENALTY,
        "sampleMinutes": SAMPLE_MINUTES,
        "minDuration": dict(MIN_DURATION),
        "defaultMinDuration": DEFAULT_MIN_DURATION,
        "exceptionalQuality": EXCEPTIONAL_QUALITY,
    }
