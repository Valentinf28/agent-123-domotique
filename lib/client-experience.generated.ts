// Généré depuis ma-maison-portail-site/shared/client-experience.json. Ne pas modifier à la main.
export const CLIENT_EXPERIENCE = {
  "tabs": [
    {
      "key": "home",
      "label": "Maison",
      "mobileIcon": "home-variant-outline",
      "portalIcon": "⌂",
      "eyebrow": "Vue d’ensemble",
      "required": true
    },
    {
      "key": "solar",
      "label": "Solaire",
      "mobileIcon": "solar-power",
      "portalIcon": "☀",
      "eyebrow": "Énergie"
    },
    {
      "key": "heating",
      "label": "Chauffage",
      "mobileIcon": "home-thermometer-outline",
      "portalIcon": "♨",
      "eyebrow": "Confort"
    },
    {
      "key": "access",
      "label": "Équipements",
      "mobileIcon": "lightbulb-group-outline",
      "portalIcon": "◉",
      "eyebrow": "Maison"
    },
    {
      "key": "pool",
      "label": "Piscine",
      "mobileIcon": "pool",
      "portalIcon": "≋",
      "eyebrow": "Extérieur",
      "optional": true
    },
    {
      "key": "vehicle",
      "label": "Véhicule",
      "mobileIcon": "car-electric",
      "portalIcon": "◇",
      "eyebrow": "Mobilité",
      "optional": true
    }
  ],
  "controlLabelsByTab": {
    "heating": [
      "Chauffage",
      "Ballon d’eau chaude"
    ],
    "access": [
      "Portail",
      "Terrasse",
      "Serrure Nuki",
      "Caméras"
    ],
    "pool": [
      "Filtration",
      "PAC piscine",
      "Éclairage piscine",
      "Spa",
      "Filtration spa"
    ],
    "vehicle": []
  },
  "energyScene": {
    "flowActivationWatts": 5,
    "portalImages": {
      "dawn": "/energy/energy-home-dawn.png",
      "day": "/energy/energy-home-day-premium.png",
      "dusk": "/energy/energy-home-dusk.png",
      "night": "/energy/energy-home-night-premium.png"
    },
    "daylightHours": {
      "dawnStart": 6,
      "dayStart": 7,
      "duskStart": 19,
      "nightStart": 21
    }
  }
} as const;
