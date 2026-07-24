"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type View = "Accueil" | "Appareils" | "Automatisations" | "Ajouter" | "Journal";
type Device = {
  id: number; name: string; room: string; category: string; state: string;
  detail: string; battery?: number; online: boolean; visible: boolean; icon: string;
};
type MobileOverview = {
  energy: Record<string, string>;
  controls: { label: string; active: boolean; available: boolean }[];
};

const demoDevices: Device[] = [
  { id: 1, name: "Suspension du salon", room: "Salon", category: "Éclairage", state: "Allumée", detail: "48 %", online: true, visible: true, icon: "◉" },
  { id: 2, name: "Thermostat principal", room: "Salon", category: "Climat", state: "Confort", detail: "21,5 °C", battery: 82, online: true, visible: true, icon: "♨" },
  { id: 3, name: "Détecteur fenêtre", room: "Salon", category: "Sécurité", state: "Fermée", detail: "Aucune anomalie", battery: 14, online: true, visible: true, icon: "▣" },
  { id: 4, name: "Lampe chevet gauche", room: "Chambre", category: "Éclairage", state: "Éteinte", detail: "Prête", online: true, visible: true, icon: "◉" },
  { id: 5, name: "Prise lave-linge", room: "Buanderie", category: "Énergie", state: "En veille", detail: "0,3 W", online: true, visible: false, icon: "ϟ" },
  { id: 6, name: "Capteur de jardin", room: "Extérieur", category: "Capteurs", state: "Indisponible", detail: "Vu il y a 2 h", battery: 36, online: false, visible: false, icon: "⌁" },
];

const automations = [
  { name: "Départ de la maison", trigger: "Quand le dernier occupant part", action: "Éteindre 8 appareils", active: true, icon: "↗" },
  { name: "Soirée douce", trigger: "Quand il est 20 h 30", action: "Salon à 35 % · 20 °C", active: true, icon: "☾" },
  { name: "Alerte fenêtre", trigger: "Quand une fenêtre reste ouverte", action: "Notifier après 10 minutes", active: true, icon: "!" },
  { name: "Arrosage intelligent", trigger: "Quand l’humidité est basse", action: "Arroser pendant 12 minutes", active: false, icon: "⌁" },
];

const nav: { label: View; icon: string }[] = [
  { label: "Accueil", icon: "⌂" }, { label: "Appareils", icon: "◫" },
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
  const [liveStatus, setLiveStatus] = useState<"loading" | "connected" | "demo">("loading");
  const [mobileOverview, setMobileOverview] = useState<MobileOverview | null>(null);

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
          state: string; available: boolean; battery: number | null;
        }, index: number) => ({
          id: index + 1000,
          name: device.name,
          room: device.room,
          category: device.category,
          state: friendlyState(device.state),
          detail: device.available ? "Synchronisé à l’instant" : "À vérifier",
          battery: device.battery ?? undefined,
          online: device.available,
          visible: true,
          icon: categoryIcons[device.category] ?? "◇",
        }));
        setDevices(mapped);
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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setView("Accueil")} aria-label="Retour à l’accueil">
          <span className="brand-mark">M</span><span>Ma Maison</span>
        </button>
        <nav aria-label="Navigation principale">
          {nav.map((item) => <button key={item.label} className={view === item.label ? "active" : ""} onClick={() => setView(item.label)}>
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
        {view === "Appareils" && <Devices filtered={filtered} search={search} setSearch={setSearch} room={room} setRoom={setRoom} notify={notify} setModal={setModal} />}
        {view === "Automatisations" && <Automations setModal={setModal} notify={notify} />}
        {view === "Ajouter" && <AddDevice step={guideStep} setStep={setGuideStep} notify={notify} />}
        {view === "Journal" && <Journal role={role} />}
      </main>

      <nav className="mobile-nav" aria-label="Navigation mobile">
        {nav.slice(0, 4).map((item) => <button key={item.label} className={view === item.label ? "active" : ""} onClick={() => setView(item.label)}>
          <span>{item.icon}</span><small>{item.label}</small>
        </button>)}
      </nav>

      {toast && <div className="toast">✓ {toast}</div>}
      {modal && <Modal type={modal} close={() => setModal(null)} notify={notify} />}
    </div>
  );
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

function Devices({ filtered, search, setSearch, room, setRoom, notify, setModal }: {
  filtered: Device[]; search: string; setSearch: (value: string) => void;
  room: string; setRoom: (value: string) => void;
  notify: (value: string) => void; setModal: (value: string) => void;
}) {
  return <div className="content">
    <div className="section-intro"><div><span className="eyebrow">24 appareils · 7 pièces</span><h2>Les objets de votre maison</h2><p>Renommez-les, organisez-les et choisissez ce qui apparaît dans l’application.</p></div></div>
    <div className="filters"><label><span>⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Rechercher un appareil…" /></label>
      <div className="chips">{["Toutes","Salon","Cuisine","Chambre","Extérieur"].map(x=><button key={x} className={room===x?"selected":""} onClick={()=>setRoom(x)}>{x}</button>)}</div>
      <button className="filter-button">Filtres <span>⌄</span></button>
    </div>
    <div className="device-grid">{filtered.map((d: Device)=><article className={`device-card ${!d.online?"offline":""}`} key={d.id}>
      <div className="device-head"><span className="device-icon">{d.icon}</span><span className={`status ${d.online?"online":"offline-dot"}`}>{d.online?"Disponible":"Hors ligne"}</span><button aria-label={`Options pour ${d.name}`} onClick={()=>setModal("appareil")}>•••</button></div>
      <small>{d.room} · {d.category}</small><h3>{d.name}</h3><strong>{d.state}</strong><p>{d.detail}</p>
      {d.battery !== undefined && <div className={`battery ${d.battery<20?"low":""}`}><span><i style={{width:`${d.battery}%`}} /></span>{d.battery} %</div>}
      <div className="device-foot"><label><input type="checkbox" defaultChecked={d.visible} onChange={()=>notify("Visibilité dans l’application mise à jour")} /><span /> Dans l’application</label><button onClick={()=>setModal("appareil")}>Gérer</button></div>
    </article>)}</div>
    {!filtered.length && <div className="empty"><strong>Aucun appareil trouvé</strong><p>Essayez une autre pièce ou un autre terme.</p></div>}
  </div>;
}

function Automations({ setModal, notify }: {
  setModal: (value: string) => void; notify: (value: string) => void;
}) {
  return <div className="content">
    <div className="section-intro split"><div><span className="eyebrow">Simple et puissant</span><h2>Les habitudes qui travaillent pour vous</h2><p>Créez des règles faciles à comprendre, sans réglage technique.</p></div><button className="primary" onClick={()=>setModal("automation")}>＋ Créer une automatisation</button></div>
    <div className="automation-layout"><section><h3>Vos automatisations <span>4</span></h3><div className="automation-list">{automations.map((a,i)=><article key={a.name}>
      <span className="automation-icon">{a.icon}</span><div><h4>{a.name}</h4><p><b>QUAND</b> {a.trigger}</p><p><b>ALORS</b> {a.action}</p></div>
      <label className="switch"><input type="checkbox" defaultChecked={a.active} onChange={()=>notify(`${a.name} mise à jour`)} /><span /></label>
      <button onClick={()=>setModal(i===3?"delete":"automation")}>•••</button>
    </article>)}</div></section>
    <aside className="templates"><small>POUR COMMENCER</small><h3>Modèles populaires</h3>
      {[["☾","Bonne nuit","Éteint les lumières et baisse le chauffage"],["↗","Je quitte la maison","Sécurise et économise en un geste"],["☼","Réveil en douceur","Ouvre les volets progressivement"]].map(x=><button key={x[1]} onClick={()=>setModal("automation")}><span>{x[0]}</span><div><b>{x[1]}</b><small>{x[2]}</small></div><em>＋</em></button>)}
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

function Modal({ type, close, notify }: { type: string; close: () => void; notify: (v: string) => void }) {
  if(type==="alertes") return <div className="modal-backdrop" onMouseDown={close}><div className="modal" onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={close}>×</button><span className="modal-symbol">!</span><small>UNE ACTION RECOMMANDÉE</small><h3>Batterie bientôt épuisée</h3><p>Le détecteur de fenêtre du salon est à 14 %. Son fonctionnement peut devenir irrégulier.</p><div className="alert-detail"><b>Détecteur fenêtre</b><span>Salon · Batterie CR2032</span></div><button className="primary full" onClick={()=>{notify("Rappel programmé pour demain");close()}}>Me le rappeler demain</button></div></div>;
  if(type==="delete") return <div className="modal-backdrop"><div className="modal"><button className="modal-close" onClick={close}>×</button><span className="modal-symbol danger">×</span><small>CONFIRMATION REQUISE</small><h3>Supprimer cette automatisation ?</h3><p>« Arrosage intelligent » ne s’exécutera plus. Cette action ne pourra pas être annulée.</p><div className="modal-actions"><button onClick={close}>Annuler</button><button className="danger-button" onClick={()=>{notify("Automatisation supprimée");close()}}>Supprimer</button></div></div></div>;
  if(type==="appareil") return <div className="modal-backdrop"><div className="modal wide"><button className="modal-close" onClick={close}>×</button><small>GÉRER L’APPAREIL</small><h3>Suspension du salon</h3><label className="field">Nom convivial<input defaultValue="Suspension du salon" /></label><label className="field">Pièce<select defaultValue="Salon"><option>Salon</option><option>Cuisine</option><option>Chambre</option><option>Entrée</option></select></label><label className="check-row"><input type="checkbox" defaultChecked /> Visible dans l’application Ma Maison</label><button className="primary full" onClick={()=>{notify("Modifications enregistrées");close()}}>Enregistrer les modifications</button></div></div>;
  return <div className="modal-backdrop"><div className="modal automation-modal"><button className="modal-close" onClick={close}>×</button><small>RÈGLE SIMPLE</small><h3>Créer une automatisation</h3>{["QUAND","SI","ALORS"].map((x,i)=><div className="rule-row" key={x}><b>{x}</b><button>{i===0?"Un horaire est atteint":i===1?"La maison est occupée (facultatif)":"Éteindre les lumières"}<span>⌄</span></button></div>)}<button className="primary full" onClick={()=>{notify("Automatisation enregistrée");close()}}>Enregistrer et activer</button></div></div>;
}
