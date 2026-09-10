"""
The wire contract. §7, §75, §76, §79.

Parsing and validation live apart from the handler so that "this request is malformed" is
decided in exactly one place, and so the same parser serves the Worker, the local dev
server and the tests without any of them re-deriving the rules.

§76 IS THE POINT OF THIS FILE. The Research Worker converts nearly every failure into a
200 with a degraded body, which is right for a research outage and wrong for everything
else: a typo in a species name is not a degraded result, it is a mistake, and answering it
with a cheerful plan for the wrong fish hides a bug from whoever is going to have to find
it later. So a client error is a 400 naming the field, an unknown route is a 404, an
unauthorised internal call is a 403, and 200-with-degradation is reserved for the case it
was designed for — the deterministic plan succeeded and something optional did not.
"""
import datetime as _dt
import time

from ..domain.method import TackleMethod
from ..domain.planning import SCHEMA_VERSION
from ..domain.zone import Craft
from ..species.profiles import SPECIES

#: Requests further out than this are refused rather than answered badly.
#:
#: WEATHER IS THE BINDING CONSTRAINT, not the release forecast — this constant used to say
#: 7 and blame the release schedule, which was simply wrong. The snapshot carries 96 hours
#: of hourly weather from build time, so a window four days out finds ZERO rows in it. The
#: confidence model already handles that correctly and visibly, degrading 55.9 -> 43.9 ->
#: 13.9 -> 1.9 -> 0.0 as the rows run out, so nothing was being hidden. But a plan with a
#: forecast confidence of zero is not an answer, and offering to compute one invites
#: somebody to read the destination and skip the number.
#:
#: Three days is what the data supports. Verified by planning at +1 through +6 and
#: watching where the weather rows stop; test_v3.py pins it.
MAX_DAYS_OUT = 3

#: A day longer than this is not a fishing trip, and letting it through makes the
#: itinerary search do a great deal of work to produce something nobody asked for.
MAX_DAY_HOURS = 18.0

#: Below this the constraint solver has nothing to solve.
MIN_DAY_MINUTES = 30.0


class BadRequest(ValueError):
    """A client error. Carries the field so the response can point at it. §76."""

    def __init__(self, message, field=""):
        super().__init__(message)
        self.field = field
        self.message = message


def _num(body, key, required=False, default=None):
    v = body.get(key, None)
    if v is None:
        if required:
            raise BadRequest("%s is required" % key, key)
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise BadRequest("%s must be a number" % key, key)
    try:
        return float(v)
    except (TypeError, ValueError):
        raise BadRequest("%s must be a number, got %r" % (key, v), key)


def _iso_or_epoch(value, field, tz):
    """Accept an epoch or an ISO 8601 string. Reject anything else by name."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise BadRequest("%s must be a time, not a boolean" % field, field)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return float(s)
        try:
            import datetime as dt
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=tz)
            return d.timestamp()
        except ValueError:
            raise BadRequest("%s is not a valid ISO 8601 time: %r" % (field, value), field)
    raise BadRequest("%s must be an ISO 8601 string or an epoch" % field, field)


def parse_origin(body):
    """(lat, lon) or None. §15/§16 — an origin is optional, always."""
    o = body.get("origin")
    if o in (None, {}, ""):
        return None
    if not isinstance(o, dict):
        raise BadRequest("origin must be an object with lat and lon", "origin")
    lat, lon = o.get("lat"), o.get("lon")
    if lat is None or lon is None:
        raise BadRequest("origin needs both lat and lon", "origin")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise BadRequest("origin lat and lon must be numbers", "origin")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise BadRequest("origin is not a point on Earth", "origin")
    return (lat, lon)


def parse(body, now=None, tz_name="America/Chicago"):
    """A validated planner Request. Raises BadRequest, never returns a partial one."""
    from ..planner.engine import Request
    from ..tz import zone as tzf

    if not isinstance(body, dict):
        raise BadRequest("the request body must be a JSON object")
    now = now or time.time()
    tz = tzf(tz_name)

    species = body.get("species")
    if not species:
        raise BadRequest("species is required", "species")
    if species not in SPECIES:
        raise BadRequest("unknown species %r — expected one of %s"
                         % (species, ", ".join(sorted(SPECIES))), "species")

    craft = body.get("craft") or Craft.ANY
    if craft not in Craft.ALL:
        raise BadRequest("unknown craft %r — expected one of %s"
                         % (craft, ", ".join(Craft.ALL)), "craft")

    method = body.get("method") or TackleMethod.EITHER
    if method not in TackleMethod.ALL:
        raise BadRequest("unknown method %r — expected one of %s"
                         % (method, ", ".join(TackleMethod.ALL)), "method")

    av = body.get("availability") or {}
    if not isinstance(av, dict):
        raise BadRequest("availability must be an object", "availability")

    depart = _iso_or_epoch(av.get("depart_after"), "availability.depart_after", tz)
    ret = _iso_or_epoch(av.get("return_by"), "availability.return_by", tz)
    fish_after = _iso_or_epoch(av.get("fish_after"), "availability.fish_after", tz)
    fish_before = _iso_or_epoch(av.get("fish_before"), "availability.fish_before", tz)

    if depart is None and ret is None and fish_after is None and fish_before is None:
        raise BadRequest(
            "availability needs either (depart_after, return_by) for a whole day or "
            "(fish_after, fish_before) for a fishing window", "availability")
    if (depart is None) != (ret is None):
        raise BadRequest(
            "depart_after and return_by must be given together — a day needs both ends",
            "availability")
    if depart is None and (fish_after is None or fish_before is None):
        raise BadRequest("a fishing window needs both fish_after and fish_before",
                         "availability")

    lo = depart if depart is not None else fish_after
    hi = ret if ret is not None else fish_before
    if hi <= lo:
        raise BadRequest("availability ends before it starts", "availability")
    span_h = (hi - lo) / 3600.0
    if span_h > MAX_DAY_HOURS:
        raise BadRequest("availability spans %.1f hours; the maximum is %.0f"
                         % (span_h, MAX_DAY_HOURS), "availability")
    if (hi - lo) / 60.0 < MIN_DAY_MINUTES:
        raise BadRequest("availability is under %d minutes" % MIN_DAY_MINUTES,
                         "availability")
    # CALENDAR DAYS, not float days. This used to be `(lo - now) / 86400.0`, which made
    # the horizon shrink as the clock moved: "three days out" was accepted at 08:00,
    # 14:00 and 22:00 and REJECTED at 00:51, because a 6 a.m. window three calendar days
    # away is 3.2 float-days from one in the morning. A scheduled build caught it, at the
    # worst possible hour to find it — before dawn is exactly when somebody opens a
    # fishing app.
    #
    # "Three days out" means three calendar days to a person, and a bound that depends on
    # what time they ask is not a bound they can learn. Thin weather at the far edge is
    # handled where thin data belongs: the confidence model degrades it, visibly. Gates
    # are for requests that are WRONG; confidence is for answers that are WEAK.
    req_date = _dt.datetime.fromtimestamp(lo, tz).date()
    today = _dt.datetime.fromtimestamp(now, tz).date()
    days_out = (req_date - today).days
    if days_out > MAX_DAYS_OUT:
        raise BadRequest(
            "that is %d days out. The hourly weather forecast only reaches %d days, "
            "and past that a plan carries a forecast confidence of zero — which is not "
            "an answer, however confidently the destination is printed."
            % (days_out, MAX_DAYS_OUT), "availability")

    origin = parse_origin(body)
    max_drive = _num(body, "max_drive_minutes")
    if max_drive is not None and max_drive <= 0:
        raise BadRequest("max_drive_minutes must be positive", "max_drive_minutes")

    prefs = body.get("preferences") or {}
    if not isinstance(prefs, dict):
        raise BadRequest("preferences must be an object", "preferences")

    if depart is not None:
        return Request(species, start=fish_after, end=fish_before, craft=craft,
                       tz=tz_name, now=now, origin=origin, method=method,
                       depart_after=depart, return_by=ret,
                       max_drive_minutes=max_drive, preferences=prefs)
    return Request(species, start=fish_after, end=fish_before, craft=craft, tz=tz_name,
                   now=now, origin=origin, method=method,
                   max_drive_minutes=max_drive, preferences=prefs)


def error(status, message, field="", code=""):
    """The one error shape every endpoint returns. §75, §76."""
    return status, {
        "error": {"message": message, "field": field,
                  "code": code or _CODES.get(status, "error"), "status": status},
        "schema_version": SCHEMA_VERSION,
    }


_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden",
          404: "not_found", 405: "method_not_allowed", 429: "rate_limited",
          500: "internal_error", 503: "unavailable"}
