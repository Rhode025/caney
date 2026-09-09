/**
 * App state. §41, §9.
 *
 * Three product states, not three tabs of one page: PLAN answers "what should I do",
 * TRIP answers "what should I do right now", REFERENCE answers "show me everything".
 * §41 is explicit that mixing them into one scrolling document is the thing to stop doing,
 * and keeping them as separate top-level modes in the state machine is what stops it
 * growing back.
 *
 * The SESSION lifecycle is the server's (caney/domain/session.py). This mirrors it for
 * rendering and never advances it locally — a state the server refused is not a state the
 * app is in.
 */
import { signal, computed } from "@preact/signals";
import type { PlanEnvelope, PlanDelta, Session } from "../api/types";
import { cachedPlan, cachedSession } from "../api/client";
import { loadPrefs, savePrefs, type Prefs } from "./prefs";

export type Mode = "home" | "plan" | "trip" | "reference";
export type PlanTab = "brief" | "map" | "why";
export type TripTab = "now" | "map" | "plan";

export const mode = signal<Mode>("home");
export const planTab = signal<PlanTab>("brief");
export const tripTab = signal<TripTab>("now");

export const envelope = signal<PlanEnvelope | null>(cachedPlan());
export const session = signal<Session | null>(cachedSession());
export const delta = signal<PlanDelta | null>(null);
export const loading = signal<boolean>(false);
export const error = signal<string | null>(null);

/** §60 — offline is a state the UI must show, not a failure it hides. */
export const online = signal<boolean>(navigator.onLine);
window.addEventListener("online", () => (online.value = true));
window.addEventListener("offline", () => (online.value = false));

/** The clock, ticked once a minute. §54 — the current step follows real time. */
export const now = signal<number>(Date.now() / 1000);
setInterval(() => (now.value = Date.now() / 1000), 30_000);

export const prefs = signal<Prefs>(loadPrefs());
export function setPrefs(p: Partial<Prefs>) {
  const next = { ...prefs.value, ...p };
  prefs.value = next;
  savePrefs(next);
}

/** True when the cached plan is being shown without a live check behind it. */
export const stalePlan = computed(() => {
  const e = envelope.value;
  if (!e) return false;
  return now.value > e.expires_at;
});

/** §54 — which segment is happening now, by the clock, not by scroll position. */
export const currentSegmentIndex = computed(() => {
  const segs = envelope.value?.recommendation?.itinerary?.segments ?? [];
  const t = now.value;
  for (let i = 0; i < segs.length; i++) {
    const s = segs[i]!;
    if (t >= s.start && t < s.end) return i;
  }
  // Before the first or after the last: point at the nearest upcoming one, so the HUD
  // reads "next" rather than nothing.
  for (let i = 0; i < segs.length; i++) if (t < segs[i]!.start) return i;
  return segs.length ? segs.length - 1 : -1;
});

export function reset() {
  envelope.value = null;
  session.value = null;
  delta.value = null;
  error.value = null;
  mode.value = "home";
}
