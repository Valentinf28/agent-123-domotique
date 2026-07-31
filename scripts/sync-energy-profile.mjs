import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sources = [
  {
    canonicalPath: resolve(root, "shared/energy-profile.json"),
    portalPath: resolve(root, "lib/energy-profile.generated.ts"),
    mobilePath: resolve(root, "../mobile/src/config/energyProfile.generated.js"),
    exportName: "ENERGY_PROFILE",
  },
  {
    canonicalPath: resolve(root, "shared/client-experience.json"),
    portalPath: resolve(root, "lib/client-experience.generated.ts"),
    mobilePath: resolve(root, "../mobile/src/config/clientExperience.generated.js"),
    exportName: "CLIENT_EXPERIENCE",
  },
  {
    canonicalPath: resolve(root, "shared/house-bindings.json"),
    portalPath: resolve(root, "lib/house-bindings.generated.ts"),
    mobilePath: resolve(root, "../mobile/src/config/houseBindings.generated.js"),
    exportName: "HOUSE_BINDINGS",
  },
];

const outputs = [];
for (const source of sources) {
  const canonical = JSON.parse(await readFile(source.canonicalPath, "utf8"));
  const payload = JSON.stringify(canonical, null, 2);
  const relativeSource = source.canonicalPath.slice(root.length + 1);
  const banner = `// Généré depuis ma-maison-portail-site/${relativeSource}. Ne pas modifier à la main.\n`;
  outputs.push(
    [source.portalPath, `${banner}export const ${source.exportName} = ${payload} as const;\n`],
    [source.mobilePath, `${banner}export const ${source.exportName} = ${payload};\n`],
  );
}

const energyAllocationSource = await readFile(resolve(root, "shared/energy-allocation.js"), "utf8");
const energyAllocationBanner = "// Généré depuis ma-maison-portail-site/shared/energy-allocation.js. Ne pas modifier à la main.\n";
outputs.push(
  [resolve(root, "lib/energy-allocation.generated.js"), `${energyAllocationBanner}${energyAllocationSource}`],
  [resolve(root, "../mobile/src/services/energyAllocation.js"), `${energyAllocationBanner}${energyAllocationSource}`],
);

if (process.argv.includes("--check")) {
  for (const [path, expected] of outputs) {
    assert.equal(await readFile(path, "utf8"), expected, `${path} n'est pas synchronisé`);
  }
  console.log("Profils partagés synchronisés.");
} else {
  for (const [path, content] of outputs) await writeFile(path, content, "utf8");
  console.log("Profils partagés générés pour le portail et l'application.");
}
