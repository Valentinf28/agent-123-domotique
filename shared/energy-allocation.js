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

export function energyValueKwh(value, unit = 'kWh', fallback = null) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  const normalizedUnit = String(unit || 'kWh').trim().toLowerCase();
  if (normalizedUnit === 'wh') return numeric / 1000;
  if (normalizedUnit === 'mwh') return numeric * 1000;
  return numeric;
}

export function energyEntityKwh(entity, fallback = null) {
  if (!entityIsAvailable(entity)) return fallback;
  return energyValueKwh(
    entity.state,
    entity.attributes?.unit_of_measurement || 'kWh',
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

export function createEnergyFlowState({
  solarWatts,
  homeWatts,
  gridWatts,
  batteryWatts,
  vehicleWatts,
  vehiclePlugged = false,
  activationWatts = 5,
}) {
  const threshold = Math.max(0, Number(activationWatts) || 0);
  const solar = Number(solarWatts) || 0;
  const home = Math.max(0, Number(homeWatts) || 0);
  const grid = Number(gridWatts) || 0;
  const battery = Number(batteryWatts) || 0;
  const vehicle = Math.max(0, Number(vehicleWatts) || 0);

  return {
    solar: { active: solar > threshold, reverse: false },
    // Convention Deye/Home Assistant : réseau positif = import, négatif = export.
    // Le tracé est défini de l'onduleur vers le réseau : l'import est donc inversé.
    grid: {
      active: Math.abs(grid) > threshold,
      reverse: grid > 0,
      direction: grid > 0 ? 'import' : grid < 0 ? 'export' : 'idle',
      arrow: grid > 0 ? '→' : grid < 0 ? '←' : '',
    },
    home: { active: home > threshold, reverse: false },
    // Convention Deye/Home Assistant : batterie positive = décharge, négative = charge.
    // Le tracé est défini de l'onduleur vers la batterie : la décharge est donc inversée.
    battery: {
      active: Math.abs(battery) > threshold,
      reverse: battery > 0,
      direction: battery > 0 ? 'discharging' : battery < 0 ? 'charging' : 'idle',
      arrow: battery > 0 ? '↑' : battery < 0 ? '↓' : '',
    },
    vehicle: {
      active: Boolean(vehiclePlugged) && vehicle > threshold,
      reverse: false,
    },
  };
}

export function flowDurationMs(powerWatts) {
  const pixelsPerSecond = 6 + Math.min(Math.abs(Number(powerWatts) || 0), 10000) * 0.009;
  return Math.max(500, Math.round(32000 / pixelsPerSecond));
}

export function formatWatts(powerWatts) {
  return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(Math.abs(Number(powerWatts) || 0))} W`;
}

export function formatKilowatts(powerWatts) {
  const numeric = Number(powerWatts);
  if (!Number.isFinite(numeric)) return '—';
  return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 }).format(Math.abs(numeric) / 1000)} kW`;
}

export function formatKwh(energyKwh, fallback = '—') {
  const numeric = Number(energyKwh);
  if (!Number.isFinite(numeric)) return fallback;
  return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 }).format(numeric)} kWh`;
}

export function formatPercent(percent, fallback = '—') {
  const numeric = Number(percent);
  if (!Number.isFinite(numeric)) return fallback;
  return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(numeric)} %`;
}

export function formatEuros(amount, fallback = '—') {
  const numeric = Number(amount);
  if (!Number.isFinite(numeric)) return fallback;
  return `${new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(numeric)} €`;
}
