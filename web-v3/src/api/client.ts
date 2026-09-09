/**
 * Talking to the API. §7, §11, §60, §74.
 *
 * Thin on purpose. §2 and §6 say the browser may format, sort and render but may never
 * decide which plan wins, and the surest way to keep that true is for this file to hold
 * no logic that could constitute a decision. It sends a request, it caches the answer for
 * offline, and it hands back what the server said.
 *
 * The one judgement it does make is which BASE to talk to, and that is deployment, not
 * planning.
 */
import type { ApiError, PlanEnvelope, PlanRequest, RefreshResponse, Session } from "./types";

const META = (import.meta as unknown as { env: Record<string, string | undefined> }).env;

/** Configured at build time; falls back to the deployed Worker. */
export const API_BASE =
  META?.VITE_CANEY_API ?? "https://caney-api.steven-b9c.workers.dev";

export class CaneyApiError extends Error {
  status: number;
  field: string;
  code: string;
  constructor(e: ApiError["error"]) {
    super(e.message);
    this.status = e.status;
    this.field = e.field;
    this.code = e.code;
  }
}

/** Offline (§60): the last plan and its session, so a trip survives losing signal. */
const CACHE_KEY = "caney.v3.plan";
const SESSION_KEY = "caney.v3.session";

function store(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode, quota, disabled storage — a cache miss, not a failure */
  }
}

function load<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function cachedPlan(): PlanEnvelope | null {
  return load<PlanEnvelope>(CACHE_KEY);
}

export function cachedSession(): Session | null {
  return load<Session>(SESSION_KEY);
}

export function cacheSession(s: Session | null) {
  if (s) store(SESSION_KEY, s);
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    throw new CaneyApiError({
      message: `the server sent ${res.status} with a body that is not JSON`,
      field: "", code: "bad_gateway", status: res.status,
    });
  }
  if (!res.ok) {
    const e = (body as ApiError)?.error;
    throw new CaneyApiError(
      e ?? { message: `request failed (${res.status})`, field: "", code: "error", status: res.status },
    );
  }
  return body as T;
}

export async function plan(req: PlanRequest): Promise<PlanEnvelope> {
  const env = await call<PlanEnvelope>("/api/v3/plan", {
    method: "POST",
    body: JSON.stringify(req),
  });
  store(CACHE_KEY, env);
  return env;
}

/**
 * §11 — the SERVER decides whether a change is material. This returns the verdict and the
 * structured delta; nothing here re-derives one, and the thresholds ride along in the
 * payload so the UI can explain the answer without being able to reach a different one.
 *
 * §16 — the origin is sent per request because the server does not keep it. A door-to-door
 * plan cannot be re-checked without it, and the API says so rather than silently
 * degrading to a window-only comparison.
 */
export async function refresh(
  planId: string,
  origin?: { lat: number; lon: number } | null,
): Promise<RefreshResponse> {
  const out = await call<RefreshResponse>(`/api/v3/plans/${encodeURIComponent(planId)}/refresh`, {
    method: "POST",
    body: JSON.stringify(origin ? { origin } : {}),
  });
  if (out.plan) store(CACHE_KEY, out.plan);
  return out;
}

export async function startSession(planId: string): Promise<Session> {
  const out = await call<{ session: Session }>("/api/v3/sessions", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId }),
  });
  cacheSession(out.session);
  return out.session;
}

export async function advanceSession(
  id: string,
  state: Session["state"],
  extra?: Record<string, unknown>,
): Promise<Session> {
  const out = await call<{ session: Session }>(`/api/v3/sessions/${encodeURIComponent(id)}`, {
    method: "POST",
    body: JSON.stringify({ state, ...(extra ?? {}) }),
  });
  cacheSession(out.session);
  return out.session;
}

export async function health(): Promise<Record<string, unknown>> {
  return call<Record<string, unknown>>("/health");
}
