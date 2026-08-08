export type EnergyMeasurement = {
  state: string;
  unit?: string | null;
};

function numeric(item?: EnergyMeasurement | null) {
  if (!item || ["unknown", "unavailable", "none", ""].includes(item.state.trim().toLowerCase())) {
    return null;
  }
  const value = Number(item.state.replace(",", "."));
  return Number.isFinite(value) ? value : null;
}

export function powerWatts(item?: EnergyMeasurement | null) {
  const value = numeric(item);
  if (value === null) return null;
  const unit = item?.unit?.trim().toLowerCase();
  if (unit === "kw") return value * 1_000;
  if (unit === "mw") return value * 1_000_000;
  return value;
}

export function energyWh(item?: EnergyMeasurement | null) {
  const value = numeric(item);
  if (value === null) return null;
  const unit = item?.unit?.trim().toLowerCase();
  if (unit === "kwh") return value * 1_000;
  if (unit === "mwh") return value * 1_000_000;
  return value;
}
