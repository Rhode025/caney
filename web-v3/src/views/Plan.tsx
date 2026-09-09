/** The plan screen: BRIEF / MAP / WHY. §47. */
import { envelope, planTab, mode, session, prefs, online } from "../state/store";
import { startSession, advanceSession } from "../api/client";
import { Hero } from "../components/Hero";
import { Brief } from "../components/Brief";
import { Why } from "../components/Why";
import { PlanMap } from "../components/Map";

export function Plan() {
  const env = envelope.value;
  if (!env) return null;

  async function start() {
    try {
      const s = await startSession(env!.plan_id);
      // §13 — permission is asked AFTER Start trip, never on first load.
      if (prefs.value.notifications && "Notification" in window) {
        void Notification.requestPermission();
      }
      session.value = await advanceSession(s.id, "EN_ROUTE", { reason: "start trip" });
    } catch {
      /* offline: the trip still runs from the cached plan (§60, §93) */
    }
    mode.value = "trip";
  }

  return (
    <div class="planview">
      {!online.value && (
        <p class="banner offline" role="status">
          Offline — showing the saved plan. Conditions cannot be re-checked.
        </p>
      )}
      <Hero env={env} onStart={start} />

      <nav class="tabs" aria-label="Plan detail">
        {(["brief", "map", "why"] as const).map((t) => (
          <button
            key={t}
            type="button"
            aria-current={planTab.value === t ? "page" : undefined}
            class={planTab.value === t ? "on" : ""}
            onClick={() => (planTab.value = t)}
          >
            {t === "brief" ? "Brief" : t === "map" ? "Map" : "Why"}
          </button>
        ))}
      </nav>

      {planTab.value === "brief" && <Brief env={env} />}
      {planTab.value === "map" && <PlanMap env={env} />}
      {planTab.value === "why" && <Why env={env} />}

      <p class="reference-link">
        {/* §83, §84 — the river pages are REFERENCE. Reachable from a plan, never a step
            on the way to making one. */}
        <a href={env.recommendation.location.detail_page || "/rivers.html"}>
          View full water details
        </a>
      </p>
    </div>
  );
}
