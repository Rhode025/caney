/**
 * Local preferences. §16, §66.
 *
 * ALL OF IT STAYS ON THE DEVICE. §16 is explicit that saved origins are local by default
 * and that Caney must not build a travel-history database, and the server enforces its
 * half by redacting the origin out of every stored plan. This is the other half: the
 * coordinates live in localStorage and are attached to a request only when that request
 * needs them.
 *
 * No account, for a personal tool that does not want one.
 */
export interface Origin {
  id: string;
  label: string;
  lat: number;
  lon: number;
}

export interface Prefs {
  origin: Origin | null;
  savedOrigins: Origin[];
  craft: string;
  method: string;
  species: string;
  maxDriveMinutes: number | null;
  theme: "system" | "light" | "dark";
  notifications: boolean;
}

const KEY = "caney.v3.prefs";

export const DEFAULTS: Prefs = {
  origin: null,
  savedOrigins: [],
  craft: "any",
  method: "either",
  species: "striped_bass",
  maxDriveMinutes: null,
  theme: "system",
  notifications: false,
};

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Prefs>) };
  } catch {
    return { ...DEFAULTS };
  }
}

export function savePrefs(p: Prefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* storage unavailable — preferences simply do not persist */
  }
}

/** §15 — location permission is optional, always. A refusal is not an error. */
export async function currentLocation(): Promise<Origin | null> {
  if (!("geolocation" in navigator)) return null;
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          id: "current",
          label: "Current location",
          lat: Number(pos.coords.latitude.toFixed(5)),
          lon: Number(pos.coords.longitude.toFixed(5)),
        }),
      () => resolve(null),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 120000 },
    );
  });
}
