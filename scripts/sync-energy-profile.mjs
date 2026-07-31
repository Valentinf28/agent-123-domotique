import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const canonicalPath = resolve(root, "shared/energy-profile.json");
const portalPath = resolve(root, "lib/energy-profile.generated.ts");
const mobilePath = resolve(root, "../mobile/src/config/energyProfile.generated.js");
const canonical = JSON.parse(await readFile(canonicalPath, "utf8"));
const payload = JSON.stringify(canonical, null, 2);
const banner = "// Généré depuis ma-maison-portail-site/shared/energy-profile.json. Ne pas modifier à la main.\n";
const outputs = [
  [portalPath, `${banner}export const ENERGY_PROFILE = ${payload} as const;\n`],
  [mobilePath, `${banner}export const ENERGY_PROFILE = ${payload};\n`],
];

if (process.argv.includes("--check")) {
  for (const [path, expected] of outputs) {
    assert.equal(await readFile(path, "utf8"), expected, `${path} n'est pas synchronisé`);
  }
  console.log("Profil énergétique synchronisé.");
} else {
  for (const [path, content] of outputs) await writeFile(path, content, "utf8");
  console.log("Profil énergétique généré pour le portail et l'application.");
}
