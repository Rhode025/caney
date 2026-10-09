/**
 * Service worker. §42.
 *
 * The rule that shapes it: WHEN OFFLINE, NEVER IMPLY THE DATA IS CURRENT. Every page and
 * every JSON file is NETWORK-FIRST with a cache fallback, and each one reads its own build
 * stamp to decide what to say. A cached water number is served with its age attached or
 * not at all. Only scripts and styles are served from cache, revalidated behind it.
 */
const VERSION = "caney-v2-2";   // bump clears every older cache on activate
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

  // Pages and data are NETWORK-FIRST, cache as the offline fallback. Every page here is
  // rebuilt hourly and carries live readings; cache-first served a river page from the
  // first visit forever, so caney.html said "built 3 days ago" while the live copy was an
  // hour old. A cached page still reads its own build stamp and says how old it is.
  if (req.mode === "navigate" || /\.(html|json)$/.test(url.pathname)) {
    e.respondWith(
      fetch(req).then((r) => {
        if (r.ok && r.type === "basic") {
          const copy = r.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
        }
        return r;
      }).catch(() => caches.match(req).then((r) =>
        r || (req.mode === "navigate" ? caches.match("./offline.html") : offline())))
    );
    return;
  }

  // Scripts and styles are not content-hashed, so serve the cached copy for speed but
  // refresh it in the background — the next load picks up a new deploy.
  e.respondWith(
    caches.match(req).then((hit) => {
      const net = fetch(req).then((r) => {
        if (r.ok && r.type === "basic") {
          const copy = r.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
        }
        return r;
      });
      if (hit) { net.catch(() => {}); return hit; }
      return net.catch(() => offline());
    })
  );
});

function offline() {
  return new Response(JSON.stringify({ offline: true }), {
    status: 503, headers: { "content-type": "application/json" },
  });
}
