/**
 * The map. §34.
 *
 * NO INVENTED COORDINATES. A zone whose geometry is a corridor is drawn as a corridor;
 * only an access point that carries verified coordinates becomes a pin. A textual source
 * describing "the dam downstream to the Caney Fork mouth" produces a line, never a
 * fictional secret spot.
 *
 * Leaflet is loaded from the locally bundled copy so the map works offline (§42). If it
 * is missing the block degrades to a static list of coordinates rather than an empty box.
 */
const LEAFLET_JS = "assets/leaflet.js";
const LEAFLET_CSS = "assets/leaflet.css";
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

let loading = null;

function ensureLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (loading) return loading;
  loading = new Promise((res, rej) => {
    const css = document.createElement("link");
    css.rel = "stylesheet"; css.href = LEAFLET_CSS;
    document.head.appendChild(css);
    const s = document.createElement("script");
    s.src = LEAFLET_JS;
    s.onload = () => res(window.L);
    s.onerror = () => rej(new Error("leaflet unavailable"));
    document.head.appendChild(s);
  });
  return loading;
}

export async function draw(el) {
  let cfg;
  try { cfg = JSON.parse(el.getAttribute("data-geometry")); } catch (e) { return; }
  const pts = (cfg.geom && cfg.geom.points) || [];
  if (!pts.length) return;

  let L;
  try { L = await ensureLeaflet(); } catch (e) { return fallback(el, cfg); }
  if (!L) return fallback(el, cfg);

  const map = L.map(el, { scrollWheelZoom: false });
  L.tileLayer(TILES, { maxZoom: 17, attribution: "© OpenStreetMap contributors" }).addTo(map);

  const layers = [];
  if (cfg.geom.kind === "point" && pts.length === 1) {
    layers.push(L.circleMarker(pts[0], { radius: 9, color: "#0a5ec2", weight: 3,
      fillOpacity: .35 }).bindPopup(esc(cfg.name)).addTo(map));
  } else {
    layers.push(L.polyline(pts, { color: "#0a5ec2", weight: 6, opacity: .75 })
      .bindPopup(esc(cfg.name) + " — " + esc(cfg.geom.note || "")).addTo(map));
  }
  for (const a of cfg.access || []) {
    if (a.lat === null || a.lat === undefined) continue;
    const isLaunch = cfg.launch && a.id === cfg.launch.id;
    const isTakeout = cfg.takeout && a.id === cfg.takeout.id;
    layers.push(L.circleMarker([a.lat, a.lon], {
      radius: isLaunch ? 9 : 6,
      color: isLaunch ? "#17864a" : isTakeout ? "#96650a" : "#5a6b7c",
      weight: 3, fillOpacity: a.verified ? .8 : .25,
    }).bindPopup(
      "<b>" + esc(a.name) + "</b><br>" + esc(a.note || "") +
      "<br><i>" + esc(a.verified ? "verified: " + (a.source || "") :
                      "coordinates NOT verified to RIVER_SPEC §2") + "</i>"
    ).addTo(map));
  }
  map.fitBounds(L.featureGroup(layers).getBounds().pad(0.25));
}

function fallback(el, cfg) {
  const rows = (cfg.access || []).filter((a) => a.lat !== null && a.lat !== undefined)
    .map((a) => `<li>${esc(a.name)} — ${a.lat.toFixed(5)}, ${a.lon.toFixed(5)}` +
                `${a.verified ? "" : " <i>(unverified)</i>"}</li>`).join("");
  el.innerHTML = `<div style="padding:14px;font-size:13px">
    <b>Map unavailable</b> — coordinates for ${esc(cfg.name)}:
    <ul style="margin:8px 0 0;padding-left:18px">${rows}</ul></div>`;
  el.style.height = "auto";
}

function esc(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
