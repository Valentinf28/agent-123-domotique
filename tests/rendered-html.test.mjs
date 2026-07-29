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
  const [portal, heartbeat, agent, config] = await Promise.all([
    readFile(new URL("../app/portal.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/agent/heartbeat/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../agent_123_domotique/agent.py", import.meta.url), "utf8"),
    readFile(new URL("../agent_123_domotique/config.yaml", import.meta.url), "utf8"),
  ]);
  assert.match(portal, /HOME_REFRESH_MS = 5_000/);
  assert.match(heartbeat, /nextHeartbeatSeconds: 5/);
  assert.match(heartbeat, /inventoryMode === "delta"/);
  assert.match(agent, /FULL_INVENTORY_SECONDS = 60/);
  assert.match(agent, /FAST_ENTITY_PREFIXES/);
  assert.match(config, /version: "0\.5\.8"/);
  assert.match(config, /heartbeat_seconds: "int\(5,300\)"/);
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
