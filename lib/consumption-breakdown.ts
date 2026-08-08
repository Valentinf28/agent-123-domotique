import type { EnergyInventoryItem } from "./energy-snapshot";

export type ConsumptionLoad = {
  id: string;
  name: string;
  category: string;
  icon: string;
  enabled: boolean;
  powerEntityId?: string;
  showInConsumption?: boolean;
};

export type ConsumptionBreakdownItem = {
  id: string;
  name: string;
  category: string;
  icon: string;
  watts: number;
  sharePercent: number;
};

function configuredPowerFrom(inventory: EnergyInventoryItem[], entityId: string | undefined) {
  if (!entityId) return 0;
  const item = inventory.find((candidate) => candidate.entityId === entityId);
  const value = Number(item?.state);
  if (!Number.isFinite(value)) return 0;
  const unit = String(item?.attributes?.unit_of_measurement ?? "W").toLowerCase();
  return Math.max(0, Math.round(unit === "kw" ? value * 1000 : value));
}

export function consumptionBreakdownFromInventory(
  inventory: EnergyInventoryItem[],
  loads: ConsumptionLoad[],
  homeWatts: number,
): ConsumptionBreakdownItem[] {
  const usedPowerEntities = new Set<string>();
  const measured = loads
    .filter((load) => load.enabled && load.showInConsumption !== false && load.powerEntityId)
    .filter((load) => {
      const entityId = load.powerEntityId!.trim().toLowerCase();
      if (!entityId || usedPowerEntities.has(entityId)) return false;
      usedPowerEntities.add(entityId);
      return true;
    })
    .map((load) => ({ ...load, watts: configuredPowerFrom(inventory, load.powerEntityId) }))
    .filter((load) => load.watts >= 5)
    .sort((left, right) => right.watts - left.watts);
  const measuredTotal = measured.reduce((sum, load) => sum + load.watts, 0);
  const total = Math.max(homeWatts, measuredTotal, 1);
  const result: ConsumptionBreakdownItem[] = measured.map((load) => ({
    id: load.id,
    name: load.name,
    category: load.category,
    icon: load.icon,
    watts: load.watts,
    sharePercent: Math.min(100, Math.round(load.watts / total * 100)),
  }));
  const unallocated = Math.max(0, homeWatts - measuredTotal);
  if (unallocated >= 5) result.push({
    id: "other-home",
    name: "Autres usages de la maison",
    category: "other",
    icon: "⌂",
    watts: unallocated,
    sharePercent: Math.min(100, Math.round(unallocated / total * 100)),
  });
  return result;
}
