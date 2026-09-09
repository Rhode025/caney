/**
 * Offline. §60, §61, §93.
 *
 * §61 IS THE DESIGN DECISION HERE, and it is a subtraction. Caney 2.1 shipped a full
 * planner in the browser, so it could generate a NEW plan offline. That is gone, and
 * deliberately: once the API is canonical there must be one implementation (§2), and
 * keeping a second one alive purely for offline would mean two models that could disagree
 * about safety — with the offline one, by construction, running on older data.
 *
 * So offline serves the TRIP YOU ARE ON. The shell, the last plan, its map geometry and
 * its safety claims are available; a new authoritative plan is not, and the UI says so
 * rather than pretending (§60). Cleaner and safer than the alternative.
 */
const VERSION = "caney-v3-1";
const SHELL = "shell-" + VERSION;

// The shell only. Plan data lives in localStorage, written by the API client, because it
// has to survive independently of whether any fetch succeeded.
const PRECACHE = ["/app/", "/app/index.html"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(SHELL).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // NEVER cache the API. A stale plan served as though it were live is exactly the
  // failure §60 names: the app must say "saved at 5:48, cannot re-check", not hand back
  // yesterday's generation forecast with a fresh timestamp on it.
  if (url.pathname.startsWith("/api/")) return;

  // Vite content-hashes assets, so cache-first is safe and fast.
  if (url.pathname.startsWith("/app/assets/")) {
    e.respondWith(
      caches.match(req).then((hit) =>
        hit || fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(req, copy));
          return res;
        })),
    );
    return;
  }

  // Navigations: network first, shell as the fallback. Someone opening the app on the
  // water gets the shell, which renders the saved plan out of localStorage.
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).catch(() =>
        caches.match("/app/index.html").then((r) => r || Response.error())),
    );
  }
});
