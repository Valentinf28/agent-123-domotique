import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  allocateHomeAndVehiclePower,
  createEnergyFlowState,
  powerEntityWatts,
} from "../lib/energy-allocation.generated.js";

test("affiche le portail Ma Maison en français", async () => {
  const [layout, page, portal] = await Promise.all([
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(layout, /<html lang="fr">/i);
  assert.match(page, /Ma Maison/);
  assert.match(portal, /Bonjour Valentin/);
  assert.match(portal, /Maison connectée/);
  assert.doesNotMatch(`${layout}${page}${portal}`, /codex-preview|react-loading-skeleton/i);
});

test("mémorise la maison sélectionnée entre deux visites", async () => {
  const portal = await readFile(new URL("../app/portal.tsx", import.meta.url), "utf8");
  assert.match(portal, /SELECTED_DOSSIER_STORAGE_KEY/);
  assert.match(portal, /localStorage\.setItem/);
  assert.match(portal, /localStorage\.getItem/);
});

test("n’expose aucun secret Home Assistant dans le rendu client", async () => {
  const source = await readFile(new URL("../app/portal.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /HA_ACCESS_TOKEN|RELAY_CAMERA_SECRET|Bearer\s+[A-Za-z0-9._-]{20,}/i);
});

test("inclut le parcours de préparation réservé aux installateurs", async () => {
  const source = await readFile(new URL("../app/portal.tsx", import.meta.url), "utf8");
  assert.match(source, /Configurer une nouvelle maison/);
  assert.match(source, /Catalogue validé/);
  assert.match(source, /Recherche automatique sur place/);
  assert.match(source, /Recette de la maison/i);
  assert.match(source, /Signaler un blocage/);
});

test("propose les familles d’équipements du showroom sans associer les anciennes entités indisponibles", async () => {
  const [source, discovery, resolver] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/preparation/discovery/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../shared/provisioning-discovery.js", import.meta.url), "utf8"),
  ]);
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
  assert.match(source, /Rapport de découverte/);
  assert.match(discovery, /applyCertain/);
  assert.match(discovery, /confirmations/);
  assert.match(resolver, /entityIsShowroomOnly/);
  assert.match(resolver, /requiresConfirmation: true/);
  assert.match(resolver, /report\.missing\.push/);
});

test("sauvegarde la préparation dans une base rattachée au dossier", async () => {
  const [route, schema] = await Promise.all([
    readFile(new URL("../app/api/preparation/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../db/schema.ts", import.meta.url), "utf8"),
  ]);
  assert.match(route, /export async function PUT/);
  assert.match(route, /portalApiAdminAuthorized/);
  assert.match(schema, /installationDossiers/);
  assert.match(schema, /plannedDevices/);
  assert.match(schema, /agentBoxes/);
  assert.match(schema, /agentEnrollmentCodes/);
  assert.match(route, /index \+= 4/);
  assert.match(route, /await db\.batch/);
});

test("enregistre le tarif et les heures creuses séparément pour chaque maison", async () => {
  const [portal, route, schema, migration] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/preparation/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../db/schema.ts", import.meta.url), "utf8"),
    readFile(new URL("../drizzle/0010_tariff_schedule.sql", import.meta.url), "utf8"),
  ]);
  assert.match(portal, /Tarif et heures creuses du client/);
  assert.match(portal, /Heures pleines \/ creuses/);
  assert.match(route, /sanitizeOffPeakPeriods/);
  assert.match(schema, /offPeakPeriodsJson/);
  assert.match(migration, /off_peak_periods_json/);
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

test("désactive le cache du document client et conserve les attributs utiles de Home Assistant", async () => {
  const [worker, heartbeat, agent] = await Promise.all([
    readFile(new URL("../worker/index.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/agent/heartbeat/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../agent_123_domotique/agent.py", import.meta.url), "utf8"),
  ]);
  assert.match(worker, /Cache-Control", "no-store, max-age=0, must-revalidate/);
  assert.match(worker, /Cloudflare-CDN-Cache-Control/);
  assert.match(heartbeat, /attributes\?: Record<string, unknown>/);
  assert.match(agent, /SAFE_ATTRIBUTE_KEYS/);
  assert.match(agent, /"current_temperature"/);
  assert.match(agent, /"cloud_coverage"/);
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
  assert.match(config, /version: "0\.5\.\d+"/);
  assert.match(config, /heartbeat_seconds: "int\(5,300\)"/);
  assert.match(agentHome, /resolveEntityCandidate\(inventory\.map/);
});

test("partage le même profil de capteurs énergétiques avec l’application", async () => {
  const [canonical, generatedPortal, generatedMobile, agentHome, connector, mobileProfile] = await Promise.all([
    readFile(new URL("../shared/energy-profile.json", import.meta.url), "utf8"),
    readFile(new URL("../lib/energy-profile.generated.ts", import.meta.url), "utf8"),
    readFile(new URL("../../mobile/src/config/energyProfile.generated.js", import.meta.url), "utf8"),
    readFile(new URL("../lib/agent-home.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/home-connector.ts", import.meta.url), "utf8"),
    readFile(new URL("../../mobile/src/config/houseProfile.js", import.meta.url), "utf8"),
  ]);
  const profile = JSON.parse(canonical);
  assert.deepEqual(profile.homePower.slice(0, 3), [
    "sensor.shellyem3_483fdac38616_channel_b_power",
    "sensor.onduleur_load_power",
    "sensor.inverter_load_power",
  ]);
  assert.match(generatedPortal, /sensor\.onduleur_pv_power/);
  assert.match(generatedMobile, /sensor\.onduleur_pv_power/);
  assert.match(agentHome, /ENERGY_PROFILE\.dailyExport/);
  assert.match(agentHome, /monthlyProduction/);
  assert.match(connector, /ENERGY_PROFILE\.homePower/);
  assert.match(mobileProfile, /\.\.\.ENERGY_PROFILE/);
});

test("partage les onglets et les règles visuelles avec l’application", async () => {
  const [canonical, generatedPortal, generatedMobile, portal, mobile] = await Promise.all([
    readFile(new URL("../shared/client-experience.json", import.meta.url), "utf8"),
    readFile(new URL("../lib/client-experience.generated.ts", import.meta.url), "utf8"),
    readFile(new URL("../../mobile/src/config/clientExperience.generated.js", import.meta.url), "utf8"),
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../../mobile/App.js", import.meta.url), "utf8"),
  ]);
  const experience = JSON.parse(canonical);
  assert.deepEqual(experience.tabs.map((tab) => tab.label), [
    "Maison", "Solaire", "Coach", "Chauffage", "Équipements", "Piscine", "Véhicule",
  ]);
  assert.match(generatedPortal, /CLIENT_EXPERIENCE/);
  assert.match(generatedMobile, /CLIENT_EXPERIENCE/);
  assert.match(portal, /CLIENT_EXPERIENCE\.tabs/);
  assert.match(mobile, /CLIENT_EXPERIENCE\.tabs/);
  assert.match(portal, /flowActivationWatts/);
});

test("partage les correspondances Home Assistant avec l’application", async () => {
  const [canonical, generatedPortal, generatedMobile, agentHome, connector, mobileProfile] = await Promise.all([
    readFile(new URL("../shared/house-bindings.json", import.meta.url), "utf8"),
    readFile(new URL("../lib/house-bindings.generated.ts", import.meta.url), "utf8"),
    readFile(new URL("../../mobile/src/config/houseBindings.generated.js", import.meta.url), "utf8"),
    readFile(new URL("../lib/agent-home.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/home-connector.ts", import.meta.url), "utf8"),
    readFile(new URL("../../mobile/src/config/houseProfile.js", import.meta.url), "utf8"),
  ]);
  const bindings = JSON.parse(canonical);
  assert.equal(bindings.waterHeater[0], "switch.ce_wifi_commutateur_sur_rail_din_avec_mesure_2_switch");
  assert.equal(bindings.lektricoPower[0], "sensor.1p7k_501290_puissance");
  assert.equal(bindings.teslaModelXBattery[0], "sensor.tesla_model_x_battery");
  assert.match(generatedPortal, /HOUSE_BINDINGS/);
  assert.match(generatedMobile, /HOUSE_BINDINGS/);
  assert.match(agentHome, /HOUSE_BINDINGS\.waterHeater/);
  assert.match(connector, /HOUSE_BINDINGS\.poolHeatPump/);
  assert.match(mobileProfile, /\.\.\.HOUSE_BINDINGS/);
});

test("partage le calcul maison et borne avec l’application", async () => {
  const [canonical, generatedPortal, generatedMobile, agentHome, portal] = await Promise.all([
    readFile(new URL("../shared/energy-allocation.js", import.meta.url), "utf8"),
    readFile(new URL("../lib/energy-allocation.generated.js", import.meta.url), "utf8"),
    readFile(new URL("../../mobile/src/services/energyAllocation.js", import.meta.url), "utf8"),
    readFile(new URL("../lib/agent-home.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(canonical, /measuredHome - \(chargerAvailable \? measuredCharger : 0\)/);
  assert.equal(generatedPortal.replace(/^.*\n/, ""), canonical);
  assert.equal(generatedMobile.replace(/^.*\n/, ""), canonical);
  assert.match(agentHome, /allocateHomeAndVehiclePower/);
  assert.match(agentHome, /flow:\s*\{/);
  assert.match(agentHome, /gridWatts: inventoryPowerWatts\(energyItems\.grid\)/);
  assert.match(agentHome, /batteryWatts: inventoryPowerWatts\(energyItems\.batteryPower\)/);
  assert.match(portal, /overview\?\.flow\?\.gridWatts/);
  assert.match(portal, /createEnergyFlowState/);
  assert.match(agentHome, /chargerWatts: inventoryPowerWatts\(lektricoPower, "kW"\)/);
  assert.match(agentHome, /vehiclePower: formatWatts/);
  assert.match(portal, /energy\.vehiclePower/);
});

test("convertit la borne en watts et la retire entièrement de la maison", () => {
  const chargerWatts = powerEntityWatts({
    state: "2.38269",
    attributes: { unit_of_measurement: "kW" },
  });
  assert.equal(chargerWatts, 2382.69);
  assert.deepEqual(allocateHomeAndVehiclePower({
    totalHomeWatts: 3382.69,
    chargerWatts,
    chargerAvailable: true,
  }), {
    homeWatts: 1000,
    vehicleWatts: 2382.69,
  });

  assert.deepEqual(createEnergyFlowState({ gridWatts: -2100 }).grid, {
    active: true,
    reverse: false,
    direction: "export",
    arrow: "←",
  });
  assert.deepEqual(createEnergyFlowState({ batteryWatts: -900 }).battery, {
    active: true,
    reverse: false,
    direction: "charging",
    arrow: "↓",
  });
});

test("partage la géométrie complète de la scène Maison avec l’application", async () => {
  const [canonical, generatedPortal, generatedMobile, portal] = await Promise.all([
    readFile(new URL("../shared/energy-scene.js", import.meta.url), "utf8"),
    readFile(new URL("../lib/energy-scene.generated.js", import.meta.url), "utf8"),
    readFile(new URL("../../mobile/src/services/energySceneGeometry.js", import.meta.url), "utf8"),
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
  ]);
  assert.equal(generatedPortal.replace(/^.*\n/, ""), canonical);
  assert.equal(generatedMobile.replace(/^.*\n/, ""), canonical);
  assert.match(canonical, /createEnergySceneLayout/);
  assert.match(canonical, /vehicleCable/);
  assert.match(portal, /sceneLayout\.paths\.vehicle/);
  assert.match(portal, /sceneLayout\.inverterHub/);
});

test("permet à chaque maison d’autoriser ou d’interdire l’injection réseau", async () => {
  const [portal, route, schema, migration] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/preparation/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../db/schema.ts", import.meta.url), "utf8"),
      readFile(new URL("../drizzle/0015_grid_export_policy.sql", import.meta.url), "utf8"),
  ]);
  assert.match(portal, /Le client autorise-t-il l’injection réseau/);
  assert.match(portal, /Autorisée/);
  assert.match(portal, /Interdite/);
  assert.match(route, /allowGridExport/);
  assert.match(schema, /allowGridExport/);
  assert.match(migration, /allow_grid_export/);
});

test("crée et administre les automatisations via la box 1.2.3 Home", async () => {
  const [portal, collectionRoute, itemRoute, agentHome, agent] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/automations/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/automations/[publicId]/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../lib/agent-home.ts", import.meta.url), "utf8"),
    readFile(new URL("../agent_123_domotique/agent.py", import.meta.url), "utf8"),
  ]);
  assert.match(portal, /Confirmer et activer/);
  assert.match(portal, /dossierPublicId/);
  assert.match(collectionRoute, /queueAgentAutomationCreate/);
  assert.match(itemRoute, /queueAgentAutomationState/);
  assert.match(itemRoute, /queueAgentAutomationDelete/);
  assert.match(agentHome, /ha\.automation\.create/);
  assert.match(agentHome, /ha\.automation\.delete/);
  assert.match(agent, /allowed_services/);
  assert.match(agent, /config\/automation\/config/);
  assert.match(agent, /services\/automation\/reload/);
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

test("raccorde la Nuki réelle du showroom et confirme tout déverrouillage", async () => {
  const [agentHome, portal] = await Promise.all([
    readFile(new URL("../lib/agent-home.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(agentHome, /\["lock\.accueil", "lock\.nuki", "input_boolean\.demo_nuki_locked"\]/);
  assert.match(portal, /Déverrouiller la serrure Nuki/);
  assert.match(portal, /VERROUILLÉE/);
  assert.match(portal, /DÉVERROUILLÉE/);
});

test("affecte les deux Ring au showroom et relaie un vrai direct WebRTC", async () => {
  const [portal, agentHome, cameraRoute, relay, relayHouse] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../lib/agent-home.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/home/cameras/[id]/webrtc/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../../domotique-relay/app.py", import.meta.url), "utf8"),
    readFile(new URL("../lib/relay-house.ts", import.meta.url), "utf8"),
  ]);
  assert.match(agentHome, /camera\.batiment_live_view/);
  assert.match(agentHome, /camera\.preparation_1_live_view/);
  assert.match(agentHome, /Sonnette bâtiment/);
  assert.match(agentHome, /Caméra Préparation 1/);
  assert.match(agentHome, /security: ringSecurity/);
  assert.match(agentHome, /relayHouseIdForDossier/);
  assert.match(agentHome, /RING_CAMERA_ASSIGNMENTS_JSON/);
  assert.match(agentHome, /selectRingSourceForDossier/);
  assert.match(relayHouse, /RELAY_HOUSE_MAP_JSON/);
  assert.match(portal, /security-device-grid/);
  assert.match(portal, /Détection de mouvement active/);
  assert.match(portal, /Dernière activité/);
  assert.match(portal, /Ouvrir le direct/);
  assert.match(portal, /Direct vidéo sécurisé/);
  assert.match(portal, /RTCPeerConnection/);
  assert.match(portal, /addTransceiver\("video"/);
  assert.match(cameraRoute, /resolveRingCameraForDossier/);
  assert.match(cameraRoute, /RELAY_CAMERA_SECRET/);
  assert.match(cameraRoute, /X-Relay-Authorization/);
  assert.match(relay, /internal_camera_webrtc_offer/);
  assert.match(relay, /internal_camera_webrtc_events/);
  assert.match(relay, /camera\/webrtc\/offer/);
  assert.match(relay, /camera_webrtc_sessions/);
  assert.match(relay, /valid_camera_entity_id/);
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
  assert.doesNotMatch(mobileProvision, /homeAssistantUrl/i);
  const publicResponse = mobileProvision.slice(mobileProvision.lastIndexOf("return Response.json"));
  assert.doesNotMatch(publicResponse, /entityId\s*:/i);
  assert.match(mobileProvision, /portalUrl/);
  assert.match(mobileProvision, /solarInstalledPowerWp: normalizeSolarInstalledPowerWp\(dossier\.solarPeakWatts\)/);
});

test("provisionne l’application avec un accès relayé propre à chaque maison", async () => {
  const [mobileProvision, mobileConfiguration] = await Promise.all([
    readFile(new URL("../app/api/mobile/provision/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/mobile/configuration/route.ts", import.meta.url), "utf8"),
  ]);
  assert.match(mobileProvision, /internal\/client-credential/);
  assert.match(mobileProvision, /configurationToken/);
  assert.match(mobileConfiguration, /configurationTokenHash/);
  assert.match(mobileConfiguration, /normalizeEnabledModules/);
  assert.match(mobileConfiguration, /offPeakPeriods/);
});

test("applique au portail les mêmes onglets configurés que sur le mobile", async () => {
  const [portal, agentHome, mobileProvision] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../lib/agent-home.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/mobile/provision/route.ts", import.meta.url), "utf8"),
  ]);
  assert.match(agentHome, /enabledModules: normalizeEnabledModules\(selected\.dossier\.enabledModules\)/);
  assert.match(mobileProvision, /const modules = normalizeEnabledModules\(dossier\.enabledModules\)/);
  assert.match(portal, /moduleKey === "home" \|\| moduleKey === "coach" \|\| enabledModules\.includes\(moduleKey as AppModule\)/);
  assert.match(portal, /setView\("Automatisations"\)/);
  assert.match(portal, /Coach & règles/);
  assert.match(portal, /visibleHomeTabs\.map/);
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
  assert.match(portal, /Coach énergie et maison intelligente/i);
  assert.match(portal, /coach-quick-start/);
  assert.match(portal, /Démarrer avec le Coach énergie/);
  assert.match(portal, /Réduisez votre facture, protégez la batterie/i);
  assert.match(portal, /PLAN D’ACTION PERSONNALISÉ/i);
  assert.match(portal, /mesure réelle.*estimation/i);
  assert.match(portal, /Bilan énergétique récent/);
  assert.match(portal, /coachWeek\.observedDays/);
  assert.match(portal, /Votre maison en un coup d’œil/);
  assert.match(portal, /Couverture solaire/);
  assert.match(portal, /INCLUS DANS VOTRE FORFAIT/i);
  assert.match(portal, /9,90 € \/ mois/i);
  assert.match(portal, /99 € \/ an/i);
  assert.match(subscription, /MONTHLY_PRICE_CENTS = 990/);
  assert.match(subscription, /YEARLY_PRICE_CENTS = 9900/);
  assert.match(route, /OPENAI_API_KEY/);
  assert.match(route, /safety_identifier/);
  assert.match(route, /Toute automatisation reste un brouillon/);
  assert.match(route, /Sur les sept derniers jours disponibles/);
  assert.match(route, /context\.week\.observedDays/);
  assert.match(route, /C’est une projection, pas une facture/);
  assert.match(route, /Le reste de la maison est regroupé séparément pour éviter tout double comptage/);
  assert.match(route, /La voiture ne charge pas actuellement/);
  assert.doesNotMatch(route, /agentCommands|ha\.services\.call/);
  assert.match(coach, /consumeAssistantRequest/);
  assert.match(heartbeat, /fiveMinuteBucket/);
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

test("affiche le même historique énergétique interactif que l’application", async () => {
  const [portal, styles, heartbeat] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/api/agent/heartbeat/route.ts", import.meta.url), "utf8"),
  ]);
  assert.match(portal, /Mesures toutes les 5 min/);
  assert.match(portal, /portal-energy-readout/);
  assert.match(portal, /setPointerCapture/);
  assert.match(portal, /cursor-line/);
  assert.match(portal, /soc-line/);
  assert.match(portal, /solar-area/);
  assert.match(portal, /signedPower/);
  assert.match(styles, /touch-action:none/);
  assert.match(styles, /stroke-dasharray:6 5/);
  assert.match(heartbeat, /fiveMinuteBucket/);
});

test("conserve la parité des états véhicule et du résumé Maison", async () => {
  const portal = await readFile(new URL("../app/portal.tsx", import.meta.url), "utf8");
  assert.match(portal, /const onlineState = overview\?\.comfort\?\.teslaOnline/);
  assert.match(portal, /online \? "En ligne" : "Hors ligne"/);
  assert.match(portal, /const vehicleBattery = overview\?\.comfort\?\.teslaBattery/);
  assert.match(portal, /sub=\{vehicleWatts > CLIENT_EXPERIENCE\.energyScene\.flowActivationWatts/);
  assert.ok(portal.indexOf("Bilan énergétique") < portal.indexOf("Détail des panneaux"));
});
