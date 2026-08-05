#!/usr/bin/env python3
"""
Backtest the Caney flow-projection engine against reality.

The deployed model (briefing.py) predicts downstream flow as:
    flow(point, t) = baseflow + Σ_i KERNEL[i] * release(t - i·1h)
with the kernel time-compressed by frac = miles_from_dam/15 (mass-conserving, so baseflow is
constant along the reach), leading-edge arrival timed by
the leading-edge rule (miles/WATER_MPH), auto-calibrated to the Stonewall gauge. Stonewall (15 mi) is
the one downstream gauge, so it is the ground truth for "how much water, when".

This script is an INDEPENDENT reimplementation (it does not import briefing.py) so it checks
the logic, not just the data. It replays 90 days of real Center Hill releases through the
FIXED deployed kernel and compares to the real USGS Stonewall gauge, then:
  A. magnitude accuracy  (bias, MAE, RMSE, r, Nash-Sutcliffe, peak error)
  B. timing              (cross-correlation lag: model↔gauge and release↔gauge)
  C. per-event response  (leading-edge rise lag vs the WATER_MPH rule; peak lag; attenuation)
  D. the kernel itself   (least-squares empirical impulse response vs CALIB_KERNEL)

Usage: python3 analysis/backtest_flow.py [days]
"""
import urllib.request, urllib.parse, json, datetime, math, sys, time

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 90
UA = {"User-Agent": "backtest/1.0"}

# ── the deployed model constants ──
# READ from briefing.py rather than copied into it. A hand-copied "verbatim" block silently went
# stale: commit 2c2bc2c overrode the leading-edge speed 3.0 -> 2.5 mph in briefing.py and this
# file kept WATER_MPH = 3.0, so the backtest was grading a model that is no longer deployed.
# The LOGIC below is still an independent reimplementation -- briefing.py is never imported --
# but the numbers it grades are now authoritative by construction.
import re as _re, os as _os
_SRC = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "briefing.py"), encoding="utf-8").read()
def _const(name, cast=float):
    m = _re.search(r"(?:^|;\s*)%s\s*=\s*(\[[^\]]*\]|[0-9.]+)" % _re.escape(name), _SRC, _re.M)
    if not m: raise SystemExit("cannot read %s from briefing.py" % name)
    v = m.group(1)
    return [float(x) for x in v.strip("[]").split(",")] if v.startswith("[") else cast(v)

CALIB_KERNEL = _const("CALIB_KERNEL")
BASEFLOW     = _const("CALIB_BASEFLOW")
WATER_MPH    = _const("WATER_MPH")
MFD_STONE    = _const("MFD_STONE")
print("model under test: baseflow %.0f · leading edge %.2f mph · kernel n=%d"
      % (BASEFLOW, WATER_MPH, len(CALIB_KERNEL)))
_g = sum(CALIB_KERNEL)
KERNEL = [w/_g for w in CALIB_KERNEL]                    # Stonewall kernel (frac=1.0, uncompressed)
CENTROID = sum(i*w for i, w in enumerate(KERNEL))        # mean (bulk) lag, hours
LEAD_3MPH = MFD_STONE / WATER_MPH                        # leading edge to Stonewall, hours

def get(u, h=None, tries=4):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={**UA, **(h or {})}), timeout=180) as r:
                return json.load(r)
        except Exception as e:
            if a == tries - 1: raise
            print("  retry %d/%d after %s" % (a + 1, tries - 1, e)); time.sleep(3 * (a + 1))
def hr_key(e): return int(e//3600)*3600

now = datetime.datetime.now(datetime.timezone.utc)
begin = (now - datetime.timedelta(days=DAYS)).strftime("%Y-%m-%dT%H:00:00Z")
end = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:00:00Z")

# ── fetch: Center Hill release (CWMS actual, period-ending → shift to hour-start) ──
u = ("https://cwms-data.usace.army.mil/cwms-data/timeseries?office=LRN"
     f"&name={urllib.parse.quote('CETT1-CENTER_HILL.Flow.Ave.1Hour.1Hour.man-rev')}"
     f"&begin={begin}&end={end}&unit=cfs&page-size=500000")
dam = {hr_key(t/1000) - 3600: v for t, v, q in get(u, {"Accept": "application/json;version=2"})["values"] if v is not None}
print("release samples: %d hours" % len(dam))

# ── fetch: USGS Stonewall gauge, resample instantaneous → hourly mean over each clock hour ──
gu = ("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=03424860"
      f"&startDT={(now-datetime.timedelta(days=DAYS)).strftime('%Y-%m-%d')}&endDT={now.strftime('%Y-%m-%d')}&parameterCd=00060")
gp = get(gu)["value"]["timeSeries"][0]["values"][0]["value"]
_bucket = {}
for p in gp:
    try: v = float(p["value"])
    except (TypeError, ValueError): continue
    if v < 0: continue
    k = hr_key(datetime.datetime.fromisoformat(p["dateTime"]).timestamp())
    _bucket.setdefault(k, []).append(v)
gauge = {k: sum(vs)/len(vs) for k, vs in _bucket.items()}

def dam_at(k):
    if k in dam: return dam[k]
    lo = max((x for x in dam if x <= k), default=None)
    return dam[lo] if lo is not None else None

def model_at(k, base=BASEFLOW):
    acc, ok = 0.0, False
    for i, w in enumerate(KERNEL):
        d = dam_at(k - i*3600)
        if d is not None: acc += w*d; ok = True
    return (base + acc) if ok else None

# ── aligned hourly series where model, release, and gauge all exist ──
hrs = sorted(k for k in gauge if k in dam and (k - 19*3600) in dam)
G = [gauge[k] for k in hrs]
R = [dam[k] for k in hrs]
M = [model_at(k) for k in hrs]

# baseflow auto-cal (the model does a clamped median low-flow residual); report calibrated too
low_resid = sorted(gauge[k] - model_at(k) for k in hrs if model_at(k) < 700)
CALIB_ADJ = max(-250, min(250, low_resid[len(low_resid)//2])) if len(low_resid) >= 6 else 0
Mc = [model_at(k, BASEFLOW + CALIB_ADJ) for k in hrs]

# ── metrics ──
def stats(obs, pred):
    n = len(obs); mo = sum(obs)/n; mp = sum(pred)/n
    err = [pred[i]-obs[i] for i in range(n)]
    bias = sum(err)/n
    mae = sum(abs(e) for e in err)/n
    rmse = (sum(e*e for e in err)/n)**0.5
    so = sum((o-mo)**2 for o in obs); sp = sum((p-mp)**2 for p in pred)
    cov = sum((obs[i]-mo)*(pred[i]-mp) for i in range(n))
    r = cov/((so*sp)**0.5) if so and sp else 0.0
    nse = 1 - sum(e*e for e in err)/so if so else 0.0     # Nash-Sutcliffe
    return dict(n=n, bias=bias, mae=mae, rmse=rmse, r=r, nse=nse, mean_obs=mo)

def pearson_lag(a, b, maxlag=15):
    # corr(a(k), b(k+τ)) over τ; returns list of (lag, r) and the argmax
    out = []
    for τ in range(0, maxlag+1):
        xs = a[:len(a)-τ]; ys = b[τ:]
        n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
        sx = sum((x-mx)**2 for x in xs); sy = sum((y-my)**2 for y in ys)
        cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
        out.append((τ, cov/((sx*sy)**0.5) if sx and sy else 0.0))
    best = max(out, key=lambda t: t[1])
    return out, best

# ── D: empirical impulse response via least squares  G = b + Σ h[i]·R(k-i) ──
def solve(A, y):                    # Gaussian elimination w/ partial pivoting
    n = len(A); M = [row[:] + [y[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c])); M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12: continue
        for r in range(n):
            if r != c:
                f = M[r][c]/M[c][c]
                for j in range(c, n+1): M[r][j] -= f*M[c][j]
    return [M[i][n]/M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]

def empirical_kernel(L=20):
    ks = [k for k in hrs if all((k - i*3600) in dam for i in range(L))]
    # design matrix: [1, R(k), R(k-1), ... R(k-(L-1))]
    X = [[1.0] + [dam[k - i*3600] for i in range(L)] for k in ks]
    y = [gauge[k] for k in ks]
    XtX = [[sum(X[r][a]*X[r][b] for r in range(len(X))) for b in range(L+1)] for a in range(L+1)]
    Xty = [sum(X[r][a]*y[r] for r in range(len(X))) for a in range(L+1)]
    coef = solve(XtX, Xty)
    return coef[0], coef[1:], len(ks)   # base, h[0..L-1], n

# ── C: per-event response (leading edge, peak, attenuation) ──
def events():
    seq = sorted(dam)
    evs = []; i = 0
    while i < len(seq):
        k = seq[i]
        if dam[k] >= 2000 and dam_at(k-3600) is not None and dam_at(k-3600) < 800:
            j = i
            while j+1 < len(seq) and seq[j+1] == seq[j]+3600 and dam[seq[j+1]] >= 800: j += 1
            onset = k; rel_peak_k = max(seq[i:j+1], key=lambda x: dam[x]); rel_peak = dam[rel_peak_k]
            base_g = gauge.get(onset-3600) or gauge.get(onset)
            if base_g:
                rise = None
                for h in range(0, 14):
                    gk = onset + h*3600
                    if gk in gauge and gauge[gk] > base_g + 300: rise = h; break
                win = [onset + h*3600 for h in range(0, 20) if (onset + h*3600) in gauge]
                gpk_k = max(win, key=lambda x: gauge[x]) if win else None
                if rise is not None and gpk_k is not None:
                    evs.append(dict(onset=onset, rise_lag=rise,
                                    rel_peak=rel_peak, g_peak=gauge[gpk_k],
                                    peak_lag=(gpk_k-onset)//3600, atten=gauge[gpk_k]/rel_peak))
            i = j+1
        else:
            i += 1
    return evs

# ══ REPORT ══
print("="*72)
print("CANEY FLOW-ENGINE BACKTEST — Center Hill release → Stonewall gauge (USGS 03424860)")
print("window: last %d days · %d aligned hourly points · gauge mean %.0f cfs" % (DAYS, len(hrs), stats(G, M)['mean_obs']))
print("="*72)

print("\nMODEL CONSTANTS  baseflow=%.0f  kernel centroid=%.2f h  %.2f-mph leading edge=%.1f h" % (BASEFLOW, CENTROID, WATER_MPH, LEAD_3MPH))
print("first non-trivial kernel weight at lag %dh; peak weight at lag %dh"
      % (next(i for i,w in enumerate(KERNEL) if w>0.03), max(range(len(KERNEL)), key=lambda i: KERNEL[i])))

print("\n── A. MAGNITUDE (deployed fixed kernel) ──")
for label, pred in [("nominal baseflow %.0f" % BASEFLOW, M), ("baseflow %+.0f (auto-cal)" % CALIB_ADJ, Mc)]:
    s = stats(G, pred)
    print("  %-26s bias %+5.0f  MAE %4.0f  RMSE %4.0f  r %.3f  NSE %.3f"
          % (label, s["bias"], s["mae"], s["rmse"], s["r"], s["nse"]))
# peak behaviour
gmax = max(G); mmax = max(Mc)
print("  gauge peak %.0f cfs vs model peak %.0f cfs  (%.0f%% of observed)" % (gmax, mmax, 100*mmax/gmax))

print("\n── B. TIMING (cross-correlation, hours) ──")
_, br = pearson_lag(R, G); _, bm = pearson_lag(Mc, G)
print("  release → gauge   best lag %2d h (r=%.3f)   [model bulk/centroid = %.1f h]" % (br[0], br[1], CENTROID))
print("  model   → gauge   best lag %2d h (r=%.3f)   [0 h = timing correct]" % (bm[0], bm[1]))

print("\n── C. PER-EVENT RESPONSE (release ramps ≥2000 cfs from a low base) ──")
evs = events()
if evs:
    rl = sorted(e["rise_lag"] for e in evs); pl = sorted(e["peak_lag"] for e in evs)
    at = sorted(e["atten"] for e in evs)
    med = lambda x: x[len(x)//2]
    print("  %d events  |  rise lag: median %d h (range %d–%d)   [%.2f-mph rule says %.0f h]"
          % (len(evs), med(rl), rl[0], rl[-1], WATER_MPH, LEAD_3MPH))
    print("  peak lag: median %d h (range %d–%d)   [kernel centroid %.1f h]" % (med(pl), pl[0], pl[-1], CENTROID))
    print("  attenuation gauge_peak/release_peak: median %.2f (range %.2f–%.2f)" % (med(at), at[0], at[-1]))
else:
    print("  (no clean isolated ramp events in window)")

print("\n── D. EMPIRICAL KERNEL vs CALIB_KERNEL (least-squares impulse response) ──")
try:
    eb, eh, en = empirical_kernel(20)
    gain = sum(eh)
    ecen = sum(i*max(0, w) for i, w in enumerate(eh)) / (sum(max(0, w) for w in eh) or 1)
    elead = next((i for i, w in enumerate(eh) if w > 0.03*max(eh)), None)
    print("  fit on %d hrs   implied baseflow %.0f (model %.0f)   steady-state gain Σh = %.2f (model 1.00)" % (en, eb, BASEFLOW, gain))
    print("  empirical centroid %.2f h (model %.2f)   empirical leading edge ~%s h (model 3–4)" % (ecen, CENTROID, elead))
    epk = max(range(len(eh)), key=lambda i: eh[i])
    print("  empirical peak-response lag %d h (model %d h)" % (epk, max(range(len(KERNEL)), key=lambda i: KERNEL[i])))
    # side-by-side normalized shape (positive part)
    pos = [max(0, w) for w in eh]; ps = sum(pos) or 1
    print("  lag:   " + " ".join("%4d" % i for i in range(12)))
    print("  model: " + " ".join("%4.2f" % KERNEL[i] for i in range(12)))
    print("  data:  " + " ".join("%4.2f" % (pos[i]/ps) for i in range(12)))
except Exception as e:
    print("  (empirical fit failed:", e, ")")

print("\n" + "="*72)
