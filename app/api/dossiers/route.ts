import { asc, inArray } from "drizzle-orm";
import { getDb } from "../../../db";
import { installationDossiers } from "../../../db/schema";
import {
  portalApiAdminAuthorized,
  portalApiAuthorized,
  portalAuthorizedHouseIds,
} from "../../../lib/portal-api-auth";

function publicId() {
  return `installation_${crypto.randomUUID().replaceAll("-", "")}`;
}

export async function GET() {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const allowed = await portalAuthorizedHouseIds();
  if (allowed && allowed.size === 0) {
    return Response.json({ dossiers: [] }, { headers: { "Cache-Control": "no-store" } });
  }
  const query = getDb().select().from(installationDossiers);
  const dossiers = allowed
    ? await query.where(inArray(installationDossiers.publicId, [...allowed]))
      .orderBy(asc(installationDossiers.updatedAt))
    : await query.orderBy(asc(installationDossiers.updatedAt));
  return Response.json({
    dossiers: dossiers.map((dossier) => ({
      publicId: dossier.publicId,
      reference: dossier.reference,
      customerName: dossier.customerName,
      status: dossier.status,
      updatedAt: dossier.updatedAt,
    })),
  }, { headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: Request) {
  if (!await portalApiAdminAuthorized()) {
    return Response.json({ error: "Accès installateur requis" }, { status: 403 });
  }
  try {
    const body = await request.json() as { reference?: string; customerName?: string };
    const reference = String(body.reference ?? "").trim().toUpperCase().slice(0, 40);
    const customerName = String(body.customerName ?? "").trim().slice(0, 120);
    if (reference.length < 3 || customerName.length < 2) {
      return Response.json({ error: "Référence et client requis" }, { status: 400 });
    }
    const dossierPublicId = publicId();
    const [created] = await getDb().insert(installationDossiers).values({
      publicId: dossierPublicId,
      relayHouseId: dossierPublicId,
      reference,
      customerName,
    }).returning();
    return Response.json({
      dossier: {
        publicId: created.publicId,
        reference: created.reference,
        customerName: created.customerName,
        status: created.status,
        updatedAt: created.updatedAt,
      },
    }, { status: 201 });
  } catch {
    return Response.json({ error: "Création impossible" }, { status: 503 });
  }
}
