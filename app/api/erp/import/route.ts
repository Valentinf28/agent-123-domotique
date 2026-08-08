import { and, eq, ne } from "drizzle-orm";
import { getDb } from "../../../../db";
import { installationDossiers, plannedDevices } from "../../../../db/schema";
import { getErpDossier } from "../../../../lib/erp-api";
import {
  batteryCapacityWhFromErp,
  modulesFromErp,
  peakWattsFromErp,
  plannedDevicesFromErp,
  solarArraysFromErp,
} from "../../../../lib/erp-house-import";
import { portalApiAdminAuthorized } from "../../../../lib/portal-api-auth";

function publicId(prefix: string) {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
}

export async function POST(request: Request) {
  if (!await portalApiAdminAuthorized()) {
    return Response.json({ error: "Accès installateur requis" }, { status: 403 });
  }
  try {
    const body = await request.json() as { erpDossierId?: number; dossierPublicId?: string };
    const erpDossierId = Math.round(Number(body.erpDossierId));
    const dossierPublicId = String(body.dossierPublicId || "").trim();
    if (!Number.isInteger(erpDossierId) || erpDossierId <= 0 || !dossierPublicId) {
      return Response.json({ error: "Dossier invalide" }, { status: 400 });
    }
    const db = getDb();
    const [dossier] = await db.select().from(installationDossiers)
      .where(eq(installationDossiers.publicId, dossierPublicId)).limit(1);
    if (!dossier) return Response.json({ error: "Préparation introuvable" }, { status: 404 });
    const [alreadyLinked] = await db.select({ publicId: installationDossiers.publicId })
      .from(installationDossiers)
      .where(and(eq(installationDossiers.erpDossierId, erpDossierId), ne(installationDossiers.id, dossier.id))).limit(1);
    if (alreadyLinked) {
      return Response.json({ error: "Ce dossier ERP est déjà rattaché à une autre maison" }, { status: 409 });
    }

    const erp = await getErpDossier(erpDossierId);
    const devices = plannedDevicesFromErp(Array.isArray(erp.devices) ? erp.devices : []);
    const arrays = solarArraysFromErp(erp);
    const solarPeakWatts = peakWattsFromErp(erp.solarPeakKwc);
    const batteryCapacityWh = batteryCapacityWhFromErp(erp.battery);
    const enabledModules = modulesFromErp(erp.devices || [], solarPeakWatts > 0);
    const now = new Date().toISOString();
    const rows = devices.map((item) => ({
      publicId: publicId("planned"), dossierId: dossier.id,
      catalogId: item.id, brand: item.brand, model: item.model, category: item.category,
      protocol: item.protocol, compatibilityLevel: item.level, connectionMethod: item.method,
      prerequisites: item.prerequisites, estimatedMinutes: item.estimatedMinutes, icon: item.icon,
      quantity: item.quantity, room: item.room, status: item.status,
    }));
    const insertStatements = [];
    for (let index = 0; index < rows.length; index += 4) {
      insertStatements.push(db.insert(plannedDevices).values(rows.slice(index, index + 4)));
    }
    await db.batch([
      db.delete(plannedDevices).where(eq(plannedDevices.dossierId, dossier.id)),
      ...insertStatements,
      db.update(installationDossiers).set({
        erpDossierId,
        erpImportedAt: now,
        reference: String(erp.reference || dossier.reference).toUpperCase().slice(0, 40),
        customerName: String(erp.customerName || dossier.customerName).slice(0, 120),
        customerAddress: [erp.address, erp.postalCode, erp.city].filter(Boolean).join(" · ").slice(0, 300) || null,
        enabledModules: JSON.stringify(enabledModules),
        solarPeakWatts,
        solarArraysJson: JSON.stringify(arrays),
        batteryCapacityWh,
        updatedAt: now,
      }).where(eq(installationDossiers.id, dossier.id)),
    ]);
    return Response.json({
      imported: true,
      dossier: {
        publicId: dossier.publicId,
        reference: erp.reference,
        customerName: erp.customerName,
        customerAddress: [erp.address, erp.postalCode, erp.city].filter(Boolean).join(" · "),
        erpDossierId,
        erpImportedAt: now,
        devicesSource: erp.devicesSource,
        domotiqueConfirmed: erp.domotiqueConfirmed,
      },
      items: devices,
      enabledModules,
      energyConfiguration: {
        solarPeakWatts,
        solarArrays: arrays,
        batteryCapacityWh,
        batteryReservePercent: dossier.batteryReservePercent,
        flexibleLoads: JSON.parse(dossier.flexibleLoadsJson || "[]"),
        tariffPlan: dossier.tariffPlan,
        offPeakPeriods: JSON.parse(dossier.offPeakPeriodsJson || "[]"),
      },
      warnings: [
        !erp.domotiqueConfirmed ? "La liste domotique n’est pas encore confirmée dans l’ERP" : null,
        erp.hasBattery && batteryCapacityWh === 0 ? "La capacité de la batterie doit être renseignée" : null,
        arrays.some((array) => array.orientation === "À vérifier" || array.inclinationDegrees === null)
          ? "Une orientation ou une inclinaison reste à vérifier" : null,
      ].filter(Boolean),
    });
  } catch (error) {
    const notConfigured = error instanceof Error && error.message === "ERP_NOT_CONFIGURED";
    return Response.json({
      error: notConfigured ? "La liaison ERP doit être activée" : "Import ERP impossible",
    }, { status: notConfigured ? 503 : 502 });
  }
}
