type RelayDossier = {
  publicId: string;
  relayHouseId: string | null;
  reference: string;
};

function relayHouseMap(): Record<string, string> {
  try {
    const parsed = JSON.parse(process.env.RELAY_HOUSE_MAP_JSON ?? "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([reference, houseId]) =>
          reference.length > 0 &&
          typeof houseId === "string" &&
          houseId.length > 0
        )
        .map(([reference, houseId]) => [reference, String(houseId)]),
    );
  } catch {
    return {};
  }
}

export function relayHouseIdForDossier(dossier: RelayDossier) {
  return relayHouseMap()[dossier.reference] ||
    dossier.relayHouseId ||
    dossier.publicId;
}

export function dossierReferenceForRelayHouseId(houseId: string) {
  return Object.entries(relayHouseMap())
    .find(([, mappedHouseId]) => mappedHouseId === houseId)?.[0] ?? null;
}
