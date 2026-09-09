"""
Tiny test harness. stdlib only, like everything else in this repo.

    python3 test/planner/run.py

No pytest: the build and QA path must run on a bare `actions/setup-python` with no
requirements.txt, which is the same constraint that keeps the generators dependency-free.
"""
import sys
import traceback

_state = {"pass": 0, "fail": 0, "failures": []}


def check(name, cond, detail=""):
    if cond:
        _state["pass"] += 1
        print("  \033[32m✓\033[0m " + name)
    else:
        _state["fail"] += 1
        _state["failures"].append(name)
        print("  \033[31m✗\033[0m %s%s" % (name, (" — " + str(detail)) if detail else ""))
    return bool(cond)


def eq(name, got, want):
    return check(name, got == want, "got %r, wanted %r" % (got, want))


def near(name, got, want, tol=0.05):
    ok = got is not None and abs(got - want) <= tol
    return check(name, ok, "got %r, wanted %r ±%s" % (got, want, tol))


def raises(name, exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc:
        return check(name, True)
    except Exception as e:                       # noqa: BLE001
        return check(name, False, "raised %s, wanted %s" % (type(e).__name__, exc.__name__))
    return check(name, False, "did not raise " + exc.__name__)


def skip(name, why):
    """A check that cannot run here, said out loud.

    Used only where the SAME invariant is enforced somewhere that can run it. This suite
    is contracted to need no network and no build (see run.py), so a check that needs
    out/ must say it is deferring rather than fail — and must name where it is covered,
    so a silent gap is impossible to create by accident.
    """
    print("  \033[33m~\033[0m %s — %s" % (name, why))


def section(title):
    print("\n\033[1m── %s ──\033[0m" % title)


def run(modules):
    for m in modules:
        try:
            m()
        except Exception:                        # noqa: BLE001
            _state["fail"] += 1
            _state["failures"].append(getattr(m, "__name__", "?"))
            print("  \033[31m✗ %s raised\033[0m" % getattr(m, "__name__", "?"))
            traceback.print_exc()
    print()
    if _state["fail"]:
        print("\033[31mFAILED %d check(s):\033[0m %s"
              % (_state["fail"], "; ".join(_state["failures"][:8])))
        sys.exit(1)
    print("\033[32mALL %d PLANNER CHECKS PASSED\033[0m" % _state["pass"])
