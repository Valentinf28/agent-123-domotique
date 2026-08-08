import { ENERGY_PROFILE } from "./energy-profile.generated";
import { HOUSE_BINDINGS } from "./house-bindings.generated";
import {
  allocateHomeAndVehiclePower,
  energyValueKwh,
  powerValueWatts,
} from "./energy-allocation.generated.js";

export type EnergyInventoryItem = {
  entityId: string;
  name: string;
  domain: string;
  state: string;
  deviceClass?: string | null;
  attributes?: Record<string, unknown>;
};

export type EnergySnapshotValues = {
  solarWatts: number;
  homeWatts: number;
  gridWatts: number;
  batteryPercent: number;
  batteryWatts: number;
  filtrationWatts: number;
  hotWaterWatts: number;
  vehicleWatts: number;
  dailyProductionWh: number;
  dailyConsumptionWh: number;
};

const snapshotBindings = {
  solarWatts: [...ENERGY_PROFILE.solarPower, "input_number.demo_solar_power"],
  homeWatts: [...ENERGY_PROFILE.homePower, "input_number.demo_house_power"],
  gridWatts: ENERGY_PROFILE.gridPower,
  batteryPercent: [...ENERGY_PROFILE.batteryLevel, "input_number.demo_battery_soc"],
  batteryWatts: ENERGY_PROFILE.batteryPower,
  filtrationWatts: HOUSE_BINDINGS.filtrationPower,
  hotWaterWatts: HOUSE_BINDINGS.waterHeaterPower,
  lektricoWatts: HOUSE_BINDINGS.lektricoPower,
  vehicleFallbackWatts: [
    ...HOUSE_BINDINGS.teslaModelXChargerPower,
    "input_number.demo_tesla_charge_power",
  ],
  dailyProductionWh: ENERGY_PROFILE.dailyProduction,
  dailyConsumptionWh: ENERGY_PROFILE.dailyConsumption,
} as const;

function itemFrom(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  return ids.map((id) => inventory.find((candidate) => candidate.entityId === id))
    .find(Boolean) ?? null;
}

function itemAvailable(item: EnergyInventoryItem | null) {
  return Boolean(item) && !["", "unknown", "unavailable", "none", "null"]
    .includes(String(item?.state ?? "").trim().toLowerCase());
}

function numberFrom(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  const value = Number(itemFrom(inventory, ids)?.state);
  return Number.isFinite(value) ? value : 0;
}

function powerFrom(
  inventory: EnergyInventoryItem[],
  ids: readonly string[],
  fallbackUnit = "W",
) {
  const item = itemFrom(inventory, ids);
  if (!itemAvailable(item)) return 0;
  const unit = typeof item?.attributes?.unit_of_measurement === "string"
    ? item.attributes.unit_of_measurement
    : fallbackUnit;
  return powerValueWatts(item?.state, unit);
}

function energyWhFrom(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  const item = itemFrom(inventory, ids);
  if (!itemAvailable(item)) return 0;
  const unit = typeof item?.attributes?.unit_of_measurement === "string"
    ? item.attributes.unit_of_measurement
    : "kWh";
  return (energyValueKwh(item?.state, unit, null) ?? 0) * 1000;
}

function integer(value: number) {
  return Math.round(Math.max(-100_000, Math.min(100_000, value)));
}

export function energySnapshotFromInventory(
  inventory: EnergyInventoryItem[],
): EnergySnapshotValues {
  const lektrico = itemFrom(inventory, snapshotBindings.lektricoWatts);
  const allocated = allocateHomeAndVehiclePower({
    totalHomeWatts: powerFrom(inventory, snapshotBindings.homeWatts),
    // L'unité transmise par Home Assistant est prioritaire. Le repli kW
    // conserve la compatibilité avec les anciens inventaires Lektrico.
    chargerWatts: powerFrom(inventory, snapshotBindings.lektricoWatts, "kW"),
    fallbackVehicleWatts: powerFrom(inventory, snapshotBindings.vehicleFallbackWatts, "kW"),
    chargerAvailable: itemAvailable(lektrico),
  });
  return {
    solarWatts: integer(powerFrom(inventory, snapshotBindings.solarWatts)),
    homeWatts: integer(allocated.homeWatts),
    gridWatts: integer(powerFrom(inventory, snapshotBindings.gridWatts)),
    batteryPercent: integer(numberFrom(inventory, snapshotBindings.batteryPercent)),
    batteryWatts: integer(powerFrom(inventory, snapshotBindings.batteryWatts)),
    filtrationWatts: integer(powerFrom(inventory, snapshotBindings.filtrationWatts)),
    hotWaterWatts: integer(powerFrom(inventory, snapshotBindings.hotWaterWatts)),
    vehicleWatts: integer(allocated.vehicleWatts),
    dailyProductionWh: integer(energyWhFrom(inventory, snapshotBindings.dailyProductionWh)),
    dailyConsumptionWh: integer(energyWhFrom(inventory, snapshotBindings.dailyConsumptionWh)),
  };
}
