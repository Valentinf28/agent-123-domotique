export type GridExportInventoryItem = {
  entityId: string;
  name?: string;
  domain?: string;
};

export type GridExportReleaseCommand = {
  domain: "automation" | "switch";
  service: "turn_off" | "turn_on";
  entityId: string;
};

function normalized(value: string) {
  return value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().replace(/[_-]+/g, " ");
}

export function gridExportReleaseCommands(inventory: GridExportInventoryItem[]) {
  const commands: GridExportReleaseCommand[] = [];
  const policy = inventory.find((item) => {
    const text = normalized(`${item.entityId} ${item.name ?? ""}`);
    return item.entityId.startsWith("automation.") &&
      /injection deye selon vehicule|ma maison deye vehicle export policy/.test(text);
  });
  if (policy) commands.push({ domain: "automation", service: "turn_off", entityId: policy.entityId });

  const exportSwitch = inventory.find((item) => {
    const text = normalized(`${item.entityId} ${item.name ?? ""}`);
    return item.entityId.startsWith("switch.") &&
      /solar sell|export surplus|vente solaire|injection/.test(text);
  });
  if (exportSwitch) commands.push({ domain: "switch", service: "turn_on", entityId: exportSwitch.entityId });
  return commands;
}
