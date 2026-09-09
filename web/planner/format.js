/**
 * Formatting, and the day-identity rule. RIVER_SPEC §0.
 *
 * Every time in this app is an EPOCH from Python, labelled here against the reader's own
 * clock. Nothing is ever formatted at build time and nothing is selected by index:
 * "Today" is decided by comparing dates on the device, so a stale build degrades to
 * "Fri · 2d ago" instead of claiming an old day is today.
 */

export const TZ_NOTE = "times shown in your device's local time";

export function hm(epoch) {
  if (epoch === null || epoch === undefined) return "—";
  return new Date(epoch * 1000)
    .toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function dayLabel(epoch, now = Date.now() / 1000) {
  const d = new Date(epoch * 1000), n = new Date(now * 1000);
  const dd = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const nn = new Date(n.getFullYear(), n.getMonth(), n.getDate());
  const diff = Math.round((dd - nn) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  const wd = d.toLocaleDateString([], { weekday: "short" });
  if (diff < 0) return wd + " · " + Math.abs(diff) + "d ago";
  return wd + " · in " + diff + "d";
}

export function whenLabel(start, end, now) {
  return dayLabel(start, now) + " · " + hm(start) + " – " + hm(end);
}

export function ago(epoch, now = Date.now() / 1000) {
  if (!epoch) return "unknown";
  const m = Math.max(0, (now - epoch) / 60);
  if (m < 1) return "just now";
  if (m < 90) return Math.round(m) + " min ago";
  const h = m / 60;
  if (h < 36) return Math.round(h) + " h ago";
  return Math.round(h / 24) + " days old";
}

export function countdown(epoch, now = Date.now() / 1000) {
  const s = epoch - now;
  if (s <= 0) return "now";
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return h ? h + "h " + m + "m" : m + "m";
}

export function num(v, unit) {
  if (v === null || v === undefined) return "unknown";
  const n = typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : v;
  return unit ? n + " " + unit : String(n);
}

/** Unknown must LOOK unknown (§10, §58). Never render a placeholder number. */
export function obs(o) {
  if (!o) return { text: "unknown", state: "unknown" };
  if (o.state === "unknown") return { text: "unknown", state: "unknown" };
  if (o.state === "error") return { text: "unavailable", state: "error" };
  return { text: num(o.value, o.unit), state: o.state };
}

export function esc(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Only http(s) survives. Blocks javascript: and data: URLs in any emitted href. */
export function safeUrl(u) {
  const s = String(u || "").trim();
  return /^https?:\/\//i.test(s) ? s : "";
}
