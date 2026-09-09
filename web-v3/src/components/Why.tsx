/**
 * WHY — everything that justifies the plan, on demand. §47, §50.
 *
 * This is where 2.1's twenty-section scroll went, and it is the right home for it. §40's
 * hierarchy is ANSWER FIRST, ACTION SECOND, EVIDENCE ON DEMAND: none of this material was
 * wrong, it was simply competing with the decision for the first screen.
 *
 * Collapsed by default and grouped by §50's headings.
 */
import { useState } from "preact/hooks";
import type { PlanEnvelope } from "../api/types";
import { obs } from "../format";

function Section({ title, children, open: initial = false }: {
  title: string; children: preact.ComponentChildren; open?: boolean;
}) {
  const [open, setOpen] = useState(initial);
  return (
    <section class="disc">
      <button type="button" class="disc-h" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>{title}</span>
        <span class="caret" aria-hidden="true">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div class="disc-b">{children}</div>}
    </section>
  );
}

export function Why({ env }: { env: PlanEnvelope }) {
  const r = env.recommendation;
  return (
    <div class="why">
      <Section title="Why this won" open>
        <ul class="bullets">
          {r.why_this_won.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
        {r.verdict_why && <p>{r.verdict_why}</p>}
      </Section>

      <Section title="Water">
        <dl class="kv">
          {Object.entries(r.water).map(([k, v]) => (
            <div key={k}>
              <dt>{k.replace(/_/g, " ")}</dt>
              <dd>
                {obs(v as never)}
                {v.state !== "known" && <span class="tiny warn"> · {v.state}</span>}
              </dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title="Weather">
        <dl class="kv">
          {Object.entries(r.weather).map(([k, v]) => (
            <div key={k}>
              <dt>{k.replace(/_/g, " ")}</dt>
              <dd>{obs(v as never)}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title="Biology">
        <p>{r.location.holds}</p>
        {Object.entries(r.biological_context).map(([k, v]) => (
          <p key={k} class="tiny">
            <strong>{k.replace(/_/g, " ")}:</strong> {String(v)}
          </p>
        ))}
      </Section>

      <Section title={`Research (${env.research_status_label})`}>
        {env.research_status === "disabled" && (
          <p class="tiny">
            Live research is off. The plan is fully deterministic — the seeded agency corpus
            still applies, and nothing here depended on a search.
          </p>
        )}
        <ul class="bullets">
          {r.evidence.map((e, i) => (
            <li key={i}>
              {String((e as Record<string, unknown>).text ?? "")}
              {(e as Record<string, unknown>).source_url ? (
                <>
                  {" "}
                  <a href={String((e as Record<string, unknown>).source_url)} rel="noreferrer">
                    source
                  </a>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Location confidence">
        <p class="big-line">{Math.round(env.location_confidence)}</p>
        <p class="tiny">
          How well we know WHERE, not how good the fishing is. A high score on unverified
          geography would be a strong guess about a place nobody can point to, so this is
          scored and shown separately rather than folded into one number.
        </p>
        <dl class="kv">
          {Object.entries(r.location.location_confidence ?? {}).map(([k, v]) => (
            <div key={k}>
              <dt>{k.replace(/_/g, " ")}</dt>
              <dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title="Scoring">
        <table class="score-table">
          <thead>
            <tr><th scope="col">Component</th><th scope="col">Earned</th><th scope="col">Of</th></tr>
          </thead>
          <tbody>
            {r.score_breakdown.map((l) => (
              <tr key={l.key}>
                <th scope="row">{l.label}<span class="tiny d">{l.why}</span></th>
                <td>{l.earned.toFixed(1)}</td>
                <td>{l.possible.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p class="tiny">
          Models: planner {env.model_versions.planner}, species {env.model_versions.species_model},
          zones {env.model_versions.zone_model}, hydrology {env.model_versions.hydrology}.
        </p>
      </Section>

      <Section title="Freshness">
        <ul class="fresh">
          {r.data_freshness.map((f, i) => (
            <li key={i} class={"st-" + f.state}>
              <span>{f.label}</span>
              <span class="tiny">
                {f.state}
                {f.age ? ` · ${f.age}` : ""}
                {f.source ? ` · ${f.source}` : ""}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Limitations">
        <ul class="bullets">
          {r.limitations.map((l, i) => <li key={i}>{l}</li>)}
          {env.limitations.map((l, i) => <li key={"e" + i}>{l}</li>)}
        </ul>
        <p class="tiny">
          Snapshot {env.snapshot_id}. Every number in this plan came from that frozen input
          set, so it can be replayed exactly rather than reconstructed from today's gauges.
        </p>
      </Section>

      {r.alternatives.length > 0 && (
        <Section title="What else was considered">
          <ul class="alts">
            {r.alternatives.map((a, i) => {
              const x = a as Record<string, unknown>;
              return (
                <li key={i}>
                  <strong>{String(x.name ?? x.zone_id ?? "")}</strong>
                  <p class="tiny">{String(x.why ?? x.reason ?? "")}</p>
                </li>
              );
            })}
          </ul>
        </Section>
      )}
    </div>
  );
}
