/**
 * Formatting. The only thing the browser is allowed to do to a number. §6.
 *
 * Every time here is rendered from an epoch in the READER'S timezone, never baked at
 * build time — RIVER_SPEC §0, carried forward. A stale plan must degrade to "yesterday
 * 6:40 AM", never claim an old time is now.
 */
export function clock(epoch: number | null | undefined): string {
  if (epoch == null) return "—";
  return new Date(epoch * 1000).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

export function dayLabel(epoch: number | null | undefined): string {
  if (epoch == null) return "";
  const d = new Date(epoch * 1000);
  const today = new Date();
  const same = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const tomorrow = new Date(today.getTime() + 86400_000);
  if (same(d, today)) return "Today";
  if (same(d, tomorrow)) return "Tomorrow";
  return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

export function mins(m: number | null | undefined): string {
  if (m == null) return "—";
  const n = Math.round(m);
  if (n < 60) return `${n} min`;
  const h = Math.floor(n / 60);
  const r = n % 60;
  return r ? `${h}h ${r}m` : `${h}h`;
}

export function countdown(toEpoch: number, fromEpoch: number): string {
  const d = Math.round((toEpoch - fromEpoch) / 60);
  if (d <= 0) return "now";
  return `in ${mins(d)}`;
}

export const SPECIES_LABEL: Record<string, string> = {
  striped_bass: "Stripers",
  smallmouth: "Smallmouth",
  largemouth: "Largemouth",
  trout: "Trout",
};

export const CRAFT_LABEL: Record<string, string> = {
  any: "Any", wade: "Wade", kayak: "Kayak", drift: "Drift boat", power: "Power boat",
};

export const METHOD_LABEL: Record<string, string> = {
  fly: "Fly", conventional: "Conventional", either: "Either",
};

/** §75 — unknown is not zero and must never render as one. */
export function obs(o: { value: unknown; state: string; unit: string } | undefined): string {
  if (!o) return "—";
  if (o.state === "unknown") return "not known";
  if (o.state === "error") return "unavailable";
  if (o.value == null) return "not known";
  const v = typeof o.value === "number" ? Math.round(o.value).toLocaleString() : String(o.value);
  return o.unit ? `${v} ${o.unit}` : v;
}
