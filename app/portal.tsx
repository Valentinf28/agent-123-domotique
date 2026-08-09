"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { CLIENT_EXPERIENCE } from "../lib/client-experience.generated";
import { createEnergyFlowState, flowDurationMs, formatKilowatts, formatKwh, formatWatts } from "../lib/energy-allocation.generated.js";
import { createEnergySceneLayout } from "../lib/energy-scene.generated.js";
import { addEnergyDays, energyDateKey, formatEnergyDay, isEnergyToday } from "../lib/energy-period.generated.js";
import { MOON_PHASE_GLYPHS, MOON_PHASE_LABELS, moonDisplayPhase } from "../lib/moon-phase";

type View = "Accueil" | "Préparation" | "Installation" | "Appareils" | "Automatisations" | "Ajouter" | "Journal" | "Paramètres";
const SELECTED_DOSSIER_STORAGE_KEY = "ma-maison-selected-dossier";
type HomeTab = (typeof CLIENT_EXPERIENCE.tabs)[number]["label"];
type Device = {
  id: string; name: string; room: string; areaPublicId: string | null;
  category: string; state: string;
  detail: string; battery?: number; online: boolean; visible: boolean;
  controllable?: boolean; icon: string;
};
type Area = { publicId: string; name: string };
type Automation = {
  id: string; name: string; trigger: string; action: string;
  active: boolean; icon: string; lastTriggered?: string | null;
  pending?: boolean;
};
type AutomationDraft = {
  name: string;
  time: string;
  publicDeviceId: string;
  desiredActive: boolean;
};
const canonicalAutomationName = (value: string) => value
  .toLocaleLowerCase("fr-FR")
  .replace(/^1\.2\.3 home\s*·\s*/, "")
  .trim();
type EnergyCoachInsight = {
  id: string; icon: string; tone: "positive" | "attention" | "tip";
  goal: "money" | "battery" | "solar"; confidence: "measured" | "estimated";
  title: string; description: string; impact: string; action: string;
};
type ConsumptionBreakdownItem = {
  id: string; name: string; category: string; icon: string;
  watts: number; sharePercent: number;
};
type CoachReply = {
  answer: string;
  automationProposal: {
    name: string; trigger: string; action: string; rationale: string;
  } | null;
  suggestedQuestions: string[];
};
type CoachMessage = {
  id: string; role: "client" | "coach"; text: string;
  proposal?: CoachReply["automationProposal"];
};
type AssistantAutomationRule = {
  version: 1;
  name: string;
  triggerType: "time" | "sunrise" | "sunset";
  time: string | null;
  weekdays: string[];
  publicDeviceId: string;
  deviceName: string;
  desiredActive: boolean;
  triggerLabel: string;
  actionLabel: string;
};
type AssistantAutomationHelp = {
  documentation?: { title: string; steps: string[] };
  supportTicket?: { available: boolean; subject: string };
};
type AssistantAutomationPreview = {
  result?: {
    status: "ready" | "needs_clarification" | "unsupported" | "refused";
    message?: string;
    proposal?: AssistantAutomationRule;
    summary?: string;
  };
  confirmationToken?: string;
  requiresConfirmation?: boolean;
  expiresInSeconds?: number;
  help?: AssistantAutomationHelp;
  error?: string;
  code?: string;
};
type SolarForecastSlot = { startsAt: string; estimatedWh: number };
type CoachWeekSummary = {
  productionWh: number;
  consumptionWh: number;
  historySamples: number;
  observedDays: number;
};
type CoachActionPlan = {
  status: "learning" | "ready";
  learningDays: number;
  targetDays: 14;
  daysRemaining: number;
  title: string;
  summary: string;
  actions: Array<{
    id: string; priority: number; goal: "money" | "battery" | "solar";
    title: string; description: string; impact: string; nextStep: string;
  }>;
};
type SolarForecastSummary = {
  rawTodayWh: number;
  prudentTodayWh: number;
  rawRemainingWh: number;
  prudentRemainingWh: number;
  correctionPercent: number;
  confidence: "low" | "medium" | "high";
  explanation: string | null;
};
type PredictiveEnergyPlan = {
  loadId: string;
  loadLabel: string;
  loadCategory: string;
  status: "ready_now" | "scheduled" | "protected" | "already_running" | "no_need" | "needs_forecast" | "needs_setup";
  headline: string;
  explanation: string;
  forecastRemainingWh: number;
  forecastNextSixHoursWh: number;
  flexibleLoadEnergyWh: number;
  projectedMinimumBatteryPercent: number;
  projectedEndBatteryPercent: number;
  expectedAvoidedExportWh: number;
  suggestedStartAt: string | null;
  peakAt: string | null;
  confidence: "low" | "medium" | "high";
};
type MobileOverview = {
  flow?: {
    solarWatts: number;
    homeWatts: number;
    gridWatts: number;
    batteryWatts: number;
    vehicleWatts: number;
    vehiclePlugged: boolean;
  };
  energy: Record<string, string>;
  controls: {
    publicId: string; label: string; icon: string;
    active: boolean; available: boolean; controllable?: boolean;
  }[];
  security?: {
    publicId: string; label: string; room: string;
    kind: "camera" | "doorbell"; available: boolean;
    battery: number | null; motionDetectionEnabled: boolean;
    lastActivity: string;
  }[];
  comfort?: {
    indoorTemperature: string; heatingSetpoint: string;
    bedroomTemperature?: string;
    poolTemperature: string; poolSetpoint: string;
    poolAirTemperature?: string;
    hotWaterTemperature: string; hotWaterAvailable: string;
    hotWaterPower: string; hotWaterMode: string;
    teslaBattery: string; teslaPower: string; teslaPlugged?: string; demoMode: string;
    teslaOnline?: string; teslaCharging?: string; teslaDoors?: string;
    teslaClimate?: string; teslaSentry?: string;
  };
  strategy?: {
    tariffPlan: "base" | "hp_hc";
    offPeakPeriods: OffPeakPeriod[];
  };
};
type EnergyHistoryPoint = {
  capturedAt: string;
  solarWatts: number; homeWatts: number; gridWatts: number;
  batteryWatts: number; batteryPercent: number;
};
type CompatibilityLevel = "Automatique" | "Assistée" | "Expert";
type CatalogItem = {
  id: string; brand: string; model: string; category: string; protocol: string;
  level: CompatibilityLevel; method: string; prerequisites: string;
  estimatedMinutes: number; icon: string;
};
type InstallationStatus = "À préparer" | "Prêt" | "Détecté" | "Associé" | "Testé" | "Bloqué";
type PlannedItem = CatalogItem & {
  quantity: number; room: string; status: InstallationStatus;
  matchedEntityId?: string | null; matchedEntityName?: string | null;
};
type AppModule = "home" | "solar" | "heating" | "access" | "pool" | "vehicle";
type FlexibleLoadConfiguration = {
  id: string;
  name: string;
  category: string;
  icon: string;
  powerWatts: number;
  minimumRunMinutes: number;
  priority: number;
  enabled: boolean;
  powerEntityId?: string;
  showInConsumption?: boolean;
};
type OffPeakPeriod = {
  id: string;
  label: string;
  start: string;
  end: string;
};
type EnergyConfiguration = {
  solarPeakWatts: number;
  solarArrays: Array<{
    id: string; label: string; peakWatts: number;
    orientation: string; inclinationDegrees: number | null;
  }>;
  batteryCapacityWh: number;
  batteryReservePercent: number;
  flexibleLoads: FlexibleLoadConfiguration[];
  tariffPlan: "base" | "hp_hc";
  basePriceMilliEurosPerKwh: number | null;
  peakPriceMilliEurosPerKwh: number | null;
  offPeakPriceMilliEurosPerKwh: number | null;
  exportPriceMilliEurosPerKwh: number | null;
  offPeakPeriods: OffPeakPeriod[];
  allowGridExport: boolean;
};
type AgentInventoryItem = {
  entityId: string; name: string; domain: string; state: string; deviceClass?: string | null;
};
type DiscoveryCandidate = {
  entityId: string; name: string; domain: string; state: string; score: number;
};
type DiscoverySuggestion = {
  key: string; label: string; room: string; category?: string;
  entityId: string; entityName: string; candidates: DiscoveryCandidate[]; source?: "manual";
};
type DiscoveryReport = {
  inventoryCount: number;
  preserved: Array<{ key: string; label: string; room: string; entityId: string; entityName: string }>;
  certain: DiscoverySuggestion[];
  ambiguous: Array<DiscoverySuggestion & { requiresConfirmation: true }>;
  missing: Array<{ key: string; label: string; room: string; category: string }>;
  bindings: {
    total: number;
    ready: boolean;
    resolved: DiscoverySuggestion[];
    ambiguous: Array<DiscoverySuggestion & { requiresConfirmation: true }>;
    missing: Array<{ key: string; label: string }>;
    bindings: Record<string, string>;
  };
};
type InstallationDossier = {
  publicId: string; reference: string; customerName: string; status: string; updatedAt: string;
};
type ErpDossierOption = {
  id: number; reference: string; title: string; customerName: string;
  city?: string | null; postalCode?: string | null; status?: string | null;
  solarPeakKwc?: string | number | null; hasBattery?: boolean;
};
type SubscriptionSummary = {
  status: "not_started" | "trialing" | "active" | "past_due" | "suspended" | "cancelled";
  remoteAccessAllowed: boolean;
  accessEndsAt: string | null;
  remainingDays: number | null;
  trialEndsAt: string | null;
  graceEndsAt: string | null;
  priceCents: number;
  interval: "monthly" | "yearly";
};

const HOME_REFRESH_MS = 5_000;
const homeTabs = CLIENT_EXPERIENCE.tabs.map((tab) => tab.label);
const homeTabMeta = Object.fromEntries(
  CLIENT_EXPERIENCE.tabs.map((tab) => [tab.label, { icon: tab.portalIcon, eyebrow: tab.eyebrow }]),
) as Record<HomeTab, { icon: string; eyebrow: string }>;
const homeTabKeys = Object.fromEntries(
  CLIENT_EXPERIENCE.tabs.map((tab) => [tab.label, tab.key]),
) as Record<HomeTab, (typeof CLIENT_EXPERIENCE.tabs)[number]["key"]>;

const appModules: { key: AppModule; label: string; description: string; icon: string; required?: boolean }[] = [
  { key: "home", label: "Maison", description: "Résumé et raccourcis essentiels", icon: "⌂", required: true },
  { key: "solar", label: "Solaire", description: "Production, économies et statistiques", icon: "☀" },
  { key: "heating", label: "Chauffage", description: "Températures, zones et eau chaude", icon: "♨" },
  { key: "access", label: "Équipements", description: "Lumières, volets, portail et caméras", icon: "◫" },
  { key: "pool", label: "Piscine", description: "PAC, filtration et qualité de l’eau", icon: "≋" },
  { key: "vehicle", label: "Véhicule", description: "Batterie, autonomie et recharge", icon: "◇" },
];

const flexibleLoadPresets: FlexibleLoadConfiguration[] = [
  { id: "pac-piscine", name: "PAC piscine", category: "pool", icon: "≋", powerWatts: 2000, minimumRunMinutes: 60, priority: 2, enabled: true, showInConsumption: true },
  { id: "chauffe-eau", name: "Chauffe-eau", category: "hot_water", icon: "♨", powerWatts: 2400, minimumRunMinutes: 120, priority: 1, enabled: true, showInConsumption: true },
  { id: "recharge-vehicule", name: "Recharge véhicule", category: "vehicle", icon: "◇", powerWatts: 7400, minimumRunMinutes: 120, priority: 3, enabled: true, showInConsumption: true },
  { id: "filtration-piscine", name: "Filtration piscine", category: "filtration", icon: "≋", powerWatts: 700, minimumRunMinutes: 120, priority: 4, enabled: true, showInConsumption: true },
  { id: "chauffage-maison", name: "PAC maison", category: "heating", icon: "♨", powerWatts: 3000, minimumRunMinutes: 60, priority: 1, enabled: true, showInConsumption: true },
  { id: "appareil-flexible", name: "Autre appareil", category: "other", icon: "ϟ", powerWatts: 1000, minimumRunMinutes: 60, priority: 3, enabled: true },
];

const catalogItems: CatalogItem[] = [
  { id: "shelly-plus-1pm", brand: "Shelly", model: "Plus 1PM", category: "Éclairage", protocol: "Wi-Fi", level: "Automatique", method: "Détection réseau locale", prerequisites: "Alimentation et Wi-Fi 2,4 GHz", estimatedMinutes: 2, icon: "◉" },
  { id: "hue-motion", brand: "Philips Hue", model: "Motion Sensor", category: "Capteur", protocol: "Zigbee", level: "Assistée", method: "Mise en association Zigbee", prerequisites: "Appuyer 5 s sur Setup", estimatedMinutes: 3, icon: "⌁" },
  { id: "aqara-door-p2", brand: "Aqara", model: "Door and Window P2", category: "Sécurité", protocol: "Matter", level: "Assistée", method: "Scan du QR code Matter", prerequisites: "Code Matter et réseau Thread", estimatedMinutes: 3, icon: "▣" },
  { id: "tesla-wall", brand: "Tesla", model: "Wall Connector Gen 3", category: "Recharge", protocol: "Wi-Fi", level: "Automatique", method: "Détection réseau locale", prerequisites: "Connecté au réseau du client", estimatedMinutes: 4, icon: "ϟ" },
  { id: "daikin-altherma", brand: "Daikin", model: "Altherma", category: "Chauffage", protocol: "Réseau", level: "Expert", method: "Intégration selon passerelle", prerequisites: "Modèle et passerelle à confirmer", estimatedMinutes: 15, icon: "♨" },
  { id: "fronius-gen24", brand: "Fronius", model: "GEN24", category: "Solaire", protocol: "Réseau", level: "Automatique", method: "Découverte Modbus locale", prerequisites: "Solar API activée", estimatedMinutes: 5, icon: "☀" },
  { id: "sonoff-zbmini", brand: "Sonoff", model: "ZBMINI-L2", category: "Éclairage", protocol: "Zigbee", level: "Assistée", method: "Mise en association Zigbee", prerequisites: "Action sur interrupteur ou bouton", estimatedMinutes: 3, icon: "◉" },
  { id: "pool-relay", brand: "1.2.3 Domotique", model: "Coffret piscine", category: "Piscine", protocol: "Modbus", level: "Expert", method: "Adresse réseau et registre validé", prerequisites: "Schéma électrique et accès local", estimatedMinutes: 20, icon: "♒" },
  { id: "deye-sun-15k-sg01hp3", brand: "Deye", model: "SUN-15K-SG01HP3-EU-AM2", category: "Solaire", protocol: "Réseau", level: "Expert", method: "Logger SolarMAN local", prerequisites: "IP du logger et profil hybride HP3", estimatedMinutes: 10, icon: "☀" },
  { id: "shelly-pro-1pm", brand: "Shelly", model: "Pro 1PM", category: "Eau chaude", protocol: "Réseau", level: "Automatique", method: "Détection locale du contacteur", prerequisites: "Pose au tableau et connexion Ethernet ou Wi-Fi", estimatedMinutes: 5, icon: "♨" },
  { id: "hue-bridge", brand: "Philips Hue", model: "Bridge", category: "Éclairage", protocol: "Réseau", level: "Assistée", method: "Découverte locale du pont", prerequisites: "Pont alimenté et bouton central accessible", estimatedMinutes: 4, icon: "◉" },
  { id: "nuki-smart-lock", brand: "Nuki", model: "Smart Lock", category: "Sécurité", protocol: "Réseau", level: "Assistée", method: "Association locale Nuki ou Matter", prerequisites: "Modèle et code d’association", estimatedMinutes: 5, icon: "▣" },
  { id: "onvif-camera", brand: "ONVIF", model: "Caméra IP", category: "Sécurité", protocol: "Réseau", level: "Expert", method: "Découverte ONVIF locale", prerequisites: "Identifiants locaux et accès au flux vidéo", estimatedMinutes: 8, icon: "◉" },
  { id: "ring-cameras", brand: "Ring", model: "Caméras", category: "Sécurité", protocol: "Wi-Fi", level: "Assistée", method: "Association sécurisée du compte Ring", prerequisites: "Accès au compte Ring et code à deux facteurs", estimatedMinutes: 8, icon: "◉" },
  { id: "tesla-vehicle", brand: "Tesla", model: "Véhicule", category: "Véhicule", protocol: "Réseau", level: "Assistée", method: "Association sécurisée du compte Tesla", prerequisites: "Compte Tesla et véhicule autorisé", estimatedMinutes: 8, icon: "◇" },
];

const nav: { label: View; icon: string }[] = [
  { label: "Accueil", icon: "⌂" }, { label: "Préparation", icon: "✓" }, { label: "Installation", icon: "⌁" }, { label: "Appareils", icon: "◫" },
  { label: "Automatisations", icon: "⌁" }, { label: "Ajouter", icon: "+" },
  { label: "Journal", icon: "≡" },
  { label: "Paramètres", icon: "⚙" },
];

export default function Portal({
  customerOnly = false,
  allowHouseSwitch = false,
}: {
  customerOnly?: boolean;
  allowHouseSwitch?: boolean;
}) {
  const [view, setView] = useState<View>("Accueil");
  const [search, setSearch] = useState("");
  const [room, setRoom] = useState("Toutes");
  const [role, setRole] = useState<"Client" | "Installateur">(
    customerOnly ? "Client" : "Installateur",
  );
  const [toast, setToast] = useState("");
  const [modal, setModal] = useState<string | null>(null);
  const [guideStep, setGuideStep] = useState(1);
  const [devices, setDevices] = useState<Device[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [automationItems, setAutomationItems] = useState<Automation[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [selectedAutomation, setSelectedAutomation] = useState<Automation | null>(null);
  const [liveStatus, setLiveStatus] = useState<"loading" | "connected" | "demo">("loading");
  const [mobileOverview, setMobileOverview] = useState<MobileOverview | null>(null);
  const [enabledHomeModules, setEnabledHomeModules] = useState<AppModule[]>(["home"]);
  const [subscription, setSubscription] = useState<SubscriptionSummary | null>(null);
  const [premiumSaving, setPremiumSaving] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [homeRefreshToken, setHomeRefreshToken] = useState(0);
  const [plannedItems, setPlannedItems] = useState<PlannedItem[]>([]);
  const [dossiers, setDossiers] = useState<InstallationDossier[]>([]);
  const [selectedDossierId, setSelectedDossierId] = useState("");
  const [newDossierOpen, setNewDossierOpen] = useState(false);
  const [newDossierReference, setNewDossierReference] = useState("");
  const [newDossierCustomer, setNewDossierCustomer] = useState("");
  const [creatingDossier, setCreatingDossier] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("view") === "coach") setView("Automatisations");
  }, []);

  useEffect(() => {
    if (customerOnly && !allowHouseSwitch) return;
    fetch("/api/dossiers", { headers: { Accept: "application/json" } })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((payload) => {
        const next = Array.isArray(payload.dossiers) ? payload.dossiers : [];
        setDossiers(next);
        const saved = window.localStorage.getItem(SELECTED_DOSSIER_STORAGE_KEY) ?? "";
        setSelectedDossierId((current) => {
          if (next.some((item: InstallationDossier) => item.publicId === current)) return current;
          if (next.some((item: InstallationDossier) => item.publicId === saved)) return saved;
          return next[0]?.publicId || "";
        });
      })
      .catch(() => undefined);
  }, [allowHouseSwitch, customerOnly]);

  useEffect(() => {
    if (selectedDossierId) {
      window.localStorage.setItem(SELECTED_DOSSIER_STORAGE_KEY, selectedDossierId);
    }
  }, [selectedDossierId]);

  useEffect(() => {
    let active = true;
    const query = selectedDossierId
      ? `?dossier=${encodeURIComponent(selectedDossierId)}`
      : "";

    function loadHome() {
      fetch(`/api/home${query}`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      })
        .then(async (response) => {
          if (!response.ok) throw new Error("connection");
          return response.json();
        })
        .then((payload) => {
          if (!active || !payload?.home?.devices) return;
          const categoryIcons: Record<string, string> = {
            "Éclairage": "◉", "Climat": "♨", "Sécurité": "▣",
            "Volets": "▤", "Interrupteurs": "ϟ", "Capteurs": "⌁",
            "Ventilation": "◌", "Entretien": "◇", "Multimédia": "▷",
          };
          const mapped: Device[] = payload.home.devices.map((device: {
            publicId: string; name: string; room: string; category: string;
            areaPublicId: string | null; state: string; available: boolean;
            battery: number | null; visible: boolean; controllable?: boolean;
          }) => ({
            id: device.publicId,
            name: device.name,
            room: device.room,
            areaPublicId: device.areaPublicId,
            category: device.category,
            state: friendlyState(device.state),
            detail: device.available ? "Synchronisé à l’instant" : "À vérifier",
            battery: device.battery ?? undefined,
            online: device.available,
            visible: device.visible,
            controllable: device.controllable !== false,
            icon: categoryIcons[device.category] ?? "◇",
          }));
          setDevices(mapped);
          setAreas(payload.home.areas ?? []);
          setAutomationItems((payload.home.automations ?? []).map((automation: {
            publicId: string; name: string; trigger: string; action: string;
            enabled: boolean; lastTriggered: string | null;
          }) => ({
            id: automation.publicId,
            name: automation.name,
            trigger: automation.trigger,
            action: automation.action,
            active: automation.enabled,
            lastTriggered: automation.lastTriggered,
            icon: "⌁",
          })));
          setMobileOverview(payload.home.mobileOverview ?? null);
          setSubscription(payload.home.subscription ?? null);
          if (payload.home.dossier?.publicId) {
            setSelectedDossierId((current) => current || payload.home.dossier.publicId);
          }
          setEnabledHomeModules(Array.isArray(payload.home.enabledModules)
            ? payload.home.enabledModules
            : ["home"]);
          setLastSyncedAt(new Date());
          setLiveStatus("connected");
        })
        .catch(() => {
          if (active) setLiveStatus("demo");
        });
    }

    loadHome();
    const refreshTimer = window.setInterval(loadHome, HOME_REFRESH_MS);
    return () => {
      active = false;
      window.clearInterval(refreshTimer);
    };
  }, [selectedDossierId, homeRefreshToken]);

  const filtered = useMemo(() => devices.filter((device) =>
    (room === "Toutes" || device.room === room) &&
    `${device.name} ${device.room} ${device.category}`.toLowerCase().includes(search.toLowerCase())
  ), [devices, room, search]);

  function notify(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  }

  async function openPremiumCheckout(interval: "monthly" | "yearly") {
    if (!selectedDossierId) return notify("Maison en cours d’association");
    setPremiumSaving(true);
    try {
      const response = await fetch(`/api/subscriptions/${encodeURIComponent(selectedDossierId)}/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ interval }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.url) throw new Error(payload.error || "Paiement indisponible");
      window.location.assign(payload.url);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Paiement indisponible");
      setPremiumSaving(false);
    }
  }

  async function openBillingPortal() {
    if (!selectedDossierId) return notify("Maison en cours d’association");
    setPremiumSaving(true);
    try {
      const response = await fetch(`/api/subscriptions/${encodeURIComponent(selectedDossierId)}/billing-portal`, {
        method: "POST", headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok || !payload.url) throw new Error(payload.error || "Gestion indisponible");
      window.location.assign(payload.url);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Gestion indisponible");
      setPremiumSaving(false);
    }
  }

  async function startPremiumTrial() {
    if (!selectedDossierId) return notify("Maison en cours d’association");
    setPremiumSaving(true);
    try {
      const response = await fetch(`/api/subscriptions/${encodeURIComponent(selectedDossierId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ action: "start_trial" }),
      });
      const payload = await response.json();
      if (!response.ok || !payload?.subscription) {
        throw new Error(payload?.error || "Essai indisponible");
      }
      setSubscription(payload.subscription as SubscriptionSummary);
      setModal(null);
      notify("Votre mois Premium offert est activé");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Essai indisponible");
    } finally {
      setPremiumSaving(false);
    }
  }

  async function createDossier(fromErp = false) {
    const reference = fromErp
      ? `IMPORT-${Date.now().toString().slice(-8)}`
      : newDossierReference.trim().toUpperCase();
    const customerName = fromErp ? "Nouvelle maison" : newDossierCustomer.trim();
    if (reference.length < 3 || customerName.length < 2) {
      notify("Renseignez une référence et un nom");
      return;
    }
    setCreatingDossier(true);
    try {
      const response = await fetch("/api/dossiers", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ reference, customerName }),
      });
      const payload = await response.json();
      if (!response.ok || !payload?.dossier) {
        throw new Error(payload?.error || "Création impossible");
      }
      const dossier = payload.dossier as InstallationDossier;
      setDossiers((items) => [...items, dossier]);
      setSelectedDossierId(dossier.publicId);
      setNewDossierOpen(false);
      setNewDossierReference("");
      setNewDossierCustomer("");
      setView("Préparation");
      notify(fromErp ? "Sélectionnez maintenant le dossier ERP" : `Dossier ${dossier.reference} créé`);
    } catch {
      notify("La création du dossier a échoué");
    } finally {
      setCreatingDossier(false);
    }
  }

  async function updateDevice(
    device: Device,
    update: { name?: string; areaPublicId?: string | null; visible?: boolean },
  ) {
    const response = await fetch(`/api/devices/${encodeURIComponent(device.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ ...update, dossierPublicId: selectedDossierId }),
    });
    if (!response.ok) throw new Error("update");
    const area = update.areaPublicId === undefined
      ? undefined
      : areas.find((item) => item.publicId === update.areaPublicId);
    setDevices((items) => items.map((item) => item.id === device.id
      ? {
          ...item,
          ...(update.name === undefined ? {} : { name: update.name }),
          ...(update.visible === undefined ? {} : { visible: update.visible }),
          ...(update.areaPublicId === undefined
            ? {}
            : {
                areaPublicId: update.areaPublicId,
                room: area?.name ?? "Maison",
              }),
        }
      : item));
  }

  async function setAutomationEnabled(automation: Automation, enabled: boolean) {
    const response = await fetch(
      `/api/automations/${encodeURIComponent(automation.id)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          enabled,
          dossierPublicId: selectedDossierId || undefined,
        }),
      },
    );
    if (!response.ok) throw new Error("update");
    setAutomationItems((items) => items.map((item) =>
      item.id === automation.id ? { ...item, active: enabled } : item
    ));
  }

  async function setHomeControl(
    control: MobileOverview["controls"][number],
    enabled: boolean,
  ) {
    if (!control.available) {
      notify(`${control.label} est momentanément indisponible`);
      return;
    }
    if (
      control.label === "Serrure Nuki" &&
      !enabled &&
      !window.confirm("Déverrouiller la serrure Nuki ?")
    ) {
      return;
    }
    setMobileOverview((current) => current ? {
      ...current,
      controls: current.controls.map((item) =>
        item.publicId === control.publicId ? { ...item, active: enabled } : item
      ),
    } : current);
    try {
      const response = await fetch(
        `/api/home/controls/${encodeURIComponent(control.publicId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            active: enabled,
            dossierPublicId: selectedDossierId || undefined,
          }),
        },
      );
      if (!response.ok) throw new Error("command");
      notify(`${control.label} · commande envoyée à la box 1.2.3. Home`);
    } catch {
      setMobileOverview((current) => current ? {
        ...current,
        controls: current.controls.map((item) =>
          item.publicId === control.publicId ? { ...item, active: control.active } : item
        ),
      } : current);
      notify(`La commande ${control.label} n’a pas pu être envoyée`);
    }
  }

  async function deleteAutomation(automation: Automation) {
    const response = await fetch(
      `/api/automations/${encodeURIComponent(automation.id)}${
        selectedDossierId
          ? `?dossier=${encodeURIComponent(selectedDossierId)}`
          : ""
      }`,
      { method: "DELETE", headers: { Accept: "application/json" } },
    );
    if (!response.ok) throw new Error("delete");
    setAutomationItems((items) => items.filter((item) => item.id !== automation.id));
  }

  async function createAutomation(draft: AutomationDraft) {
    const response = await fetch("/api/automations", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        ...draft,
        dossierPublicId: selectedDossierId || undefined,
      }),
    });
    if (!response.ok) throw new Error("create");
  }

  return (
    <div className={`app-shell ${customerOnly ? "customer-shell" : ""}`}>
      {!customerOnly && <aside className="sidebar">
        <button className="brand" onClick={() => setView("Accueil")} aria-label="Retour à l’accueil">
          <span className="brand-mark">M</span><span>Ma Maison</span>
        </button>
        <nav aria-label="Navigation principale">
          {nav.filter((item) => !["Préparation", "Installation"].includes(item.label) || role === "Installateur").map((item) => <button key={item.label} className={view === item.label ? "active" : ""} onClick={() => setView(item.label)}>
            <span className="nav-icon">{item.icon}</span><span>{item.label}</span>
          </button>)}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection"><i /> Maison connectée <small>{lastSyncedAt ? `Synchronisée à ${lastSyncedAt.toLocaleTimeString("fr-FR")}` : "Connexion en cours…"}</small></div>
          <button className="profile" disabled={customerOnly} onClick={() => {
            if (!customerOnly) setRole(role === "Client" ? "Installateur" : "Client");
          }}>
            <span>VF</span><b>Valentin Fettig<small>{customerOnly ? "Application client" : `${role} · Basculer`}</small></b>{!customerOnly && <em>⌄</em>}
          </button>
        </div>
      </aside>}

      <main>
        <header className={`topbar ${customerOnly ? "customer-topbar" : ""}`}>
          {customerOnly ? <div className="customer-brand">
            <img src="/brand/logo-123-home.png" alt="" />
            <span><small>1.2.3. HOME</small><strong>Maison de Valentin</strong></span>
          </div> : <div>
            <p>{new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", timeZone: "Europe/Paris" }).format(new Date())}</p>
            <h1>{view === "Accueil" ? "Bonjour Valentin" : view}</h1>
          </div>}
          <div className="top-actions">
            {customerOnly && allowHouseSwitch && dossiers.length > 1 && <div className="house-source-switch" role="group" aria-label="Maison affichée">
              {dossiers.map((dossier) => {
                const showroom = dossier.reference.toUpperCase().includes("SHOWROOM");
                return <button
                  key={dossier.publicId}
                  type="button"
                  className={selectedDossierId === dossier.publicId ? "active" : ""}
                  aria-pressed={selectedDossierId === dossier.publicId}
                  onClick={() => setSelectedDossierId(dossier.publicId)}
                >
                  {showroom ? "Showroom" : "Ma maison"}
                </button>;
              })}
            </div>}
            {role === "Installateur" && dossiers.length > 0 && <label className="tech-house-select">
              <span>Dossier</span>
              <select value={selectedDossierId} onChange={(event) => setSelectedDossierId(event.target.value)}>
                {dossiers.map((dossier) => <option key={dossier.publicId} value={dossier.publicId}>{dossier.reference} · {dossier.customerName}</option>)}
              </select>
            </label>}
            {role === "Installateur" && <button className="icon-button" aria-label="Créer un dossier" title="Créer un dossier" onClick={() => setNewDossierOpen(true)}>＋</button>}
            {!customerOnly && <Link className="dashboard-link" href="/ma-maison">Vue client</Link>}
            {customerOnly && <button className="premium-pill" onClick={() => setModal("premium")}><span>✦</span> Premium</button>}
            {customerOnly && <button className="icon-button" aria-label="Paramètres" onClick={() => setView("Paramètres")}>⚙</button>}
            <button className="icon-button" aria-label="Actualiser" onClick={() => {
              setHomeRefreshToken((value) => value + 1);
              notify("Actualisation demandée");
            }}>↻</button>
            {!customerOnly && <button className="icon-button notification" aria-label="Notifications" onClick={() => setModal("alertes")}>♢<i /></button>}
            {!customerOnly && <button className="primary" onClick={() => setView("Ajouter")}><span>＋</span> Ajouter un appareil</button>}
          </div>
        </header>

        {customerOnly && view !== "Accueil" && <nav className="customer-section-nav" aria-label="Navigation client">
          <button type="button" onClick={() => setView("Accueil")}><span>⌂</span> Maison</button>
          <button type="button" className={view === "Automatisations" ? "active" : ""} onClick={() => setView("Automatisations")}><span>✦</span> Coach & règles</button>
          <button type="button" className={view === "Appareils" ? "active" : ""} onClick={() => setView("Appareils")}><span>◫</span> Appareils</button>
          <button type="button" className={view === "Paramètres" ? "active" : ""} onClick={() => setView("Paramètres")}><span>⚙</span> Paramètres</button>
        </nav>}

        {view === "Accueil" && <Dashboard dossierId={selectedDossierId} enabledModules={enabledHomeModules} setView={setView} setModal={setModal} notify={notify} devices={devices} liveStatus={liveStatus} overview={mobileOverview} lastSyncedAt={lastSyncedAt} onControl={setHomeControl} />}
        {view === "Préparation" && <Preparation dossierId={selectedDossierId} plannedItems={plannedItems} setPlannedItems={setPlannedItems} notify={notify} setView={setView} />}
        {view === "Installation" && <Installation dossierId={selectedDossierId} notify={notify} />}
        {view === "Appareils" && <Devices filtered={filtered} areas={areas} search={search} setSearch={setSearch} room={room} setRoom={setRoom} notify={notify} manage={(device) => { setSelectedDevice(device); setModal("appareil"); }} updateDevice={updateDevice} />}
        {view === "Automatisations" && <Automations dossierId={selectedDossierId} items={automationItems} setModal={setModal} notify={notify} selectAutomation={setSelectedAutomation} setEnabled={setAutomationEnabled} requestHomeRefresh={() => setHomeRefreshToken((value) => value + 1)} />}
        {view === "Ajouter" && <AddDevice step={guideStep} setStep={setGuideStep} notify={notify} />}
        {view === "Journal" && <Journal role={role} />}
        {view === "Paramètres" && <CustomerSettings dossierId={selectedDossierId} notify={notify} />}
      </main>

      <nav className={`mobile-nav ${customerOnly ? "customer-mobile-nav" : ""}`} aria-label="Navigation mobile">
        {(customerOnly
          ? [{ label: "Accueil" as View, icon: "⌂", copy: "Maison" }, { label: "Automatisations" as View, icon: "✦", copy: "Coach" }, { label: "Appareils" as View, icon: "◫", copy: "Appareils" }, { label: "Paramètres" as View, icon: "⚙", copy: "Réglages" }]
          : nav.filter((item) => !["Préparation", "Installation"].includes(item.label)).slice(0, 4).map((item) => ({ ...item, copy: item.label })))
          .map((item) => <button key={item.label} className={view === item.label ? "active" : ""} onClick={() => setView(item.label)}>
            <span>{item.icon}</span><small>{item.copy}</small>
          </button>)}
      </nav>

      {toast && <div className="toast">✓ {toast}</div>}
      {newDossierOpen && <div className="modal-backdrop" role="presentation">
        <section className="modal" role="dialog" aria-modal="true" aria-labelledby="new-dossier-title">
          <button className="modal-close" aria-label="Fermer" onClick={() => setNewDossierOpen(false)}>×</button>
          <div className="modal-symbol">⌂</div>
          <small>NOUVELLE INSTALLATION</small>
          <h3 id="new-dossier-title">Créer un dossier</h3>
          <p>Créez une identité distincte avant d’enrôler la box. Une box restaurée ne doit jamais conserver l’identité de l’installation source.</p>
          <button className="erp-start-button" disabled={creatingDossier} onClick={() => void createDossier(true)}>
            <span>↗</span><b>Créer depuis un dossier ERP<small>Nom, adresse, solaire, batterie et équipements seront repris automatiquement.</small></b>
          </button>
          <div className="modal-separator"><span>ou créer manuellement</span></div>
          <label className="field">Référence
            <input value={newDossierReference} onChange={(event) => setNewDossierReference(event.target.value)} placeholder="SHOWROOM-123" autoFocus />
          </label>
          <label className="field">Nom de l’installation
            <input value={newDossierCustomer} onChange={(event) => setNewDossierCustomer(event.target.value)} placeholder="1.2.3. Home Démo" />
          </label>
          <div className="modal-actions">
            <button onClick={() => setNewDossierOpen(false)}>Annuler</button>
            <button className="primary" disabled={creatingDossier} onClick={() => void createDossier(false)}>
              {creatingDossier ? "Création…" : "Créer le dossier"}
            </button>
          </div>
        </section>
      </div>}
      {modal === "premium" && <PremiumModal
        subscription={subscription}
        saving={premiumSaving}
        close={() => setModal(null)}
        startTrial={startPremiumTrial}
        checkout={openPremiumCheckout}
        manage={openBillingPortal}
      />}
      {modal && modal !== "premium" && <Modal key={`${modal}:${selectedDevice?.id ?? selectedAutomation?.id ?? "none"}`} type={modal} close={() => setModal(null)} notify={notify} device={selectedDevice} devices={devices} areas={areas} saveDevice={updateDevice} automation={selectedAutomation} createAutomation={createAutomation} deleteAutomation={deleteAutomation} />}
    </div>
  );
}

function Preparation({ dossierId, plannedItems, setPlannedItems, notify, setView }: {
  dossierId: string;
  plannedItems: PlannedItem[];
  setPlannedItems: (items: PlannedItem[]) => void;
  notify: (value: string) => void;
  setView: (value: View) => void;
}) {
  const [query, setQuery] = useState("");
  const [protocol, setProtocol] = useState("Tous");
  const [selectedRoom, setSelectedRoom] = useState("Salon");
  const [dossier, setDossier] = useState<{
    reference: string; customerName: string; customerAddress?: string | null;
    erpDossierId?: number | null; erpImportedAt?: string | null;
  }>({ reference: "Chargement…", customerName: "" });
  const [tunnelStep, setTunnelStep] = useState(0);
  const [erpQuery, setErpQuery] = useState("");
  const [erpOptions, setErpOptions] = useState<ErpDossierOption[]>([]);
  const [erpState, setErpState] = useState<"idle" | "searching" | "importing" | "error">("idle");
  const [erpMessage, setErpMessage] = useState("");
  const [importWarnings, setImportWarnings] = useState<string[]>([]);
  const [enabledModules, setEnabledModules] = useState<AppModule[]>(["home", "solar", "heating", "access", "vehicle"]);
  const [energyConfiguration, setEnergyConfiguration] = useState<EnergyConfiguration>({
    solarPeakWatts: 0,
    solarArrays: [],
    batteryCapacityWh: 0,
    batteryReservePercent: 25,
    flexibleLoads: [],
    tariffPlan: "base",
    basePriceMilliEurosPerKwh: null,
    peakPriceMilliEurosPerKwh: null,
    offPeakPriceMilliEurosPerKwh: null,
    exportPriceMilliEurosPerKwh: null,
    offPeakPeriods: [],
    allowGridExport: true,
  });
  const [saveState, setSaveState] = useState<"saved" | "saving" | "offline">("saving");
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const saveRevision = useRef(0);

  useEffect(() => {
    let active = true;
    if (!dossierId) return undefined;
    fetch(`/api/preparation?dossier=${encodeURIComponent(dossierId)}`, { headers: { Accept: "application/json" } })
      .then(async (response) => {
        if (!response.ok) throw new Error("load");
        return response.json();
      })
      .then((payload) => {
        if (!active) return;
        setDossier(payload.dossier);
        setPlannedItems(payload.items);
        if (Array.isArray(payload.dossier.enabledModules)) setEnabledModules(payload.dossier.enabledModules);
        if (payload.dossier.energyConfiguration) setEnergyConfiguration({
          ...payload.dossier.energyConfiguration,
          solarArrays: Array.isArray(payload.dossier.energyConfiguration.solarArrays)
            ? payload.dossier.energyConfiguration.solarArrays
            : [],
          tariffPlan: payload.dossier.energyConfiguration.tariffPlan === "hp_hc" ? "hp_hc" : "base",
          offPeakPeriods: Array.isArray(payload.dossier.energyConfiguration.offPeakPeriods)
            ? payload.dossier.energyConfiguration.offPeakPeriods
            : [],
          allowGridExport: payload.dossier.energyConfiguration.allowGridExport !== false,
        });
        setSaveState("saved");
      })
      .catch(() => {
        if (!active) return;
        setDossier({ reference: "DOSSIER-PILOTE", customerName: "Maison pilote" });
        setSaveState("offline");
      });
    return () => { active = false; };
  }, [dossierId, setPlannedItems]);

  async function save(
    items: PlannedItem[],
    modules = enabledModules,
    energy = energyConfiguration,
  ) {
    const revision = ++saveRevision.current;
    setPlannedItems(items);
    setEnabledModules(modules);
    setEnergyConfiguration(energy);
    setSaveState("saving");
    const previousSave = saveQueue.current;
    const currentSave = previousSave.catch(() => undefined).then(async () => {
      const response = await fetch("/api/preparation", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          items,
          enabledModules: modules,
          energyConfiguration: energy,
          dossierPublicId: dossierId,
        }),
      });
      if (!response.ok) throw new Error("save");
    });
    saveQueue.current = currentSave;
    try {
      await currentSave;
      if (revision === saveRevision.current) setSaveState("saved");
    } catch {
      if (revision === saveRevision.current) setSaveState("offline");
      notify("La liste reste affichée, mais sa sauvegarde a échoué");
    }
  }

  const matches = catalogItems.filter((item) =>
    (protocol === "Tous" || item.protocol === protocol) &&
    `${item.brand} ${item.model} ${item.category} ${item.protocol}`.toLowerCase().includes(query.toLowerCase())
  );
  const totalObjects = plannedItems.reduce((sum, item) => sum + item.quantity, 0);
  const estimated = plannedItems.reduce((sum, item) => sum + item.quantity * item.estimatedMinutes, 0);

  function add(item: CatalogItem) {
    const existing = plannedItems.find((planned) => planned.id === item.id && planned.room === selectedRoom);
    if (existing) {
      void save(plannedItems.map((planned) => planned === existing ? { ...planned, quantity: planned.quantity + 1 } : planned));
    } else {
      void save([...plannedItems, { ...item, quantity: 1, room: selectedRoom, status: "À préparer" }]);
    }
    notify(`${item.brand} ${item.model} ajouté à ${selectedRoom}`);
  }

  function toggleModule(module: AppModule) {
    if (module === "home") return;
    const next = enabledModules.includes(module)
      ? enabledModules.filter(value => value !== module)
      : [...enabledModules, module];
    void save(plannedItems, next);
  }

  async function searchErp() {
    setErpState("searching");
    setErpMessage("");
    try {
      const response = await fetch(`/api/erp/dossiers?q=${encodeURIComponent(erpQuery)}`, { headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Recherche indisponible");
      setErpOptions(Array.isArray(payload.dossiers) ? payload.dossiers : []);
      setErpState("idle");
      if (!payload.dossiers?.length) setErpMessage("Aucun dossier 1.2.3. correspondant");
    } catch (error) {
      setErpState("error");
      setErpMessage(error instanceof Error ? error.message : "ERP indisponible");
    }
  }

  async function importErp(erpDossierId: number) {
    setErpState("importing");
    setErpMessage("");
    try {
      const response = await fetch("/api/erp/import", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ erpDossierId, dossierPublicId: dossierId }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Import impossible");
      setDossier(payload.dossier);
      setPlannedItems(payload.items);
      setEnabledModules(payload.enabledModules);
      setEnergyConfiguration(payload.energyConfiguration);
      setImportWarnings(Array.isArray(payload.warnings) ? payload.warnings : []);
      setErpState("idle");
      setTunnelStep(1);
      notify(`Dossier ${payload.dossier.reference} importé depuis l’ERP`);
    } catch (error) {
      setErpState("error");
      setErpMessage(error instanceof Error ? error.message : "Import impossible");
    }
  }

  function updateSolarArray(index: number, update: Partial<EnergyConfiguration["solarArrays"][number]>, persist = false) {
    const solarArrays = energyConfiguration.solarArrays.map((array, arrayIndex) => arrayIndex === index ? { ...array, ...update } : array);
    const next = { ...energyConfiguration, solarArrays, solarPeakWatts: solarArrays.reduce((sum, array) => sum + Math.max(0, Number(array.peakWatts) || 0), 0) };
    setEnergyConfiguration(next);
    if (persist) void save(plannedItems, enabledModules, next);
  }

  function addSolarArray() {
    const index = energyConfiguration.solarArrays.length + 1;
    let suffix = index;
    while (energyConfiguration.solarArrays.some((array) => array.id === `pan-${suffix}`)) suffix += 1;
    const next = { ...energyConfiguration, solarArrays: [...energyConfiguration.solarArrays, { id: `pan-${suffix}`, label: `Pan ${index}`, peakWatts: 0, orientation: "Sud", inclinationDegrees: 30 }] };
    void save(plannedItems, enabledModules, next);
  }

  function removeSolarArray(index: number) {
    const solarArrays = energyConfiguration.solarArrays.filter((_, arrayIndex) => arrayIndex !== index);
    const next = { ...energyConfiguration, solarArrays, solarPeakWatts: solarArrays.reduce((sum, array) => sum + array.peakWatts, 0) };
    void save(plannedItems, enabledModules, next);
  }

  function updateEnergySetting(key: "solarPeakWatts" | "batteryCapacityWh" | "batteryReservePercent", value: number) {
    const next = { ...energyConfiguration, [key]: Math.max(0, Math.round(value || 0)) };
    setEnergyConfiguration(next);
    void save(plannedItems, enabledModules, next);
  }

  function setTariffPlan(tariffPlan: "base" | "hp_hc") {
    const next = {
      ...energyConfiguration,
      tariffPlan,
      offPeakPeriods: tariffPlan === "hp_hc" && energyConfiguration.offPeakPeriods.length === 0
        ? [{ id: "nuit", label: "Nuit", start: "22:30", end: "06:30" }]
        : energyConfiguration.offPeakPeriods,
    };
    void save(plannedItems, enabledModules, next);
  }

  function updateTariffPrice(key: "basePriceMilliEurosPerKwh" | "peakPriceMilliEurosPerKwh" | "offPeakPriceMilliEurosPerKwh" | "exportPriceMilliEurosPerKwh", euros: string, persist = false) {
    const parsed = euros.trim() === "" ? null : Math.round(Math.max(0, Number(euros) || 0) * 1000);
    const next = { ...energyConfiguration, [key]: parsed };
    setEnergyConfiguration(next);
    if (persist) void save(plannedItems, enabledModules, next);
  }

  function addOffPeakPeriod() {
    if (energyConfiguration.offPeakPeriods.length >= 4) return;
    const index = energyConfiguration.offPeakPeriods.length + 1;
    let sequence = 1;
    while (energyConfiguration.offPeakPeriods.some((period) => period.id === `hc-${sequence}`)) sequence += 1;
    const next = {
      ...energyConfiguration,
      offPeakPeriods: [...energyConfiguration.offPeakPeriods, {
        id: `hc-${sequence}`,
        label: `Plage ${index}`,
        start: "12:00",
        end: "14:00",
      }],
    };
    void save(plannedItems, enabledModules, next);
  }

  function updateOffPeakPeriod(id: string, update: Partial<OffPeakPeriod>, persist = false) {
    const next = {
      ...energyConfiguration,
      offPeakPeriods: energyConfiguration.offPeakPeriods.map((period) =>
        period.id === id ? { ...period, ...update } : period
      ),
    };
    setEnergyConfiguration(next);
    if (persist) void save(plannedItems, enabledModules, next);
  }

  function removeOffPeakPeriod(id: string) {
    const next = {
      ...energyConfiguration,
      offPeakPeriods: energyConfiguration.offPeakPeriods.filter((period) => period.id !== id),
    };
    void save(plannedItems, enabledModules, next);
  }

  function addFlexibleLoad(preset: FlexibleLoadConfiguration) {
    if (energyConfiguration.flexibleLoads.some((load) => load.id === preset.id)) {
      notify(`${preset.name} est déjà dans le plan énergétique`);
      return;
    }
    const next = {
      ...energyConfiguration,
      flexibleLoads: [...energyConfiguration.flexibleLoads, { ...preset }],
    };
    void save(plannedItems, enabledModules, next);
    notify(`${preset.name} ajouté au pilotage prédictif`);
  }

  function updateFlexibleLoad(
    id: string,
    update: Partial<FlexibleLoadConfiguration>,
    persist = false,
  ) {
    const next = {
      ...energyConfiguration,
      flexibleLoads: energyConfiguration.flexibleLoads.map((load) =>
        load.id === id ? { ...load, ...update } : load
      ),
    };
    setEnergyConfiguration(next);
    if (persist) void save(plannedItems, enabledModules, next);
  }

  function removeFlexibleLoad(id: string) {
    const next = {
      ...energyConfiguration,
      flexibleLoads: energyConfiguration.flexibleLoads.filter((load) => load.id !== id),
    };
    void save(plannedItems, enabledModules, next);
  }

  return <div className="content preparation">
    <div className="section-intro split">
      <div><span className="eyebrow">Dossier {dossier.reference} · {dossier.customerName}</span><h2>Configurer une nouvelle maison</h2><p>Importez le dossier ERP, contrôlez les données utiles, puis générez la préparation du technicien.</p></div>
      <div className="prep-heading-actions"><span className={`save-state ${saveState}`}>{saveState === "saved" ? "✓ Liste enregistrée" : saveState === "saving" ? "Enregistrement…" : "Sauvegarde à reprendre"}</span><button className="primary" onClick={() => setView("Installation")}>Ouvrir la checklist</button></div>
    </div>
    <section className="house-tunnel">
      <nav className="house-tunnel-steps" aria-label="Étapes de configuration">
        {["Dossier ERP", "Énergie", "Équipements", "Application", "Validation"].map((label, index) =>
          <button type="button" key={label} className={index === tunnelStep ? "active" : index < tunnelStep ? "done" : ""} onClick={() => setTunnelStep(index)}>
            <i>{index < tunnelStep ? "✓" : index + 1}</i><span>{label}</span>
          </button>
        )}
      </nav>

      {tunnelStep === 0 && <div className="tunnel-panel erp-import-panel">
        <div className="tunnel-copy"><small>ÉTAPE 1 · SOURCE UNIQUE</small><h3>Importer le dossier depuis 1.2.3. Gestion</h3><p>La fiche client, la puissance solaire, la batterie, les pans de toiture et la liste domotique seront repris sans ressaisie.</p></div>
        {dossier.erpDossierId ? <div className="erp-linked">
          <span>✓</span><div><b>{dossier.reference} · {dossier.customerName}</b><small>{dossier.customerAddress || "Adresse à vérifier"}</small></div><em>ERP n° {dossier.erpDossierId}</em>
        </div> : null}
        <div className="erp-search"><label><span>⌕</span><input value={erpQuery} onChange={event => setErpQuery(event.target.value)} onKeyDown={event => { if (event.key === "Enter") void searchErp(); }} placeholder="Référence, nom du client ou chantier…" /></label><button type="button" onClick={() => void searchErp()} disabled={erpState === "searching"}>{erpState === "searching" ? "Recherche…" : "Rechercher dans l’ERP"}</button></div>
        {erpMessage && <p className={`erp-message ${erpState}`}>{erpMessage}</p>}
        <div className="erp-results">{erpOptions.map(option => <article key={option.id}>
          <div><small>{option.reference}</small><b>{option.customerName}</b><span>{[option.postalCode, option.city].filter(Boolean).join(" ") || option.title}</span></div>
          <div className="erp-result-energy"><span>{option.solarPeakKwc ? `${option.solarPeakKwc} kWc` : "Puissance à vérifier"}</span><em>{option.hasBattery ? "Batterie" : "Sans batterie"}</em></div>
          <button type="button" onClick={() => void importErp(option.id)} disabled={erpState === "importing"}>{erpState === "importing" ? "Import…" : "Importer"}</button>
        </article>)}</div>
        <div className="tunnel-actions"><span>Le technicien pourra corriger les données manquantes à l’étape suivante.</span><button type="button" className="primary" onClick={() => setTunnelStep(1)}>Continuer manuellement</button></div>
      </div>}

      {tunnelStep === 1 && <div className="tunnel-panel energy-tunnel-panel">
        <div className="tunnel-copy"><small>ÉTAPE 2 · PRODUCTION ET STOCKAGE</small><h3>Vérifier l’installation énergétique</h3><p>Les pans servent aux prévisions de production. Leur somme doit correspondre à la puissance réellement installée.</p></div>
        {importWarnings.length > 0 && <div className="import-warnings">{importWarnings.map(warning => <span key={warning}>! {warning}</span>)}</div>}
        <div className="solar-array-list">{energyConfiguration.solarArrays.map((array, index) => <article key={array.id}>
          <div className="solar-array-number">☀<small>Pan {index + 1}</small></div>
          <label><span>Nom</span><input value={array.label} onChange={event => updateSolarArray(index, { label: event.target.value })} onBlur={() => updateSolarArray(index, {}, true)} /></label>
          <label><span>Puissance</span><div><input type="number" min="0" value={array.peakWatts} onChange={event => updateSolarArray(index, { peakWatts: Number(event.target.value) })} onBlur={() => updateSolarArray(index, {}, true)} /><em>Wc</em></div></label>
          <label><span>Orientation</span><select value={array.orientation} onChange={event => updateSolarArray(index, { orientation: event.target.value }, true)}>{["Nord","Nord-Est","Est","Sud-Est","Sud","Sud-Ouest","Ouest","Nord-Ouest","À vérifier"].map(value => <option key={value}>{value}</option>)}</select></label>
          <label><span>Inclinaison</span><div><input type="number" min="0" max="90" value={array.inclinationDegrees ?? ""} onChange={event => updateSolarArray(index, { inclinationDegrees: event.target.value === "" ? null : Number(event.target.value) })} onBlur={() => updateSolarArray(index, {}, true)} /><em>°</em></div></label>
          <button type="button" aria-label={`Supprimer ${array.label}`} onClick={() => removeSolarArray(index)}>×</button>
        </article>)}</div>
        {!energyConfiguration.solarArrays.length && <div className="solar-array-empty">Aucun pan importé. Ajoutez au moins un pan pour activer la prévision solaire.</div>}
        <button type="button" className="solar-array-add" onClick={addSolarArray}>＋ Ajouter un pan de toiture</button>
        <div className="energy-tunnel-summary">
          <label><span>Puissance totale</span><div><input type="number" value={energyConfiguration.solarPeakWatts} onChange={event => setEnergyConfiguration({ ...energyConfiguration, solarPeakWatts: Number(event.target.value) })} onBlur={event => updateEnergySetting("solarPeakWatts", Number(event.target.value))} /><em>Wc</em></div><small>{energyConfiguration.solarArrays.length ? "Calculée depuis les pans" : "Saisie manuelle"}</small></label>
          <label><span>Capacité utile batterie</span><div><input type="number" min="0" value={energyConfiguration.batteryCapacityWh} onChange={event => setEnergyConfiguration({ ...energyConfiguration, batteryCapacityWh: Number(event.target.value) })} onBlur={event => updateEnergySetting("batteryCapacityWh", Number(event.target.value))} /><em>Wh</em></div><small>0 Wh si aucune batterie</small></label>
          <label><span>Réserve minimale</span><div><input type="number" min="5" max="80" value={energyConfiguration.batteryReservePercent} onChange={event => setEnergyConfiguration({ ...energyConfiguration, batteryReservePercent: Number(event.target.value) })} onBlur={event => updateEnergySetting("batteryReservePercent", Number(event.target.value))} /><em>%</em></div><small>Protection du stockage</small></label>
        </div>
        <div className="grid-export-configuration">
          <div><small>INJECTION DU SURPLUS</small><h4>Le client autorise-t-il l’injection réseau ?</h4><p>Ce choix pilote la règle installée sur la box 1.2.3. Home.</p></div>
          <div className="grid-export-choice" role="group" aria-label="Autorisation d’injection réseau">
            <button type="button" className={energyConfiguration.allowGridExport ? "selected" : ""} onClick={() => void save(plannedItems, enabledModules, { ...energyConfiguration, allowGridExport: true })}><b>Autorisée</b><small>Le surplus peut être envoyé sur le réseau. Aucune règle de blocage.</small></button>
            <button type="button" className={!energyConfiguration.allowGridExport ? "selected blocked" : ""} onClick={() => void save(plannedItems, enabledModules, { ...energyConfiguration, allowGridExport: false })}><b>Interdite</b><small>La box bloque l’injection lorsque la voiture ne charge pas.</small></button>
          </div>
        </div>
        <div className="tunnel-actions"><button type="button" onClick={() => setTunnelStep(0)}>Retour</button><button type="button" className="primary" onClick={() => setTunnelStep(2)}>Valider l’énergie</button></div>
      </div>}

      {tunnelStep === 2 && <div className="tunnel-panel devices-tunnel-panel">
        <div className="tunnel-copy"><small>ÉTAPE 3 · LISTE COMMERCIALE</small><h3>Contrôler les équipements à connecter</h3><p>Les modèles encore inconnus restent signalés « à confirmer » afin que le technicien prépare ses accès avant le rendez-vous.</p></div>
        <div className="tunnel-device-list">{plannedItems.map((item, index) => <article key={`${item.id}-${index}`}>
          <i>{item.icon}</i><div><small>{item.category} · {item.room}</small><b>{item.brand} {item.model}</b><span>{item.prerequisites}</span></div>
          <label><span>Quantité</span><input type="number" min="1" max="99" value={item.quantity} onChange={event => void save(plannedItems.map((planned, itemIndex) => itemIndex === index ? { ...planned, quantity: Math.max(1, Number(event.target.value)) } : planned))} /></label>
          <em className={item.model === item.category || item.brand === "Marque à confirmer" ? "warning" : ""}>{item.protocol}</em>
          <button type="button" aria-label={`Retirer ${item.model}`} onClick={() => void save(plannedItems.filter((_, itemIndex) => itemIndex !== index))}>×</button>
        </article>)}</div>
        {!plannedItems.length && <div className="solar-array-empty">Aucun équipement n’est prévu dans le dossier ERP. Utilisez les réglages avancés pour en ajouter.</div>}
        <div className="tunnel-actions"><button type="button" onClick={() => setTunnelStep(1)}>Retour</button><button type="button" className="primary" onClick={() => setTunnelStep(3)}>Valider les équipements</button></div>
      </div>}

      {tunnelStep === 3 && <div className="tunnel-panel modules-tunnel-panel">
        <div className="tunnel-copy"><small>ÉTAPE 4 · EXPÉRIENCE CLIENT</small><h3>Choisir les onglets de l’application</h3><p>La sélection est proposée automatiquement d’après les équipements. Le client ne verra que ce qui existe réellement chez lui.</p></div>
        <div className="module-grid">{appModules.map(module => {
          const enabled = enabledModules.includes(module.key);
          return <button key={module.key} type="button" className={enabled ? "enabled" : ""} onClick={() => toggleModule(module.key)} aria-pressed={enabled}>
            <i>{module.icon}</i><span><b>{module.label}</b><small>{module.description}</small></span><em>{module.required ? "Toujours actif" : enabled ? "Activé" : "Masqué"}</em>
          </button>;
        })}</div>
        <div className="tunnel-actions"><button type="button" onClick={() => setTunnelStep(2)}>Retour</button><button type="button" className="primary" onClick={() => setTunnelStep(4)}>Voir le récapitulatif</button></div>
      </div>}

      {tunnelStep === 4 && <div className="tunnel-panel review-tunnel-panel">
        <div className="tunnel-copy"><small>ÉTAPE 5 · PRÊT POUR LE TECHNICIEN</small><h3>Valider la préparation de {dossier.customerName}</h3><p>Un dernier contrôle évite toute ressaisie et signale ce qui devra être confirmé sur place.</p></div>
        <div className="review-grid">
          <article><i>⌂</i><span><small>Maison</small><b>{dossier.reference}</b><em>{dossier.customerAddress || "Adresse à vérifier"}</em></span></article>
          <article className={energyConfiguration.solarPeakWatts > 0 ? "ok" : "warning"}><i>☀</i><span><small>Photovoltaïque</small><b>{energyConfiguration.solarPeakWatts.toLocaleString("fr-FR")} Wc</b><em>{energyConfiguration.solarArrays.length} pan{energyConfiguration.solarArrays.length > 1 ? "s" : ""} de toiture</em></span></article>
          <article className={energyConfiguration.batteryCapacityWh > 0 ? "ok" : "neutral"}><i>▥</i><span><small>Batterie</small><b>{energyConfiguration.batteryCapacityWh > 0 ? `${(energyConfiguration.batteryCapacityWh / 1000).toLocaleString("fr-FR")} kWh` : "Non prévue"}</b><em>Réserve {energyConfiguration.batteryReservePercent} %</em></span></article>
          <article className={plannedItems.length ? "ok" : "warning"}><i>◇</i><span><small>Équipements</small><b>{totalObjects} objet{totalObjects > 1 ? "s" : ""}</b><em>{plannedItems.filter(item => item.brand === "Marque à confirmer").length} à préciser</em></span></article>
          <article className="ok"><i>▣</i><span><small>Application</small><b>{enabledModules.length} onglets</b><em>{enabledModules.map(value => appModules.find(module => module.key === value)?.label).filter(Boolean).join(" · ")}</em></span></article>
        </div>
        <div className="final-check"><span>✓</span><div><b>La configuration est enregistrée</b><p>La checklist d’installation reprend ces données et guidera ensuite la détection automatique des appareils.</p></div></div>
        <div className="tunnel-actions"><button type="button" onClick={() => setTunnelStep(3)}>Retour</button><button type="button" className="primary" onClick={() => setView("Installation")}>Générer la checklist</button></div>
      </div>}
    </section>
    <details className="preparation-advanced">
      <summary>Réglages avancés et catalogue manuel <span>À utiliser uniquement pour compléter le dossier ERP</span></summary>
    <section className="prep-summary">
      <div><small>Objets prévus</small><strong>{totalObjects}</strong><span>{plannedItems.length} références</span></div>
      <div><small>Temps estimé</small><strong>{estimated} min</strong><span>hors câblage</span></div>
      <div><small>Installation automatique</small><strong>{plannedItems.filter(item => item.level === "Automatique").length}/{plannedItems.length}</strong><span>références</span></div>
      <div className={plannedItems.some(item => item.level === "Expert") ? "attention" : ""}><small>À vérifier avant départ</small><strong>{plannedItems.filter(item => item.level === "Expert").length}</strong><span>matériel expert</span></div>
    </section>
    <section className="module-selector">
      <div className="panel-title"><div><small>APPLICATION CLIENT</small><h3>Onglets à afficher</h3></div><span>{enabledModules.length} actifs</span></div>
      <p>Le client verra uniquement les univers présents dans sa maison. L’onglet Maison reste toujours disponible.</p>
      <div className="module-grid">{appModules.map(module => {
        const enabled = enabledModules.includes(module.key);
        return <button key={module.key} type="button" className={enabled ? "enabled" : ""} onClick={() => toggleModule(module.key)} aria-pressed={enabled}>
          <i>{module.icon}</i><span><b>{module.label}</b><small>{module.description}</small></span>
          <em>{module.required ? "Toujours actif" : enabled ? "Activé" : "Masqué"}</em>
        </button>;
      })}</div>
    </section>
    <section className="predictive-setup">
      <div className="panel-title">
        <div><small>PILOTAGE PRÉDICTIF</small><h3>Caractéristiques énergétiques</h3></div>
        <span>Prévision solaire</span>
      </div>
      <p>Ces valeurs viennent en priorité de l’ERP. Le technicien les vérifie lors de la recette avant d’autoriser un futur pilotage automatique.</p>
      <div className="predictive-fields">
        <label><span>Puissance photovoltaïque</span><div><input type="number" min="0" max="100000" value={energyConfiguration.solarPeakWatts} onChange={event => setEnergyConfiguration({ ...energyConfiguration, solarPeakWatts: Number(event.target.value) })} onBlur={event => updateEnergySetting("solarPeakWatts", Number(event.target.value))} /><em>Wc</em></div></label>
        <label><span>Capacité utile batterie</span><div><input type="number" min="0" max="500000" value={energyConfiguration.batteryCapacityWh} onChange={event => setEnergyConfiguration({ ...energyConfiguration, batteryCapacityWh: Number(event.target.value) })} onBlur={event => updateEnergySetting("batteryCapacityWh", Number(event.target.value))} /><em>Wh</em></div></label>
        <label><span>Réserve minimale</span><div><input type="number" min="5" max="80" value={energyConfiguration.batteryReservePercent} onChange={event => setEnergyConfiguration({ ...energyConfiguration, batteryReservePercent: Number(event.target.value) })} onBlur={event => updateEnergySetting("batteryReservePercent", Number(event.target.value))} /><em>%</em></div></label>
      </div>
      <div className="tariff-configuration">
        <div className="tariff-heading">
          <div><small>CONTRAT D’ÉLECTRICITÉ</small><h4>Tarif et heures creuses du client</h4></div>
          <span>Utilisé pour les replis automatiques</span>
        </div>
        <div className="tariff-choice" role="group" aria-label="Type de contrat électrique">
          <button type="button" className={energyConfiguration.tariffPlan === "base" ? "selected" : ""} onClick={() => setTariffPlan("base")}>
            <b>Option Base</b><small>Un tarif identique toute la journée</small>
          </button>
          <button type="button" className={energyConfiguration.tariffPlan === "hp_hc" ? "selected" : ""} onClick={() => setTariffPlan("hp_hc")}>
            <b>Heures pleines / creuses</b><small>Les appareils peuvent se replier sur les HC</small>
          </button>
        </div>
        <div className="tariff-price-fields">
          {energyConfiguration.tariffPlan === "base" ? <label><span>Prix d’achat</span><div><input type="number" min="0" max="2" step="0.001" placeholder="0,251" value={energyConfiguration.basePriceMilliEurosPerKwh === null ? "" : energyConfiguration.basePriceMilliEurosPerKwh / 1000} onChange={event => updateTariffPrice("basePriceMilliEurosPerKwh", event.target.value)} onBlur={event => updateTariffPrice("basePriceMilliEurosPerKwh", event.target.value, true)} /><em>€ / kWh</em></div></label> : <>
            <label><span>Prix heures pleines</span><div><input type="number" min="0" max="2" step="0.001" placeholder="0,270" value={energyConfiguration.peakPriceMilliEurosPerKwh === null ? "" : energyConfiguration.peakPriceMilliEurosPerKwh / 1000} onChange={event => updateTariffPrice("peakPriceMilliEurosPerKwh", event.target.value)} onBlur={event => updateTariffPrice("peakPriceMilliEurosPerKwh", event.target.value, true)} /><em>€ / kWh</em></div></label>
            <label><span>Prix heures creuses</span><div><input type="number" min="0" max="2" step="0.001" placeholder="0,207" value={energyConfiguration.offPeakPriceMilliEurosPerKwh === null ? "" : energyConfiguration.offPeakPriceMilliEurosPerKwh / 1000} onChange={event => updateTariffPrice("offPeakPriceMilliEurosPerKwh", event.target.value)} onBlur={event => updateTariffPrice("offPeakPriceMilliEurosPerKwh", event.target.value, true)} /><em>€ / kWh</em></div></label>
          </>}
          <label><span>Rémunération de l’injection</span><div><input type="number" min="0" max="2" step="0.001" placeholder="0,040" value={energyConfiguration.exportPriceMilliEurosPerKwh === null ? "" : energyConfiguration.exportPriceMilliEurosPerKwh / 1000} onChange={event => updateTariffPrice("exportPriceMilliEurosPerKwh", event.target.value)} onBlur={event => updateTariffPrice("exportPriceMilliEurosPerKwh", event.target.value, true)} /><em>€ / kWh</em></div></label>
        </div>
        {energyConfiguration.tariffPlan === "hp_hc" && <div className="off-peak-editor">
          <div className="off-peak-list">{energyConfiguration.offPeakPeriods.map((period) => <article key={period.id}>
            <label><span>Nom</span><input value={period.label} onChange={event => updateOffPeakPeriod(period.id, { label: event.target.value })} onBlur={() => updateOffPeakPeriod(period.id, {}, true)} /></label>
            <label><span>Début</span><input type="time" value={period.start} onChange={event => updateOffPeakPeriod(period.id, { start: event.target.value })} onBlur={() => updateOffPeakPeriod(period.id, {}, true)} /></label>
            <label><span>Fin</span><input type="time" value={period.end} onChange={event => updateOffPeakPeriod(period.id, { end: event.target.value })} onBlur={() => updateOffPeakPeriod(period.id, {}, true)} /></label>
            <button type="button" aria-label={`Supprimer ${period.label}`} onClick={() => removeOffPeakPeriod(period.id)}>×</button>
          </article>)}</div>
          <button type="button" className="off-peak-add" disabled={energyConfiguration.offPeakPeriods.length >= 4} onClick={addOffPeakPeriod}>＋ Ajouter une plage d’heures creuses</button>
          <p>Les plages qui traversent minuit sont acceptées, par exemple 22:30 → 06:30.</p>
        </div>}
      </div>
      <div className="flexible-load-heading">
        <div><small>APPAREILS FLEXIBLES</small><h4>Ce que la maison peut décaler intelligemment</h4></div>
        <span>{energyConfiguration.flexibleLoads.filter((load) => load.enabled).length} actif{energyConfiguration.flexibleLoads.filter((load) => load.enabled).length > 1 ? "s" : ""}</span>
      </div>
      <div className="flexible-load-presets">{flexibleLoadPresets.map((preset) =>
        <button type="button" key={preset.id} onClick={() => addFlexibleLoad(preset)} disabled={energyConfiguration.flexibleLoads.some((load) => load.id === preset.id)}>
          <i>{preset.icon}</i>{preset.name}<span>＋</span>
        </button>
      )}</div>
      <div className="flexible-load-list">{energyConfiguration.flexibleLoads.map((load) =>
        <article key={load.id} className={load.enabled ? "enabled" : ""}>
          <button type="button" className="flexible-load-toggle" aria-pressed={load.enabled} onClick={() => updateFlexibleLoad(load.id, { enabled: !load.enabled }, true)}><i /></button>
          <span className="flexible-load-icon">{load.icon}</span>
          <label><span>Appareil</span><input value={load.name} onChange={event => updateFlexibleLoad(load.id, { name: event.target.value })} onBlur={() => updateFlexibleLoad(load.id, {}, true)} /></label>
          <label><span>Puissance</span><div><input type="number" min="0" max="50000" value={load.powerWatts} onChange={event => updateFlexibleLoad(load.id, { powerWatts: Number(event.target.value) })} onBlur={() => updateFlexibleLoad(load.id, {}, true)} /><em>W</em></div></label>
          <label><span>Capteur de puissance</span><input placeholder="sensor.appareil_puissance" value={load.powerEntityId || ""} onChange={event => updateFlexibleLoad(load.id, { powerEntityId: event.target.value })} onBlur={() => updateFlexibleLoad(load.id, {}, true)} /></label>
          <label><span>Répartition</span><select value={load.showInConsumption === false ? "no" : "yes"} onChange={event => updateFlexibleLoad(load.id, { showInConsumption: event.target.value === "yes" }, true)}><option value="yes">Afficher</option><option value="no">Masquer</option></select></label>
          <label><span>Cycle minimum</span><div><input type="number" min="15" max="720" value={load.minimumRunMinutes} onChange={event => updateFlexibleLoad(load.id, { minimumRunMinutes: Number(event.target.value) })} onBlur={() => updateFlexibleLoad(load.id, {}, true)} /><em>min</em></div></label>
          <label><span>Priorité</span><select value={load.priority} onChange={event => updateFlexibleLoad(load.id, { priority: Number(event.target.value) }, true)}>{[1,2,3,4,5].map((priority) => <option value={priority} key={priority}>{priority}</option>)}</select></label>
          <button type="button" className="flexible-load-remove" aria-label={`Retirer ${load.name}`} onClick={() => removeFlexibleLoad(load.id)}>×</button>
        </article>
      )}</div>
      <div className="predictive-note"><span>☀</span><div><b>Source recommandée : prévision solaire de la box 1.2.3. Home</b><p>La box récupère la courbe horaire sans exposer l’adresse de la maison ni une clé météo dans l’application.</p></div></div>
    </section>
    <div className="prep-layout">
      <section className="catalog-panel">
        <div className="panel-title"><div><small>Catalogue validé</small><h3>Trouver un équipement</h3></div></div>
        <div className="catalog-tools"><label><span>⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Marque, modèle ou catégorie…" /></label><select value={protocol} onChange={event => setProtocol(event.target.value)}>{["Tous","Wi-Fi","Zigbee","Matter","Réseau","Modbus"].map(value => <option key={value}>{value}</option>)}</select><select aria-label="Pièce de destination" value={selectedRoom} onChange={event => setSelectedRoom(event.target.value)}>{["Salon","Cuisine","Chambre","Entrée","Extérieur","Garage","Local technique"].map(value => <option key={value}>{value}</option>)}</select></div>
        <div className="catalog-list">{matches.map(item => <article key={item.id}>
          <span className="catalog-icon">{item.icon}</span><div className="catalog-main"><small>{item.category} · {item.protocol}</small><h4>{item.brand} <b>{item.model}</b></h4><p>{item.method}</p></div>
          <span className={`level level-${item.level.toLowerCase()}`}>{item.level}</span><div className="catalog-meta"><small>Prévoir</small><b>{item.prerequisites}</b><em>≈ {item.estimatedMinutes} min</em></div>
          <button onClick={() => add(item)}>Ajouter</button>
        </article>)}</div>
      </section>
      <aside className="planned-panel">
        <div className="panel-title"><div><small>Liste commerciale</small><h3>Installation prévue</h3></div><span>{totalObjects} objets</span></div>
        <div className="planned-list">{plannedItems.map((item, index) => <article key={`${item.id}-${item.room}`}>
          <div><span>{item.icon}</span><p><b>{item.brand} {item.model}</b><small>{item.room} · {item.method}</small></p><em className={`level level-${item.level.toLowerCase()}`}>{item.level}</em></div>
          <div className="planned-actions"><label>Qté <input type="number" min="1" max="99" value={item.quantity} onChange={event => void save(plannedItems.map((planned, plannedIndex) => plannedIndex === index ? { ...planned, quantity: Math.max(1, Number(event.target.value)) } : planned))} /></label><select value={item.status} onChange={event => void save(plannedItems.map((planned, plannedIndex) => plannedIndex === index ? { ...planned, status: event.target.value as InstallationStatus } : planned))}>{["À préparer","Prêt","Détecté","Associé","Testé","Bloqué"].map(status => <option key={status}>{status}</option>)}</select><button aria-label={`Retirer ${item.model}`} onClick={() => void save(plannedItems.filter((_, plannedIndex) => plannedIndex !== index))}>×</button></div>
        </article>)}</div>
        {!plannedItems.length && <div className="planned-empty">Ajoutez les équipements prévus pour générer la checklist.</div>}
        <div className="discovery-note"><span>⌁</span><div><b>Recherche automatique sur place</b><p>Les appareils réseau seront rapprochés par modèle, numéro de série et adresse MAC. L’adresse IP ne sera demandée qu’en dernier recours.</p></div></div>
      </aside>
    </div>
    </details>
  </div>;
}

const installationStages: InstallationStatus[] = ["Prêt", "Détecté", "Associé", "Testé"];

function Installation({ dossierId, notify }: { dossierId: string; notify: (value: string) => void }) {
  const [items, setItems] = useState<PlannedItem[]>([]);
  const [dossier, setDossier] = useState({ reference: "Chargement…", customerName: "" });
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState("");
  const [agent, setAgent] = useState<{ status: string; haVersion?: string | null; inventoryCount: number; lastSeenAt?: string | null; inventory?: AgentInventoryItem[] } | null>(null);
  const [enrollment, setEnrollment] = useState<{ code: string; expiresAt: string } | null>(null);
  const [mobilePairing, setMobilePairing] = useState<{ code: string; expiresAt: string } | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionSummary | null>(null);
  const [subscriptionSaving, setSubscriptionSaving] = useState(false);
  const [discoveryReport, setDiscoveryReport] = useState<DiscoveryReport | null>(null);
  const associableInventory = (agent?.inventory ?? []).filter((entity) =>
    !["unknown", "unavailable"].includes(String(entity.state).toLowerCase())
  );

  useEffect(() => {
    let active = true;
    if (!dossierId) return undefined;
    fetch(`/api/preparation?dossier=${encodeURIComponent(dossierId)}`, { headers: { Accept: "application/json" } })
      .then(async response => {
        if (!response.ok) throw new Error("load");
        return response.json();
      })
      .then(payload => {
        if (!active) return;
        setDossier(payload.dossier);
        setItems(payload.items);
      })
      .catch(() => notify("La checklist n’a pas pu être chargée"))
      .finally(() => { if (active) setLoading(false); });
    fetch(`/api/agent/enrollment?dossier=${encodeURIComponent(dossierId)}`, { headers: { Accept: "application/json" } })
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(payload => { if (active) setAgent(payload.agent); })
      .catch(() => undefined);
    fetch(`/api/subscriptions/${encodeURIComponent(dossierId)}`, { headers: { Accept: "application/json" } })
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(payload => { if (active) setSubscription(payload.subscription); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [dossierId]);

  async function save(next: PlannedItem[], activeId: string) {
    setItems(next);
    setSavingId(activeId);
    try {
      const response = await fetch("/api/preparation", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ items: next, dossierPublicId: dossierId }),
      });
      if (!response.ok) throw new Error("save");
    } catch {
      notify("L’état n’a pas été enregistré, réessayez");
    } finally {
      setSavingId("");
    }
  }

  function updateStatus(item: PlannedItem, status: InstallationStatus) {
    void save(items.map(current => current.id === item.id && current.room === item.room ? { ...current, status } : current), `${item.id}:${item.room}`);
  }

  async function discover() {
    if (!agent || agent.status !== "online") {
      notify("La box doit être connectée pour lancer la découverte");
      return;
    }
    const inventory = associableInventory;
    if (!inventory.length) {
      notify("L’inventaire est en cours de remontée par la box");
      return;
    }
    setSavingId("discovery");
    try {
      const response = await fetch("/api/preparation/discovery", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ dossierPublicId: dossierId, applyCertain: true }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Découverte impossible");
      setDiscoveryReport(payload.report);
      const refreshed = await fetch(`/api/preparation?dossier=${encodeURIComponent(dossierId)}`, {
        headers: { Accept: "application/json" }, cache: "no-store",
      });
      if (refreshed.ok) setItems((await refreshed.json()).items);
      const applied = Array.isArray(payload.applied) ? payload.applied.length : 0;
      notify(applied
        ? `${applied} association${applied > 1 ? "s" : ""} certaine${applied > 1 ? "s" : ""} enregistrée${applied > 1 ? "s" : ""}`
        : "Inventaire analysé : consultez le rapport de découverte");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Découverte impossible");
    } finally {
      setSavingId("");
    }
  }

  async function confirmBinding(key: string, entityId: string) {
    if (!entityId) return;
    setSavingId(`binding:${key}`);
    try {
      const response = await fetch("/api/preparation/discovery", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          dossierPublicId: dossierId,
          bindingConfirmations: [{ key, entityId }],
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Association impossible");
      setDiscoveryReport(payload.report);
      const entity = associableInventory.find(candidate => candidate.entityId === entityId);
      notify(`${entity?.name || entityId} est maintenant utilisé pour cette maison`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Association impossible");
    } finally {
      setSavingId("");
    }
  }

  async function createEnrollment() {
    try {
      const response = await fetch(`/api/agent/enrollment?dossier=${encodeURIComponent(dossierId)}`, {
        method: "POST", headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error);
      setEnrollment(payload);
      notify("Code de box généré pour 30 minutes");
    } catch (error) {
      notify(error instanceof Error && error.message ? error.message : "Code impossible à générer");
    }
  }

  function associateEntity(item: PlannedItem, entityId: string) {
    const entity = (agent?.inventory ?? []).find((candidate) => candidate.entityId === entityId);
    const next = items.map((current) => current.id === item.id && current.room === item.room
      ? {
          ...current,
          matchedEntityId: entity?.entityId ?? null,
          matchedEntityName: entity?.name ?? null,
          status: entity ? "Associé" as InstallationStatus : "Prêt" as InstallationStatus,
        }
      : current);
    void save(next, `${item.id}:${item.room}`);
    notify(entity ? `${entity.name} associé à ${item.model}` : `Association retirée pour ${item.model}`);
  }

  async function createMobilePairing() {
    try {
      const response = await fetch(`/api/mobile/code?dossier=${encodeURIComponent(dossierId)}`, { method: "POST", headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error);
      setMobilePairing(payload);
      notify("Code d’application généré pour 30 minutes");
    } catch (error) {
      notify(error instanceof Error && error.message ? error.message : "Code d’application impossible à générer");
    }
  }

  async function updateSubscription(
    action: "start_trial" | "activate" | "mark_past_due" | "suspend",
    interval?: "monthly" | "yearly",
  ) {
    setSubscriptionSaving(true);
    try {
      const response = await fetch(`/api/subscriptions/${encodeURIComponent(dossierId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ action, interval }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Mise à jour impossible");
      setSubscription(payload.subscription);
      const messages = {
        start_trial: "Essai de 30 jours démarré",
        activate: "Abonnement activé",
        mark_past_due: "Délai de grâce de 7 jours démarré",
        suspend: "Accès extérieur suspendu, fonctionnement local conservé",
      };
      notify(messages[action]);
    } catch (error) {
      notify(error instanceof Error ? error.message : "L’abonnement n’a pas pu être mis à jour");
    } finally {
      setSubscriptionSaving(false);
    }
  }

  async function completeInstallation() {
    if (subscription?.status === "not_started") {
      await updateSubscription("start_trial");
    }
    notify("Installation terminée · accès extérieur offert pendant 30 jours");
  }

  const tested = items.filter(item => item.status === "Testé").reduce((sum, item) => sum + item.quantity, 0);
  const total = items.reduce((sum, item) => sum + item.quantity, 0);
  const blocked = items.filter(item => item.status === "Bloqué").length;
  const progress = total ? Math.round((tested / total) * 100) : 0;

  return <div className="content intervention">
    <div className="section-intro split"><div><span className="eyebrow">Intervention · {dossier.reference}</span><h2>Installer chez {dossier.customerName}</h2><p>Suivez la liste préparée. Chaque étape est enregistrée et peut être reprise par un autre technicien.</p></div><button className="primary" disabled={savingId === "discovery"} onClick={discover}>{savingId === "discovery" ? "Analyse en cours…" : "⌁ Lancer la découverte"}</button></div>
    <section className="intervention-progress">
      <div className="progress-ring" style={{ "--progress": `${progress * 3.6}deg` } as React.CSSProperties}><span><strong>{progress}%</strong><small>terminé</small></span></div>
      <div><small>RECETTE DE LA MAISON</small><h3>{tested} objet{tested > 1 ? "s" : ""} testé{tested > 1 ? "s" : ""} sur {total}</h3><div className="progress-bar"><i style={{ width: `${progress}%` }} /></div><p>{blocked ? `${blocked} blocage${blocked > 1 ? "s" : ""} à résoudre avant la remise client.` : "Aucun blocage signalé."}</p></div>
      <div className={`box-state ${agent?.status === "online" ? "online" : ""}`}><i /><span>Agent de la box<strong>{agent?.status === "online" ? `Connecté · HA ${agent.haVersion || "détecté"} · ${agent.inventoryCount} entités` : enrollment ? `Code ${enrollment.code} · valable 30 min` : "En attente d’association"}</strong></span><button onClick={agent ? () => notify(`Dernier contact : ${agent.lastSeenAt ? new Date(agent.lastSeenAt).toLocaleString("fr-FR") : "inconnu"}`) : createEnrollment}>{agent ? "Voir l’état" : enrollment ? "Nouveau code" : "Associer la box"}</button></div>
    </section>
    {discoveryReport && <section className="discovery-report">
      <div className="panel-title"><div><small>Inventaire de la box 1.2.3. Home · {discoveryReport.inventoryCount} éléments</small><h3>Rapport de découverte</h3></div><span>{discoveryReport.certain.length} sûre{discoveryReport.certain.length > 1 ? "s" : ""}</span></div>
      <div className="discovery-report-grid">
        <article className="discovery-safe"><b>Associations enregistrées</b><strong>{discoveryReport.certain.length}</strong><small>Les choix existants sont conservés.</small></article>
        <article className="discovery-ambiguous"><b>À confirmer</b><strong>{discoveryReport.ambiguous.length}</strong><small>Aucune association ambiguë n’est appliquée seule.</small></article>
        <article className="discovery-missing"><b>Éléments manquants</b><strong>{discoveryReport.missing.length}</strong><small>À connecter ou à rechercher sur place.</small></article>
      </div>
      <div className="discovery-list">
        <b>Capteurs essentiels de la maison</b>
        <p>
          <span>{discoveryReport.bindings.ready ? "✓ Configuration énergétique prête" : "Configuration énergétique à terminer"}</span>
          <small>{discoveryReport.bindings.resolved.length}/{discoveryReport.bindings.total} capteurs reconnus automatiquement</small>
        </p>
        {discoveryReport.bindings.resolved.filter(item => item.source === "manual").map(item => <p key={item.key}><span>✓ Validé · {item.label}</span><small>{item.entityName}</small></p>)}
        {discoveryReport.bindings.ambiguous.map(item => <p key={item.key}>
          <span>À confirmer · {item.label}</span>
          <select aria-label={`Choisir le capteur pour ${item.label}`} disabled={savingId === `binding:${item.key}`} defaultValue="" onChange={event => void confirmBinding(item.key, event.target.value)}>
            <option value="">Sélectionner la bonne mesure…</option>
            {item.candidates.map(candidate => <option key={candidate.entityId} value={candidate.entityId}>{candidate.name} · {candidate.entityId}</option>)}
          </select>
        </p>)}
        {discoveryReport.bindings.missing.map(item => <p key={item.key}>
          <span>Manquant · {item.label}</span>
          <select aria-label={`Choisir le capteur pour ${item.label}`} disabled={savingId === `binding:${item.key}`} defaultValue="" onChange={event => void confirmBinding(item.key, event.target.value)}>
            <option value="">Rechercher dans les entités disponibles…</option>
            {associableInventory.map(entity => <option key={entity.entityId} value={entity.entityId}>{entity.name} · {entity.entityId}</option>)}
          </select>
        </p>)}
      </div>
      {discoveryReport.ambiguous.length > 0 && <div className="discovery-list"><b>Suggestions à confirmer dans la checklist</b>{discoveryReport.ambiguous.map(item => <p key={item.key}><span>{item.label} · {item.room}</span><small>{item.candidates.slice(0, 3).map(candidate => candidate.name).join(" · ")}</small></p>)}</div>}
      {discoveryReport.missing.length > 0 && <div className="discovery-list missing"><b>Non trouvés dans cette maison</b>{discoveryReport.missing.map(item => <p key={item.key}><span>{item.label} · {item.room}</span><small>{item.category}</small></p>)}</div>}
    </section>}
    {loading ? <div className="checklist-empty">Chargement de la checklist…</div> : !items.length ? <div className="checklist-empty">Aucun équipement n’a encore été préparé pour ce dossier.</div> :
      <section className="installation-list">{items.map(item => {
        const activeIndex = installationStages.indexOf(item.status);
        const rowId = `${item.id}:${item.room}`;
        return <article key={rowId} className={item.status === "Bloqué" ? "blocked" : item.status === "Testé" ? "tested" : ""}>
          <div className="installation-device"><span>{item.icon}</span><div><small>{item.category} · {item.protocol} · Qté {item.quantity}</small><h3>{item.brand} {item.model}</h3><p>{item.room} · {item.method}</p></div><em className={`level level-${item.level.toLowerCase()}`}>{item.level}</em></div>
          <div className="stage-track">{installationStages.map((stage, index) => <button key={stage} className={item.status !== "Bloqué" && index <= activeIndex ? "done" : ""} onClick={() => updateStatus(item, stage)}><i>{item.status !== "Bloqué" && index <= activeIndex ? "✓" : index + 1}</i><span>{stage}</span></button>)}</div>
          <div className="entity-association">
            <label><b>Appareil ou capteur associé</b><select value={item.matchedEntityId ?? ""} onChange={(event) => associateEntity(item, event.target.value)}>
              <option value="">Choisir une entité détectée…</option>
              {associableInventory.map((entity) => <option key={entity.entityId} value={entity.entityId}>{entity.name} · {entity.entityId}</option>)}
            </select></label>
            <span className={item.matchedEntityId ? "matched" : ""}>{item.matchedEntityId ? `✓ ${item.matchedEntityName || item.matchedEntityId}` : "Association à valider"}</span>
          </div>
          <div className="installation-detail"><span><b>À prévoir</b>{item.prerequisites}</span><span><b>Temps prévu</b>≈ {item.estimatedMinutes * item.quantity} min</span><button className={item.status === "Bloqué" ? "unblock" : "block"} disabled={savingId === rowId} onClick={() => updateStatus(item, item.status === "Bloqué" ? "Prêt" : "Bloqué")}>{savingId === rowId ? "Enregistrement…" : item.status === "Bloqué" ? "Reprendre" : "Signaler un blocage"}</button></div>
        </article>;
      })}</section>}
    <section className="mobile-pairing"><div><span>▣</span><p><b>Application du client</b><small>Le code configure automatiquement la maison et les onglets choisis pendant la préparation.</small></p></div><strong>{mobilePairing ? mobilePairing.code : "Aucun code actif"}</strong><button onClick={createMobilePairing}>{mobilePairing ? "Nouveau code" : "Générer le code"}</button></section>
    <SubscriptionCard
      subscription={subscription}
      saving={subscriptionSaving}
      update={updateSubscription}
    />
    <section className="handover"><div><span>✓</span><p><b>Remise au client</b><small>La validation démarre les 30 jours d’accès 4G/5G offerts. La domotique locale restera toujours disponible.</small></p></div><button disabled={progress < 100 || blocked > 0 || subscriptionSaving} onClick={() => void completeInstallation()}>{subscription?.status === "not_started" ? "Terminer et démarrer l’essai" : "Terminer l’installation"}</button></section>
  </div>;
}

function SubscriptionCard({ subscription, saving, update }: {
  subscription: SubscriptionSummary | null;
  saving: boolean;
  update: (
    action: "start_trial" | "activate" | "mark_past_due" | "suspend",
    interval?: "monthly" | "yearly",
  ) => Promise<void>;
}) {
  if (!subscription) return null;
  const labels: Record<SubscriptionSummary["status"], string> = {
    not_started: "Essai non démarré",
    trialing: `Essai offert · ${subscription.remainingDays ?? 0} jour${subscription.remainingDays === 1 ? "" : "s"} restant${subscription.remainingDays === 1 ? "" : "s"}`,
    active: `Abonnement ${subscription.interval === "yearly" ? "annuel" : "mensuel"} actif`,
    past_due: `Paiement à régulariser · ${subscription.remainingDays ?? 0} jour${subscription.remainingDays === 1 ? "" : "s"} de grâce`,
    suspended: "Accès extérieur suspendu",
    cancelled: "Abonnement résilié",
  };
  return <section className={`subscription-card subscription-${subscription.status}`}>
    <div className="subscription-heading"><span>✦</span><p><b>Forfait 1.2.3. Home</b><small>{labels[subscription.status]} · Le Wi‑Fi et les automatismes locaux restent disponibles.</small></p></div>
    <div className="subscription-benefits" aria-label="Services inclus dans le forfait">
      <span><i>↗</i><b>Accès distant 4G/5G</b></span>
      <span><i>✦</i><b>Assistant domotique</b><em>Inclus</em></span>
      <span><i>⌁</i><b>Coach énergie</b><em>Inclus</em></span>
    </div>
    <strong>{subscription.interval === "yearly" ? "99 € / an" : "9,90 € / mois"}</strong>
    <div className="subscription-actions">
      {subscription.status === "not_started" && <button disabled={saving} onClick={() => void update("start_trial")}>Démarrer l’essai</button>}
      {["trialing", "suspended", "cancelled"].includes(subscription.status) && <>
        <button disabled={saving} onClick={() => void update("activate", "monthly")}>Activer mensuel</button>
        <button disabled={saving} onClick={() => void update("activate", "yearly")}>Activer annuel</button>
      </>}
      {subscription.status === "active" && <>
        <button disabled={saving} onClick={() => void update("mark_past_due")}>Signaler un impayé</button>
        <button disabled={saving} onClick={() => void update("suspend")}>Suspendre</button>
      </>}
      {subscription.status === "past_due" && <>
        <button disabled={saving} onClick={() => void update("activate", subscription.interval)}>Paiement reçu</button>
        <button disabled={saving} onClick={() => void update("suspend")}>Suspendre</button>
      </>}
    </div>
  </section>;
}

function PremiumModal({ subscription, saving, close, startTrial, checkout, manage }: {
  subscription: SubscriptionSummary | null;
  saving: boolean;
  close: () => void;
  startTrial: () => Promise<void>;
  checkout: (interval: "monthly" | "yearly") => Promise<void>;
  manage: () => Promise<void>;
}) {
  const active = subscription?.status === "active";
  const trialing = subscription?.status === "trialing";
  return <div className="modal-backdrop premium-backdrop" onMouseDown={close}>
    <section className="modal premium-modal" onMouseDown={(event) => event.stopPropagation()}>
      <button className="modal-close" aria-label="Fermer" onClick={close}>×</button>
      <span className="premium-symbol">✦</span>
      <small>1.2.3 HOME PREMIUM</small>
      <h3>{active ? "Votre forfait est actif" : trialing ? "Profitez pleinement de votre essai" : "Votre maison, partout avec vous"}</h3>
      <p>Accès 4G/5G, assistant domotique, coach énergie et recommandations intelligentes. Le fonctionnement local reste toujours disponible.</p>
      {trialing && <div className="premium-trial"><b>{subscription?.remainingDays ?? 0} jours offerts restants</b><span>Le prélèvement commencera seulement à la fin de l’essai.</span></div>}
      <div className="premium-features">
        <span><i>↗</i><b>Accès distant</b><small>Wi-Fi, 4G et 5G</small></span>
        <span><i>✦</i><b>Assistant domotique</b><small>Règles en langage naturel</small></span>
        <span><i>⌁</i><b>Coach énergie</b><small>Conseils personnalisés</small></span>
      </div>
      {active ? <button className="primary full" disabled={saving} onClick={() => void manage()}>{saving ? "Ouverture…" : "Gérer mon abonnement"}</button> : subscription?.status === "not_started" ? <div className="premium-start-trial">
        <button className="primary full" disabled={saving} onClick={() => void startTrial()}>{saving ? "Activation…" : "Démarrer mon mois offert"}</button>
        <small>Sans prélèvement aujourd’hui · vous choisirez votre formule ensuite.</small>
      </div> : <div className="premium-offers">
        <button disabled={saving} onClick={() => void checkout("monthly")}><b>9,90 €</b><span>par mois</span></button>
        <button className="recommended" disabled={saving} onClick={() => void checkout("yearly")}><em>2 mois offerts</em><b>99 €</b><span>par an</span></button>
      </div>}
      <small className="premium-note">Paiement sécurisé · résiliable à tout moment</small>
    </section>
  </div>;
}

function friendlyState(state: string) {
  const states: Record<string, string> = {
    on: "Allumé", off: "Éteint", open: "Ouvert", closed: "Fermé",
    locked: "Verrouillé", unlocked: "Déverrouillé", home: "À la maison",
    unavailable: "Indisponible", unknown: "État inconnu", idle: "En veille",
    playing: "Lecture en cours", paused: "En pause", cleaning: "Nettoyage",
  };
  return states[state.toLowerCase()] ?? state;
}

function SecurityCameraStream({ publicId, dossierId, label }: {
  publicId: string;
  dossierId: string;
  label: string;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let disposed = false;
    let connection: RTCPeerConnection | null = null;
    let scope = "";
    let pollTimer: number | null = null;
    const endpoint =
      `/api/home/cameras/${encodeURIComponent(publicId)}/webrtc`;
    const playing = () => {
      if (!disposed) {
        setLoaded(true);
        setFailed(false);
      }
    };
    const unavailable = () => {
      if (!disposed) {
        setLoaded(false);
        setFailed(true);
      }
    };
    video.addEventListener("playing", playing);
    video.addEventListener("error", unavailable);
    const post = async (payload: Record<string, unknown>) => {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...payload, dossier: dossierId }),
        cache: "no-store",
      });
      if (!response.ok) throw new Error("WEBRTC_UNAVAILABLE");
      return response.json();
    };
    const waitForIce = (peer: RTCPeerConnection) => new Promise<void>((resolve) => {
      if (peer.iceGatheringState === "complete") {
        resolve();
        return;
      }
      const timeout = window.setTimeout(resolve, 8_000);
      const changed = () => {
        if (peer.iceGatheringState !== "complete") return;
        window.clearTimeout(timeout);
        peer.removeEventListener("icegatheringstatechange", changed);
        resolve();
      };
      peer.addEventListener("icegatheringstatechange", changed);
    });
    const start = async () => {
      const client = await post({ action: "config" }) as {
        configuration?: RTCConfiguration;
      };
      if (disposed) return;
      const peer = new RTCPeerConnection(client.configuration ?? {});
      connection = peer;
      const received = new MediaStream();
      video.srcObject = received;
      peer.ontrack = (event) => {
        if (event.streams[0]) {
          video.srcObject = event.streams[0];
        } else {
          received.addTrack(event.track);
        }
        void video.play().catch(unavailable);
      };
      peer.onconnectionstatechange = () => {
        if (["failed", "disconnected", "closed"].includes(peer.connectionState)) {
          unavailable();
        }
      };
      peer.addTransceiver("video", { direction: "recvonly" });
      peer.addTransceiver("audio", { direction: "recvonly" });
      await peer.setLocalDescription(await peer.createOffer());
      await waitForIce(peer);
      if (disposed || !peer.localDescription?.sdp) return;
      const negotiated = await post({
        action: "offer",
        offer: peer.localDescription.sdp,
      }) as {
        answer: string;
        candidates?: RTCIceCandidateInit[];
        scope: string;
      };
      if (disposed) return;
      scope = negotiated.scope;
      await peer.setRemoteDescription({
        type: "answer",
        sdp: negotiated.answer,
      });
      for (const candidate of negotiated.candidates ?? []) {
        await peer.addIceCandidate(candidate);
      }
      pollTimer = window.setInterval(() => {
        if (!scope || disposed) return;
        void post({ action: "poll", scope }).then(async (payload: {
          events?: { type?: string; candidate?: RTCIceCandidateInit }[];
        }) => {
          for (const event of payload.events ?? []) {
            if (event.type === "candidate" && event.candidate) {
              await peer.addIceCandidate(event.candidate);
            } else if (event.type === "error") {
              unavailable();
            }
          }
        }).catch(unavailable);
      }, 750);
    };
    void start().catch(unavailable);
    return () => {
      disposed = true;
      if (pollTimer !== null) window.clearInterval(pollTimer);
      if (scope) {
        void fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "close",
            dossier: dossierId,
            scope,
          }),
          keepalive: true,
        });
      }
      connection?.close();
      video.pause();
      video.srcObject = null;
      video.removeEventListener("playing", playing);
      video.removeEventListener("error", unavailable);
    };
  }, [dossierId, publicId]);
  return <div className={`security-camera-frame ${loaded ? "loaded" : ""} ${failed ? "failed" : ""}`}>
    {!loaded && !failed && <span>Connexion au direct…</span>}
    {failed && <span>Direct momentanément indisponible</span>}
    <video
      ref={videoRef}
      aria-label={`Vue en direct · ${label}`}
      autoPlay
      controls
      muted
      playsInline
    />
    <em><i /> Direct vidéo sécurisé</em>
  </div>;
}

function Dashboard({ dossierId, enabledModules, setView, setModal, notify, devices, liveStatus, overview, lastSyncedAt, onControl }: {
  dossierId: string;
  enabledModules: AppModule[];
  setView: (v: View) => void; setModal: (v: string) => void;
  notify: (v: string) => void; devices: Device[];
  liveStatus: "loading" | "connected" | "demo";
  overview: MobileOverview | null;
  lastSyncedAt: Date | null;
  onControl: (
    control: MobileOverview["controls"][number],
    enabled: boolean,
  ) => Promise<void>;
}) {
  const [homeTab, setHomeTab] = useState<HomeTab>("Maison");
  const detectedPool = Boolean(
    overview?.controls?.some((control) =>
      CLIENT_EXPERIENCE.controlLabelsByTab.pool.includes(
        control.label as (typeof CLIENT_EXPERIENCE.controlLabelsByTab.pool)[number],
      )
    ),
  );
  const visibleHomeTabs = useMemo(() => homeTabs.filter((tab) => {
    const moduleKey = homeTabKeys[tab];
    return moduleKey === "home" || moduleKey === "coach" || enabledModules.includes(moduleKey as AppModule) || (moduleKey === "pool" && detectedPool);
  }), [detectedPool, enabledModules]);
  const activeHomeTab = visibleHomeTabs.includes(homeTab) ? homeTab : "Maison";
  const [openCameraId, setOpenCameraId] = useState<string | null>(null);
  const available = devices.filter((device) => device.online).length;
  const lowBattery = devices.filter((device) => device.battery !== undefined && device.battery < 20).length;
  // Une maison ne doit jamais afficher des équipements fictifs pendant une
  // reconnexion : la liste reste vide jusqu'au retour des données de sa box.
  const controls = overview?.controls ?? [];
  const controlLabels = Object.fromEntries(
    visibleHomeTabs.map((tab) => [
      tab,
      CLIENT_EXPERIENCE.controlLabelsByTab[
        homeTabKeys[tab] as keyof typeof CLIENT_EXPERIENCE.controlLabelsByTab
      ] ?? [],
    ]),
  ) as Partial<Record<HomeTab, readonly string[]>>;
  const visibleControls = activeHomeTab === "Maison"
    ? controls
    : controls.filter((control) => controlLabels[activeHomeTab]?.includes(control.label));
  const hotWaterControl = controls.find((control) => control.label === "Ballon d’eau chaude");
  const hotWaterPower = powerNumber(overview?.comfort?.hotWaterPower);
  const hotWaterStatus = hotWaterPower >= 50
    ? "En chauffe"
    : hotWaterControl?.active ? "Prêt · thermostat en attente" : "Arrêté";
  const offPeakCopy = overview?.strategy?.tariffPlan === "hp_hc"
    ? overview.strategy.offPeakPeriods.map((period) => `${period.start}–${period.end}`).join(" · ") || "Plages HC à renseigner"
    : "Option Base";

  return <div className="content app-home app-client-content">
    <section className="app-preview">
      <div className="app-tabs" role="tablist">{visibleHomeTabs.map((tab) => <button key={tab} role="tab" aria-selected={activeHomeTab === tab} className={activeHomeTab === tab ? "selected" : ""} onClick={() => {
        if (tab === "Coach") {
          setView("Automatisations");
          return;
        }
        setHomeTab(tab);
      }}><span>{homeTabMeta[tab].icon}</span><b>{tab}</b></button>)}</div>
      <div className="app-connection"><i className={liveStatus === "connected" ? "online" : ""} />{liveStatus === "connected" ? `Maison connectée en direct${lastSyncedAt ? ` · ${lastSyncedAt.toLocaleTimeString("fr-FR")}` : ""}` : liveStatus === "loading" ? "Connexion en cours…" : "Données momentanément indisponibles"}</div>
      {activeHomeTab === "Maison" && <EnergyScene overview={overview} />}
      {activeHomeTab === "Solaire" && <SolarPortalView overview={overview} tariffCopy={offPeakCopy} dossierId={dossierId} />}
      {activeHomeTab === "Chauffage" && <HeatingPortalView overview={overview} hotWaterStatus={hotWaterStatus} tariffCopy={offPeakCopy} />}
      {activeHomeTab === "Piscine" && <PoolPortalView overview={overview} controls={controls} onControl={onControl} />}
      {activeHomeTab === "Équipements" && <div className="equipment-premium mobile-section">
        <PortalCategoryHeader eyebrow="ÉQUIPEMENTS" title="Votre maison" subtitle="Lumières, volets, accès et surveillance." icon="◉" />
        <div className="equipment-overview"><article><small>ÉQUIPEMENTS DISPONIBLES</small><strong>{available}<em> / {devices.length}</em></strong><span>Synchronisés avec la box 1.2.3. Home</span></article><article><small>ÉTAT DE LA MAISON</small><strong>{lowBattery ? `${lowBattery} alerte${lowBattery > 1 ? "s" : ""}` : "Tout va bien"}</strong><span>{lowBattery ? "Batteries à vérifier" : "Aucune anomalie détectée"}</span></article></div>
      </div>}
      {activeHomeTab === "Équipements" && Boolean(overview?.security?.length) && <div className="security-device-grid">
        {overview?.security?.map((device) => <article key={device.publicId}>
          <div className="security-device-head">
            <span>{device.kind === "doorbell" ? "▣" : "◉"}</span>
            <em className={device.available ? "online" : ""}>{device.available ? "EN LIGNE" : "HORS LIGNE"}</em>
          </div>
          <small>{device.kind === "doorbell" ? "Sonnette Ring" : "Caméra Ring"} · {device.room}</small>
          <strong>{device.label}</strong>
          <p>{device.motionDetectionEnabled ? "Détection de mouvement active" : "Détection de mouvement désactivée"}</p>
          {openCameraId === device.publicId && <SecurityCameraStream publicId={device.publicId} dossierId={dossierId} label={device.label} />}
          <footer>
            <span>Dernière activité · {device.lastActivity}</span>
            {device.battery !== null && <b>{device.battery} %</b>}
          </footer>
          <button
            className="security-live-button"
            disabled={!device.available}
            onClick={() => setOpenCameraId((current) => current === device.publicId ? null : device.publicId)}
          >
            {openCameraId === device.publicId ? "Fermer le direct" : "Ouvrir le direct"}
          </button>
        </article>)}
      </div>}
      {activeHomeTab === "Véhicule" && <VehiclePortalView overview={overview} controls={controls} onControl={onControl} />}
      {visibleControls.length > 0 && <div className="mobile-controls">
        {visibleControls.map((control) => <button key={control.publicId} disabled={!control.available || control.controllable === false} onClick={() => void onControl(control, !control.active)}>
          <span className={control.active ? "control-state active" : "control-state"}>{
            !control.available
              ? "INDISPONIBLE"
              : control.controllable === false
                ? "EN LIGNE"
                : control.label === "Serrure Nuki"
                  ? control.active ? "VERROUILLÉE" : "DÉVERROUILLÉE"
                  : control.active ? "ACTIF" : "ARRÊT"
          }</span>
          <i>{control.icon}</i><b>{control.label}</b>
        </button>)}
      </div>}
    </section>
  </div>;
}

function PortalCategoryHeader({ eyebrow, title, subtitle, icon, color = "#f4c430" }: {
  eyebrow: string; title: string; subtitle: string; icon: string; color?: string;
}) {
  return <header className="portal-category-header">
    <span style={{ color }}>{icon}</span>
    <div><small style={{ color }}>{eyebrow}</small><h2>{title}</h2><p>{subtitle}</p></div>
  </header>;
}

function integrateHistory(points: EnergyHistoryPoint[], field: keyof EnergyHistoryPoint, predicate = (_value: number) => true) {
  if (points.length < 2) return null;
  const orderedPoints = [...points].sort((a, b) => Date.parse(a.capturedAt) - Date.parse(b.capturedAt));
  let wattHours = 0;
  for (let index = 0; index < orderedPoints.length - 1; index += 1) {
    const value = Number(orderedPoints[index][field]);
    if (!Number.isFinite(value) || !predicate(value)) continue;
    const elapsedHours = Math.min(15 * 60 * 1000, Math.max(0, Date.parse(orderedPoints[index + 1].capturedAt) - Date.parse(orderedPoints[index].capturedAt))) / 3_600_000;
    wattHours += Math.abs(value) * elapsedHours;
  }
  return wattHours / 1000;
}

function PortalEnergyChart({ history, date }: { history: EnergyHistoryPoint[]; date: string }) {
  const width = 720; const height = 270; const left = 45; const right = 705; const top = 18; const bottom = 228;
  const orderedHistory = useMemo(() => [...history].sort((a, b) => Date.parse(a.capturedAt) - Date.parse(b.capturedAt)), [history]);
  const defaultIndex = Math.max(0, orderedHistory.length - 1);
  const [cursorIndex, setCursorIndex] = useState(defaultIndex);
  const values = orderedHistory.flatMap((point) => [point.solarWatts, point.homeWatts, point.gridWatts, point.batteryWatts]);
  const maximum = Math.ceil(Math.max(1000, ...values.map((value) => Math.max(0, Number(value) || 0))) / 1000) * 1000;
  const minimum = Math.floor(Math.min(-1000, ...values.map((value) => Math.min(0, Number(value) || 0))) / 1000) * 1000;
  const x = (timestamp: string) => {
    const point = new Date(timestamp);
    const minutes = Number(new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(point).find((part) => part.type === "hour")?.value) * 60 + Number(new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", minute: "2-digit" }).formatToParts(point).find((part) => part.type === "minute")?.value);
    return left + minutes / 1440 * (right - left);
  };
  const y = (value: number) => top + (maximum - value) / (maximum - minimum) * (bottom - top);
  const ySoc = (value: number) => bottom - Math.max(0, Math.min(100, value)) / 100 * (bottom - top);
  const line = (field: keyof EnergyHistoryPoint) => orderedHistory.map((point, index) => `${index ? "L" : "M"}${x(point.capturedAt).toFixed(1)} ${y(Number(point[field]) || 0).toFixed(1)}`).join(" ");
  const socLine = orderedHistory.map((point, index) => `${index ? "L" : "M"}${x(point.capturedAt).toFixed(1)} ${ySoc(Number(point.batteryPercent) || 0).toFixed(1)}`).join(" ");
  const solarArea = orderedHistory.length
    ? `${line("solarWatts")} L${x(orderedHistory[orderedHistory.length - 1].capturedAt).toFixed(1)} ${y(0).toFixed(1)} L${x(orderedHistory[0].capturedAt).toFixed(1)} ${y(0).toFixed(1)} Z`
    : "";
  const selected = orderedHistory[Math.min(cursorIndex, defaultIndex)] ?? null;
  const cursorPosition = selected ? x(selected.capturedAt) : right;
  const selectedTime = selected ? new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" }).format(new Date(selected.capturedAt)) : "—";
  const updateCursor = (clientX: number, target: SVGSVGElement) => {
    if (!orderedHistory.length) return;
    const bounds = target.getBoundingClientRect();
    const viewX = Math.max(left, Math.min(right, (clientX - bounds.left) / bounds.width * width));
    let nearest = 0; let nearestDistance = Number.POSITIVE_INFINITY;
    orderedHistory.forEach((point, index) => {
      const distance = Math.abs(x(point.capturedAt) - viewX);
      if (distance < nearestDistance) { nearest = index; nearestDistance = distance; }
    });
    setCursorIndex(nearest);
  };
  if (orderedHistory.length < 2) return <section className="portal-energy-chart empty"><header><div><small>{formatEnergyDay(new Date(`${date}T12:00:00`)).toUpperCase()}</small><h3>Profil de puissance</h3></div></header><p>Les mesures de cette journée ne sont pas encore disponibles.</p></section>;
  const signedPower = (value: number) => `${value < 0 ? "−" : ""}${formatWatts(value)}`;
  return <section className="portal-energy-chart"><header><div><small>{formatEnergyDay(new Date(`${date}T12:00:00`)).toUpperCase()}</small><h3>Profil de puissance</h3></div><span>Mesures toutes les 5 min</span></header><div className="portal-energy-readout"><strong>{selectedTime}</strong><span><i className="solar" />Production <b>{formatWatts(selected?.solarWatts ?? 0)}</b></span><span><i className="home" />Consommation <b>{formatWatts(selected?.homeWatts ?? 0)}</b></span><span><i className="grid" />Réseau <b>{signedPower(selected?.gridWatts ?? 0)}</b></span><span><i className="battery" />Batterie <b>{signedPower(selected?.batteryWatts ?? 0)}</b></span><span><i className="soc" />SOC <b>{Math.round(selected?.batteryPercent ?? 0)} %</b></span></div><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Courbes de puissance de la journée" onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); updateCursor(event.clientX, event.currentTarget); }} onPointerMove={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) updateCursor(event.clientX, event.currentTarget); }}>
    {[top, (top + bottom) / 2, bottom].map((position) => <line key={position} x1={left} x2={right} y1={position} y2={position} className="grid-line" />)}
    <line x1={left} x2={right} y1={y(0)} y2={y(0)} className="zero-line" />
    <path d={solarArea} className="solar-area" /><path d={line("solarWatts")} className="solar-line" /><path d={line("homeWatts")} className="home-line" /><path d={line("gridWatts")} className="grid-power-line" /><path d={line("batteryWatts")} className="battery-line" /><path d={socLine} className="soc-line" />
    <text x={left - 6} y={top + 4} textAnchor="end">{Math.round(maximum / 100) / 10} kW</text><text x={left - 6} y={bottom + 4} textAnchor="end">{Math.round(minimum / 100) / 10} kW</text><text x={right + 6} y={top + 4} className="soc-axis">100 %</text><text x={right + 6} y={bottom + 4} className="soc-axis">0 %</text>
    <line x1={cursorPosition} x2={cursorPosition} y1={top} y2={bottom} className="cursor-line" />
    {[0, 6, 12, 18, 24].map((hour) => <text key={hour} x={left + hour / 24 * (right - left)} y="255" textAnchor={hour === 0 ? "start" : hour === 24 ? "end" : "middle"}>{String(hour).padStart(2, "0")}:00</text>)}
  </svg></section>;
}

function SolarPortalView({ overview, tariffCopy, dossierId }: { overview: MobileOverview | null; tariffCopy: string; dossierId: string }) {
  const [period, setPeriod] = useState<"day" | "month" | "year">("day");
  const [selectedDate, setSelectedDate] = useState(() => energyDateKey());
  const [history, setHistory] = useState<EnergyHistoryPoint[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => { if (active) setHistoryLoading(true); });
    const query = new URLSearchParams({ date: selectedDate });
    if (dossierId) query.set("dossier", dossierId);
    fetch(`/api/home/history?${query}`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((payload) => { if (active) setHistory(Array.isArray(payload.history) ? payload.history : []); })
      .catch(() => { if (active) setHistory([]); })
      .finally(() => { if (active) setHistoryLoading(false); });
    return () => { active = false; };
  }, [dossierId, selectedDate]);
  const energy = overview?.energy ?? {};
  const historicalDay = !isEnergyToday(new Date(`${selectedDate}T12:00:00`));
  const historicalProduction = integrateHistory(history, "solarWatts", (value) => value >= 0);
  const historicalConsumption = integrateHistory(history, "homeWatts", (value) => value >= 0);
  const historicalImport = integrateHistory(history, "gridWatts", (value) => value > 0);
  const historicalExport = integrateHistory(history, "gridWatts", (value) => value < 0);
  const historicalSelfConsumed = historicalProduction === null
    ? null
    : Math.max(0, historicalProduction - (historicalExport ?? 0));
  const historicalSelfConsumption = historicalProduction && historicalProduction > 0 && historicalSelfConsumed !== null
    ? `${Math.round(historicalSelfConsumed / historicalProduction * 100)} %`
    : "—";
  const historicalAutonomy = historicalConsumption && historicalConsumption > 0
    ? `${Math.round(Math.max(0, 1 - (historicalImport ?? 0) / historicalConsumption) * 100)} %`
    : "—";
  const historicalSavings = historicalSelfConsumed === null
    ? "—"
    : `${new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 2 }).format(historicalSelfConsumed * 0.194)}`;
  const periodValues = {
    day: {
      label: historicalDay ? formatEnergyDay(new Date(`${selectedDate}T12:00:00`)) : "Aujourd’hui",
      production: historicalDay ? formatKwh(historicalProduction) : energy.dailyProduction,
      consumption: historicalDay ? formatKwh(historicalConsumption) : energy.dailyConsumption,
      imported: historicalDay ? formatKwh(historicalImport) : energy.dailyImport,
      exported: historicalDay ? formatKwh(historicalExport) : energy.dailyExport,
    },
    month: {
      label: "Ce mois",
      production: energy.monthlyProduction,
      consumption: energy.monthlyConsumption,
      imported: energy.monthlyImport,
      exported: energy.monthlyExport,
    },
    year: {
      label: "Cette année",
      production: energy.yearlyProduction,
      consumption: energy.yearlyConsumption,
      imported: energy.yearlyImport,
      exported: energy.yearlyExport,
    },
  }[period];
  const livePower = Math.max(0, powerNumber(energy.solar));
  const installedPower = Math.max(1, powerNumber(energy.installedPower) || 9635);
  const liveRatio = Math.min(100, Math.max(1, livePower / installedPower * 100));
  const homePower = Math.max(0, overview?.flow?.homeWatts ?? 0);
  const liveSurplus = Math.max(0, livePower - homePower);
  const liveSolarShare = homePower > 0 ? Math.min(100, Math.round(livePower / homePower * 100)) : 0;
  const liveMessage = livePower < 100
    ? "La production est très faible pour le moment."
    : liveSurplus > 100
      ? `La maison est couverte et environ ${Math.round(liveSurplus).toLocaleString("fr-FR")} W sont disponibles.`
      : `Le solaire couvre environ ${liveSolarShare} % de la consommation actuelle.`;

  return <div className="mobile-section solar-mobile-section">
    <PortalCategoryHeader eyebrow="ÉNERGIE" title="Mon solaire" subtitle="L’essentiel d’abord. Le détail reste disponible quand vous en avez besoin." icon="☀" />
    <section className="solar-focus-card">
      <div className="solar-focus-live"><small>PRODUCTION MAINTENANT</small><strong>{energy.solar ?? "0 W"}</strong><p>{liveMessage}</p><div><i style={{ width: `${liveRatio}%` }} /></div><span>{Math.round(livePower / installedPower * 100)} % de la puissance installée</span></div>
      <div className="solar-focus-summary">
        <article><small>Produit {period === "day" ? "aujourd’hui" : periodValues.label.toLowerCase()}</small><strong>{periodValues.production ?? "—"}</strong></article>
        <article><small>Utilisé dans la maison</small><strong>{period === "day" ? historicalDay ? formatKwh(historicalSelfConsumed) : energy.selfConsumed ?? "—" : energy.selfConsumption ?? "—"}</strong></article>
        <article><small>Économies estimées</small><strong>{historicalDay ? historicalSavings : energy.savings ?? "—"}</strong></article>
      </div>
    </section>
    <section className="solar-period-bar" aria-label="Période affichée">
      <div className="period-tabs">{([['day', 'Jour'], ['month', 'Mois'], ['year', 'Année']] as const).map(([key, label]) => <button key={key} className={period === key ? "selected" : ""} onClick={() => setPeriod(key)}>{label}</button>)}</div>
      {period === "day" && <div className="portal-date-navigation"><button aria-label="Jour précédent" onClick={() => setSelectedDate(energyDateKey(addEnergyDays(new Date(`${selectedDate}T12:00:00`), -1)))}>‹</button><label><strong>{formatEnergyDay(new Date(`${selectedDate}T12:00:00`))}</strong><input type="date" max={energyDateKey()} value={selectedDate} onChange={(event) => event.target.value && setSelectedDate(event.target.value)} /></label><button aria-label="Jour suivant" disabled={isEnergyToday(new Date(`${selectedDate}T12:00:00`))} onClick={() => setSelectedDate(energyDateKey(addEnergyDays(new Date(`${selectedDate}T12:00:00`), 1)))}>›</button>{historyLoading && <em>Actualisation…</em>}</div>}
    </section>
    <section className="solar-essential-grid">
      <article><small>AUTOCONSOMMATION</small><strong>{historicalDay ? historicalSelfConsumption : energy.selfConsumption ?? "—"}</strong><p>Part de votre solaire utilisée chez vous.</p></article>
      <article><small>AUTONOMIE</small><strong>{historicalDay ? historicalAutonomy : energy.autonomy ?? "—"}</strong><p>Part de vos besoins couverte sans achat réseau.</p></article>
      <article><small>RÉSEAU</small><strong>{periodValues.imported ?? "—"}</strong><p>Acheté · {periodValues.exported ?? "—"} injecté.</p></article>
    </section>
    {period === "day" && <details className="solar-detail" open><summary><span><b>Courbe de la journée</b><small>Production, maison, réseau et batterie</small></span><i>⌄</i></summary><div><PortalEnergyChart key={selectedDate} history={history} date={selectedDate} /></div></details>}
    {period === "day" && !historicalDay && <section className="solar-next-action"><span>✦</span><div><small>CONSEIL DU JOUR</small><strong>Utilisez d’abord le surplus réellement disponible</strong><p>Le Coach privilégie le solaire puis utilise {tariffCopy} uniquement comme solution de repli.</p></div></section>}
    <details className="solar-detail"><summary><span><b>Prévision et bilan complet</b><small>Production attendue, consommation et échanges réseau</small></span><i>⌄</i></summary><div className="solar-detail-grid">
      {period === "day" && !historicalDay && <><article><small>Prévision du jour</small><strong>{energy.forecastToday ?? "—"}</strong></article><article><small>Reste à produire</small><strong>{energy.forecastRemaining ?? "—"}</strong></article></>}
      <article><small>Consommation</small><strong>{periodValues.consumption ?? "—"}</strong></article><article><small>CO₂ évité</small><strong>{energy.co2Avoided ?? "—"}</strong></article>
    </div></details>
    <details className="solar-detail"><summary><span><b>Mon installation</b><small>{energy.installedPower ?? "9 635 Wc"} installés · détail des panneaux</small></span><i>⌄</i></summary><div className="solar-detail-grid"><article><small>PV1</small><strong>{energy.pv1 ?? "0 W"}</strong></article><article><small>PV2</small><strong>{energy.pv2 ?? "0 W"}</strong></article><article><small>PV3</small><strong>{energy.pv3 ?? "0 W"}</strong></article><article><small>Pic du jour</small><strong>{energy.peakPower ?? "0 W"}</strong></article></div></details>
  </div>;
}

function HeatingPortalView({ overview, hotWaterStatus, tariffCopy }: {
  overview: MobileOverview | null; hotWaterStatus: string; tariffCopy: string;
}) {
  const current = overview?.comfort?.indoorTemperature ?? "—";
  const target = overview?.comfort?.heatingSetpoint ?? "—";
  return <div className="mobile-section heating-mobile-section">
    <PortalCategoryHeader eyebrow="CONFORT" title="Chauffage" subtitle="La bonne température, pièce par pièce." icon="♨" color="#ff8169" />
    <section className="heating-layout compact-category-layout">
      <article className="thermostat-card"><div className="thermostat-state"><i /> Température maintenue</div><div className="thermostat-dial"><div><span>♨</span><strong>{current}</strong><small>Température actuelle</small></div></div><small>TEMPÉRATURE SOUHAITÉE</small><div className="target-temperature"><button disabled>−</button><strong>{target}</strong><button disabled>＋</button></div><p>Chambre · {overview?.comfort?.bedroomTemperature ?? "—"}</p></article>
      <article className="hot-water-card"><header><span>♨</span><div><small>EAU CHAUDE</small><h3>Ballon intelligent</h3></div><em>{hotWaterStatus}</em></header><div className="hot-water-main"><strong>{overview?.comfort?.hotWaterPower ?? "0 W"}</strong><span>Puissance instantanée</span></div><div className="hot-water-data"><span><small>Consommation du jour</small><b>{overview?.energy.hotWaterToday ?? "—"}</b></span><span><small>Mode</small><b>{overview?.comfort?.hotWaterMode ?? "Automatique"}</b></span></div><footer><b>Solaire prioritaire</b><span>{tariffCopy} en secours</span></footer></article>
    </section>
  </div>;
}

function PoolPortalView({ overview, controls, onControl }: {
  overview: MobileOverview | null;
  controls: MobileOverview["controls"];
  onControl: (control: MobileOverview["controls"][number], enabled: boolean) => Promise<void>;
}) {
  const hour = new Date().getHours();
  const isDay = hour >= 7 && hour < 20;
  const filtration = controls.find((control) => control.label === "Filtration");
  const heatPump = controls.find((control) => control.label === "PAC piscine");
  const light = controls.find((control) => /éclairage piscine|lumière piscine/i.test(control.label));
  const statusButton = (control: MobileOverview["controls"][number] | undefined, label: string, tone: string) => <button disabled={!control?.available || control.controllable === false} className={`pool-status ${control?.active ? "active" : ""}`} style={{ "--pool-tone": tone } as CSSProperties} onClick={() => control && void onControl(control, !control.active)}><i /><span><b>{label}</b><small>{!control?.available ? "Indisponible" : control.active ? "En marche" : "Arrêté"}</small></span></button>;
  return <div className="mobile-section pool-mobile-section">
    <div className="pool-visual"><img src={isDay ? "/pool/pool-day.png" : "/pool/pool-night-lit.png"} alt="Piscine et local technique" /><div className="pool-visual-shade" /><div className="pool-statuses">{statusButton(heatPump, "PAC", "#ff6f61")}{statusButton(filtration, "Filtration", "#f4c430")}{light && statusButton(light, "Éclairage", "#4ed6f5")}</div></div>
    <section className="pool-metrics"><article><small>EAU</small><strong>{overview?.comfort?.poolTemperature ?? "—"}</strong></article><article><small>AIR</small><strong>{overview?.comfort?.poolAirTemperature ?? "—"}</strong></article><article><small>PH</small><strong>{overview?.energy.poolPh ?? "—"}</strong></article><article><small>CHLORE</small><strong>{overview?.energy.poolChlorine ?? "—"}</strong></article></section>
    <section className="pool-target"><button disabled>−</button><div><small>CONSIGNE PAC</small><strong>{overview?.comfort?.poolSetpoint ?? "—"}</strong><div><span><small>FILTRATION</small><b>{overview?.energy.filtration ?? "0 W"}</b><em>{overview?.energy.filtrationToday ?? "—"} aujourd’hui</em></span><span><small>PAC</small><b>{overview?.energy.poolHeatPump ?? "0 W"}</b><em>{overview?.energy.poolHeatPumpToday ?? "—"} aujourd’hui</em></span></div></div><button disabled>＋</button></section>
  </div>;
}

function VehiclePortalView({ overview, controls, onControl }: {
  overview: MobileOverview | null;
  controls: MobileOverview["controls"];
  onControl: (control: MobileOverview["controls"][number], enabled: boolean) => Promise<void>;
}) {
  const battery = overview?.comfort?.teslaBattery ?? "—";
  const plugged = overview?.comfort?.teslaPlugged?.toLowerCase() ?? "";
  const connected = ["on", "connected", "charging", "complete", "stopped", "branchée"].some((state) => plugged.includes(state));
  const onlineState = overview?.comfort?.teslaOnline?.toLowerCase() ?? "";
  const online = !["off", "unavailable", "unknown", "hors ligne"].includes(onlineState);
  const actionDefinitions = [
    ["❄", "Climatisation", "Climatisation Tesla"],
    ["ϟ", "Recharge", "Recharge Tesla"],
    ["▣", "Portières", "Portières Tesla"],
    ["◉", "Trappe de charge", "Trappe Tesla"],
    ["⬡", "Mode Sentinelle", "Mode Sentinelle"],
  ] as const;
  return <div className="mobile-section vehicle-mobile-section">
    <PortalCategoryHeader eyebrow="MOBILITÉ" title="Véhicule" subtitle="Batterie, recharge et autonomie." icon="◇" color="#55c8bd" />
    <section className="vehicle-premium-card"><header><div><h3>Model X</h3><span><i className={online ? "" : "offline"} /> {online ? "En ligne" : "Hors ligne"}</span></div><em>✓ SÉCURISÉ</em></header><img src="/vehicles/tesla-model-x-grey.png" alt="Tesla Model X grise" /></section>
    <section className="vehicle-metric-row"><article><span>▰</span><div><strong>{battery}</strong><small>Batterie</small></div></article><article><span>↗</span><div><strong>{overview?.energy.teslaRange ?? "—"}</strong><small>Autonomie</small></div></article><article><span>♨</span><div><strong>{overview?.energy.teslaCabinTemperature ?? "—"}</strong><small>Habitacle</small></div></article><article><i className={online ? "" : "offline"} /><div><strong>{online ? "En ligne" : "Hors ligne"}</strong><small>Connexion</small></div></article></section>
    <div className={`vehicle-charge-state ${connected ? "connected" : ""}`}><span>ϟ</span><b>{connected ? `Branchée · ${overview?.comfort?.teslaPower ?? "0 W"}` : "Prête à charger"}</b></div>
    <section className="vehicle-actions-web"><header><h3>Commandes</h3><span>Actions sécurisées Tesla</span></header>{actionDefinitions.map(([icon, label, controlLabel]) => {
      const control = controls.find((candidate) => candidate.label === controlLabel);
      return <button key={label} disabled={!control?.available || control.controllable === false} onClick={() => control && void onControl(control, !control.active)}><span>{icon}</span><div><b>{label}</b><small>{!control?.available ? "Indisponible" : control.active ? "Actif" : "Arrêté"}</small></div><em>›</em></button>;
    })}</section>
  </div>;
}

function powerNumber(value?: string) {
  if (!value) return 0;
  const normalized = value
    .replace(/[\s\u00a0\u202f]/g, "")
    .replace(",", ".");
  const numeric = Number(normalized.match(/-?\d+(?:\.\d+)?/)?.[0] ?? 0);
  return /kw/i.test(normalized) ? numeric * 1000 : numeric;
}

function SceneFlow({ route, d, active, reverse, color, power }: {
  route: "solar" | "grid" | "home" | "battery" | "vehicle";
  d: string;
  active: boolean;
  reverse?: boolean;
  color: string;
  power: number;
}) {
  const style = {
    "--flow-color": color,
    "--flow-duration": `${flowDurationMs(power)}ms`,
  } as CSSProperties;
  return <g
    className={`scene-flow route-${route}${active ? " is-active" : ""}${reverse ? " is-reverse" : ""}`}
    style={style}
    aria-hidden="true"
  >
    <path className="scene-flow-base" d={d} />
    {active && <path className="scene-flow-glow" d={d} />}
    {active && <path className="scene-flow-dashes" d={d} />}
  </g>;
}

function SceneLabel({ className, icon, title, value, sub, color }: {
  className: string;
  icon: string;
  title: string;
  value: string;
  sub?: string;
  color: string;
}) {
  return <div className={`scene-label ${className}`}>
    <span className="scene-label-title"><i style={{ color }}>{icon}</i>{title}</span>
    <strong>{value}</strong>
    {sub && <em>{sub}</em>}
  </div>;
}

function EnergyScene({ overview }: { overview: MobileOverview | null }) {
  const [scenePeriod, setScenePeriod] = useState<"dawn" | "day" | "dusk" | "night">("day");

  useEffect(() => {
    const updateDaylight = () => {
      const hour = new Date().getHours();
      const hours = CLIENT_EXPERIENCE.energyScene.daylightHours;
      setScenePeriod(
        hour >= hours.dayStart && hour < hours.duskStart
          ? "day"
          : hour >= hours.dawnStart && hour < hours.dayStart
            ? "dawn"
            : hour >= hours.duskStart && hour < hours.nightStart
              ? "dusk"
              : "night",
      );
    };
    updateDaylight();
    const timer = window.setInterval(updateDaylight, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const solarWatts = overview?.flow?.solarWatts ?? powerNumber(overview?.energy.solar);
  const homeWatts = overview?.flow?.homeWatts ?? powerNumber(overview?.energy.home);
  const gridWatts = overview?.flow?.gridWatts ?? powerNumber(overview?.energy.grid);
  const batteryWatts = overview?.flow?.batteryWatts ?? powerNumber(overview?.energy.batteryPower);
  const vehicleWatts = overview?.flow?.vehicleWatts
    ?? Math.max(0, powerNumber(overview?.energy.vehiclePower ?? overview?.comfort?.teslaPower));
  const pluggedState = overview?.comfort?.teslaPlugged?.toLowerCase() ?? "";
  const vehiclePlugged = overview?.flow?.vehiclePlugged ?? (vehicleWatts > 5
    || ["on", "connected", "charging", "complete", "stopped", "no_power", "starting", "branchée"].some((state) => pluggedState.includes(state)));
  const vehicleBattery = overview?.comfort?.teslaBattery ?? "";
  const hasVehicleBattery = /\d/.test(vehicleBattery);
  const flowState = createEnergyFlowState({
    solarWatts,
    homeWatts,
    gridWatts,
    batteryWatts,
    vehicleWatts,
    vehiclePlugged,
    activationWatts: CLIENT_EXPERIENCE.energyScene.flowActivationWatts,
  });
  const isDay = scenePeriod !== "night";
  const sceneLayout = createEnergySceneLayout(scenePeriod, 370, 630);
  const labelTop = (base: number) => `${((base + sceneLayout.verticalOffset) / 630) * 100}%`;
  const sceneImage = CLIENT_EXPERIENCE.energyScene.portalImages[scenePeriod];
  const moonPhase = moonDisplayPhase(overview?.energy.moonPhase);
  return <div className="energy-scene-wrap">
    <div
      className={`energy-scene-card ${isDay ? "is-day" : "is-night"}`}
    >
      <img
        src={sceneImage}
        alt=""
        className="energy-scene-house"
      />
      <div className="energy-scene-shade" />
      {!isDay && <span
        className="portal-moon-phase"
        role="img"
        aria-label={MOON_PHASE_LABELS[moonPhase]}
        title={MOON_PHASE_LABELS[moonPhase]}
      >
        {MOON_PHASE_GLYPHS[moonPhase]}
      </span>}

      <svg className="scene-flow-svg" viewBox="0 0 370 630" preserveAspectRatio="none" aria-hidden="true">
        <SceneFlow route="solar" d={sceneLayout.paths.solar} {...flowState.solar} color="#ffe700" power={solarWatts} />
        <SceneFlow route="grid" d={sceneLayout.paths.grid} {...flowState.grid} color="#438ed0" power={gridWatts} />
        <SceneFlow route="home" d={sceneLayout.paths.home} {...flowState.home} color="#55c8bd" power={homeWatts} />
        <SceneFlow route="battery" d={sceneLayout.paths.battery} {...flowState.battery} color="#f05d9b" power={batteryWatts} />
        <SceneFlow route="vehicle" d={sceneLayout.paths.vehicle} {...flowState.vehicle} color="#4ed6f5" power={vehicleWatts} />
        <circle className="scene-inverter-hub" cx={sceneLayout.inverterHub.x} cy={sceneLayout.inverterHub.y} r="6" />
      </svg>

      <div style={{ top: labelTop(58) }} className="scene-label-anchor"><SceneLabel className="scene-production" icon="☀" title="Production" value={formatWatts(solarWatts)} color="#ffe700" /></div>
      <div style={{ top: labelTop(238) }} className="scene-label-anchor"><SceneLabel
        className="scene-grid"
        icon="♜"
        title="Réseau"
        value={!flowState.grid.active ? "0 W" : `${flowState.grid.arrow} ${formatWatts(gridWatts)}`}
        color="#438ed0"
      /></div>
      <div style={{ top: labelTop(268) }} className="scene-label-anchor"><SceneLabel className="scene-home" icon="⌂" title="Consommation" value={formatWatts(homeWatts)} color="#55c8bd" /></div>
      <div style={{ top: labelTop(424) }} className="scene-label-anchor"><SceneLabel
        className="scene-battery"
        icon="▰"
        title="Batterie"
        value={overview?.energy.battery ?? "0 %"}
        sub={!flowState.battery.active ? "0 W" : `${flowState.battery.arrow} ${formatWatts(batteryWatts)}`}
        color="#f05d9b"
      /></div>
      {vehiclePlugged && <div style={{ top: labelTop(448) }} className="scene-label-anchor"><SceneLabel
        className="scene-vehicle"
        icon="◇"
        title="Voiture"
        value={vehicleWatts > CLIENT_EXPERIENCE.energyScene.flowActivationWatts && hasVehicleBattery ? vehicleBattery : formatWatts(vehicleWatts)}
        sub={vehicleWatts > CLIENT_EXPERIENCE.energyScene.flowActivationWatts && hasVehicleBattery ? formatWatts(vehicleWatts) : undefined}
        color="#4ed6f5"
      /></div>}
    </div>
  </div>;
}

function Devices({ filtered, areas, search, setSearch, room, setRoom, notify, manage, updateDevice }: {
  filtered: Device[]; areas: Area[]; search: string; setSearch: (value: string) => void;
  room: string; setRoom: (value: string) => void;
  notify: (value: string) => void; manage: (device: Device) => void;
  updateDevice: (
    device: Device,
    update: { name?: string; areaPublicId?: string | null; visible?: boolean },
  ) => Promise<void>;
}) {
  return <div className="content">
    <div className="section-intro"><div><span className="eyebrow">{filtered.length} appareil{filtered.length > 1 ? "s" : ""}</span><h2>Les objets de votre maison</h2><p>Renommez-les, organisez-les et choisissez ce qui apparaît dans l’application.</p></div></div>
    <div className="filters"><label><span>⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Rechercher un appareil…" /></label>
      <div className="chips">{["Toutes", ...areas.map((area) => area.name)].map(x=><button key={x} className={room===x?"selected":""} onClick={()=>setRoom(x)}>{x}</button>)}</div>
      <button className="filter-button">Filtres <span>⌄</span></button>
    </div>
    <div className="device-grid">{filtered.map((d: Device)=><article className={`device-card ${!d.online?"offline":""}`} key={d.id}>
      <div className="device-head"><span className="device-icon">{d.icon}</span><span className={`status ${d.online?"online":"offline-dot"}`}>{d.online?"Disponible":"Hors ligne"}</span><button aria-label={`Options pour ${d.name}`} onClick={()=>manage(d)}>•••</button></div>
      <small>{d.room} · {d.category}</small><h3>{d.name}</h3><strong>{d.state}</strong><p>{d.detail}</p>
      {d.battery !== undefined && <div className={`battery ${d.battery<20?"low":""}`}><span><i style={{width:`${d.battery}%`}} /></span>{d.battery} %</div>}
      <div className="device-foot"><label><input type="checkbox" checked={d.visible} onChange={event=>{
        const visible = event.target.checked;
        updateDevice(d, { visible })
          .then(() => notify(visible ? "Appareil affiché dans l’application" : "Appareil masqué dans l’application"))
          .catch(() => notify("La visibilité n’a pas pu être modifiée"));
      }} /><span /> Dans l’application</label><button onClick={()=>manage(d)}>Gérer</button></div>
    </article>)}</div>
    {!filtered.length && <div className="empty"><strong>Aucun appareil trouvé</strong><p>Essayez une autre pièce ou un autre terme.</p></div>}
  </div>;
}

function Automations({ dossierId, items, setModal, notify, selectAutomation, setEnabled, requestHomeRefresh }: {
  dossierId: string;
  items: Automation[]; setModal: (value: string) => void;
  notify: (value: string) => void;
  selectAutomation: (automation: Automation | null) => void;
  setEnabled: (automation: Automation, enabled: boolean) => Promise<void>;
  requestHomeRefresh: () => void;
}) {
  const [coachOpen, setCoachOpen] = useState(false);
  const [coachLoading, setCoachLoading] = useState(false);
  const [coachQuestion, setCoachQuestion] = useState("");
  const [assistantRequest, setAssistantRequest] = useState("");
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [assistantPreview, setAssistantPreview] = useState<AssistantAutomationPreview | null>(null);
  const [assistantCreated, setAssistantCreated] = useState<string | null>(null);
  const [pendingAutomations, setPendingAutomations] = useState<Automation[]>([]);
  const [trackedAutomations, setTrackedAutomations] = useState<Automation[]>([]);
  const [automationSyncError, setAutomationSyncError] = useState<string | null>(null);
  const [supportBusy, setSupportBusy] = useState(false);
  const [coachInsights, setCoachInsights] = useState<EnergyCoachInsight[]>([]);
  const [consumptionBreakdown, setConsumptionBreakdown] = useState<ConsumptionBreakdownItem[]>([]);
  const [solarForecast, setSolarForecast] = useState<SolarForecastSlot[]>([]);
  const [coachWeek, setCoachWeek] = useState<CoachWeekSummary | null>(null);
  const [coachActionPlan, setCoachActionPlan] = useState<CoachActionPlan | null>(null);
  const [solarForecastSummary, setSolarForecastSummary] = useState<SolarForecastSummary | null>(null);
  const [predictivePlan, setPredictivePlan] = useState<PredictiveEnergyPlan | null>(null);
  const [predictivePlans, setPredictivePlans] = useState<PredictiveEnergyPlan[]>([]);
  const [coachSuggestions, setCoachSuggestions] = useState([
    "Que puis-je économiser ce mois-ci ?",
    "Quand recharger la voiture ?",
    "Comment augmenter mon autoconsommation ?",
  ]);
  const [coachMessages, setCoachMessages] = useState<CoachMessage[]>([
    {
      id: "welcome",
      role: "coach",
      text: "Bonjour ! J’analyse la maison et je peux vous aider à réduire la consommation sans sacrifier votre confort.",
    },
  ]);
  const assistantExamples = [
    "Allume la filtration en semaine à 10h30",
    "Allume la lumière piscine au coucher du soleil le week-end",
    "Coupe le ballon d’eau chaude tous les jours à 16h",
  ];

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("view") !== "coach") return;
    const question = params.get("coachQuestion")?.trim().slice(0, 600) ?? "";
    setCoachOpen(true);
    if (question) setCoachQuestion(question);
  }, []);

  useEffect(() => {
    let active = true;
    const loadStatus = () => fetch(`/api/assistant/automation/status?dossier=${encodeURIComponent(dossierId)}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    }).then((response) => response.ok ? response.json() : Promise.reject())
      .then((payload) => {
        if (!active) return;
        const commands = Array.isArray(payload.commands) ? payload.commands : [];
        const failed = commands.find((command: { status?: string }) => command.status === "failed");
        setAutomationSyncError(failed?.error
          ? `Une automatisation n’a pas pu être créée : ${failed.error}`
          : null);
        setTrackedAutomations(commands
          .filter((command: { status?: string }) => command.status !== "failed")
          .map((command: { id: string; name: string; trigger: string; action: string; status: string }) => ({
            id: `tracked-${command.id}`,
            name: command.name,
            trigger: command.trigger,
            action: command.status === "completed"
              ? "Créée · actualisation de la liste en cours"
              : "Envoi en cours vers la box 1.2.3. Home",
            active: true,
            icon: "⌁",
            pending: true,
          })));
      })
      .catch(() => undefined);
    if (dossierId) loadStatus();
    const timer = window.setInterval(loadStatus, 5_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [dossierId]);

  useEffect(() => {
    let active = true;
    const query = dossierId ? `?dossier=${encodeURIComponent(dossierId)}` : "";
    fetch(`/api/assistant/energy${query}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((payload) => {
        if (active && Array.isArray(payload?.coach?.insights)) {
          setCoachInsights(payload.coach.insights);
          setConsumptionBreakdown(Array.isArray(payload?.coach?.consumptionBreakdown)
            ? payload.coach.consumptionBreakdown
            : []);
          setSolarForecast(Array.isArray(payload?.coach?.solarForecast?.slots)
            ? payload.coach.solarForecast.slots
            : []);
          const week = payload?.coach?.week;
          setCoachWeek(
            week && Number.isFinite(week.productionWh) && Number.isFinite(week.consumptionWh)
              ? {
                productionWh: week.productionWh,
                consumptionWh: week.consumptionWh,
                historySamples: Number(payload?.coach?.historySamples) || 0,
                observedDays: Math.max(1, Number(week.observedDays) || 1),
              }
              : null,
          );
          setCoachActionPlan(payload?.coach?.actionPlan?.status === "ready" || payload?.coach?.actionPlan?.status === "learning"
            ? payload.coach.actionPlan
            : null);
          const summary = payload?.coach?.solarForecast;
          setSolarForecastSummary(
            summary && Number.isFinite(summary.rawTodayWh) && Number.isFinite(summary.prudentTodayWh)
              ? {
                rawTodayWh: summary.rawTodayWh,
                prudentTodayWh: summary.prudentTodayWh,
                rawRemainingWh: summary.rawRemainingWh,
                prudentRemainingWh: summary.prudentRemainingWh,
                correctionPercent: summary.correctionPercent,
                confidence: summary.confidence,
                explanation: summary.explanation,
              }
              : null,
          );
          const plans = Array.isArray(payload?.coach?.predictivePlans)
            ? payload.coach.predictivePlans
            : payload?.coach?.predictivePlan ? [payload.coach.predictivePlan] : [];
          setPredictivePlans(plans);
          setPredictivePlan(plans[0] ?? null);
        }
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [dossierId]);

  async function askCoach(suggested?: string) {
    const message = (suggested ?? coachQuestion).trim();
    if (message.length < 3 || coachLoading) return;
    setCoachOpen(true);
    setCoachQuestion("");
    setCoachMessages((messages) => [...messages, {
      id: `client-${Date.now()}`,
      role: "client",
      text: message,
    }]);
    setCoachLoading(true);
    try {
      const response = await fetch("/api/assistant/energy", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          message,
          dossierPublicId: dossierId || undefined,
          conversation: coachMessages.slice(-6).map((item) => ({
            role: item.role,
            text: item.proposal
              ? `${item.text}\nProposition affichée : ${item.proposal.name}. Quand : ${item.proposal.trigger}. Action : ${item.proposal.action}. Pourquoi : ${item.proposal.rationale}.`
              : item.text,
          })),
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload?.reply?.answer) throw new Error("coach");
      const reply = payload.reply as CoachReply;
      setCoachMessages((messages) => [...messages, {
        id: `coach-${Date.now()}`,
        role: "coach",
        text: reply.answer,
        proposal: reply.automationProposal,
      }]);
      if (reply.suggestedQuestions?.length) {
        setCoachSuggestions(reply.suggestedQuestions.slice(0, 3));
      }
    } catch {
      setCoachMessages((messages) => [...messages, {
        id: `coach-error-${Date.now()}`,
        role: "coach",
        text: "Je n’arrive pas à analyser les données pour le moment. Vos équipements continuent de fonctionner normalement.",
      }]);
    } finally {
      setCoachLoading(false);
    }
  }

  async function prepareAssistantAutomation(requestOverride?: string) {
    const message = (requestOverride ?? assistantRequest).trim();
    if (message.length < 3 || assistantBusy) return;
    setAssistantRequest(message);
    setAssistantCreated(null);
    setAssistantBusy(true);
    try {
      const response = await fetch("/api/assistant/automation/propose", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          message,
          dossierPublicId: dossierId,
          conversation: coachMessages.slice(-6).map((item) => ({
            role: item.role,
            text: item.text,
          })),
        }),
      });
      const payload = await response.json() as AssistantAutomationPreview;
      setAssistantPreview(payload);
      if (!response.ok) notify(payload.error ?? "La proposition ne peut pas être préparée");
    } catch {
      setAssistantPreview({ error: "La box 1.2.3. Home ne répond pas pour le moment." });
    } finally {
      setAssistantBusy(false);
    }
  }

  async function confirmAssistantAutomation() {
    if (!assistantPreview?.confirmationToken || assistantBusy) return;
    setAssistantBusy(true);
    try {
      const response = await fetch("/api/assistant/automation/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          confirmationToken: assistantPreview.confirmationToken,
          confirmed: true,
        }),
      });
      const payload = await response.json() as {
        message?: string;
        error?: string;
        commandId?: string;
        rule?: AssistantAutomationRule;
      };
      if (!response.ok) {
        setAssistantPreview((preview) => preview ? { ...preview, error: payload.error } : null);
        return;
      }
      const message = payload.message ?? "Automatisation envoyée à la box 1.2.3. Home.";
      if (payload.rule) {
        setPendingAutomations((pending) => {
          const next: Automation = {
            id: `pending-${payload.commandId ?? Date.now()}`,
            name: payload.rule!.name,
            trigger: payload.rule!.triggerLabel,
            action: `${payload.rule!.actionLabel} · Synchronisation en cours`,
            active: true,
            icon: "⌁",
            pending: true,
          };
          return [...pending.filter((item) => item.name !== next.name), next];
        });
      }
      setAssistantCreated(message);
      setAssistantPreview(null);
      setAssistantRequest("");
      notify(message);
      window.setTimeout(requestHomeRefresh, 6_000);
    } catch {
      setAssistantPreview((preview) => preview ? { ...preview, error: "La confirmation n’a pas pu être envoyée." } : null);
    } finally {
      setAssistantBusy(false);
    }
  }

  async function createSupportTicket() {
    if (supportBusy) return;
    setSupportBusy(true);
    try {
      const reason = assistantPreview?.result?.message ?? assistantPreview?.error ?? "Automatisation à préciser";
      const response = await fetch("/api/assistant/automation/support", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          dossierPublicId: dossierId,
          message: assistantRequest,
          reason,
        }),
      });
      const payload = await response.json() as { message?: string; error?: string };
      notify(response.ok ? (payload.message ?? "Ticket transmis au support") : (payload.error ?? "Le support n’est pas encore configuré"));
    } catch {
      notify("Le support n’est pas joignable pour le moment");
    } finally {
      setSupportBusy(false);
    }
  }

  const forecastMaximum = Math.max(1, ...solarForecast.slice(0, 12).map((slot) => slot.estimatedWh));
  const forecastTime = (value: string | null) => value
    ? new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(new Date(value))
    : "—";
  const forecastKwh = (value: number) => value >= 1000
    ? `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(value / 1000)} kWh`
    : `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Math.max(0, value))} Wh`;
  const confidenceLabel = solarForecastSummary?.confidence === "high"
    ? "Élevée"
    : solarForecastSummary?.confidence === "medium" ? "Moyenne" : "Faible";
  const pendingByName = new Map<string, Automation>();
  for (const candidate of [...pendingAutomations, ...trackedAutomations]) {
    pendingByName.set(canonicalAutomationName(candidate.name), candidate);
  }
  const displayedAutomations = [
    ...[...pendingByName.values()].filter((candidate) => !items.some((item) =>
      canonicalAutomationName(item.name) === canonicalAutomationName(candidate.name)
    )),
    ...items,
  ];

  return <div className="content coach-page">
    <div className="section-intro"><span className="eyebrow">INCLUS DANS VOTRE FORFAIT</span><h2>Mon Coach 1.2.3. Home</h2><p>Posez une question. Le Coach analyse votre maison et vous propose une action utile, sans jargon.</p></div>
    {coachWeek && coachWeek.historySamples >= 4 && <details className="coach-detail coach-week-detail"><summary><span><b>Mon bilan récent</b><small>{coachWeek.observedDays} jours · {coachWeek.historySamples} relevés analysés</small></span><i>⌄</i></summary><section className="coach-week-summary" aria-label="Bilan énergétique récent">
      <div><small>BILAN SUR {coachWeek.observedDays} JOUR{coachWeek.observedDays > 1 ? "S" : ""}</small><strong>Votre maison en un coup d’œil</strong><span>{coachWeek.historySamples} relevés analysés</span></div>
      <article><small>Production solaire</small><strong>{forecastKwh(coachWeek.productionWh)}</strong><span>Énergie produite</span></article>
      <article><small>Consommation</small><strong>{forecastKwh(coachWeek.consumptionWh)}</strong><span>Énergie utilisée</span></article>
      <article><small>Couverture solaire</small><strong>{coachWeek.consumptionWh > 0 ? Math.min(100, Math.round(coachWeek.productionWh / coachWeek.consumptionWh * 100)) : 0} %</strong><span>Indicateur théorique</span></article>
    </section></details>}
    {coachActionPlan && <section className={`coach-action-plan ${coachActionPlan.status}`} aria-label="Plan d’action du Coach">
      <header><span>◎</span><div><small>{coachActionPlan.status === "ready" ? "APRÈS 14 JOURS D’ANALYSE" : `APPRENTISSAGE · JOUR ${coachActionPlan.learningDays} SUR 14`}</small><h3>{coachActionPlan.title}</h3><p>{coachActionPlan.summary}</p></div>{coachActionPlan.status === "ready" && <em>Plan disponible</em>}</header>
      {coachActionPlan.status === "learning" ? <div className="coach-learning-progress">
        <div><i style={{ width: `${Math.round(coachActionPlan.learningDays / coachActionPlan.targetDays * 100)}%` }} /></div>
        <p><strong>{coachActionPlan.daysRemaining} jour{coachActionPlan.daysRemaining > 1 ? "s" : ""} d’analyse restant{coachActionPlan.daysRemaining > 1 ? "s" : ""}</strong><span>Votre premier plan sera disponible avant la fin du mois offert.</span></p>
      </div> : <div className="coach-action-list">{coachActionPlan.actions.map((action) => <article key={action.id}>
        <b>{action.priority}</b><div><small>{action.goal === "money" ? "ÉCONOMIES" : action.goal === "battery" ? "BATTERIE" : "SOLAIRE"}</small><h4>{action.title}</h4><p>{action.description}</p><em>{action.impact}</em></div><button type="button" onClick={() => void askCoach(action.nextStep)}>Passer à l’action →</button>
      </article>)}</div>}
    </section>}
    <details className="coach-detail coach-automation-detail" open><summary><span><b>Créer une automatisation</b><small>Décrivez la règle, vérifiez son aperçu, puis confirmez</small></span><i>⌄</i></summary><section className="automation-assistant" id="assistant-domotique" aria-label="Assistant de création d’automatisations">
      <header>
        <div><span>✦</span><div><small>ASSISTANT DOMOTIQUE PREMIUM</small><h3>Dites simplement ce que vous voulez</h3><p>L’assistant prépare une règle sûre. Il ne crée rien avant votre confirmation explicite.</p></div></div>
        <em>Aperçu obligatoire</em>
      </header>
      <form onSubmit={(event) => {
        event.preventDefault();
        void prepareAssistantAutomation();
      }}>
        <textarea
          value={assistantRequest}
          maxLength={600}
          onChange={(event) => {
            setAssistantRequest(event.target.value);
            setAssistantPreview(null);
            setAssistantCreated(null);
          }}
          placeholder="Ex. Allume la filtration tous les jours à 10h30"
          aria-label="Décrivez l’automatisation souhaitée"
        />
        <button className="primary" disabled={assistantBusy || assistantRequest.trim().length < 3}>
          {assistantBusy ? "Préparation…" : "Préparer l’aperçu"}
        </button>
      </form>
      <div className="assistant-examples" aria-label="Exemples de règles compatibles">
        <small>ESSAYEZ PAR EXEMPLE</small>
        <div>{assistantExamples.map((example) => <button type="button" key={example} onClick={() => {
          setAssistantRequest(example);
          setAssistantPreview(null);
          setAssistantCreated(null);
        }}>{example}</button>)}</div>
      </div>
      {assistantCreated && <div className="assistant-result success" role="status"><span>✓</span><div><b>Demande confirmée</b><p>{assistantCreated}</p></div></div>}
      {assistantPreview?.result?.status === "ready" && assistantPreview.result.proposal && <article className="assistant-preview">
        <div className="assistant-preview-heading"><div><small>APERÇU À CONFIRMER · NON ACTIVÉ</small><h4>{assistantPreview.result.proposal.name}</h4></div><span>Valable 10 min</span></div>
        <p>{assistantPreview.result.summary}</p>
        <div className="assistant-rule"><span><b>QUAND</b>{assistantPreview.result.proposal.triggerLabel}</span><i>→</i><span><b>ALORS</b>{assistantPreview.result.proposal.actionLabel}</span></div>
        {assistantPreview.error && <p className="assistant-error">{assistantPreview.error}</p>}
        <div className="assistant-preview-actions">
          <button type="button" onClick={() => setAssistantPreview(null)}>Modifier la demande</button>
          <button type="button" className="primary" disabled={assistantBusy} onClick={() => void confirmAssistantAutomation()}>{assistantBusy ? "Confirmation…" : "Confirmer et créer"}</button>
        </div>
        <small className="assistant-safety-note">En confirmant, seule la règle affichée ci-dessus sera envoyée à votre box 1.2.3. Home.</small>
      </article>}
      {assistantPreview?.result && assistantPreview.result.status !== "ready" && <div className={`assistant-result ${assistantPreview.result.status === "refused" ? "refused" : "attention"}`} role="status">
        <span>{assistantPreview.result?.status === "refused" ? "!" : "?"}</span>
        <div><b>{assistantPreview.result?.status === "refused" ? "Action non autorisée" : "Il me manque une précision"}</b><p>{assistantPreview.result?.message ?? assistantPreview.error}</p></div>
      </div>}
      {assistantPreview?.error && !assistantPreview.result && <div className="assistant-result attention" role="status"><span>!</span><div><b>Assistant indisponible</b><p>{assistantPreview.error}</p></div></div>}
      {assistantPreview?.result && assistantPreview.result.status !== "ready" && <div className="assistant-help">
        <div><small>{assistantPreview.help?.documentation?.title ?? "Pour réussir votre demande"}</small><ol>{(assistantPreview.help?.documentation?.steps ?? [
          "Vérifiez que l’appareil est en ligne dans Équipements.",
          "Indiquez une action, un appareil et une heure précise.",
          "Relisez l’aperçu avant de confirmer.",
        ]).map((step) => <li key={step}>{step}</li>)}</ol></div>
        <button type="button" disabled={supportBusy} onClick={() => void createSupportTicket()}>{supportBusy ? "Envoi…" : "Créer un ticket support"}</button>
      </div>}
    </section></details>
    {predictivePlan && <details className="coach-detail coach-analysis-detail"><summary><span><b>Prévision énergétique</b><small>Solaire, batterie et appareils flexibles</small></span><i>⌄</i></summary><section className={`predictive-plan status-${predictivePlan.status}`} aria-label="Plan énergétique prédictif">
      {predictivePlans.length > 1 && <div className="predictive-load-tabs">{predictivePlans.map((plan) =>
        <button type="button" key={plan.loadId} className={plan.loadId === predictivePlan.loadId ? "selected" : ""} onClick={() => setPredictivePlan(plan)}>
          {plan.loadLabel}
        </button>
      )}</div>}
      <div className="predictive-plan-copy">
        <span className="predictive-plan-icon">☀</span>
        <div>
          <small>PRÉVISION SOLAIRE · {predictivePlan.loadLabel.toUpperCase()} · BATTERIE</small>
          <h3>{predictivePlan.headline}</h3>
          <p>{predictivePlan.explanation}</p>
        </div>
        <em>{predictivePlan.status === "ready_now" ? "Démarrer maintenant" : predictivePlan.status === "scheduled" ? `Prévu à ${forecastTime(predictivePlan.suggestedStartAt)}` : predictivePlan.status === "protected" ? "Batterie protégée" : predictivePlan.status === "needs_forecast" ? "À configurer" : "Surveillance active"}</em>
      </div>
      <div className="predictive-plan-data">
        <div><small>Solaire dans 6 h</small><strong>{forecastKwh(predictivePlan.forecastNextSixHoursWh)}</strong><span>Pic vers {forecastTime(predictivePlan.peakAt)}</span></div>
        <div><small>Batterie minimale prévue</small><strong>{predictivePlan.projectedMinimumBatteryPercent} %</strong><span>Réserve toujours respectée</span></div>
        <div><small>Énergie du cycle</small><strong>{forecastKwh(predictivePlan.flexibleLoadEnergyWh)}</strong><span>{forecastKwh(predictivePlan.expectedAvoidedExportWh)} de surplus valorisable</span></div>
      </div>
      {solarForecastSummary && <div className="solar-forecast-summary" aria-label="Correction adaptative de la prévision solaire">
        <div><small>Prévision météo</small><strong>{forecastKwh(solarForecastSummary.rawTodayWh)}</strong><span>Estimation brute du jour</span></div>
        <div className="prudent"><small>Prévision prudente</small><strong>{forecastKwh(solarForecastSummary.prudentTodayWh)}</strong><span>{solarForecastSummary.correctionPercent > 0 ? `Corrigée de −${solarForecastSummary.correctionPercent} %` : "Aucune correction nécessaire"}</span></div>
        <div className={`confidence-${solarForecastSummary.confidence}`}><small>Niveau de confiance</small><strong>{confidenceLabel}</strong><span>Calculé avec la production réelle</span></div>
        {solarForecastSummary.explanation && <p>{solarForecastSummary.explanation}</p>}
      </div>}
      {solarForecast.length > 0 && <div className="solar-forecast-chart" aria-label="Prévision solaire des prochaines heures">
        {solarForecast.slice(0, 12).map((slot) => <div key={slot.startsAt}>
          <i style={{ height: `${Math.max(4, Math.round(slot.estimatedWh / forecastMaximum * 100))}%` }} />
          <span>{forecastTime(slot.startsAt)}</span>
        </div>)}
      </div>}
      {["ready_now", "scheduled"].includes(predictivePlan.status) && <button className="predictive-ask" onClick={() => void askCoach(`Explique-moi le plan prédictif de ${predictivePlan.loadLabel} et les garde-fous batterie.`)}>Demander une explication au coach →</button>}
    </section></details>}
    {consumptionBreakdown.length > 0 && <details className="coach-detail coach-consumption-detail"><summary><span><b>Consommation en direct</b><small>Voir qui consomme quoi maintenant</small></span><i>⌄</i></summary><section className="coach-consumption-breakdown" aria-label="Qui consomme quoi maintenant">
      <header><div><small>MESURES EN DIRECT</small><h3>Qui consomme quoi maintenant ?</h3></div><strong>{formatWatts(consumptionBreakdown.reduce((sum, item) => sum + item.watts, 0))}</strong></header>
      <div>{consumptionBreakdown.slice(0, 6).map((item) => <article key={item.id}>
        <span>{item.icon || "ϟ"}</span><p><b>{item.name}</b><small>{item.sharePercent} % de la puissance mesurée</small></p><strong>{formatWatts(item.watts)}</strong>
        <i><em style={{ width: `${Math.max(2, item.sharePercent)}%` }} /></i>
      </article>)}</div>
      <button type="button" onClick={() => void askCoach("Quels appareils consomment le plus maintenant et comment réduire leur consommation ?")}>Demander l’analyse du Coach →</button>
    </section></details>}
    {coachInsights.length > 0 && <details className="coach-detail coach-priorities-detail"><summary><span><b>Autres priorités détectées</b><small>Conseils classés selon les mesures de la maison</small></span><i>⌄</i></summary><section className="coach-insights-section" aria-label="Conseils énergétiques personnalisés">
      <header><div><small>PLAN D’ACTION PERSONNALISÉ</small><h3>Vos priorités maintenant</h3></div><span>Classées selon les mesures de la maison</span></header>
      <div className="energy-coach-insights">{coachInsights.slice(0, 3).map((insight, index) => <article className={`coach-insight ${insight.tone}`} key={insight.id}>
        <span>{insight.icon}</span>
        <div><small>PRIORITÉ {index + 1} · {insight.goal === "money" ? "ÉCONOMIES" : insight.goal === "battery" ? "BATTERIE" : "SOLAIRE"}</small><h3>{insight.title}</h3><p>{insight.description}</p><em>{insight.impact} · {insight.confidence === "measured" ? "mesure réelle" : "estimation"}</em></div>
        <button onClick={() => void askCoach(insight.action)} aria-label={`Demander conseil : ${insight.title}`}>→</button>
      </article>)}</div>
    </section></details>}
    <section className="energy-coach-chat" aria-label="Conversation avec le coach énergie">
      <header><div><span>✦</span><p><b>Coach 1.2.3. Home</b><small><i /> Analyse personnalisée de votre maison</small></p></div><em>Inclus</em></header>
      <div className="coach-conversation" aria-live="polite">
        {coachMessages.map((message) => <div className={`coach-message ${message.role}`} key={message.id}>
          <p>{message.text}</p>
          {message.role === "coach" && !message.proposal && /filtration/i.test(message.text) && /usage flexible|pilotable|pilotée/i.test(message.text) && <button className="coach-setup-button" onClick={() => {
            const request = "Mettre la filtration en pause à 20 % de batterie si le solaire ne couvre pas sa puissance, puis la relancer lorsque le surplus réel suffit, en respectant sa durée quotidienne minimale.";
            void prepareAssistantAutomation(request);
            window.setTimeout(() => document.getElementById("assistant-domotique")?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
          }}>Préparer cette proposition</button>}
          {message.proposal && <article className="coach-proposal">
            <small>AUTOMATISATION PROPOSÉE · NON ACTIVÉE</small>
            <b>{message.proposal.name}</b>
            <span><strong>Quand</strong>{message.proposal.trigger}</span>
            <span><strong>Alors</strong>{message.proposal.action}</span>
            <button onClick={() => {
              const request = `${message.proposal?.action ?? ""} ${message.proposal?.trigger ?? ""}`.trim();
              setAssistantRequest(request);
              setAssistantPreview(null);
              setAssistantCreated(null);
              window.setTimeout(() => document.getElementById("assistant-domotique")?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
              notify("Précisez la règle puis préparez son aperçu");
            }}>Préparer cette proposition</button>
          </article>}
        </div>)}
        {coachLoading && <div className="coach-message coach"><p><i className="coach-thinking" /> J’analyse les mesures…</p></div>}
      </div>
      <div className="coach-suggestions">{coachSuggestions.map((suggestion) =>
        <button key={suggestion} disabled={coachLoading} onClick={() => void askCoach(suggestion)}>{suggestion}</button>
      )}</div>
      <form className="coach-composer" onSubmit={(event) => {
        event.preventDefault();
        void askCoach();
      }}>
        <input value={coachQuestion} maxLength={600} onChange={(event) => setCoachQuestion(event.target.value)} placeholder="Ex. Comment consommer davantage mon solaire ?" aria-label="Votre question au coach énergie" />
        <button disabled={coachLoading || coachQuestion.trim().length < 3} aria-label="Envoyer la question">↑</button>
      </form>
      <footer>Les conseils sont basés sur les données disponibles et restent des estimations.</footer>
    </section>
    {automationSyncError && <div className="assistant-result attention" role="alert"><span>!</span><div><b>Création non terminée</b><p>{automationSyncError}</p></div></div>}
    <details className="coach-detail coach-existing-automations"><summary><span><b>Mes automatisations</b><small>{displayedAutomations.length} règle{displayedAutomations.length > 1 ? "s" : ""} enregistrée{displayedAutomations.length > 1 ? "s" : ""}</small></span><i>⌄</i></summary><div className="automation-layout"><section><h3>Vos automatisations <span>{displayedAutomations.length}</span></h3><div className="automation-list">{displayedAutomations.map((a)=><article className={a.pending ? "pending" : ""} key={a.id}>
      <span className="automation-icon">{a.icon}</span><div><h4>{a.name}</h4><p><b>QUAND</b> {a.trigger}</p><p><b>ALORS</b> {a.action}</p></div>
      <label className="switch"><input type="checkbox" checked={a.active} disabled={a.pending} onChange={(event)=>{
        const enabled = event.target.checked;
        setEnabled(a, enabled)
          .then(() => notify(`${a.name} ${enabled ? "activée" : "désactivée"}`))
          .catch(() => notify("L’automatisation n’a pas pu être modifiée"));
      }} /><span /></label>
      <button disabled={a.pending} aria-label={a.pending ? `${a.name} en cours de synchronisation` : `Options pour ${a.name}`} onClick={()=>{selectAutomation(a);setModal("delete")}}>{a.pending ? "…" : "•••"}</button>
    </article>)}</div></section>
    <aside className="templates"><small>POUR COMMENCER</small><h3>Modèles populaires</h3>
      {[["☾","Bonne nuit","Éteint les lumières et baisse le chauffage"],["↗","Je quitte la maison","Sécurise et économise en un geste"],["☼","Réveil en douceur","Ouvre les volets progressivement"]].map(x=><button key={x[1]} onClick={()=>{selectAutomation(null);setModal("automation")}}><span>{x[0]}</span><div><b>{x[1]}</b><small>{x[2]}</small></div><em>＋</em></button>)}
      <button className="all-templates">Découvrir tous les modèles →</button>
    </aside></div></details>
  </div>;
}

function AddDevice({ step, setStep, notify }: {
  step: number; setStep: (value: number) => void; notify: (value: string) => void;
}) {
  const protocols = [["Zigbee","Idéal pour capteurs, lampes et interrupteurs","Rapide · Économe","⌁"],["Wi-Fi","Pour caméras et appareils connectés","Réseau 2,4 GHz requis","⌁"],["Matter","Le nouveau standard universel","Code QR · Très simple","◇"],["Bluetooth","Pour les appareils à proximité","Courte portée","ᛒ"]];
  return <div className="content guide">
    <div className="section-intro"><span className="eyebrow">Ajout guidé · Étape {step} sur 3</span><h2>{step===1?"Quel type de connexion utilise votre appareil ?":step===2?"Préparons votre appareil":"Recherche en cours"}</h2><p>{step===1?"Choisissez la technologie indiquée sur l’emballage. Nous vous guidons ensuite.":step===2?"Placez l’appareil près de la box et mettez-le en mode association.":"Nous recherchons les nouveaux appareils à proximité."}</p></div>
    <div className="stepper"><i className="done">✓</i><span className={step>=2?"done-line":""}/><i className={step>=2?"done":""}>{step>2?"✓":"2"}</i><span className={step>=3?"done-line":""}/><i className={step>=3?"done":""}>3</i></div>
    {step===1 && <div className="protocol-grid">{protocols.map(p=><button key={p[0]} onClick={()=>setStep(2)}><span>{p[3]}</span><h3>{p[0]}</h3><p>{p[1]}</p><small>{p[2]}</small><em>→</em></button>)}</div>}
    {step===2 && <div className="tutorial-card"><div className="tutorial-visual"><span>①</span><i>⌁</i></div><div><small>AVANT DE CONTINUER</small><h3>Maintenez le bouton d’association</h3><ol><li>Branchez ou alimentez l’appareil.</li><li>Maintenez son bouton pendant 5 secondes.</li><li>Attendez que le voyant clignote.</li></ol><div className="guide-actions"><button onClick={()=>setStep(1)}>Retour</button><button className="primary" onClick={()=>setStep(3)}>Le voyant clignote →</button></div></div></div>}
    {step===3 && <div className="searching-card"><div className="radar"><i>⌁</i><span/><b/></div><h3>Recherche des appareils…</h3><p>Gardez l’appareil à moins de 2 mètres de la box.</p><button onClick={()=>{notify("Progression enregistrée. Vous pourrez reprendre plus tard.");setStep(1)}}>Reprendre plus tard</button></div>}
    <div className="help-strip"><span>?</span><div><b>Besoin d’aide ?</b><small>Consultez le tutoriel de votre appareil ou lancez un diagnostic.</small></div><button onClick={()=>notify("Diagnostic prêt à démarrer")}>Dépanner</button></div>
  </div>;
}

type CustomerEnergyContract = Pick<EnergyConfiguration,
  "tariffPlan" | "basePriceMilliEurosPerKwh" | "peakPriceMilliEurosPerKwh" |
  "offPeakPriceMilliEurosPerKwh" | "exportPriceMilliEurosPerKwh" | "offPeakPeriods">;

function CustomerSettings({ dossierId, notify }: { dossierId: string; notify: (value: string) => void }) {
  const [contract, setContract] = useState<CustomerEnergyContract | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setContract(null);
    setError("");
    if (!dossierId) return undefined;
    fetch(`/api/settings/energy?dossier=${encodeURIComponent(dossierId)}`, { headers: { Accept: "application/json" } })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Chargement impossible");
        return payload.energyContract as CustomerEnergyContract;
      })
      .then((value) => { if (active) setContract(value); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Chargement impossible"); });
    return () => { active = false; };
  }, [dossierId]);

  function priceValue(value: number | null) {
    return value === null ? "" : String(value / 1000);
  }

  function setPrice(key: keyof Pick<CustomerEnergyContract, "basePriceMilliEurosPerKwh" | "peakPriceMilliEurosPerKwh" | "offPeakPriceMilliEurosPerKwh" | "exportPriceMilliEurosPerKwh">, value: string) {
    setContract((current) => current ? { ...current, [key]: value === "" ? null : Math.round(Math.max(0, Number(value) || 0) * 1000) } : current);
  }

  function updatePeriod(id: string, update: Partial<OffPeakPeriod>) {
    setContract((current) => current ? {
      ...current,
      offPeakPeriods: current.offPeakPeriods.map((period) => period.id === id ? { ...period, ...update } : period),
    } : current);
  }

  async function saveContract() {
    if (!contract) return;
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/settings/energy", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ dossierPublicId: dossierId, ...contract }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Enregistrement impossible");
      setContract(payload.energyContract);
      notify("Contrat d’électricité mis à jour pour le Coach");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Enregistrement impossible");
    } finally {
      setSaving(false);
    }
  }

  if (!contract) return <div className="content settings-page"><section className="settings-contract"><p>{error || "Chargement du contrat…"}</p></section></div>;
  return <div className="content settings-page">
    <div className="section-intro"><div><span className="eyebrow">PARAMÈTRES DE LA MAISON</span><h2>Contrat d’électricité</h2><p>Ces informations permettent au Coach de convertir les kWh en euros sans inventer de tarif. Modifiez-les lorsque votre fournisseur ou votre offre change.</p></div></div>
    <section className="settings-contract">
      <header><div><small>OFFRE ACTUELLE</small><h3>Type de contrat et prix de fourniture</h3></div><span>Maison sélectionnée uniquement</span></header>
      <div className="settings-plan-choice" role="group" aria-label="Type de contrat électrique">
        <button type="button" className={contract.tariffPlan === "base" ? "selected" : ""} onClick={() => setContract({ ...contract, tariffPlan: "base" })}><b>Option Base</b><small>Même prix toute la journée</small></button>
        <button type="button" className={contract.tariffPlan === "hp_hc" ? "selected" : ""} onClick={() => setContract({ ...contract, tariffPlan: "hp_hc", offPeakPeriods: contract.offPeakPeriods.length ? contract.offPeakPeriods : [{ id: "nuit", label: "Nuit", start: "22:30", end: "06:30" }] })}><b>Heures pleines / creuses</b><small>Prix différent selon les plages</small></button>
      </div>
      <div className="settings-price-grid">
        {contract.tariffPlan === "base" ? <label><span>Prix d’achat du kWh</span><div><input type="number" min="0" max="2" step="0.001" placeholder="0,251" value={priceValue(contract.basePriceMilliEurosPerKwh)} onChange={(event) => setPrice("basePriceMilliEurosPerKwh", event.target.value)} /><em>€ / kWh</em></div></label> : <>
          <label><span>Prix heures pleines</span><div><input type="number" min="0" max="2" step="0.001" placeholder="0,270" value={priceValue(contract.peakPriceMilliEurosPerKwh)} onChange={(event) => setPrice("peakPriceMilliEurosPerKwh", event.target.value)} /><em>€ / kWh</em></div></label>
          <label><span>Prix heures creuses</span><div><input type="number" min="0" max="2" step="0.001" placeholder="0,207" value={priceValue(contract.offPeakPriceMilliEurosPerKwh)} onChange={(event) => setPrice("offPeakPriceMilliEurosPerKwh", event.target.value)} /><em>€ / kWh</em></div></label>
        </>}
        <label><span>Rémunération de l’injection</span><div><input type="number" min="0" max="2" step="0.001" placeholder="0,040" value={priceValue(contract.exportPriceMilliEurosPerKwh)} onChange={(event) => setPrice("exportPriceMilliEurosPerKwh", event.target.value)} /><em>€ / kWh</em></div></label>
      </div>
      {contract.tariffPlan === "hp_hc" && <div className="settings-periods"><h4>Plages d’heures creuses</h4>{contract.offPeakPeriods.map((period) => <article key={period.id}>
        <input aria-label="Nom de la plage" value={period.label} onChange={(event) => updatePeriod(period.id, { label: event.target.value })} />
        <label><span>Début</span><input type="time" value={period.start} onChange={(event) => updatePeriod(period.id, { start: event.target.value })} /></label>
        <label><span>Fin</span><input type="time" value={period.end} onChange={(event) => updatePeriod(period.id, { end: event.target.value })} /></label>
        <button type="button" aria-label={`Supprimer ${period.label}`} onClick={() => setContract({ ...contract, offPeakPeriods: contract.offPeakPeriods.filter((item) => item.id !== period.id) })}>×</button>
      </article>)}<button type="button" className="settings-add-period" disabled={contract.offPeakPeriods.length >= 4} onClick={() => setContract({ ...contract, offPeakPeriods: [...contract.offPeakPeriods, { id: `hc-${Date.now()}`, label: `Plage ${contract.offPeakPeriods.length + 1}`, start: "12:00", end: "14:00" }] })}>＋ Ajouter une plage</button></div>}
      {error && <p className="settings-error">{error}</p>}
      <footer><p>Le Coach utilisera ces prix pour ses prochaines estimations. Les montants restent indiqués hors abonnement et taxes fixes.</p><button type="button" className="primary" disabled={saving} onClick={() => void saveContract()}>{saving ? "Enregistrement…" : "Enregistrer le contrat"}</button></footer>
    </section>
  </div>;
}

function Journal({ role }: { role: string }) {
  const rows = [
    ["Aujourd’hui, 09:42","Valentin","Visibilité modifiée","Prise lave-linge masquée dans l’application"],
    ["Aujourd’hui, 08:15","Système","Automatisation exécutée","Départ de la maison · 8 appareils éteints"],
    ["Hier, 18:26","Installateur","Appareil renommé","« Sonoff ZBMini » devient « Suspension du salon »"],
    ["Hier, 16:03","Valentin","Pièce modifiée","Thermostat principal déplacé dans Salon"],
    ["21 juil., 11:34","Installateur","Nouvel appareil","Détecteur fenêtre ajouté et testé"],
  ];
  return <div className="content"><div className="section-intro"><span className="eyebrow">Traçabilité · Vue {role.toLowerCase()}</span><h2>Journal des actions importantes</h2><p>Retrouvez les changements, leurs auteurs et leur date. Les données sensibles restent masquées.</p></div>
    <section className="log-table"><div className="log-head"><b>Date</b><b>Auteur</b><b>Action</b><b>Détail</b></div>{rows.map(r=><div className="log-row" key={r[0]+r[2]}>{r.map((x,i)=><span key={x} data-label={["Date","Auteur","Action","Détail"][i]}>{x}</span>)}</div>)}</section>
  </div>;
}

function Modal({
  type, close, notify, device, devices, areas, saveDevice, automation,
  createAutomation, deleteAutomation,
}: {
  type: string;
  close: () => void;
  notify: (value: string) => void;
  device: Device | null;
  devices: Device[];
  areas: Area[];
  saveDevice: (
    device: Device,
    update: { name?: string; areaPublicId?: string | null; visible?: boolean },
  ) => Promise<void>;
  automation: Automation | null;
  createAutomation: (draft: AutomationDraft) => Promise<void>;
  deleteAutomation: (automation: Automation) => Promise<void>;
}) {
  const [deviceName, setDeviceName] = useState(device?.name ?? "");
  const [deviceArea, setDeviceArea] = useState(device?.areaPublicId ?? "");
  const [deviceVisible, setDeviceVisible] = useState(device?.visible ?? true);
  const actionableDevices = devices.filter((item) =>
    item.controllable !== false && item.online
  );
  const [automationName, setAutomationName] = useState("");
  const [automationTime, setAutomationTime] = useState("20:30");
  const [automationDeviceId, setAutomationDeviceId] = useState(
    actionableDevices[0]?.id ?? "",
  );
  const [automationDesiredActive, setAutomationDesiredActive] = useState(false);
  const [automationConfirmation, setAutomationConfirmation] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submitDevice() {
    if (!device || deviceName.trim().length < 2) {
      notify("Saisissez un nom d’au moins 2 caractères");
      return;
    }
    setBusy(true);
    try {
      await saveDevice(device, {
        name: deviceName.trim(),
        areaPublicId: deviceArea || null,
        visible: deviceVisible,
      });
      notify("Modifications enregistrées dans votre maison");
      close();
    } catch {
      notify("Les modifications n’ont pas pu être enregistrées");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDeletion() {
    if (!automation) return;
    setBusy(true);
    try {
      await deleteAutomation(automation);
      notify("Automatisation supprimée");
      close();
    } catch {
      notify("L’automatisation n’a pas pu être supprimée");
    } finally {
      setBusy(false);
    }
  }

  async function submitAutomation() {
    if (
      automationName.trim().length < 3 ||
      !automationDeviceId ||
      !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(automationTime)
    ) {
      notify("Complétez le nom, l’horaire et l’appareil");
      return;
    }
    setBusy(true);
    try {
      await createAutomation({
        name: automationName.trim(),
        time: automationTime,
        publicDeviceId: automationDeviceId,
        desiredActive: automationDesiredActive,
      });
      notify("Automatisation envoyée à votre box 1.2.3. Home");
      close();
    } catch {
      notify("L’automatisation n’a pas pu être créée");
    } finally {
      setBusy(false);
    }
  }

  if (type === "alertes") return <div className="modal-backdrop" onMouseDown={close}><div className="modal" onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={close}>×</button><span className="modal-symbol">!</span><small>UNE ACTION RECOMMANDÉE</small><h3>Batterie bientôt épuisée</h3><p>Le détecteur de fenêtre du salon est à 14 %. Son fonctionnement peut devenir irrégulier.</p><div className="alert-detail"><b>Détecteur fenêtre</b><span>Salon · Batterie CR2032</span></div><button className="primary full" onClick={()=>{notify("Rappel programmé pour demain");close()}}>Me le rappeler demain</button></div></div>;
  if (type === "delete") return <div className="modal-backdrop" onMouseDown={close}><div className="modal" onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={close}>×</button><span className="modal-symbol danger">×</span><small>CONFIRMATION REQUISE</small><h3>Supprimer cette automatisation ?</h3><p>« {automation?.name ?? "Cette automatisation"} » ne s’exécutera plus. Cette action ne pourra pas être annulée.</p><div className="modal-actions"><button disabled={busy} onClick={close}>Annuler</button><button disabled={busy || !automation} className="danger-button" onClick={confirmDeletion}>{busy ? "Suppression…" : "Supprimer"}</button></div></div></div>;
  if (type === "appareil") return <div className="modal-backdrop" onMouseDown={close}><div className="modal wide" onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={close}>×</button><small>GÉRER L’APPAREIL</small><h3>{device?.name ?? "Appareil"}</h3><label className="field">Nom convivial<input value={deviceName} maxLength={80} onChange={event=>setDeviceName(event.target.value)} /></label><label className="field">Pièce<select value={deviceArea} onChange={event=>setDeviceArea(event.target.value)}><option value="">Maison · sans pièce</option>{areas.map((area)=><option key={area.publicId} value={area.publicId}>{area.name}</option>)}</select></label><label className="check-row"><input type="checkbox" checked={deviceVisible} onChange={event=>setDeviceVisible(event.target.checked)} /> Visible dans l’application Ma Maison</label><button disabled={busy || !device} className="primary full" onClick={submitDevice}>{busy ? "Enregistrement…" : "Enregistrer les modifications"}</button></div></div>;
  const selectedTarget = actionableDevices.find(
    (item) => item.id === automationDeviceId,
  );
  const actionLabel = selectedTarget?.category === "Sécurité"
    ? automationDesiredActive ? "Verrouiller" : "Déverrouiller"
    : automationDesiredActive ? "Allumer" : "Éteindre";
  return <div className="modal-backdrop" onMouseDown={close}><div className="modal automation-modal wide" onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={close}>×</button><small>RÈGLE SIMPLE · BOX 1.2.3 HOME</small><h3>Créer une automatisation</h3><p>La règle est préparée ici puis exécutée localement dans votre maison, même si Internet est coupé.</p><label className="field">Nom de la règle<input value={automationName} maxLength={80} placeholder="Éclairage du soir" onChange={event=>{setAutomationName(event.target.value);setAutomationConfirmation(false)}} /></label><div className="rule-row"><b>QUAND</b><label><span>Chaque jour à</span><input type="time" value={automationTime} onChange={event=>{setAutomationTime(event.target.value);setAutomationConfirmation(false)}} /></label></div><div className="rule-row"><b>SI</b><div className="optional-condition">Toujours · aucune condition supplémentaire</div></div><div className="rule-row"><b>ALORS</b><div className="automation-action-fields"><select value={automationDeviceId} onChange={event=>{setAutomationDeviceId(event.target.value);setAutomationConfirmation(false)}}><option value="">Choisir un appareil</option>{actionableDevices.map((item)=><option key={item.id} value={item.id}>{item.name} · {item.room}</option>)}</select><select value={automationDesiredActive ? "on" : "off"} onChange={event=>{setAutomationDesiredActive(event.target.value==="on");setAutomationConfirmation(false)}}><option value="on">{selectedTarget?.category === "Sécurité" ? "Verrouiller" : "Allumer"}</option><option value="off">{selectedTarget?.category === "Sécurité" ? "Déverrouiller" : "Éteindre"}</option></select></div></div>{automationConfirmation && <div className="automation-confirmation"><b>Confirmez la règle</b><p>Tous les jours à {automationTime}, la box 1.2.3. Home va {actionLabel.toLowerCase()} « {selectedTarget?.name ?? "l’appareil sélectionné"} ».</p></div>}<button disabled={busy || !actionableDevices.length} className="primary full" onClick={()=>automationConfirmation ? void submitAutomation() : setAutomationConfirmation(true)}>{busy ? "Envoi à la maison…" : automationConfirmation ? "Confirmer et activer" : "Vérifier la règle"}</button>{!actionableDevices.length && <p className="automation-empty">Aucun appareil pilotable n’est actuellement disponible.</p>}</div></div>;
}
