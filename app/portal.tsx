"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type View = "Accueil" | "Préparation" | "Installation" | "Appareils" | "Automatisations" | "Ajouter" | "Journal";
type Device = {
  id: string; name: string; room: string; areaPublicId: string | null;
  category: string; state: string;
  detail: string; battery?: number; online: boolean; visible: boolean; icon: string;
};
type Area = { publicId: string; name: string };
type Automation = {
  id: string; name: string; trigger: string; action: string;
  active: boolean; icon: string; lastTriggered?: string | null;
};
type MobileOverview = {
  energy: Record<string, string>;
  controls: { label: string; active: boolean; available: boolean }[];
};
type CompatibilityLevel = "Automatique" | "Assistée" | "Expert";
type CatalogItem = {
  id: string; brand: string; model: string; category: string; protocol: string;
  level: CompatibilityLevel; method: string; prerequisites: string;
  estimatedMinutes: number; icon: string;
};
type InstallationStatus = "À préparer" | "Prêt" | "Détecté" | "Associé" | "Testé" | "Bloqué";
type PlannedItem = CatalogItem & { quantity: number; room: string; status: InstallationStatus };

const catalogItems: CatalogItem[] = [
  { id: "shelly-plus-1pm", brand: "Shelly", model: "Plus 1PM", category: "Éclairage", protocol: "Wi-Fi", level: "Automatique", method: "Détection réseau locale", prerequisites: "Alimentation et Wi-Fi 2,4 GHz", estimatedMinutes: 2, icon: "◉" },
  { id: "hue-motion", brand: "Philips Hue", model: "Motion Sensor", category: "Capteur", protocol: "Zigbee", level: "Assistée", method: "Mise en association Zigbee", prerequisites: "Appuyer 5 s sur Setup", estimatedMinutes: 3, icon: "⌁" },
  { id: "aqara-door-p2", brand: "Aqara", model: "Door and Window P2", category: "Sécurité", protocol: "Matter", level: "Assistée", method: "Scan du QR code Matter", prerequisites: "Code Matter et réseau Thread", estimatedMinutes: 3, icon: "▣" },
  { id: "tesla-wall", brand: "Tesla", model: "Wall Connector Gen 3", category: "Recharge", protocol: "Wi-Fi", level: "Automatique", method: "Détection réseau locale", prerequisites: "Connecté au réseau du client", estimatedMinutes: 4, icon: "ϟ" },
  { id: "daikin-altherma", brand: "Daikin", model: "Altherma", category: "Chauffage", protocol: "Réseau", level: "Expert", method: "Intégration selon passerelle", prerequisites: "Modèle et passerelle à confirmer", estimatedMinutes: 15, icon: "♨" },
  { id: "fronius-gen24", brand: "Fronius", model: "GEN24", category: "Solaire", protocol: "Réseau", level: "Automatique", method: "Découverte Modbus locale", prerequisites: "Solar API activée", estimatedMinutes: 5, icon: "☀" },
  { id: "sonoff-zbmini", brand: "Sonoff", model: "ZBMINI-L2", category: "Éclairage", protocol: "Zigbee", level: "Assistée", method: "Mise en association Zigbee", prerequisites: "Action sur interrupteur ou bouton", estimatedMinutes: 3, icon: "◉" },
  { id: "pool-relay", brand: "1.2.3 Domotique", model: "Coffret piscine", category: "Piscine", protocol: "Modbus", level: "Expert", method: "Adresse réseau et registre validé", prerequisites: "Schéma électrique et accès local", estimatedMinutes: 20, icon: "♒" },
];

const demoDevices: Device[] = [
  { id: "demo_1", name: "Suspension du salon", room: "Salon", areaPublicId: null, category: "Éclairage", state: "Allumée", detail: "48 %", online: true, visible: true, icon: "◉" },
  { id: "demo_2", name: "Thermostat principal", room: "Salon", areaPublicId: null, category: "Climat", state: "Confort", detail: "21,5 °C", battery: 82, online: true, visible: true, icon: "♨" },
  { id: "demo_3", name: "Détecteur fenêtre", room: "Salon", areaPublicId: null, category: "Sécurité", state: "Fermée", detail: "Aucune anomalie", battery: 14, online: true, visible: true, icon: "▣" },
  { id: "demo_4", name: "Lampe chevet gauche", room: "Chambre", areaPublicId: null, category: "Éclairage", state: "Éteinte", detail: "Prête", online: true, visible: true, icon: "◉" },
  { id: "demo_5", name: "Prise lave-linge", room: "Buanderie", areaPublicId: null, category: "Énergie", state: "En veille", detail: "0,3 W", online: true, visible: false, icon: "ϟ" },
  { id: "demo_6", name: "Capteur de jardin", room: "Extérieur", areaPublicId: null, category: "Capteurs", state: "Indisponible", detail: "Vu il y a 2 h", battery: 36, online: false, visible: false, icon: "⌁" },
];

const demoAutomations: Automation[] = [
  { id: "demo_a1", name: "Départ de la maison", trigger: "Quand le dernier occupant part", action: "Éteindre 8 appareils", active: true, icon: "↗" },
  { id: "demo_a2", name: "Soirée douce", trigger: "Quand il est 20 h 30", action: "Salon à 35 % · 20 °C", active: true, icon: "☾" },
  { id: "demo_a3", name: "Alerte fenêtre", trigger: "Quand une fenêtre reste ouverte", action: "Notifier après 10 minutes", active: true, icon: "!" },
  { id: "demo_a4", name: "Arrosage intelligent", trigger: "Quand l’humidité est basse", action: "Arroser pendant 12 minutes", active: false, icon: "⌁" },
];

const nav: { label: View; icon: string }[] = [
  { label: "Accueil", icon: "⌂" }, { label: "Préparation", icon: "✓" }, { label: "Installation", icon: "⌁" }, { label: "Appareils", icon: "◫" },
  { label: "Automatisations", icon: "⌁" }, { label: "Ajouter", icon: "+" },
  { label: "Journal", icon: "≡" },
];

export default function Portal() {
  const [view, setView] = useState<View>("Accueil");
  const [search, setSearch] = useState("");
  const [room, setRoom] = useState("Toutes");
  const [role, setRole] = useState<"Client" | "Installateur">("Client");
  const [toast, setToast] = useState("");
  const [modal, setModal] = useState<string | null>(null);
  const [guideStep, setGuideStep] = useState(1);
  const [devices, setDevices] = useState<Device[]>(demoDevices);
  const [areas, setAreas] = useState<Area[]>([]);
  const [automationItems, setAutomationItems] = useState<Automation[]>(demoAutomations);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [selectedAutomation, setSelectedAutomation] = useState<Automation | null>(null);
  const [liveStatus, setLiveStatus] = useState<"loading" | "connected" | "demo">("loading");
  const [mobileOverview, setMobileOverview] = useState<MobileOverview | null>(null);
  const [plannedItems, setPlannedItems] = useState<PlannedItem[]>([
    { ...catalogItems[5], quantity: 1, room: "Local technique", status: "Prêt" },
    { ...catalogItems[6], quantity: 4, room: "Salon", status: "À préparer" },
  ]);

  useEffect(() => {
    let active = true;
    fetch("/api/home", { headers: { Accept: "application/json" } })
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
          battery: number | null; visible: boolean;
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
        setLiveStatus("connected");
      })
      .catch(() => setLiveStatus("demo"));
    return () => { active = false; };
  }, []);

  const filtered = useMemo(() => devices.filter((device) =>
    (room === "Toutes" || device.room === room) &&
    `${device.name} ${device.room} ${device.category}`.toLowerCase().includes(search.toLowerCase())
  ), [devices, room, search]);

  function notify(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  }

  async function updateDevice(
    device: Device,
    update: { name?: string; areaPublicId?: string | null; visible?: boolean },
  ) {
    const response = await fetch(`/api/devices/${encodeURIComponent(device.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(update),
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
        body: JSON.stringify({ enabled }),
      },
    );
    if (!response.ok) throw new Error("update");
    setAutomationItems((items) => items.map((item) =>
      item.id === automation.id ? { ...item, active: enabled } : item
    ));
  }

  async function deleteAutomation(automation: Automation) {
    const response = await fetch(
      `/api/automations/${encodeURIComponent(automation.id)}`,
      { method: "DELETE", headers: { Accept: "application/json" } },
    );
    if (!response.ok) throw new Error("delete");
    setAutomationItems((items) => items.filter((item) => item.id !== automation.id));
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setView("Accueil")} aria-label="Retour à l’accueil">
          <span className="brand-mark">M</span><span>Ma Maison</span>
        </button>
        <nav aria-label="Navigation principale">
          {nav.filter((item) => !["Préparation", "Installation"].includes(item.label) || role === "Installateur").map((item) => <button key={item.label} className={view === item.label ? "active" : ""} onClick={() => setView(item.label)}>
            <span className="nav-icon">{item.icon}</span><span>{item.label}</span>
          </button>)}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection"><i /> Maison connectée <small>Dernière synchro à l’instant</small></div>
          <button className="profile" onClick={() => setRole(role === "Client" ? "Installateur" : "Client")}>
            <span>VF</span><b>Valentin Fettig<small>{role} · Basculer</small></b><em>⌄</em>
          </button>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <p>Jeudi 23 juillet</p>
            <h1>{view === "Accueil" ? "Bonjour Valentin" : view}</h1>
          </div>
          <div className="top-actions">
            <Link className="dashboard-link" href="/ma-maison">Ouvrir Ma Maison</Link>
            <button className="icon-button" aria-label="Actualiser" onClick={() => notify("Maison actualisée à l’instant")}>↻</button>
            <button className="icon-button notification" aria-label="Notifications" onClick={() => setModal("alertes")}>♢<i /></button>
            <button className="primary" onClick={() => setView("Ajouter")}><span>＋</span> Ajouter un appareil</button>
          </div>
        </header>

        {view === "Accueil" && <Dashboard setView={setView} setModal={setModal} notify={notify} devices={devices} liveStatus={liveStatus} overview={mobileOverview} />}
        {view === "Préparation" && <Preparation plannedItems={plannedItems} setPlannedItems={setPlannedItems} notify={notify} setView={setView} />}
        {view === "Installation" && <Installation notify={notify} />}
        {view === "Appareils" && <Devices filtered={filtered} areas={areas} search={search} setSearch={setSearch} room={room} setRoom={setRoom} notify={notify} manage={(device) => { setSelectedDevice(device); setModal("appareil"); }} updateDevice={updateDevice} />}
        {view === "Automatisations" && <Automations items={automationItems} setModal={setModal} notify={notify} selectAutomation={setSelectedAutomation} setEnabled={setAutomationEnabled} />}
        {view === "Ajouter" && <AddDevice step={guideStep} setStep={setGuideStep} notify={notify} />}
        {view === "Journal" && <Journal role={role} />}
      </main>

      <nav className="mobile-nav" aria-label="Navigation mobile">
        {nav.filter((item) => !["Préparation", "Installation"].includes(item.label)).slice(0, 4).map((item) => <button key={item.label} className={view === item.label ? "active" : ""} onClick={() => setView(item.label)}>
          <span>{item.icon}</span><small>{item.label}</small>
        </button>)}
      </nav>

      {toast && <div className="toast">✓ {toast}</div>}
      {modal && <Modal key={`${modal}:${selectedDevice?.id ?? selectedAutomation?.id ?? "none"}`} type={modal} close={() => setModal(null)} notify={notify} device={selectedDevice} areas={areas} saveDevice={updateDevice} automation={selectedAutomation} deleteAutomation={deleteAutomation} />}
    </div>
  );
}

function Preparation({ plannedItems, setPlannedItems, notify, setView }: {
  plannedItems: PlannedItem[];
  setPlannedItems: (items: PlannedItem[]) => void;
  notify: (value: string) => void;
  setView: (value: View) => void;
}) {
  const [query, setQuery] = useState("");
  const [protocol, setProtocol] = useState("Tous");
  const [selectedRoom, setSelectedRoom] = useState("Salon");
  const [dossier, setDossier] = useState({ reference: "Chargement…", customerName: "" });
  const [saveState, setSaveState] = useState<"saved" | "saving" | "offline">("saving");

  useEffect(() => {
    let active = true;
    fetch("/api/preparation", { headers: { Accept: "application/json" } })
      .then(async (response) => {
        if (!response.ok) throw new Error("load");
        return response.json();
      })
      .then((payload) => {
        if (!active) return;
        setDossier(payload.dossier);
        setPlannedItems(payload.items);
        setSaveState("saved");
      })
      .catch(() => {
        if (!active) return;
        setDossier({ reference: "DOSSIER-PILOTE", customerName: "Maison pilote" });
        setSaveState("offline");
      });
    return () => { active = false; };
  }, [setPlannedItems]);

  async function save(items: PlannedItem[]) {
    setPlannedItems(items);
    setSaveState("saving");
    try {
      const response = await fetch("/api/preparation", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ items }),
      });
      if (!response.ok) throw new Error("save");
      setSaveState("saved");
    } catch {
      setSaveState("offline");
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

  return <div className="content preparation">
    <div className="section-intro split">
      <div><span className="eyebrow">Dossier {dossier.reference} · {dossier.customerName}</span><h2>Préparer les objets à connecter</h2><p>La liste commerciale est transformée en procédure d’installation. Complétez les modèles avant le départ.</p></div>
      <div className="prep-heading-actions"><span className={`save-state ${saveState}`}>{saveState === "saved" ? "✓ Liste enregistrée" : saveState === "saving" ? "Enregistrement…" : "Sauvegarde à reprendre"}</span><button className="primary" onClick={() => setView("Installation")}>Ouvrir la checklist</button></div>
    </div>
    <section className="prep-summary">
      <div><small>Objets prévus</small><strong>{totalObjects}</strong><span>{plannedItems.length} références</span></div>
      <div><small>Temps estimé</small><strong>{estimated} min</strong><span>hors câblage</span></div>
      <div><small>Installation automatique</small><strong>{plannedItems.filter(item => item.level === "Automatique").length}/{plannedItems.length}</strong><span>références</span></div>
      <div className={plannedItems.some(item => item.level === "Expert") ? "attention" : ""}><small>À vérifier avant départ</small><strong>{plannedItems.filter(item => item.level === "Expert").length}</strong><span>matériel expert</span></div>
    </section>
    <div className="prep-layout">
      <section className="catalog-panel">
        <div className="panel-title"><div><small>Catalogue validé</small><h3>Trouver un équipement</h3></div></div>
        <div className="catalog-tools"><label><span>⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Marque, modèle ou catégorie…" /></label><select value={protocol} onChange={event => setProtocol(event.target.value)}>{["Tous","Wi-Fi","Zigbee","Matter","Réseau","Modbus"].map(value => <option key={value}>{value}</option>)}</select><select aria-label="Pièce de destination" value={selectedRoom} onChange={event => setSelectedRoom(event.target.value)}>{["Salon","Cuisine","Chambre","Extérieur","Garage","Local technique"].map(value => <option key={value}>{value}</option>)}</select></div>
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
  </div>;
}

const installationStages: InstallationStatus[] = ["Prêt", "Détecté", "Associé", "Testé"];

function Installation({ notify }: { notify: (value: string) => void }) {
  const [items, setItems] = useState<PlannedItem[]>([]);
  const [dossier, setDossier] = useState({ reference: "Chargement…", customerName: "" });
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/preparation", { headers: { Accept: "application/json" } })
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
    return () => { active = false; };
  }, []);

  async function save(next: PlannedItem[], activeId: string) {
    setItems(next);
    setSavingId(activeId);
    try {
      const response = await fetch("/api/preparation", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ items: next }),
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

  const tested = items.filter(item => item.status === "Testé").reduce((sum, item) => sum + item.quantity, 0);
  const total = items.reduce((sum, item) => sum + item.quantity, 0);
  const blocked = items.filter(item => item.status === "Bloqué").length;
  const progress = total ? Math.round((tested / total) * 100) : 0;

  return <div className="content intervention">
    <div className="section-intro split"><div><span className="eyebrow">Intervention · {dossier.reference}</span><h2>Installer chez {dossier.customerName}</h2><p>Suivez la liste préparée. Chaque étape est enregistrée et peut être reprise par un autre technicien.</p></div><button className="primary" onClick={() => notify("La recherche démarrera dès que l’agent de la box sera connecté")}>⌁ Lancer la découverte</button></div>
    <section className="intervention-progress">
      <div className="progress-ring" style={{ "--progress": `${progress * 3.6}deg` } as React.CSSProperties}><span><strong>{progress}%</strong><small>terminé</small></span></div>
      <div><small>RECETTE DE LA MAISON</small><h3>{tested} objet{tested > 1 ? "s" : ""} testé{tested > 1 ? "s" : ""} sur {total}</h3><div className="progress-bar"><i style={{ width: `${progress}%` }} /></div><p>{blocked ? `${blocked} blocage${blocked > 1 ? "s" : ""} à résoudre avant la remise client.` : "Aucun blocage signalé."}</p></div>
      <div className="box-state"><i /><span>Agent de la box<strong>En attente de connexion</strong></span><button onClick={() => notify("Diagnostic de connexion préparé")}>Diagnostiquer</button></div>
    </section>
    {loading ? <div className="checklist-empty">Chargement de la checklist…</div> : !items.length ? <div className="checklist-empty">Aucun équipement n’a encore été préparé pour ce dossier.</div> :
      <section className="installation-list">{items.map(item => {
        const activeIndex = installationStages.indexOf(item.status);
        const rowId = `${item.id}:${item.room}`;
        return <article key={rowId} className={item.status === "Bloqué" ? "blocked" : item.status === "Testé" ? "tested" : ""}>
          <div className="installation-device"><span>{item.icon}</span><div><small>{item.category} · {item.protocol} · Qté {item.quantity}</small><h3>{item.brand} {item.model}</h3><p>{item.room} · {item.method}</p></div><em className={`level level-${item.level.toLowerCase()}`}>{item.level}</em></div>
          <div className="stage-track">{installationStages.map((stage, index) => <button key={stage} className={item.status !== "Bloqué" && index <= activeIndex ? "done" : ""} onClick={() => updateStatus(item, stage)}><i>{item.status !== "Bloqué" && index <= activeIndex ? "✓" : index + 1}</i><span>{stage}</span></button>)}</div>
          <div className="installation-detail"><span><b>À prévoir</b>{item.prerequisites}</span><span><b>Temps prévu</b>≈ {item.estimatedMinutes * item.quantity} min</span><button className={item.status === "Bloqué" ? "unblock" : "block"} disabled={savingId === rowId} onClick={() => updateStatus(item, item.status === "Bloqué" ? "Prêt" : "Bloqué")}>{savingId === rowId ? "Enregistrement…" : item.status === "Bloqué" ? "Reprendre" : "Signaler un blocage"}</button></div>
        </article>;
      })}</section>}
    <section className="handover"><div><span>✓</span><p><b>Remise au client</b><small>Disponible lorsque tous les équipements sont testés et qu’aucun blocage ne subsiste.</small></p></div><button disabled={progress < 100 || blocked > 0} onClick={() => notify("Rapport de mise en service généré")}>Terminer l’installation</button></section>
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

function Dashboard({ setView, setModal, notify, devices, liveStatus, overview }: {
  setView: (v: View) => void; setModal: (v: string) => void;
  notify: (v: string) => void; devices: Device[];
  liveStatus: "loading" | "connected" | "demo";
  overview: MobileOverview | null;
}) {
  const available = devices.filter((device) => device.online).length;
  const lowBattery = devices.filter((device) => device.battery !== undefined && device.battery < 20).length;
  return <div className="content app-home">
    <section className="app-preview">
      <div className="app-tabs"><button className="selected">Home</button><button>Énergie</button><button>Piscine</button><button>Spa</button></div>
      <div className="app-connection"><i />{liveStatus === "connected" ? "Maison connectée" : liveStatus === "loading" ? "Connexion en cours…" : "Mode démonstration"}</div>
      <div className="energy-flow">
        <div className="flow-lines"><span className="line solar-home"/><span className="line grid-home"/><span className="line battery-home"/><i className="hub"/></div>
        <FlowNode className="solar" icon="☀" label="Solaire" value={overview?.energy.solar ?? "0 W"} color="yellow" />
        <FlowNode className="grid" icon="♜" label="Réseau" value={overview?.energy.grid ?? "0 W"} color="blue" />
        <FlowNode className="house" icon="⌂" label="Maison" value={overview?.energy.home ?? "0 W"} color="teal" />
        <FlowNode className="battery-node" icon="▰" label="Batterie" value={overview?.energy.battery ?? "0 %"} sub={overview?.energy.batteryPower} color="green" />
        <FlowNode className="filter-node" icon="♒" label="Filtration" value={overview?.energy.filtration ?? "0 W"} color="cyan" />
      </div>
      <div className="mobile-controls">
        {(overview?.controls ?? [
          {label:"Portail",active:false,available:true},{label:"Terrasse",active:false,available:true},
          {label:"PAC piscine",active:false,available:true},{label:"Filtration",active:false,available:true},
          {label:"Spa",active:false,available:true},{label:"Filtration spa",active:false,available:true},
        ]).map((control, index) => <button key={control.label} onClick={() => notify(`${control.label} : commande disponible prochainement`)}>
          <span className={control.active ? "control-state active" : "control-state"}>{!control.available ? "INDISPONIBLE" : control.active ? "ACTIF" : "ARRÊT"}</span>
          <i>{["▯","♨","♒","▤","♨","▤"][index]}</i><b>{control.label}</b>
        </button>)}
      </div>
      <div className="today-energy"><div><small>Aujourd’hui</small><strong>{overview?.energy.dailyProduction ?? "—"}</strong><span>Production</span></div><div><small>Consommation</small><strong>{overview?.energy.dailyConsumption ?? "—"}</strong><span>Maison</span></div><button onClick={() => notify("Détail énergétique")}>Voir l’énergie →</button></div>
    </section>
    <section className="hero">
      <div><span className="eyebrow"><i /> {liveStatus === "connected" ? "Maison connectée en direct" : liveStatus === "loading" ? "Connexion en cours" : "Mode démonstration"}</span><h2>Votre maison est calme<br />et sous contrôle.</h2><p>{liveStatus === "connected" ? `${available} appareils sur ${devices.length} sont disponibles.` : "Les informations de démonstration sont affichées temporairement."}</p></div>
      <div className="hero-temperature"><span>Ensoleillé</span><strong>24°</strong><small>Intérieur · 21,5°</small></div>
    </section>
    <div className="metrics">
      <article><span className="metric-icon yellow">◫</span><div><small>Appareils</small><strong>{devices.length}</strong><p><i /> {available} disponibles</p></div><button onClick={() => setView("Appareils")}>›</button></article>
      <article><span className="metric-icon blue">ϟ</span><div><small>Énergie aujourd’hui</small><strong>8,4 <em>kWh</em></strong><p className="positive">↓ 12 % vs hier</p></div></article>
      <article className="warning-card"><span className="metric-icon orange">!</span><div><small>À vérifier</small><strong>{lowBattery} alerte{lowBattery > 1 ? "s" : ""}</strong><p>{lowBattery ? "Batterie faible détectée" : "Aucune batterie faible"}</p></div><button onClick={() => setModal("alertes")}>›</button></article>
      <article><span className="metric-icon purple">⌁</span><div><small>Automatisations</small><strong>6 actives</strong><p>3 exécutées aujourd’hui</p></div><button onClick={() => setView("Automatisations")}>›</button></article>
    </div>
    <div className="dashboard-grid">
      <section className="panel rooms">
        <div className="panel-title"><div><small>Vue d’ensemble</small><h3>Pièces</h3></div><button onClick={() => setView("Appareils")}>Voir tous les appareils <span>→</span></button></div>
        <div className="room-grid">
          {[["Salon", "8 appareils", "21,5°", "◎"], ["Cuisine", "5 appareils", "20,8°", "⌂"], ["Chambre", "6 appareils", "19,5°", "▣"], ["Extérieur", "5 appareils", "12°", "⌁"]].map(([name, count, temp, icon], i) =>
            <button className="room-card" key={name} onClick={() => setView("Appareils")}><span className={`room-visual room-${i}`}>{icon}</span><b>{name}</b><small>{count}<em>{temp}</em></small></button>)}
        </div>
      </section>
      <section className="panel activity">
        <div className="panel-title"><div><small>En direct</small><h3>Activité récente</h3></div><button onClick={() => setView("Journal")}>Tout voir</button></div>
        <ul>
          <li><span className="activity-icon">☼</span><div><b>Volets du salon ouverts</b><small>Automatisation « Réveil »</small></div><time>07:32</time></li>
          <li><span className="activity-icon">♨</span><div><b>Température ajustée à 21°</b><small>Thermostat principal</small></div><time>06:45</time></li>
          <li><span className="activity-icon">⌁</span><div><b>Portail fermé</b><small>Action de Valentin</small></div><time>Hier</time></li>
          <li><span className="activity-icon warn">!</span><div><b>Batterie faible détectée</b><small>Détecteur fenêtre salon</small></div><time>Hier</time></li>
        </ul>
      </section>
    </div>
    <section className="energy-strip"><div><span className="metric-icon blue">ϟ</span><div><small>Consommation instantanée</small><strong>1,24 kW</strong></div></div><div className="bars">{[24,32,28,42,38,56,48,64,52,60,44,38,30,26,34,48,62,76,55,40].map((h,i)=><i key={i} style={{height:`${h}%`}} />)}</div><div><small>Estimation du mois</small><strong>68,40 €</strong><button onClick={() => notify("Le détail énergétique sera disponible après raccordement")}>Voir le détail →</button></div></section>
  </div>;
}

function FlowNode({ className, icon, label, value, sub, color }: {
  className: string; icon: string; label: string; value: string; sub?: string; color: string;
}) {
  return <div className={`flow-node ${className} ${color}`}><small>{label}</small><span>{icon}</span><strong>{value}</strong>{sub && <em>{sub}</em>}</div>;
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

function Automations({ items, setModal, notify, selectAutomation, setEnabled }: {
  items: Automation[]; setModal: (value: string) => void;
  notify: (value: string) => void;
  selectAutomation: (automation: Automation | null) => void;
  setEnabled: (automation: Automation, enabled: boolean) => Promise<void>;
}) {
  return <div className="content">
    <div className="section-intro split"><div><span className="eyebrow">Simple et puissant</span><h2>Les habitudes qui travaillent pour vous</h2><p>Créez des règles faciles à comprendre, sans réglage technique.</p></div><button className="primary" onClick={()=>{selectAutomation(null);setModal("automation")}}>＋ Créer une automatisation</button></div>
    <div className="automation-layout"><section><h3>Vos automatisations <span>{items.length}</span></h3><div className="automation-list">{items.map((a)=><article key={a.id}>
      <span className="automation-icon">{a.icon}</span><div><h4>{a.name}</h4><p><b>QUAND</b> {a.trigger}</p><p><b>ALORS</b> {a.action}</p></div>
      <label className="switch"><input type="checkbox" checked={a.active} onChange={(event)=>{
        const enabled = event.target.checked;
        setEnabled(a, enabled)
          .then(() => notify(`${a.name} ${enabled ? "activée" : "désactivée"}`))
          .catch(() => notify("L’automatisation n’a pas pu être modifiée"));
      }} /><span /></label>
      <button aria-label={`Options pour ${a.name}`} onClick={()=>{selectAutomation(a);setModal("delete")}}>•••</button>
    </article>)}</div></section>
    <aside className="templates"><small>POUR COMMENCER</small><h3>Modèles populaires</h3>
      {[["☾","Bonne nuit","Éteint les lumières et baisse le chauffage"],["↗","Je quitte la maison","Sécurise et économise en un geste"],["☼","Réveil en douceur","Ouvre les volets progressivement"]].map(x=><button key={x[1]} onClick={()=>{selectAutomation(null);setModal("automation")}}><span>{x[0]}</span><div><b>{x[1]}</b><small>{x[2]}</small></div><em>＋</em></button>)}
      <button className="all-templates">Découvrir tous les modèles →</button>
    </aside></div>
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
  type, close, notify, device, areas, saveDevice, automation, deleteAutomation,
}: {
  type: string;
  close: () => void;
  notify: (value: string) => void;
  device: Device | null;
  areas: Area[];
  saveDevice: (
    device: Device,
    update: { name?: string; areaPublicId?: string | null; visible?: boolean },
  ) => Promise<void>;
  automation: Automation | null;
  deleteAutomation: (automation: Automation) => Promise<void>;
}) {
  const [deviceName, setDeviceName] = useState(device?.name ?? "");
  const [deviceArea, setDeviceArea] = useState(device?.areaPublicId ?? "");
  const [deviceVisible, setDeviceVisible] = useState(device?.visible ?? true);
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

  if (type === "alertes") return <div className="modal-backdrop" onMouseDown={close}><div className="modal" onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={close}>×</button><span className="modal-symbol">!</span><small>UNE ACTION RECOMMANDÉE</small><h3>Batterie bientôt épuisée</h3><p>Le détecteur de fenêtre du salon est à 14 %. Son fonctionnement peut devenir irrégulier.</p><div className="alert-detail"><b>Détecteur fenêtre</b><span>Salon · Batterie CR2032</span></div><button className="primary full" onClick={()=>{notify("Rappel programmé pour demain");close()}}>Me le rappeler demain</button></div></div>;
  if (type === "delete") return <div className="modal-backdrop" onMouseDown={close}><div className="modal" onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={close}>×</button><span className="modal-symbol danger">×</span><small>CONFIRMATION REQUISE</small><h3>Supprimer cette automatisation ?</h3><p>« {automation?.name ?? "Cette automatisation"} » ne s’exécutera plus. Cette action ne pourra pas être annulée.</p><div className="modal-actions"><button disabled={busy} onClick={close}>Annuler</button><button disabled={busy || !automation} className="danger-button" onClick={confirmDeletion}>{busy ? "Suppression…" : "Supprimer"}</button></div></div></div>;
  if (type === "appareil") return <div className="modal-backdrop" onMouseDown={close}><div className="modal wide" onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={close}>×</button><small>GÉRER L’APPAREIL</small><h3>{device?.name ?? "Appareil"}</h3><label className="field">Nom convivial<input value={deviceName} maxLength={80} onChange={event=>setDeviceName(event.target.value)} /></label><label className="field">Pièce<select value={deviceArea} onChange={event=>setDeviceArea(event.target.value)}><option value="">Maison · sans pièce</option>{areas.map((area)=><option key={area.publicId} value={area.publicId}>{area.name}</option>)}</select></label><label className="check-row"><input type="checkbox" checked={deviceVisible} onChange={event=>setDeviceVisible(event.target.checked)} /> Visible dans l’application Ma Maison</label><button disabled={busy || !device} className="primary full" onClick={submitDevice}>{busy ? "Enregistrement…" : "Enregistrer les modifications"}</button></div></div>;
  return <div className="modal-backdrop" onMouseDown={close}><div className="modal automation-modal" onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={close}>×</button><small>RÈGLE SIMPLE</small><h3>Créer une automatisation</h3>{["QUAND","SI","ALORS"].map((x,i)=><div className="rule-row" key={x}><b>{x}</b><button>{i===0?"Un horaire est atteint":i===1?"La maison est occupée (facultatif)":"Éteindre les lumières"}<span>⌄</span></button></div>)}<button className="primary full" onClick={()=>notify("Choisissez d’abord les éléments de la règle")}>Continuer</button></div></div>;
}
