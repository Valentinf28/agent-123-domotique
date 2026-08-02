export const CLIENT_MODULE_KEYS = [
  "home",
  "solar",
  "heating",
  "access",
  "pool",
  "vehicle",
];

export const DEFAULT_SOLAR_INSTALLED_POWER_WP = 9_635;

export function normalizeEnabledModules(value) {
  let requested = value;
  if (typeof requested === "string") {
    try {
      requested = JSON.parse(requested);
    } catch {
      requested = [];
    }
  }
  const selected = new Set(Array.isArray(requested) ? requested : []);
  return CLIENT_MODULE_KEYS.filter((module) => module === "home" || selected.has(module));
}

export function normalizeSolarInstalledPowerWp(value) {
  const watts = Math.round(Number(value));
  return Number.isFinite(watts) && watts > 0
    ? watts
    : DEFAULT_SOLAR_INSTALLED_POWER_WP;
}
