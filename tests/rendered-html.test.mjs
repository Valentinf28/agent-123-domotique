import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("affiche le portail Ma Maison en français", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<html lang="fr">/i);
  assert.match(html, /Ma Maison/);
  assert.match(html, /Bonjour Valentin/);
  assert.match(html, /Votre maison est calme/);
  assert.doesNotMatch(html, /Home Assistant|codex-preview|react-loading-skeleton/i);
});

test("n’expose aucun secret ni identifiant technique dans le rendu", async () => {
  const response = await render();
  const html = await response.text();
  assert.doesNotMatch(html, /token|access_token|entity_id|sensor\./i);
});
