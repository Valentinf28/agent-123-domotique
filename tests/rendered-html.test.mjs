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
});
