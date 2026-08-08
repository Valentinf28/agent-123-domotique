import { HOUSE_BINDINGS } from './house-bindings.generated';
import { resolveEntityCandidate } from './entity-resolution.generated.js';
import type { EnergyInventoryItem } from './energy-snapshot';

function hasBinding(inventory: EnergyInventoryItem[], ids: readonly string[]) {
  return Boolean(resolveEntityCandidate(inventory.map((item) => ({
    item,
    entityId: item.entityId,
    name: item.name,
    deviceClass: item.deviceClass ?? '',
    state: item.state,
  })), ids));
}

export function equipmentCapabilitiesFromInventory(inventory: EnergyInventoryItem[]) {
  return {
    hotWater: hasBinding(inventory, HOUSE_BINDINGS.waterHeater) ||
      hasBinding(inventory, HOUSE_BINDINGS.hotWaterClimate) ||
      hasBinding(inventory, HOUSE_BINDINGS.waterHeaterPower),
    vehicle: hasBinding(inventory, HOUSE_BINDINGS.lektricoState) ||
      hasBinding(inventory, HOUSE_BINDINGS.lektricoPower) ||
      hasBinding(inventory, HOUSE_BINDINGS.teslaModelXBattery) ||
      hasBinding(inventory, HOUSE_BINDINGS.teslaYBattery),
  };
}
