/**
 * BRIEF — the actionable itinerary. §47, §48.
 *
 * The order is §48's, and it is the order a guide would say it in: destination, leave,
 * launch, the window, the first feature, the move, what to throw, what to watch. Every
 * leg is a real timed thing, so this is the whole day rather than a fishing report with
 * travel implied.
 */
import type { PlanEnvelope, Leg } from "../api/types";
import { clock, mins } from "../format";

const LEG_ICON: Record<Leg["kind"], string> = {
  depart: "🚪", drive_out: "🚗", prep: "🎒", run_out: "🛥",
  fish: "🎣", move: "↪", run_back: "🛥", takeout: "🎒",
  drive_home: "🚗", home: "🏁",
};

export function Brief({ env }: { env: PlanEnvelope }) {
  const r = env.recommendation;
  const legs = env.logistics?.legs ?? [];
  const segs = r.itinerary?.segments ?? [];
  const fishSegs = segs.filter((s) => s.type === "fish" || s.type === "move_feature");

  return (
    <div class="brief">
      {legs.length > 0 && (
        <section class="card">
          <h2>Your day</h2>
          <ol class="legs">
            {legs.map((l, i) => (
              <li key={i} class={"leg leg-" + l.kind}>
                <span class="ic" aria-hidden="true">{LEG_ICON[l.kind]}</span>
                <span class="lt">{clock(l.start)}</span>
                <span class="ll">
                  {l.label}
                  {l.minutes > 0 && <span class="tiny"> · {mins(l.minutes)}</span>}
                  {l.provenance === "estimated" && l.kind.startsWith("drive") && (
                    <span class="tiny prov"> · estimated</span>
                  )}
                  {l.detail && <span class="tiny d">{l.detail}</span>}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section class="card">
        <h2>On the water</h2>
        <ol class="steps">
          {fishSegs.map((s, i) => (
            <li key={i} class={"step " + s.type}>
              <span class="lt">{clock(s.start)}</span>
              <div>
                <p class="si">{s.instructions}</p>
                {s.reason && <p class="tiny">{s.reason}</p>}
                {s.feature_confidence && (
                  <p class="tiny prov">
                    {s.feature_type.replace(/_/g, " ")} · {s.feature_confidence.toLowerCase().replace(/_/g, " ")}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
      </section>

      {r.technique && (
        <section class="card">
          <h2>What to throw</h2>
          <p class="big-line">{r.technique.primary}</p>
          <dl class="kv">
            {([
              ["Size", r.technique.primary_size],
              ["Colour", r.technique.primary_color],
              ["Line", r.technique.line],
              ["Leader", r.technique.leader],
              ["Depth", r.technique.depth],
              ["Retrieve", r.technique.retrieve],
              ["Target", r.technique.target_structure],
            ] as Array<[string, string]>)
              .filter(([, v]) => !!v)
              .map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
          </dl>
          {r.technique.why && <p class="tiny">{r.technique.why}</p>}
          {r.technique.alternate && (
            <p class="tiny">
              On {r.technique.alternate.method_label?.toLowerCase()}:{" "}
              {r.technique.alternate.primary_fly || r.technique.alternate.primary_lure}
            </p>
          )}
        </section>
      )}

      {r.safety.length > 0 && <SafetyCard env={env} />}

      {r.backup_plan && r.backup_plan.branches.length > 0 && (
        <section class="card">
          <h2>What would change this</h2>
          <ul class="branches">
            {r.backup_plan.branches.map((b, i) => (
              <li key={i}>
                <strong>If {b.if}</strong>
                <p>{b.then}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/**
 * §58 — safety is impossible to miss when it is relevant, and is never collapsed into a
 * generic confidence score. The bound is stated because "earliest" and "typical" are
 * different promises and the difference is the margin somebody is standing in.
 */
export function SafetyCard({ env }: { env: PlanEnvelope }) {
  const claims = env.recommendation.safety;
  if (!claims.length) return null;
  return (
    <section class="card safety" aria-labelledby="safety-h">
      <h2 id="safety-h">Safety</h2>
      <ul class="claims">
        {claims.map((c) => (
          <li key={c.id}>
            <p>{c.text}</p>
            <p class="tiny">
              {c.bound === "earliest" ? "Conservative bound" : c.bound} ·{" "}
              {c.source_url ? (
                <a href={c.source_url} rel="noreferrer">{c.source}</a>
              ) : (
                c.source
              )}
              {c.state !== "known" && <span class="warn"> · {c.state}</span>}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
