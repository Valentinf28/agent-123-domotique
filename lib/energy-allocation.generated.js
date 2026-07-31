// Généré depuis ma-maison-portail-site/shared/energy-allocation.js. Ne pas modifier à la main.
const unavailableStates = new Set(['', 'unknown', 'unavailable', 'none', 'null']);

export function entityIsAvailable(entity) {
  return Boolean(entity)
    && !unavailableStates.has(String(entity.state ?? '').trim().toLowerCase());
}

export function powerValueWatts(value, unit = 'W', fallback = 0) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  const normalizedUnit = String(unit || 'W').trim().toLowerCase();
  if (normalizedUnit === 'kw') return numeric * 1000;
  if (normalizedUnit === 'mw') return numeric * 1000000;
  return numeric;
}

export function powerEntityWatts(entity, fallback = 0) {
  if (!entityIsAvailable(entity)) return fallback;
  return powerValueWatts(
    entity.state,
    entity.attributes?.unit_of_measurement || 'W',
    fallback,
  );
}

export function allocateHomeAndVehiclePower({
  totalHomeWatts,
  chargerWatts,
  fallbackVehicleWatts = 0,
  chargerAvailable = true,
}) {
  const measuredHome = Math.max(0, Number(totalHomeWatts) || 0);
  const measuredCharger = Math.max(0, Number(chargerWatts) || 0);
  const fallbackVehicle = Math.max(0, Number(fallbackVehicleWatts) || 0);
  const vehicleWatts = chargerAvailable ? measuredCharger : fallbackVehicle;

  return {
    // Le compteur général inclut la borne. On la retire de la maison pour ne
    // représenter sa puissance qu'une fois, sur la branche du véhicule.
    homeWatts: Math.max(0, measuredHome - (chargerAvailable ? measuredCharger : 0)),
    vehicleWatts,
  };
}

export function flowDurationMs(powerWatts) {
  const pixelsPerSecond = 6 + Math.min(Math.abs(Number(powerWatts) || 0), 10000) * 0.009;
  return Math.max(500, Math.round(32000 / pixelsPerSecond));
}

export function formatWatts(powerWatts) {
  return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(Math.abs(Number(powerWatts) || 0))} W`;
}
