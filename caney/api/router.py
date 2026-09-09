"""
Path dispatch. §7, §11, §76, §77.

Shared by the Cloudflare Worker and the local dev server so there is exactly one
statement of what the API's surface is. A route that exists in one and not the other is
the kind of drift that makes a shadow comparison meaningless.

§77 — the surface is deliberately small. Health may be externally reachable because it is
useful and says nothing. Everything else is the planner. There is no research endpoint
here at all: the browser reaches research through the planner or not at all, and the
Research Worker is bound privately (§35).
"""
from ..domain.planning import SCHEMA_VERSION
from . import handler
from .contract import error

PREFIX = "/api/v3"


def route(method, path, body, ctx):
    """(status, dict). Never raises for a client's benefit; a raise here is a 500."""
    method = (method or "GET").upper()
    path = (path or "/").rstrip("/") or "/"

    if path in ("/health", PREFIX + "/health"):
        if method not in ("GET", "HEAD"):
            return error(405, "health is GET only")
        return handler.health(ctx)

    if not path.startswith(PREFIX):
        return error(404, "no such endpoint: %s" % path)

    rest = path[len(PREFIX):] or "/"

    if rest == "/plan":
        if method != "POST":
            return error(405, "POST a request body to %s/plan" % PREFIX)
        return handler.plan(body, ctx)

    if rest == "/sessions":
        if method != "POST":
            return error(405, "POST to %s/sessions to start one" % PREFIX)
        return handler.session(body, ctx)

    parts = [p for p in rest.split("/") if p]

    # /plans/{id}/refresh
    if len(parts) == 3 and parts[0] == "plans" and parts[2] == "refresh":
        if method != "POST":
            return error(405, "refresh is POST")
        return handler.refresh(parts[1], body, ctx)

    # /plans/{id}
    if len(parts) == 2 and parts[0] == "plans":
        if method != "GET":
            return error(405, "GET a stored plan, or POST to its /refresh")
        stored = ctx.store.get("plan", parts[1])
        if not stored:
            return error(404, "no plan with id %r — it may have expired" % parts[1])
        return 200, stored

    # /sessions/{id}
    if len(parts) == 2 and parts[0] == "sessions":
        if method == "GET":
            raw = ctx.store.get("session", parts[1])
            if not raw:
                return error(404, "no session %r" % parts[1])
            return 200, {"schema_version": SCHEMA_VERSION, "session": raw}
        if method in ("POST", "PATCH"):
            return handler.session(body, ctx, session_id=parts[1])
        return error(405, "GET or POST a session")

    return error(404, "no such endpoint: %s" % path)


#: §77 — CORS. The browser calls /plan from the Pages origin, so the planner endpoints
#: need it; nothing here is a wildcard by accident. `ALLOWED_ORIGINS` is read from the
#: environment by the host and defaults to the production site.
DEFAULT_ORIGINS = ("https://caney.pages.dev",)


def cors_headers(origin, allowed=None):
    allowed = tuple(allowed or DEFAULT_ORIGINS)
    hdrs = {"Vary": "Origin"}
    if origin and (origin in allowed or "*" in allowed):
        hdrs["Access-Control-Allow-Origin"] = origin
        hdrs["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        hdrs["Access-Control-Allow-Headers"] = "Content-Type"
        hdrs["Access-Control-Max-Age"] = "86400"
    return hdrs
