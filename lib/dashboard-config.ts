type DashboardDevice = {
  category: string;
  entityId: string;
  name: string;
  room: string;
};

const viewCatalog = {
  home: { title: "Maison", path: "0", icon: "mdi:home-variant-outline" },
  solar: { title: "Solaire", path: "solaire", icon: "mdi:solar-power" },
  heating: { title: "Chauffage", path: "chauffage", icon: "mdi:home-thermometer-outline" },
  access: { title: "Équipements", path: "equipements", icon: "mdi:lightbulb-group-outline" },
  pool: { title: "Piscine", path: "piscine", icon: "mdi:pool" },
  vehicle: { title: "Véhicule", path: "vehicule", icon: "mdi:car-electric" },
} as const;

const categoriesByModule: Record<keyof typeof viewCatalog, string[]> = {
  home: [],
  solar: ["solaire", "énergie"],
  heating: ["chauffage", "climat", "eau chaude"],
  access: ["éclairage", "sécurité", "volets", "accès", "caméra", "interrupteurs"],
  pool: ["piscine", "spa"],
  vehicle: ["véhicule", "recharge"],
};

function normalized(value: string) {
  return value.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function devicesForModule(module: keyof typeof viewCatalog, devices: DashboardDevice[]) {
  if (module === "home") return devices.slice(0, 12);
  const terms = categoriesByModule[module].map(normalized);
  return devices.filter((device) => terms.some((term) => normalized(device.category).includes(term)));
}

function entityCards(devices: DashboardDevice[]) {
  if (!devices.length) {
    return [{
      type: "markdown",
      content: "### Configuration en cours\nAucun équipement n’est encore associé à cet univers.",
    }];
  }
  const byRoom = new Map<string, DashboardDevice[]>();
  for (const device of devices) {
    const room = device.room || "Maison";
    byRoom.set(room, [...(byRoom.get(room) ?? []), device]);
  }
  return Array.from(byRoom.entries()).map(([room, roomDevices]) => ({
    type: "entities",
    title: room,
    show_header_toggle: false,
    entities: roomDevices.map((device) => ({
      entity: device.entityId,
      name: device.name,
    })),
  }));
}

export function buildDashboardConfig(enabledModules: string[], devices: DashboardDevice[]) {
  const modules = [...new Set(["home", ...enabledModules])]
    .filter((module): module is keyof typeof viewCatalog => module in viewCatalog);
  return {
    title: "1.2.3 Home",
    views: modules.map((module) => {
      const view = viewCatalog[module];
      const assigned = devicesForModule(module, devices);
      return {
        title: view.title,
        path: view.path,
        icon: view.icon,
        badges: [],
        cards: module === "home"
          ? [{
              type: "markdown",
              content: "## Ma maison\nLes équipements essentiels, configurés par votre installateur.",
            }, ...entityCards(assigned)]
          : entityCards(assigned),
      };
    }),
  };
}
