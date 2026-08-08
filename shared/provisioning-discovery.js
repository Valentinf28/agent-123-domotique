import { entityStateIsAvailable, normalizeEntityText, scoreEntityCandidate } from './entity-resolution.js';

const domainsByCategory = {
  'eclairage': ['light', 'switch'],
  'capteur': ['sensor', 'binary_sensor'],
  'securite': ['binary_sensor', 'lock', 'alarm_control_panel', 'camera'],
  'recharge': ['switch', 'number', 'select', 'sensor', 'binary_sensor'],
  'chauffage': ['climate', 'water_heater', 'switch', 'sensor'],
  'solaire': ['sensor'],
  'piscine': ['switch', 'sensor', 'climate', 'number', 'select'],
  'eau chaude': ['switch', 'sensor', 'water_heater'],
  'vehicule': ['device_tracker', 'sensor', 'binary_sensor', 'climate', 'lock', 'button'],
};

const genericWords = new Set([
  'plus', 'gen', 'pro', 'smart', 'bridge', 'camera', 'cameras', 'lock', 'vehicle',
  'vehicule', 'sun', 'home', 'assistant', 'module', 'appareil', 'system', 'wifi', 'zigbee',
]);

const showroomOnlyEntityIds = new Set([
  'input_boolean.demo_heating',
  'input_boolean.demo_pool_filtration',
  'input_boolean.demo_pool_heat_pump',
  'input_boolean.demo_nuki_locked',
  'input_boolean.demo_camera_surveillance',
  'input_boolean.chauffe_eau_shelly',
  'input_number.demo_solar_power',
  'input_number.demo_house_power',
  'input_number.demo_battery_soc',
  'input_number.demo_indoor_temperature',
  'input_number.demo_heating_setpoint',
  'input_number.demo_pool_temperature',
  'input_number.demo_pool_setpoint',
  'input_number.demo_tesla_soc',
  'input_number.demo_tesla_charge_power',
  'input_select.demo_mode',
]);

function itemKey(item) {
  return `${String(item?.catalogId ?? item?.id ?? '')}:${String(item?.room ?? 'Maison')}`;
}
function usefulWords(value) {
  return normalizeEntityText(value).split(' ')
    .filter((word) => word.length >= 3 && !genericWords.has(word));
}

function aliasesForItem(item) {
  const brand = normalizeEntityText(item?.brand);
  const modelWords = usefulWords(item?.model);
  const roomWords = usefulWords(item?.room);
  const model = modelWords.join(' ');
  const aliases = [
    model && brand ? `${brand} ${model}` : '',
    model,
    model && roomWords.length ? `${model} ${roomWords.join(' ')}` : '',
    normalizeEntityText(item?.catalogId ?? item?.id),
  ].filter(Boolean);
  return [...new Set(aliases)];
}

export function entityIsShowroomOnly(entity) {
  const entityId = String(entity?.entityId ?? '').toLowerCase();
  const searchable = normalizeEntityText(`${entityId} ${entity?.name ?? ''}`);
  return showroomOnlyEntityIds.has(entityId)
    || entityId.includes('.demo_')
    || searchable.includes('showroom')
    || searchable.includes('demonstration');
}

function candidateScore(entity, item) {
  const aliases = aliasesForItem(item);
  const base = scoreEntityCandidate(entity, aliases);
  if (!base) return 0;
  const searchable = normalizeEntityText(
    `${entity?.entityId ?? ''} ${entity?.name ?? ''} ${entity?.deviceClass ?? ''} ${JSON.stringify(entity?.attributes ?? {})}`,
  );
  const brandWords = usefulWords(item?.brand);
  const modelWords = usefulWords(item?.model);
  const roomWords = usefulWords(item?.room);
  const modelHits = modelWords.filter((word) => searchable.includes(word)).length;
  const brandHits = brandWords.filter((word) => searchable.includes(word)).length;
  const roomHits = roomWords.filter((word) => searchable.includes(word)).length;
  return base + modelHits * 180 + brandHits * 80 + roomHits * 30;
}

export function rankProvisioningCandidates(item, inventory, options = {}) {
  const category = normalizeEntityText(item?.category);
  const domains = domainsByCategory[category] ?? [];
  const isShowroom = options.isShowroom === true;
  const reservedEntityIds = options.reservedEntityIds ?? new Set();
  return (Array.isArray(inventory) ? inventory : [])
    .filter((entity) => entity && typeof entity.entityId === 'string')
    .filter((entity) => entityStateIsAvailable(entity.state))
    .filter((entity) => !domains.length || domains.includes(String(entity.domain ?? entity.entityId.split('.')[0])))
    .filter((entity) => isShowroom || !entityIsShowroomOnly(entity))
    .filter((entity) => !reservedEntityIds.has(entity.entityId))
    .map((entity) => ({
      entityId: entity.entityId,
      name: String(entity.name || entity.entityId),
      domain: String(entity.domain || entity.entityId.split('.')[0]),
      state: String(entity.state ?? ''),
      score: candidateScore(entity, item),
    }))
    .filter((candidate) => candidate.score > 0)
    .sort((left, right) => right.score - left.score || left.entityId.localeCompare(right.entityId));
}

export function analyzeProvisioning({ items, inventory, isShowroom = false }) {
  const plannedItems = Array.isArray(items) ? items : [];
  const entities = Array.isArray(inventory) ? inventory : [];
  const reservedEntityIds = new Set(
    plannedItems.map((item) => String(item?.matchedEntityId ?? '')).filter(Boolean),
  );
  const report = {
    inventoryCount: entities.length,
    preserved: [],
    certain: [],
    ambiguous: [],
    missing: [],
  };

  for (const item of plannedItems) {
    const key = itemKey(item);
    const label = `${String(item?.brand ?? '').trim()} ${String(item?.model ?? '').trim()}`.trim();
    if (item?.matchedEntityId) {
      report.preserved.push({
        key, label, room: item.room, entityId: item.matchedEntityId,
        entityName: item.matchedEntityName || item.matchedEntityId,
      });
      continue;
    }
    const candidates = rankProvisioningCandidates(item, entities, { isShowroom, reservedEntityIds });
    if (!candidates.length) {
      report.missing.push({ key, label, room: item.room, category: item.category });
      continue;
    }
    const top = candidates[0];
    const second = candidates[1];
    const margin = top.score - (second?.score ?? 0);
    const certain = top.score >= 5_300 && (!second || margin >= 300);
    const suggestion = {
      key, label, room: item.room, category: item.category,
      entityId: top.entityId, entityName: top.name, score: top.score,
      candidates: candidates.slice(0, 4),
    };
    if (certain) {
      report.certain.push(suggestion);
      reservedEntityIds.add(top.entityId);
    } else {
      report.ambiguous.push({ ...suggestion, requiresConfirmation: true });
    }
  }
  return report;
}

export function applyCertainProvisioning(items, report) {
  const certainByKey = new Map((report?.certain ?? []).map((suggestion) => [suggestion.key, suggestion]));
  return (Array.isArray(items) ? items : []).map((item) => {
    if (item?.matchedEntityId) return item;
    const suggestion = certainByKey.get(itemKey(item));
    if (!suggestion) return item;
    return {
      ...item,
      status: 'Détecté',
      matchedEntityId: suggestion.entityId,
      matchedEntityName: suggestion.entityName,
    };
  });
}
