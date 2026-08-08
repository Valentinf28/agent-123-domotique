const unavailableStates = new Set(['', 'unknown', 'unavailable', 'none', 'null']);

export function normalizeEntityText(value = '') {
  return String(value)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function entityStateIsAvailable(state) {
  return !unavailableStates.has(String(state ?? '').trim().toLowerCase());
}

export function scoreEntityCandidate(candidate, aliases) {
  const entityId = normalizeEntityText(candidate?.entityId);
  const searchable = normalizeEntityText(
    `${candidate?.entityId || ''} ${candidate?.name || ''} ${candidate?.deviceClass || ''}`,
  );

  return aliases.reduce((best, alias, aliasIndex) => {
    const target = normalizeEntityText(alias);
    if (!target) return best;
    const priority = Math.max(0, 999 - aliasIndex);
    if (entityId === target) return Math.max(best, 10000 + priority);
    if (searchable.includes(target)) return Math.max(best, 5000 + target.length + priority);
    const words = target.split(' ').filter(Boolean);
    if (words.length > 1 && words.every((word) => searchable.includes(word))) {
      return Math.max(best, 2500 + words.length + priority);
    }
    return best;
  }, 0);
}

export function resolveEntityCandidate(candidates, aliases) {
  const ranked = candidates
    .map((candidate, index) => ({
      candidate,
      index,
      available: entityStateIsAvailable(candidate?.state),
      score: scoreEntityCandidate(candidate, aliases),
    }))
    .filter(({ score }) => score > 0)
    .sort((left, right) => (
      Number(right.available) - Number(left.available)
      || right.score - left.score
      || left.index - right.index
    ));
  return ranked[0]?.candidate ?? null;
}
