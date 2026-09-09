/**
 * Service worker. §42.
 *
 * The rule that shapes it: WHEN OFFLINE, NEVER IMPLY THE DATA IS CURRENT. The shell is
 * cache-first because it never changes meaning; plan/data.json is NETWORK-FIRST with a
 * cache fallback, and the app reads the dataset's own `built` timestamp to decide what to
 * say. A cached water number is served with its age attached or not at all.
 */
const VERSION = "caney-v2-1";
const SHELL = [
  "./", "./index.html", "./offline.html",
  "./assets/app.css",
  "./assets/planner/app.js", "./assets/planner/model.js", "./assets/planner/ui.js",
  "./assets/planner/timeline.js", "./assets/planner/format.js", "./assets/planner/map.js",
  "./assets/leaflet.js", "./assets/leaflet.css",
  "./manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION)
    .then((c) => Promise.allSettled(SHELL.map((u) => c.add(u))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // tiles etc. go straight to network

  if (/plan\/(data|parity|build)\.json$/.test(url.pathname) ||
      /plan\/featured\//.test(url.pathname)) {
    e.respondWith(
      fetch(req).then((r) => {
        const copy = r.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
        return r;
      }).catch(() => caches.match(req).then((r) => r || offline()))
    );
    return;
  }

  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((r) => {
      if (r.ok && r.type === "basic") {
        const copy = r.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
      }
      return r;
    }).catch(() => (req.mode === "navigate" ? caches.match("./offline.html") : offline())))
  );
});

function offline() {
  return new Response(JSON.stringify({ offline: true }), {
    status: 503, headers: { "content-type": "application/json" },
  });
}
