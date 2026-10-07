// Starts deploy.yml when GitHub's scheduler has not. See wrangler.toml for why.
//
// Never dispatches while a run is queued or in progress (deploy.yml's concurrency group
// would only queue it behind), and never within STALE_MINUTES of the last run's start,
// whatever started it — push, schedule, or this worker.

const ACTIVE = new Set(["queued", "in_progress", "waiting", "pending", "requested"]);

async function gh(env, path, init = {}) {
  return fetch(`https://api.github.com/repos/${env.REPO}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "caney-deploy-trigger",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.headers || {}),
    },
  });
}

export async function decide(env, now = Date.now()) {
  const r = await gh(env, `/actions/workflows/${env.WORKFLOW}/runs?per_page=10`);
  if (!r.ok) return { dispatch: false, why: `runs lookup failed: HTTP ${r.status}` };
  const runs = (await r.json()).workflow_runs || [];
  const active = runs.find((x) => ACTIVE.has(x.status));
  if (active) return { dispatch: false, why: `run ${active.id} is ${active.status}` };
  const last = runs[0];
  if (!last) return { dispatch: true, why: "no runs on record" };
  const age = Math.round((now - Date.parse(last.created_at)) / 60000);
  return {
    dispatch: age >= Number(env.STALE_MINUTES),
    why: `last run ${last.id} (${last.event}, ${last.conclusion}) started ${age} min ago`,
  };
}

async function dispatch(env) {
  const r = await gh(env, `/actions/workflows/${env.WORKFLOW}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: env.REF }),
  });
  return r.status === 204 ? "dispatched" : `dispatch failed: HTTP ${r.status} ${await r.text()}`;
}

export default {
  async scheduled(_event, env) {
    const d = await decide(env);
    const outcome = d.dispatch ? await dispatch(env) : "skipped";
    console.log(JSON.stringify({ ...d, outcome }));
  },

  // GET reports what the next tick would do, without doing it.
  async fetch(_req, env) {
    return Response.json(await decide(env));
  },
};
