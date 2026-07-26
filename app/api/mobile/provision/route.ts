import { and, eq, gt, isNull } from "drizzle-orm";
import { getDb } from "../../../../db";
import { installationDossiers, mobilePairingCodes } from "../../../../db/schema";
import { sha256 } from "../../../../lib/agent-auth";

const viewCatalog = {
  home: { key: "home", label: "Maison", icon: "home-variant-outline", path: "/lovelace/0" },
  solar: { key: "solar", label: "Solaire", icon: "solar-power", path: "/lovelace/solaire" },
  heating: { key: "heating", label: "Chauffage", icon: "home-thermometer-outline", path: "/lovelace/chauffage" },
  access: { key: "access", label: "Équipements", icon: "lightbulb-group-outline", path: "/lovelace/equipements" },
  pool: { key: "pool", label: "Piscine", icon: "pool", path: "/lovelace/piscine" },
  vehicle: { key: "vehicle", label: "Véhicule", icon: "car-electric", path: "/lovelace/vehicule" },
} as const;

export async function POST(request: Request) {
  try {
    const body = await request.json() as { code?: string };
    const code = String(body.code ?? "").trim().toUpperCase();
    if (!/^[A-Z2-9]{8}$/.test(code)) return Response.json({ error: "Code invalide" }, { status: 400 });
    const db = getDb();
    const [pairing] = await db.select().from(mobilePairingCodes).where(and(
      eq(mobilePairingCodes.codeHash, await sha256(code)),
      isNull(mobilePairingCodes.usedAt),
      gt(mobilePairingCodes.expiresAt, new Date().toISOString()),
    )).limit(1);
    if (!pairing) return Response.json({ error: "Code expiré ou déjà utilisé" }, { status: 410 });
    const [dossier] = await db.select().from(installationDossiers)
      .where(eq(installationDossiers.id, pairing.dossierId)).limit(1);
    if (!dossier) return Response.json({ error: "Maison introuvable" }, { status: 404 });
    let modules: string[] = ["home"];
    try { modules = JSON.parse(dossier.enabledModules); } catch {}
    const views = modules
      .filter((module): module is keyof typeof viewCatalog => module in viewCatalog)
      .map(module => viewCatalog[module]);
    await db.update(mobilePairingCodes).set({ usedAt: new Date().toISOString() })
      .where(eq(mobilePairingCodes.id, pairing.id));
    return Response.json({
      installationId: dossier.publicId,
      houseName: dossier.customerName || "Ma Maison",
      homeAssistantUrl: "http://homeassistant.local:8123",
      modules,
      views,
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Association impossible" }, { status: 503 });
  }
}
