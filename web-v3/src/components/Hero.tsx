/**
 * The answer, above the fold. §44, §45, §46.
 *
 * This is the whole product in one block: where to drive, when to leave, when the fishing
 * is, when you are home, and how much to trust it. §44 says the first phone screen should
 * contain almost everything needed to make the decision, and §45 says the four scores
 * belong under WHY rather than dominating the headline — so the confidence here is a
 * WORD, and the numbers are one tap away (§46).
 *
 * The scores are not hidden. They are ranked below the decision, which is the actual
 * complaint: a reader wants to know whether to go, not to audit four gauges first.
 */
import { useState } from "preact/hooks";
import type { PlanEnvelope } from "../api/types";
import { clock, dayLabel, mins, SPECIES_LABEL } from "../format";

const GRADE_CLASS: Record<string, string> = { HIGH: "go", MEDIUM: "cond", LOW: "skip" };

export function Hero({ env, onStart }: { env: PlanEnvelope; onStart: () => void }) {
  const [open, setOpen] = useState(false);
  const r = env.recommendation;
  const s = env.logistics?.summary;
  const doorToDoor = !!env.logistics?.door_to_door;

  const rows: Array<[string, string]> = doorToDoor && s
    ? [
        ["Leave", clock(s.leave)],
        ["Launch", clock(s.launch)],
        ["Fish", `${clock(s.fish_start)}–${clock(s.fish_end)}`],
        ["Off water", clock(s.off_water)],
        ["Home", clock(s.home)],
      ]
    : [["Fish", `${clock(s?.fish_start ?? null)}–${clock(s?.fish_end ?? null)}`]];

  const segs = r.itinerary?.segments?.filter((x) => x.type === "fish") ?? [];

  return (
    <section class="hero" aria-labelledby="hero-dest">
      <p class="eyebrow">
        {SPECIES_LABEL[r.species] ?? r.species} · {dayLabel(s?.fish_start ?? env.created_at)}
      </p>
      <h1 class="dest" id="hero-dest">
        Go to {r.location.name}
      </h1>

      <dl class="times">
        {rows.map(([k, v]) => (
          <div class="t" key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>

      <button
        type="button"
        class={"grade " + (GRADE_CLASS[env.confidence_label] ?? "cond")}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {env.confidence_label.toLowerCase()} confidence
        <span class="caret" aria-hidden="true">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <dl class="scores" aria-label="Confidence breakdown">
          {([
            ["Opportunity", env.opportunity, "How good the fishing window itself is."],
            ["Forecast", env.forecast_confidence, "How well we know what conditions will do."],
            ["Location", env.location_confidence, "How well we know WHERE — the access and the reach."],
            ["Research", env.research_confidence, "How well sourced the biology behind this is."],
          ] as Array<[string, number, string]>).map(([k, v, why]) => (
            <div class="s" key={k}>
              <dt>{k}</dt>
              <dd>{Math.round(v)}</dd>
              <p class="tiny">{why}</p>
            </div>
          ))}
          <p class="tiny grade-why">{env.confidence_explain}</p>
        </dl>
      )}

      {segs.length > 0 && (
        <div class="firsts">
          <div class="first">
            <span class="tiny label">Start</span>
            <p>{segs[0]!.feature_name || segs[0]!.zone_name}</p>
          </div>
          {segs.length > 1 && (
            <div class="first">
              <span class="tiny label">Then</span>
              <p>{segs[segs.length - 1]!.feature_name || segs[segs.length - 1]!.zone_name}</p>
            </div>
          )}
        </div>
      )}

      {r.technique && (
        <div class="firsts">
          <div class="first">
            <span class="tiny label">Start with</span>
            <p>{r.technique.primary}</p>
          </div>
        </div>
      )}

      {s && (
        <p class="tiny fishing-line">
          {mins(s.fishing_minutes)} fishing
          {doorToDoor ? ` · ${mins(s.travel_minutes)} travelling · ${mins(s.overhead_minutes)} rigging` : ""}
        </p>
      )}

      <button type="button" class="primary big" onClick={onStart}>
        Start trip
      </button>
    </section>
  );
}
