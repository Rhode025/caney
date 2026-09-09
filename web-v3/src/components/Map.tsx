/**
 * MAP — the execution view. §49, §24.
 *
 * Deliberately NOT a tile map. Leaflet plus tiles is ~45 KB and a network dependency at a
 * boat ramp with one bar, and §73 sets a 150 KB budget for a page that has to load there.
 * What the reader needs is sequence and relative position — where to launch, what to fish
 * first, where the move goes — and an SVG built from the plan's own geometry gives that
 * with no tiles and no requests.
 *
 * §24's confidence styling is the load-bearing part: a modelled corridor must not draw
 * like a surveyed pin. The dash and opacity come from the server's own STYLE table, so
 * the map cannot present geography as better known than it is.
 */
import type { PlanEnvelope } from "../api/types";
import { clock } from "../format";

interface Pt { lat: number; lon: number }

function collect(env: PlanEnvelope) {
  const r = env.recommendation;
  const pts: Array<{ p: Pt; label: string; n: number | null; kind: string; conf: string }> = [];
  const launch = (r.access?.launch ?? null) as { lat?: number; lon?: number; name?: string } | null;
  if (launch?.lat != null && launch.lon != null) {
    pts.push({ p: { lat: launch.lat, lon: launch.lon }, label: launch.name ?? "Launch", n: null, kind: "launch", conf: "" });
  }
  const geom = r.location.geometry as { points?: number[][]; evidence?: string } | null;
  const line: Pt[] = (geom?.points ?? []).map((c) => ({ lat: c[0]!, lon: c[1]! }));
  const segs = (r.itinerary?.segments ?? []).filter((s) => s.type === "fish");
  segs.forEach((s, i) => {
    const at = line.length ? line[Math.min(i, line.length - 1)]! : null;
    if (at) pts.push({ p: at, label: s.feature_name || s.zone_name, n: i + 1, kind: "fish", conf: s.feature_confidence });
  });
  return { pts, line, evidence: geom?.evidence ?? "" };
}

const DASH: Record<string, string> = {
  VERIFIED_ACCESS: "", VERIFIED_ZONE: "", AGENCY_DESCRIBED_REACH: "10 6",
  MODELED_HABITAT: "4 6", UNVERIFIED_CANDIDATE: "2 8",
};

export function PlanMap({ env }: { env: PlanEnvelope }) {
  const { pts, line, evidence } = collect(env);
  const all = [...line, ...pts.map((x) => x.p)];
  if (!all.length) {
    return <p class="empty">No mapped geometry for this water.</p>;
  }
  const lats = all.map((p) => p.lat), lons = all.map((p) => p.lon);
  const pad = 0.012;
  const minLat = Math.min(...lats) - pad, maxLat = Math.max(...lats) + pad;
  const minLon = Math.min(...lons) - pad, maxLon = Math.max(...lons) + pad;
  const W = 340, H = 260;
  const x = (lon: number) => ((lon - minLon) / (maxLon - minLon || 1)) * W;
  const y = (lat: number) => H - ((lat - minLat) / (maxLat - minLat || 1)) * H;

  const segs = (env.recommendation.itinerary?.segments ?? []).filter((s) => s.type === "fish");

  return (
    <div class="mapview">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        class="map-svg"
        role="img"
        aria-label={`Plan map for ${env.recommendation.location.name}: ${pts.length} marked positions`}
      >
        {line.length > 1 && (
          <polyline
            points={line.map((p) => `${x(p.lon)},${y(p.lat)}`).join(" ")}
            class="reach"
            stroke-dasharray={DASH[evidence] || undefined}
          />
        )}
        {pts.map((pt, i) => (
          <g key={i} class={"pin pin-" + pt.kind}>
            <circle cx={x(pt.p.lon)} cy={y(pt.p.lat)} r={pt.n ? 12 : 9} />
            {pt.n != null && (
              <text x={x(pt.p.lon)} y={y(pt.p.lat) + 4} text-anchor="middle">{pt.n}</text>
            )}
          </g>
        ))}
      </svg>

      <ol class="map-key">
        {pts.map((pt, i) => (
          <li key={i}>
            <span class={"badge " + (pt.n ? "num" : "launch")}>{pt.n ?? "L"}</span>
            <span>
              {pt.label}
              {pt.conf && <span class="tiny prov"> · {pt.conf.toLowerCase().replace(/_/g, " ")}</span>}
            </span>
          </li>
        ))}
      </ol>

      <ol class="map-steps">
        {segs.map((s, i) => (
          <li key={i}>
            <span class="badge num">{i + 1}</span>
            <span>
              {clock(s.start)}–{clock(s.end)} · {s.feature_name || s.zone_name}
            </span>
          </li>
        ))}
      </ol>

      {evidence && (
        <p class="tiny">
          The reach is drawn as {evidence.toLowerCase().replace(/_/g, " ")}. Dashed means the
          shape is described rather than surveyed — fish the stretch, not the line.
        </p>
      )}
    </div>
  );
}
