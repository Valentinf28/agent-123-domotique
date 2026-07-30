import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("affiche le portail Ma Maison en français", async () => {
  const [layout, page, portal] = await Promise.all([
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(layout, /<html lang="fr">/i);
  assert.match(page, /Ma Maison/);
  assert.match(portal, /Bonjour Valentin/);
  assert.match(portal, /Votre maison est calme/);
  assert.doesNotMatch(`${layout}${page}${portal}`, /codex-preview|react-loading-skeleton/i);
});

test("n’expose aucun secret ni identifiant technique dans le rendu", async () => {
  const source = await readFile(new URL("../app/portal.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /access_token|entity_id|sensor\./i);
});

test("inclut le parcours de préparation réservé aux installateurs", async () => {
  const source = await readFile(new URL("../app/portal.tsx", import.meta.url), "utf8");
  assert.match(source, /Préparer les objets à connecter/);
  assert.match(source, /Catalogue validé/);
  assert.match(source, /Recherche automatique sur place/);
  assert.match(source, /Recette de la maison/i);
  assert.match(source, /Signaler un blocage/);
});

test("propose les familles d’équipements du showroom sans associer les anciennes entités indisponibles", async () => {
  const source = await readFile(new URL("../app/portal.tsx", import.meta.url), "utf8");
  assert.match(source, /SUN-15K-SG01HP3-EU-AM2/);
  assert.match(source, /Shelly.*Pro 1PM/s);
  assert.match(source, /Philips Hue.*Bridge/s);
  assert.match(source, /Nuki.*Smart Lock/s);
  assert.match(source, /ONVIF.*Caméra IP/s);
  assert.match(source, /Ring.*Caméras/s);
  assert.match(source, /Tesla.*Véhicule/s);
  assert.match(source, /\["Salon","Cuisine","Chambre","Entrée","Extérieur","Garage","Local technique"\]/);
  assert.match(source, /associableInventory/);
  assert.match(source, /!\["unknown", "unavailable"\]\.includes/);
  assert.match(source, /domains\.includes\(entity\.domain\) && terms\.some/);
  assert.match(source, /item\.status === "Détecté"/);
  assert.match(source, /status: "À préparer" as InstallationStatus/);
});

test("sauvegarde la préparation dans une base rattachée au dossier", async () => {
  const [route, schema] = await Promise.all([
    readFile(new URL("../app/api/preparation/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../db/schema.ts", import.meta.url), "utf8"),
  ]);
  assert.match(route, /export async function PUT/);
  assert.match(route, /portalApiAuthorized/);
  assert.match(schema, /installationDossiers/);
  assert.match(schema, /plannedDevices/);
  assert.match(schema, /agentBoxes/);
  assert.match(schema, /agentEnrollmentCodes/);
  assert.match(route, /index \+= 4/);
  assert.match(route, /await db\.batch/);
});

test("protège l’enrôlement et les remontées de la box", async () => {
  const [enroll, heartbeat, gateway] = await Promise.all([
    readFile(new URL("../app/api/agent/enroll/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/agent/heartbeat/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../gateway/worker.ts", import.meta.url), "utf8"),
  ]);
  assert.match(enroll, /Code expiré ou déjà utilisé/);
  assert.match(heartbeat, /authenticatedAgent/);
  assert.match(gateway, /X-Agent-Authorization/);
});

test("rafraîchit les mesures importantes toutes les cinq secondes sans renvoyer tout l’inventaire", async () => {
  const [portal, heartbeat, agent, config, agentHome] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/agent/heartbeat/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../agent_123_domotique/agent.py", import.meta.url), "utf8"),
    readFile(new URL("../agent_123_domotique/config.yaml", import.meta.url), "utf8"),
    readFile(new URL("../lib/agent-home.ts", import.meta.url), "utf8"),
  ]);
  assert.match(portal, /HOME_REFRESH_MS = 5_000/);
  assert.match(heartbeat, /nextHeartbeatSeconds: 5/);
  assert.match(heartbeat, /inventoryMode === "delta"/);
  assert.match(agent, /FULL_INVENTORY_SECONDS = 60/);
  assert.match(agent, /FAST_ENTITY_PREFIXES/);
  assert.match(agent, /interval - cycle_duration/);
  assert.match(config, /version: "0\.5\.14"/);
  assert.match(config, /heartbeat_seconds: "int\(5,300\)"/);
  assert.match(agentHome, /matches\.find\(\(item\) => !\["unknown", "unavailable"\]\.includes\(item\.state\)\)/);
});

test("sépare strictement les appareils client des entités du showroom", async () => {
  const source = await readFile(
    new URL("../lib/agent-home.ts", import.meta.url),
    "utf8",
  );
  assert.match(source, /showroomOnlyEntityIds/);
  assert.match(source, /allowShowroomEntities/);
  assert.match(source, /reference\.toUpperCase\(\)\.includes\("SHOWROOM"\)/);
  assert.match(source, /!showroomOnlyEntityIds\.has\(entityId\)/);
});

test("garde Home Assistant hors du parcours client", async () => {
  const [clientPage, portal, heartbeat, schema, worker, mobileProvision] = await Promise.all([
    readFile(new URL("../app/ma-maison/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/agent/heartbeat/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../db/schema.ts", import.meta.url), "utf8"),
    readFile(new URL("../worker/index.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/mobile/provision/route.ts", import.meta.url), "utf8"),
  ]);
  assert.match(clientPage, /Portal customerOnly/);
  assert.doesNotMatch(clientPage, /Lovelace|iframe|Home Assistant/i);
  assert.doesNotMatch(portal, /iframe|lovelace/i);
  assert.match(heartbeat, /commands/);
  assert.match(schema, /agentCommands/);
  assert.doesNotMatch(worker, /Lovelace|HA_ACCESS_TOKEN|HA_BASE_URL|ma-maison\/ha/i);
  assert.doesNotMatch(mobileProvision, /homeAssistantUrl|entityId:/i);
  assert.match(mobileProvision, /portalUrl/);
});

test("gère l’essai de 30 jours sans couper la domotique locale", async () => {
  const [schema, subscription, entitlement, portal, relay] = await Promise.all([
    readFile(new URL("../db/schema.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/subscription.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/relay/entitlement/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../../domotique-relay/app.py", import.meta.url), "utf8"),
  ]);
  assert.match(schema, /subscriptionStatus/);
  assert.match(subscription, /TRIAL_DAYS = 30/);
  assert.match(subscription, /GRACE_DAYS = 7/);
  assert.match(subscription, /remoteAccessAllowed/);
  assert.match(entitlement, /X-Relay-Authorization/);
  assert.match(portal, /accès 4G\/5G offerts/i);
  assert.match(portal, /automatismes locaux restent disponibles/i);
  assert.match(relay, /role == "client"/);
  assert.doesNotMatch(relay, /role == "agent".*entitlement/s);
});

test("inclut les assistants et le nouveau tarif dans le forfait client", async () => {
  const [portal, subscription, route, coach, heartbeat, schema, migration] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../lib/subscription.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/assistant/energy/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/energy-coach.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/agent/heartbeat/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../db/schema.ts", import.meta.url), "utf8"),
    readFile(new URL("../drizzle/0008_energy_coach.sql", import.meta.url), "utf8"),
  ]);
  assert.match(portal, /Assistant domotique/i);
  assert.match(portal, /Coach énergie/i);
  assert.match(portal, /INCLUS DANS VOTRE FORFAIT/i);
  assert.match(portal, /9,90 € \/ mois/i);
  assert.match(portal, /99 € \/ an/i);
  assert.match(subscription, /MONTHLY_PRICE_CENTS = 990/);
  assert.match(subscription, /YEARLY_PRICE_CENTS = 9900/);
  assert.match(route, /OPENAI_API_KEY/);
  assert.match(route, /safety_identifier/);
  assert.match(route, /Toute automatisation reste un brouillon/);
  assert.doesNotMatch(route, /agentCommands|ha\.services\.call/);
  assert.match(coach, /consumeAssistantRequest/);
  assert.match(heartbeat, /fifteenMinuteBucket/);
  assert.match(schema, /energySnapshots/);
  assert.match(schema, /assistantUsage/);
  assert.match(migration, /UPDATE `installation_dossiers`/);
});

test("prévoit la production solaire et protège la batterie avant de piloter les appareils flexibles", async () => {
  const [agent, planner, coach, portal, schema, migration] = await Promise.all([
    readFile(new URL("../agent_123_domotique/agent.py", import.meta.url), "utf8"),
    readFile(new URL("../lib/predictive-energy.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/energy-coach.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../db/schema.ts", import.meta.url), "utf8"),
    readFile(new URL("../drizzle/0009_predictive_energy.sql", import.meta.url), "utf8"),
  ]);
  assert.match(agent, /energy\/solar_forecast/);
  assert.match(agent, /SOLAR_FORECAST_REFRESH_SECONDS = 15 \* 60/);
  assert.match(planner, /batteryReservePercent/);
  assert.match(planner, /Démarrage anticipé conseillé/);
  assert.match(coach, /buildPredictiveEnergyPlan/);
  assert.match(portal, /Caractéristiques énergétiques/);
  assert.match(portal, /APPAREILS FLEXIBLES/);
  assert.match(portal, /Chauffe-eau/);
  assert.match(portal, /Recharge véhicule/);
  assert.match(schema, /batteryCapacityWh/);
  assert.match(schema, /flexibleLoadsJson/);
  assert.match(migration, /predictive_control_enabled/);
});
