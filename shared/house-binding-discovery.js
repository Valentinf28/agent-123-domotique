import { entityStateIsAvailable, scoreEntityCandidate } from './entity-resolution.js';
import { entityIsShowroomOnly } from './provisioning-discovery.js';

export const ESSENTIAL_HOUSE_BINDINGS = [
  'solarPower',
  'homePower',
  'gridPower',
  'batteryLevel',
  'batteryPower',
  'dailyProduction',
  'dailyConsumption',
  'dailyImport',
  'dailyExport',
];

const bindingLabels = {
  solarPower: 'Production solaire instantanée',
  homePower: 'Consommation de la maison',
  gridPower: 'Échanges avec le réseau',
  batteryLevel: 'Niveau de la batterie',
  batteryPower: 'Charge / décharge de la batterie',
  dailyProduction: 'Production solaire du jour',
  dailyConsumption: 'Consommation du jour',
  dailyImport: 'Énergie achetée aujourd’hui',
  dailyExport: 'Énergie injectée aujourd’hui',
};

function normalizeInventory(inventory, isShowroom) {
  return (Array.isArray(inventory) ? inventory : [])
    .filter((entity) => entity && typeof entity.entityId === 'string')
    .filter((entity) => entityStateIsAvailable(entity.state))
    .filter((entity) => isShowroom || !entityIsShowroomOnly(entity))
    .map((entity) => ({
      entityId: entity.entityId,
      name: String(entity.name || entity.entityId),
      domain: String(entity.domain || entity.entityId.split('.')[0]),
      deviceClass: String(entity.deviceClass || ''),
      state: String(entity.state ?? ''),
    }));
}

export function analyzeHouseBindings({
  profile,
  inventory,
  isShowroom = false,
  essentialKeys = ESSENTIAL_HOUSE_BINDINGS,
  overrides = {},
}) {
  const rawEntities = (Array.isArray(inventory) ? inventory : [])
    .filter((entity) => entity && typeof entity.entityId === 'string')
    .filter((entity) => isShowroom || !entityIsShowroomOnly(entity));
  const entities = normalizeInventory(inventory, isShowroom);
  const rawById = new Map(rawEntities.map((entity) => [entity.entityId, entity]));
  const resolved = [];
  const ambiguous = [];
  const missing = [];
  const bindings = {};

  for (const key of essentialKeys) {
    const aliases = Array.isArray(profile?.[key]) ? profile[key] : [];
    const overrideId = typeof overrides?.[key] === 'string' ? overrides[key] : '';
    const overrideEntity = rawById.get(overrideId);
    if (overrideEntity) {
      resolved.push({
        key,
        label: bindingLabels[key] || key,
        entityId: overrideId,
        entityName: String(overrideEntity.name || overrideId),
        score: 1_000_000,
        source: 'manual',
        candidates: [],
      });
      bindings[key] = overrideId;
      continue;
    }
    const ranked = entities
      .map((entity) => ({ ...entity, score: scoreEntityCandidate(entity, aliases) }))
      .filter((entity) => entity.score > 0)
      .sort((left, right) => right.score - left.score || left.entityId.localeCompare(right.entityId));
    const top = ranked[0];
    if (!top) {
      missing.push({ key, label: bindingLabels[key] || key });
      continue;
    }
    const second = ranked[1];
    const exactIdentifier = top.score >= 10_000;
    const strongUniqueMatch = top.score >= 5_300 && (!second || top.score - second.score >= 300);
    const suggestion = {
      key,
      label: bindingLabels[key] || key,
      entityId: top.entityId,
      entityName: top.name,
      score: top.score,
      candidates: ranked.slice(0, 4),
    };
    if (exactIdentifier || strongUniqueMatch) {
      resolved.push(suggestion);
      bindings[key] = top.entityId;
    } else {
      ambiguous.push({ ...suggestion, requiresConfirmation: true });
    }
  }

  return {
    total: essentialKeys.length,
    ready: missing.length === 0 && ambiguous.length === 0,
    resolved,
    ambiguous,
    missing,
    bindings,
  };
}
