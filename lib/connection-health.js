export function agentConnectionHealth(lastSeenAt, nowMs = Date.now()) {
  const parsed = typeof lastSeenAt === 'string' ? Date.parse(lastSeenAt) : Number.NaN;
  if (!Number.isFinite(parsed)) {
    return {
      connected: false,
      state: 'never_connected',
      ageSeconds: null,
      message: 'La box ne s’est encore jamais connectée au portail.',
      action: 'Vérifier son alimentation et sa connexion Internet.',
    };
  }
  const ageSeconds = Math.max(0, Math.round((nowMs - parsed) / 1000));
  if (ageSeconds < 60) {
    return {
      connected: true,
      state: 'online',
      ageSeconds,
      message: 'La box communique normalement.',
      action: null,
    };
  }
  if (ageSeconds < 120) {
    return {
      connected: true,
      state: 'delayed',
      ageSeconds,
      message: 'Les dernières données ont un léger retard.',
      action: 'Actualiser dans quelques instants.',
    };
  }
  return {
    connected: false,
    state: 'offline',
    ageSeconds,
    message: 'La box ne transmet plus de données.',
    action: 'Vérifier Internet et redémarrer la box si la coupure persiste.',
  };
}
