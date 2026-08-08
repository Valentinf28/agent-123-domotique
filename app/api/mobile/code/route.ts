import { and, asc, eq, isNull } from "drizzle-orm";
import { getDb } from "../../../../db";
import { installationDossiers, mobilePairingCodes } from "../../../../db/schema";
import { enrollmentCode, sha256 } from "../../../../lib/agent-auth";
import { portalApiAdminAuthorized } from "../../../../lib/portal-api-auth";

export async function POST(request: Request) {
  if (!await portalApiAdminAuthorized()) {
    return Response.json({ error: "Accès installateur requis" }, { status: 403 });
  }
  const db = getDb();
  const requested = new URL(request.url).searchParams.get("dossier");
  const [dossier] = requested
    ? await db.select().from(installationDossiers)
      .where(eq(installationDossiers.publicId, requested)).limit(1)
    : await db.select().from(installationDossiers)
      .where(eq(installationDossiers.status, "preparation"))
      .orderBy(asc(installationDossiers.id)).limit(1);
  if (!dossier) return Response.json({ error: "Aucun dossier en préparation" }, { status: 404 });

  const code = enrollmentCode();
  const expiresAt = new Date(Date.now() + 30 * 60 * 1000).toISOString();
  await db.delete(mobilePairingCodes).where(and(
    eq(mobilePairingCodes.dossierId, dossier.id),
    isNull(mobilePairingCodes.usedAt),
  ));
  await db.insert(mobilePairingCodes).values({
    publicId: crypto.randomUUID(), dossierId: dossier.id,
    codeHash: await sha256(code), expiresAt,
  });
  return Response.json({ code, expiresAt }, { status: 201, headers: { "Cache-Control": "no-store" } });
}
