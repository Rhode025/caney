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

/**
 * §32, §73 — draw the itinerary in sequence, with geometry styled by how well we know it.
 *
 * The rule that shapes this: weakly inferred geography must never be rendered with the
 * same visual certainty as an official coordinate. A verified ramp is a solid pin; an
 * agency-described reach is a dashed corridor; modelled habitat is a dotted area. The
 * reader can tell the difference at a glance, which is the point — a confident-looking
 * pin on water nobody has checked is the most expensive thing this app could draw.
 */
const EVIDENCE_STYLE = {
  VERIFIED_ACCESS: { weight: 4, opacity: 0.95, dash: null },
  VERIFIED_ZONE: { weight: 6, opacity: 0.80, dash: null },
  AGENCY_DESCRIBED_REACH: { weight: 6, opacity: 0.62, dash: "10 7" },
  MODELED_HABITAT: { weight: 3, opacity: 0.38, dash: "4 7" },
  UNVERIFIED_CANDIDATE: { weight: 2, opacity: 0.26, dash: "2 8" },
};
const SEQ_COLOR = ["#0a5ec2", "#96650a", "#6b3fa0"];
const LAUNCH_COLOR = "#12723e";

export async function draw(el) {
  let cfg;
  try { cfg = JSON.parse(el.getAttribute("data-geometry")); } catch (e) { return; }
  const seq = (cfg.sequence || []).filter((z) => z.geometry && (z.geometry.points || []).length);
  if (!seq.length) return;

  let L;
  try { L = await ensureLeaflet(); } catch (e) { return fallback(el, seq); }
  if (!L) return fallback(el, seq);

  const map = L.map(el, { scrollWheelZoom: false });
  L.tileLayer(TILES, { maxZoom: 17, attribution: "© OpenStreetMap contributors" }).addTo(map);
  const layers = [];

  seq.forEach((z, i) => {
    const color = SEQ_COLOR[Math.min(i, SEQ_COLOR.length - 1)];
    const ev = z.geometry.evidence || "MODELED_HABITAT";
    const st = EVIDENCE_STYLE[ev] || EVIDENCE_STYLE.MODELED_HABITAT;
    const label = z.geometry.evidence_label || ev;
    const popup = `<b>${i + 1}. ${esc(z.name)}</b><br>${esc(z.geometry.note || "")}` +
                  `<br><i>${esc(label)} — ${esc(z.geometry.source || "")}</i>`;

    if (z.geometry.kind === "point" && z.geometry.points.length === 1) {
      layers.push(L.circleMarker(z.geometry.points[0], {
        radius: 10, color, weight: st.weight, opacity: st.opacity, fillOpacity: st.opacity * 0.4,
        dashArray: st.dash,
      }).bindPopup(popup).addTo(map));
    } else if (z.geometry.kind === "area") {
      layers.push(L.polygon(z.geometry.points, {
        color, weight: st.weight, opacity: st.opacity, fillOpacity: st.opacity * 0.22,
        dashArray: st.dash,
      }).bindPopup(popup).addTo(map));
    } else {
      layers.push(L.polyline(z.geometry.points, {
        color, weight: st.weight, opacity: st.opacity, dashArray: st.dash,
      }).bindPopup(popup).addTo(map));
    }

    // The sequence number, so a multi-zone plan reads as 1 → 2 → 3 (§73).
    const centre = z.geometry.points.length === 1 ? z.geometry.points[0]
      : centroid(z.geometry.points);
    layers.push(L.marker(centre, {
      icon: L.divIcon({ className: "seqpin", html: `<span>${i + 1}</span>`,
                        iconSize: [26, 26], iconAnchor: [13, 13] }),
      keyboard: false,
    }).bindPopup(popup).addTo(map));

    for (const a of z.access || []) {
      if (a.lat === null || a.lat === undefined) continue;
      const isLaunch = z.launch && a.id === z.launch;
      const ast = EVIDENCE_STYLE[a.evidence] || EVIDENCE_STYLE.UNVERIFIED_CANDIDATE;
      layers.push(L.circleMarker([a.lat, a.lon], {
        radius: isLaunch ? 9 : 6,
        color: isLaunch ? LAUNCH_COLOR : color,
        weight: ast.weight, opacity: Math.max(0.5, ast.opacity),
        fillOpacity: a.verified ? 0.85 : 0.2,
        dashArray: a.verified ? null : "2 4",
      }).bindPopup(
        `<b>${esc(a.name)}</b>${isLaunch ? " — LAUNCH" : ""}<br>${esc(a.note || "")}` +
        `<br><i>${esc(a.evidence_label || (a.verified ? "verified" : "unverified"))}: ` +
        `${esc(a.source || "")}</i>`
      ).addTo(map));
    }
  });

  map.fitBounds(L.featureGroup(layers).getBounds().pad(0.22));
}

function centroid(points) {
  let la = 0, lo = 0;
  for (const p of points) { la += p[0]; lo += p[1]; }
  return [la / points.length, lo / points.length];
}

function fallback(el, seq) {
  const rows = seq.map((z, i) => {
    const pts = (z.access || []).filter((a) => a.lat !== null && a.lat !== undefined)
      .map((a) => `<li>${esc(a.name)} — ${a.lat.toFixed(5)}, ${a.lon.toFixed(5)}` +
                  `${a.verified ? "" : " <i>(unverified)</i>"}</li>`).join("");
    return `<b>${i + 1}. ${esc(z.name)}</b><ul style="margin:4px 0 8px;padding-left:18px">${rows}</ul>`;
  }).join("");
  el.innerHTML = `<div style="padding:14px;font-size:13px"><b>Map unavailable</b><br>${rows}</div>`;
  el.style.height = "auto";
}

function esc(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
