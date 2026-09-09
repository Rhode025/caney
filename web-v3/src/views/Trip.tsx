/**
 * Active trip. §51, §52, §53, §54, §56, §57.
 *
 * §51 is emphatic: when the trip starts, the planning report goes away. A person standing
 * in a river at 7:40 does not want a twenty-section document, they want NOW, NEXT, WATCH,
 * and what to throw. The interface changes rather than adding a banner to the old one.
 *
 * §54 — the current step follows the CLOCK. Nobody should be scrolling past the morning's
 * steps at 9:10 to find the one they are on.
 */
import { useEffect, useState } from "preact/hooks";
import { currentSegmentIndex, delta, envelope, now, online, session, tripTab, prefs, mode } from "../state/store";
import { advanceSession, refresh } from "../api/client";
import { clock, countdown, mins } from "../format";
import { PlanMap } from "../components/Map";
import { Brief } from "../components/Brief";
import type { Segment } from "../api/types";

export function Trip() {
  const env = envelope.value;
  const sess = session.value;
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);

  // §12 — while a trip is live, re-check on the cadence the SERVER named for this state.
  useEffect(() => {
    if (!env || !sess?.active || !online.value) return;
    const every = (sess.refresh_seconds ?? 600) * 1000;
    const id = setInterval(() => void check(), every);
    return () => clearInterval(id);
  }, [env?.plan_id, sess?.state, sess?.refresh_seconds, online.value]);

  async function check() {
    if (!env) return;
    setChecking(true);
    try {
      const o = prefs.value.origin;
      const res = await refresh(env.plan_id, o ? { lat: o.lat, lon: o.lon } : null);
      setCheckedAt(res.checked_at);
      delta.value = res.delta;
      if (res.plan) envelope.value = res.plan;
    } catch {
      /* offline or the plan expired — the cached plan stays usable (§60) */
    } finally {
      setChecking(false);
    }
  }

  if (!env) return null;
  const segs = env.recommendation.itinerary?.segments ?? [];
  const i = currentSegmentIndex.value;
  const cur: Segment | undefined = i >= 0 ? segs[i] : undefined;
  const next: Segment | undefined = segs.slice(i + 1).find((s) => s.type !== "change_technique");
  const d = delta.value;

  return (
    <div class="trip">
      {!online.value && (
        <p class="banner offline" role="status">
          Offline. Showing the plan saved at {clock(env.created_at)} — live conditions cannot
          be re-checked.
        </p>
      )}

      {d?.verdict === "MATERIAL_CHANGE" && (
        <div class="banner change" role="alert">
          <strong>Plan changed</strong>
          <p>{d.headline}</p>
          <details>
            <summary>See what changed</summary>
            <ul>
              {d.changes.map((c, k) => (
                <li key={k} class={"m-" + c.materiality}>
                  <strong>{c.label}</strong> {c.was_label} → {c.now_label}
                  <span class="tiny d">{c.why}</span>
                </li>
              ))}
            </ul>
          </details>
          <button type="button" onClick={() => (delta.value = null)}>Got it</button>
        </div>
      )}

      {d?.verdict === "UNCHANGED" && checkedAt && (
        <p class="banner ok" role="status">
          Plan still good. Checked {clock(checkedAt)}.
        </p>
      )}

      {tripTab.value === "now" && (
        <div class="hud">
          <section class="now-card">
            <span class="tiny label">Now</span>
            {cur ? (
              <>
                <h1>{cur.instructions || cur.zone_name}</h1>
                <p class="until">
                  until {clock(cur.end)} · {mins((cur.end - now.value) / 60)} left
                </p>
                {cur.reason && <p class="tiny">{cur.reason}</p>}
              </>
            ) : (
              <h1>Trip complete</h1>
            )}
          </section>

          {next && (
            <section class="next-card">
              <span class="tiny label">Next</span>
              <h2>{next.instructions || next.zone_name}</h2>
              <p class="until">{countdown(next.start, now.value)} · {clock(next.start)}</p>
              {next.reason && <p class="tiny">{next.reason}</p>}
            </section>
          )}

          <section class="watch-card">
            <span class="tiny label">Watch</span>
            {(cur?.triggers ?? []).length > 0 ? (
              <ul>
                {(cur!.triggers as Array<Record<string, unknown>>).slice(0, 3).map((t, k) => (
                  <li key={k}>{String(t.text ?? t.what ?? "")}</li>
                ))}
              </ul>
            ) : (
              <p class="tiny">Nothing scheduled to change in this stretch.</p>
            )}
            {env.recommendation.safety.slice(0, 2).map((c) => (
              <p key={c.id} class="safety-line">{c.text}</p>
            ))}
          </section>

          {env.recommendation.technique && (
            <section class="tech-card">
              <span class="tiny label">{env.recommendation.technique.method_label}</span>
              <p class="big-line">{env.recommendation.technique.primary}</p>
              <p class="tiny">
                {env.recommendation.technique.presentation} · {env.recommendation.technique.depth}
              </p>
            </section>
          )}

          <div class="trip-actions">
            <button type="button" onClick={() => void check()} disabled={checking || !online.value}>
              {checking ? "Checking…" : "Re-check conditions"}
            </button>
            {sess && !sess.terminal && (
              <button
                type="button"
                class="ghost"
                onClick={async () => {
                  const s = await advanceSession(sess.id, "COMPLETED");
                  session.value = s;
                  mode.value = "plan";
                }}
              >
                End trip
              </button>
            )}
          </div>
        </div>
      )}

      {tripTab.value === "map" && <PlanMap env={env} />}
      {tripTab.value === "plan" && <Brief env={env} />}

      <nav class="tripnav" aria-label="Trip">
        {(["now", "map", "plan"] as const).map((t) => (
          <button
            key={t}
            type="button"
            aria-current={tripTab.value === t ? "page" : undefined}
            class={tripTab.value === t ? "on" : ""}
            onClick={() => (tripTab.value = t)}
          >
            {t === "now" ? "Now" : t === "map" ? "Map" : "Plan"}
          </button>
        ))}
      </nav>
    </div>
  );
}
