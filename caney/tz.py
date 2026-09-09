"""
Timezones that survive a runtime with no tz database. §4, §30.

`zoneinfo` reads `/usr/share/zoneinfo`. A Cloudflare Python Worker is a Pyodide sandbox
with no filesystem to read it from, so `ZoneInfo("America/Chicago")` — which every part of
this planner depends on for sun times, day boundaries and the "leave by" clock — raises
`ZoneInfoNotFoundError` there and takes the whole request with it.

So: use `zoneinfo` when it works, and fall back to the arithmetic when it does not. The
fallback is not a general tz implementation and does not pretend to be one. It knows the
post-2007 US rule (second Sunday in March to first Sunday in November) and the four US
zones this product actually plans in. Anything else raises rather than guessing, because
silently returning UTC for an unknown zone would move every sun time by six hours and
nothing downstream would notice.

`caney/sources/weather.py` and everything under `caney/planner/` import from here rather
than from `zoneinfo` directly; `test_architecture.py` pins that.
"""
import datetime as dt

#: (standard offset hours, standard abbreviation, daylight abbreviation)
_US_ZONES = {
    "America/Chicago":     (-6, "CST", "CDT"),
    "America/New_York":    (-5, "EST", "EDT"),
    "America/Denver":      (-7, "MST", "MDT"),
    "America/Los_Angeles": (-8, "PST", "PDT"),
    "UTC":                 (0, "UTC", "UTC"),
}


def _nth_weekday(year, month, weekday, n):
    """The nth `weekday` (0=Mon) of `month`. Naive date."""
    d = dt.date(year, month, 1)
    shift = (weekday - d.weekday()) % 7
    return d + dt.timedelta(days=shift + 7 * (n - 1))


class _USTimeZone(dt.tzinfo):
    """The post-2007 US daylight rule, evaluated in local standard time.

    DST begins 02:00 local standard on the second Sunday in March and ends 02:00 local
    daylight (01:00 standard) on the first Sunday in November. Expressing both switch
    instants in STANDARD time is what makes the comparison below single-valued — doing it
    in local wall time makes the November hour ambiguous and the March hour nonexistent,
    which is the classic way this gets written wrong.
    """

    def __init__(self, name):
        std_hours, std_abbr, dst_abbr = _US_ZONES[name]
        self._name = name
        self._std = dt.timedelta(hours=std_hours)
        self._dst = dt.timedelta(hours=std_hours + 1)
        self._std_abbr, self._dst_abbr = std_abbr, dst_abbr
        self._has_dst = std_abbr != dst_abbr

    def _bounds(self, year):
        """The two switch instants, expressed in LOCAL STANDARD time.

        Standard time is the only frame in which both are single-valued. The US rule
        starts DST at 02:00 standard on the second Sunday in March and ends it at 02:00
        daylight — which is 01:00 standard — on the first Sunday in November.
        """
        return (dt.datetime.combine(_nth_weekday(year, 3, 6, 2), dt.time(2)),
                dt.datetime.combine(_nth_weekday(year, 11, 6, 1), dt.time(1)))

    def _is_dst(self, d):
        """DST for a WALL-CLOCK datetime, which is not always answerable without `fold`.

        Two hours a year are not a simple comparison:

          * March, 02:00-02:59 wall — never happens. `fold=0` resolves to the offset
            in force before the jump (standard), `fold=1` to the one after (daylight).
            That is the reverse of the November case.
          * November, 01:00-01:59 wall — happens twice. `fold=0` is the first pass and is
            still daylight; `fold=1` is the repeat and is standard. Ignoring `fold` here
            is what made this class disagree with `zoneinfo` by an hour once a year.
        """
        if not self._has_dst or d is None:
            return False
        naive = d.replace(tzinfo=None)
        mar_std, nov_std = self._bounds(naive.year)
        # Wall-clock thresholds: DST starts at 02:00 wall, and the repeated hour runs
        # from 01:00 to 02:00 wall.
        dst_start_wall = mar_std                       # 02:00, the hour that is skipped
        ambiguous_from = nov_std                       # 01:00 wall
        ambiguous_to = nov_std + dt.timedelta(hours=1)  # 02:00 wall
        if naive < dst_start_wall:
            return False
        if naive < dst_start_wall + dt.timedelta(hours=1):
            # The skipped hour. PEP 495 gives `fold` the OPPOSITE sense in a gap than in
            # a repeat: fold=0 means the offset in force BEFORE the jump (standard),
            # fold=1 the one after (daylight). Reading it the same way round as November
            # is what put this hour an hour out.
            return getattr(d, "fold", 0) == 1
        if naive < ambiguous_from:
            return True
        if naive < ambiguous_to:
            return getattr(d, "fold", 0) == 0
        return False

    def utcoffset(self, d):
        return self._dst if self._is_dst(d) else self._std

    def dst(self, d):
        return dt.timedelta(hours=1) if self._is_dst(d) else dt.timedelta(0)

    def tzname(self, d):
        return self._dst_abbr if self._is_dst(d) else self._std_abbr

    def fromutc(self, d):
        """UTC is unambiguous, so this is the direction that decides `fold` for the other."""
        local_std = d.replace(tzinfo=None) + self._std
        if self._has_dst:
            mar_std, nov_std = self._bounds(local_std.year)
            if mar_std <= local_std < nov_std:
                return (d + self._dst).replace(tzinfo=self, fold=0)
            # Standard time. If the wall clock lands in the repeated hour, this is the
            # SECOND pass through it — PEP 495 calls that fold=1.
            wall = d.replace(tzinfo=None) + self._std
            if nov_std <= wall < nov_std + dt.timedelta(hours=1):
                return wall.replace(tzinfo=self, fold=1)
            return wall.replace(tzinfo=self, fold=0)
        return (d + self._std).replace(tzinfo=self)

    def __repr__(self):
        return "_USTimeZone(%r)" % self._name

    def __str__(self):
        return self._name

    #: dataclasses/asdict and JSON dumps of localised datetimes want a stable key.
    def __eq__(self, other):
        return isinstance(other, _USTimeZone) and other._name == self._name

    def __hash__(self):
        return hash(("_USTimeZone", self._name))


_CACHE = {}
#: True once we have proven `zoneinfo` can actually load a zone in this runtime.
_ZONEINFO_OK = None


def _zoneinfo_works():
    global _ZONEINFO_OK
    if _ZONEINFO_OK is None:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo("America/Chicago")
            _ZONEINFO_OK = True
        except Exception:                       # noqa: BLE001 — any failure means fallback
            _ZONEINFO_OK = False
    return _ZONEINFO_OK


def zone(name="America/Chicago"):
    """A tzinfo for `name`. `zoneinfo` where available, the US rule where it is not."""
    if name in _CACHE:
        return _CACHE[name]
    tz = None
    if _zoneinfo_works():
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(name)
        except Exception:                       # noqa: BLE001
            tz = None
    if tz is None:
        if name not in _US_ZONES:
            raise KeyError(
                "no tz database in this runtime and %r is not one of the zones caney "
                "carries a rule for (%s)" % (name, ", ".join(sorted(_US_ZONES))))
        tz = _USTimeZone(name)
    _CACHE[name] = tz
    return tz


def backend():
    """Which implementation is in use — reported in the API's health payload."""
    return "zoneinfo" if _zoneinfo_works() else "builtin-us-rule"
