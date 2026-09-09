/**
 * Caney 3.0. §41, §62.
 *
 * The browser renders plans. It does not invent them (§2, §6): there is no scoring, no
 * window optimiser, no beam search and no segment logic anywhere under src/. Everything
 * this app knows about which water wins came down the wire from caney/api.
 */
import { render } from "preact";
import { envelope, error, loading, mode, prefs, session } from "./state/store";
import { plan as callPlan, CaneyApiError, cachedPlan } from "./api/client";
import { Home } from "./views/Home";
import { Plan } from "./views/Plan";
import { Trip } from "./views/Trip";
import type { PlanRequest } from "./api/types";
import "./styles/app.css";

function applyTheme() {
  const t = prefs.value.theme;
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
}

async function makePlan(req: PlanRequest) {
  loading.value = true;
  error.value = null;
  try {
    const env = await callPlan(req);
    envelope.value = env;
    mode.value = "plan";
  } catch (e) {
    if (e instanceof CaneyApiError) {
      error.value = e.message;
      // §60/§93 — a request that fails does not erase a plan already in hand.
      if (cachedPlan() && !envelope.value) envelope.value = cachedPlan();
    } else {
      error.value =
        "Could not reach the planner. If you have a saved plan it is still available.";
    }
  } finally {
    loading.value = false;
  }
}

function App() {
  applyTheme();
  const m = mode.value;
  return (
    <div class="app" data-mode={m}>
      {m !== "trip" && (
        <header class="top">
          <button
            type="button"
            class="wordmark"
            onClick={() => (mode.value = "home")}
            aria-label="Caney home"
          >
            Caney
          </button>
          {envelope.value && m === "home" && (
            <button type="button" class="ghost" onClick={() => (mode.value = "plan")}>
              Last plan
            </button>
          )}
          {session.value?.active && (
            <button type="button" class="ghost" onClick={() => (mode.value = "trip")}>
              Resume trip
            </button>
          )}
        </header>
      )}

      {error.value && (
        <p class="banner err" role="alert">
          {error.value}
          <button type="button" onClick={() => (error.value = null)} aria-label="Dismiss">
            ×
          </button>
        </p>
      )}

      {m === "home" && <Home onPlan={makePlan} />}
      {m === "plan" && <Plan />}
      {m === "trip" && <Trip />}
    </div>
  );
}

// A trip already under way wins over the home screen: someone opening the app on the
// water is not starting over.
if (session.value?.active && envelope.value) mode.value = "trip";
else if (envelope.value) mode.value = "home";

render(<App />, document.getElementById("app")!);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" }).catch(() => {
      /* offline support is an enhancement, never a requirement to load */
    });
  });
}
