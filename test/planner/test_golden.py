"""
§50 — golden model fixtures.

Deterministic release schedules and flow bands, with the plan-relevant OUTPUT pinned. The
value of these is that they are the cases that actually happen on this water and that a
refactor is most likely to get wrong: a split-generation day, a ramp that is one front and
not three, a missing forecast, and a tributary event the dam schedule cannot explain.
"""
import fixtures as F
from harness import check, eq, near, section

from caney.domain.observation import DataState
from caney.planner import scoring
from caney.planner.engine import Request, _unsafe
from caney.domain.zone import Craft
from caney.sources.registry import water_for
from caney.zones.registry import zone


def _trout_generation_fit(release, mfd=6.0, window=(6, 12), day=0, forecast_override=None):
    z = zone("caney_upper")
    s = F.snapshot("caney_upper", "caney", flow=250, temp_f=55, generation=250,
                   forecast=(forecast_override if forecast_override is not None
                             else F.GOLDEN_RELEASES.get(release)))
    F.with_arrival(s, mfd)
    prof = __import__("caney.species.profiles", fromlist=["profile"]).profile("trout")
    return scoring.fit_generation_trout(
        s, prof, water_for("caney"), 0, s.generation.ok,
        (F.at(window[0], day), F.at(window[1], day))), s


def test_golden_releases():
    section("§50 — Caney release schedules")

    fit, _ = _trout_generation_fit("no_generation")
    near("no generation: the whole 6-12 window is wadeable", fit.value, 1.0, 0.001)

    fit, s = _trout_generation_fit("single_afternoon")
    near("single afternoon release: the morning is still wholly wadeable", fit.value, 1.0, 0.001)
    fit_pm, _ = _trout_generation_fit("single_afternoon", window=(12, 18))
    check("single afternoon release: the afternoon window is cut short",
          fit_pm.value < fit.value * 0.75, "%s vs %s" % (fit_pm.value, fit.value))
    check("and it says how much of the window survives",
          "% of the window" in fit_pm.why, fit_pm.why)

    # 1U -> 2U -> 1U is ONE front, not three. What matters is when it FIRST arrives.
    fit_am, _ = _trout_generation_fit("ramp_1u_2u_1u", window=(5, 9))
    fit_mid, _ = _trout_generation_fit("ramp_1u_2u_1u", window=(6, 14))
    check("1U→2U→1U: an early window survives the ramp", fit_am.value > 0.9, fit_am.value)
    check("1U→2U→1U: a window spanning it is cut, not zeroed",
          0.1 < fit_mid.value < 0.9, fit_mid.value)

    # Two separate releases is THE case a first-window-only implementation gets wrong.
    fit_gap, _ = _trout_generation_fit("two_separate_releases", window=(10, 14))
    fit_second, _ = _trout_generation_fit("two_separate_releases", window=(14, 20))
    fit_none_pm, _ = _trout_generation_fit("no_generation", window=(14, 20))
    check("two releases: the gap between them is wadeable", fit_gap.value > 0.9, fit_gap.value)
    # THE regression this fixture exists for: a first-window-only implementation scores
    # the afternoon as if nothing were scheduled, because the morning release is behind it.
    check("two releases: the SECOND one closes the afternoon, not just the first",
          fit_second.value < fit_none_pm.value * 0.75,
          "%s vs %s with no generation" % (fit_second.value, fit_none_pm.value))

    fit_night, _ = _trout_generation_fit("overnight_into_morning", window=(6, 11), day=1)
    check("an overnight release still owns the next morning", fit_night.value < 0.6,
          fit_night.value)

    section("§50 — the absences, which must not read as 'no generation'")
    fit_missing, s_missing = _trout_generation_fit("missing_forecast", forecast_override=None)
    eq("a missing forecast is UNKNOWN, not zero cfs",
       s_missing.generation_forecast.state, DataState.UNKNOWN)
    eq("a missing forecast has no value at all", s_missing.generation_forecast.value, None)
    check("a missing forecast scores WORSE than a confirmed idle dam",
          fit_missing.value < 0.5, fit_missing.value)
    check("and it says why", "cannot be bounded" in fit_missing.why, fit_missing.why)

    _, s_stale = _trout_generation_fit("stale_forecast", forecast_override="stale")
    eq("a stale forecast is STALE, not fresh", s_stale.generation_forecast.state,
       DataState.STALE)
    check("a stale forecast keeps its schedule", bool(s_stale.generation_forecast.value))

    section("§50 — Smith Fork runoff: water the dam schedule does not explain")
    runoff = F.smith_fork_runoff(F.GOLDEN_RELEASES["no_generation"])
    s = F.snapshot("caney_upper", "caney", flow=2100, temp_f=55, generation=250,
                   forecast=runoff, flow_trend="rising")
    F.with_arrival(s, 6.0)
    check("the gauge shows water the release does not account for",
          s.flow.value > 5 * s.generation.value, "%s vs %s" % (s.flow.value, s.generation.value))
    prof = __import__("caney.species.profiles", fromlist=["profile"]).profile("trout")
    cl = scoring.fit_clarity(s, prof)
    check("a rising river is not assumed clear", "clear" not in cl.why, cl.why)


def test_warmwater_bands():
    section("§50 — warmwater flow bands")
    import riverlib
    prof = __import__("caney.species.profiles", fromlist=["profile"]).profile("smallmouth")
    m = riverlib.WATER_MODEL["duckup"]
    z = zone("duck_upper")
    results = {}
    for name in F.WARMWATER_BANDS:
        cfs = F.warmwater_flow(m, name)
        s = F.snapshot("duck_upper", "duckup", flow=cfs, temp_f=72, flow_trend="steady")
        fit = scoring.fit_flow(s, prof, "duckup", None)
        results[name] = fit.value
        check("%s (%d cfs) explains itself" % (name, cfs), bool(fit.why), fit.why)
    check("prime scores highest", results["prime"] == max(results.values()), str(results))
    check("very low is penalised", results["very_low"] < results["prime"], str(results))
    check("high is penalised more than very low",
          results["high"] < results["very_low"], str(results))
    check("blown out is the worst", results["blown"] == min(results.values()), str(results))
    check("a rising, stained level still fishes", results["rising_stained"] >= 0.6,
          str(results))

    section("§50 — a missing gauge")
    s = F.snapshot("duck_upper", "duckup", temp_f=72)
    fit = scoring.fit_flow(s, prof, "duckup", None)
    check("no flow reading scores NEUTRAL, not zero", abs(fit.value - 0.5) < 1e-9, fit.value)
    check("and is marked unknown so confidence pays for it", not fit.known)


def test_wade_gate():
    section("§50/§30 — the wade eligibility gate")
    z = zone("caney_upper")
    req = Request("trout", F.at(6), F.at(11), Craft.WADE, now=F.at(5))

    s_ok = F.with_arrival(F.snapshot("caney_upper", "caney", flow=250, generation=250,
                                     forecast=F.GOLDEN_RELEASES["single_afternoon"]), 6.0)
    eq("a morning wade under an afternoon release is allowed", _unsafe(z, s_ok, req), None)

    s_none = F.with_arrival(F.snapshot("caney_upper", "caney", flow=250, generation=250), 6.0)
    r = _unsafe(z, s_none, req)
    check("a wade request with NO release forecast is refused", bool(r), r)
    check("and the refusal says why", "cannot bound" in (r or ""), r)

    s_all = F.with_arrival(F.snapshot("caney_upper", "caney", flow=7300, generation=7300,
                                      forecast=F.GOLDEN_RELEASES["all_day"]), 6.0)
    r2 = _unsafe(z, s_all, req)
    check("a wade request under all-day generation is refused", bool(r2), r2)

    # A downstream gauge reading high must NOT eliminate a tailwater the dam is not running.
    s_high_gauge = F.with_arrival(
        F.snapshot("caney_upper", "caney", flow=9000, generation=250,
                   forecast=F.GOLDEN_RELEASES["no_generation"]), 6.0)
    eq("a high READING fifteen miles downstream does not close the dam reach",
       _unsafe(z, s_high_gauge, req), None)

    section("a free-flowing river IS its gauge")
    zd = zone("duck_upper")
    import riverlib
    no = riverlib.WATER_MODEL["duckup"]["no_wade"]
    reqd = Request("smallmouth", F.at(6), F.at(11), Craft.WADE, now=F.at(5))
    s_blown = F.snapshot("duck_upper", "duckup", flow=no * 2, temp_f=70)
    check("a blown-out free-flowing river refuses a wade request",
          bool(_unsafe(zd, s_blown, reqd)), _unsafe(zd, s_blown, reqd))
    s_prime = F.snapshot("duck_upper", "duckup", flow=no * 0.5, temp_f=70)
    eq("a prime free-flowing river allows one", _unsafe(zd, s_prime, reqd), None)

    section("§58 — thunderstorms across the whole window")
    s_storm = F.snapshot("caney_upper", "caney", flow=250, generation=250,
                         forecast=F.GOLDEN_RELEASES["no_generation"],
                         storm_hours=tuple(range(24)))
    r3 = _unsafe(z, s_storm, req)
    check("a window that is entirely thunderstorm is eliminated", bool(r3), r3)
