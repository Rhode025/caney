/**
 * The home screen. §42, §43, §15.
 *
 * Species first, then a compact constraint composer. §42 is explicit about not showing
 * nine time chips, five craft chips and a settings panel at once, so the day is chosen
 * with four presets and everything else is behind "Custom" — which is where the people
 * who want to set a departure minute will look, and where nobody else has to.
 *
 * Origin is optional (§15) and stays local (§16). Without one the request is a fishing
 * window, which is exactly the 2.1 contract and still a perfectly good answer; with one
 * it becomes a door-to-door trip.
 */
import { useState } from "preact/hooks";
import { prefs, setPrefs, loading, error } from "../state/store";
import { currentLocation } from "../state/prefs";
import { SPECIES_LABEL, CRAFT_LABEL, METHOD_LABEL } from "../format";
import type { Craft, Method, PlanRequest, Species } from "../api/types";

const SPECIES: Species[] = ["striped_bass", "smallmouth", "largemouth", "trout"];
const CRAFTS: Craft[] = ["any", "wade", "kayak", "drift", "power"];
const METHODS: Method[] = ["either", "fly", "conventional"];

type Preset = "now" | "tomorrow_am" | "tomorrow_pm" | "custom";

const PRESETS: Array<{ id: Preset; label: string }> = [
  { id: "now", label: "Go now" },
  { id: "tomorrow_am", label: "Tomorrow morning" },
  { id: "tomorrow_pm", label: "Tomorrow evening" },
  { id: "custom", label: "Custom" },
];

function atLocal(dayOffset: number, hour: number, minute = 0): Date {
  const d = new Date();
  d.setDate(d.getDate() + dayOffset);
  d.setHours(hour, minute, 0, 0);
  return d;
}

function windowFor(preset: Preset, custom: { depart: string; back: string }) {
  if (preset === "custom") {
    const depart = custom.depart ? new Date(custom.depart) : atLocal(1, 6);
    const back = custom.back ? new Date(custom.back) : atLocal(1, 12);
    return { depart, back };
  }
  if (preset === "now") {
    const depart = new Date();
    const back = new Date(depart.getTime() + 5 * 3600_000);
    return { depart, back };
  }
  if (preset === "tomorrow_pm") return { depart: atLocal(1, 16), back: atLocal(1, 21) };
  return { depart: atLocal(1, 5, 30), back: atLocal(1, 11, 30) };
}

export function Home({ onPlan }: { onPlan: (r: PlanRequest) => void }) {
  const p = prefs.value;
  const [preset, setPreset] = useState<Preset>("tomorrow_am");
  const [custom, setCustom] = useState({ depart: "", back: "" });
  const [advanced, setAdvanced] = useState(false);
  const [locating, setLocating] = useState(false);

  const useOrigin = p.origin != null;

  async function locate() {
    setLocating(true);
    const o = await currentLocation();
    setLocating(false);
    if (o) setPrefs({ origin: o });
    else error.value = "Location permission was declined. You can still plan a fishing window.";
  }

  function submit() {
    const { depart, back } = windowFor(preset, custom);
    const req: PlanRequest = {
      species: p.species as Species,
      craft: p.craft as Craft,
      method: p.method as Method,
      availability: useOrigin
        ? { depart_after: depart.toISOString(), return_by: back.toISOString() }
        : { fish_after: depart.toISOString(), fish_before: back.toISOString() },
      origin: useOrigin ? { lat: p.origin!.lat, lon: p.origin!.lon } : null,
      max_drive_minutes: p.maxDriveMinutes,
    };
    onPlan(req);
  }

  const { depart, back } = windowFor(preset, custom);

  return (
    <div class="home">
      <h1 class="ask">What do you want to catch?</h1>

      <div class="species-grid" role="radiogroup" aria-label="Species">
        {SPECIES.map((s) => (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={p.species === s}
            class={"species" + (p.species === s ? " on" : "")}
            onClick={() => setPrefs({ species: s })}
          >
            {SPECIES_LABEL[s]}
          </button>
        ))}
      </div>

      <div class="composer">
        <div class="row">
          <span class="rl">When</span>
          <div class="chips">
            {PRESETS.map((x) => (
              <button
                key={x.id}
                type="button"
                aria-pressed={preset === x.id}
                class={"chip" + (preset === x.id ? " on" : "")}
                onClick={() => setPreset(x.id)}
              >
                {x.label}
              </button>
            ))}
          </div>
        </div>

        {preset === "custom" && (
          <div class="row">
            <span class="rl">Times</span>
            <div class="custom-times">
              <label>
                Leave after
                <input
                  type="datetime-local"
                  value={custom.depart}
                  onInput={(e) => setCustom({ ...custom, depart: (e.target as HTMLInputElement).value })}
                />
              </label>
              <label>
                Back by
                <input
                  type="datetime-local"
                  value={custom.back}
                  onInput={(e) => setCustom({ ...custom, back: (e.target as HTMLInputElement).value })}
                />
              </label>
            </div>
          </div>
        )}

        <div class="row">
          <span class="rl">Leaving from</span>
          <div class="chips">
            <button
              type="button"
              class={"chip" + (useOrigin ? " on" : "")}
              onClick={() => (useOrigin ? setPrefs({ origin: null }) : locate())}
              disabled={locating}
            >
              {locating ? "Locating…" : useOrigin ? p.origin!.label : "Use my location"}
            </button>
            {!useOrigin && <span class="hint">Optional — without it you get a fishing window, not a whole trip.</span>}
          </div>
        </div>

        <div class="row">
          <span class="rl">Boat</span>
          <div class="chips">
            {CRAFTS.map((c) => (
              <button
                key={c}
                type="button"
                aria-pressed={p.craft === c}
                class={"chip" + (p.craft === c ? " on" : "")}
                onClick={() => setPrefs({ craft: c })}
              >
                {CRAFT_LABEL[c]}
              </button>
            ))}
          </div>
        </div>

        <div class="row">
          <span class="rl">Method</span>
          <div class="chips">
            {METHODS.map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={p.method === m}
                class={"chip" + (p.method === m ? " on" : "")}
                onClick={() => setPrefs({ method: m })}
              >
                {METHOD_LABEL[m]}
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          class="link-btn"
          aria-expanded={advanced}
          onClick={() => setAdvanced(!advanced)}
        >
          {advanced ? "Fewer options" : "More options"}
        </button>

        {advanced && (
          <div class="row">
            <span class="rl">Max drive</span>
            <div class="chips">
              {[null, 45, 90, 150].map((v) => (
                <button
                  key={String(v)}
                  type="button"
                  aria-pressed={p.maxDriveMinutes === v}
                  class={"chip" + (p.maxDriveMinutes === v ? " on" : "")}
                  onClick={() => setPrefs({ maxDriveMinutes: v })}
                >
                  {v == null ? "No limit" : `${v} min`}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <p class="summary-line">
        {SPECIES_LABEL[p.species]} · {depart.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })}
        {" – "}
        {back.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} · {CRAFT_LABEL[p.craft]}
      </p>

      <button type="button" class="primary big" onClick={submit} disabled={loading.value}>
        {loading.value ? "Planning…" : "Plan my trip"}
      </button>
    </div>
  );
}
