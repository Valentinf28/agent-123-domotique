import { eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { installationDossiers } from "../../../../db/schema";
import { portalApiAuthorized } from "../../../../lib/portal-api-auth";
import {
  addDays,
  GRACE_DAYS,
  MONTHLY_PRICE_CENTS,
  subscriptionSummary,
  YEARLY_PRICE_CENTS,
} from "../../../../lib/subscription";

async function dossierByPublicId(publicId: string) {
  const [dossier] = await getDb().select().from(installationDossiers)
    .where(eq(installationDossiers.publicId, publicId)).limit(1);
  return dossier;
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ publicId: string }> },
) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const { publicId } = await context.params;
  const dossier = await dossierByPublicId(publicId);
  if (!dossier) return Response.json({ error: "Maison introuvable" }, { status: 404 });
  return Response.json({
    subscription: subscriptionSummary(dossier),
  }, { headers: { "Cache-Control": "no-store" } });
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ publicId: string }> },
) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  const { publicId } = await context.params;
  const dossier = await dossierByPublicId(publicId);
  if (!dossier) return Response.json({ error: "Maison introuvable" }, { status: 404 });
  const body = await request.json() as {
    action?: string;
    interval?: "monthly" | "yearly";
  };
  const now = new Date();
  const nowIso = now.toISOString();
  const update: Partial<typeof installationDossiers.$inferInsert> = {
    updatedAt: nowIso,
  };

  if (body.action === "start_trial") {
    if (dossier.subscriptionStatus !== "not_started") {
      return Response.json({ error: "L’essai a déjà été démarré" }, { status: 409 });
    }
    update.subscriptionStatus = "trialing";
    update.trialStartedAt = nowIso;
    update.trialEndsAt = addDays(now, 30).toISOString();
    update.graceEndsAt = null;
  } else if (body.action === "activate") {
    const interval = body.interval === "yearly" ? "yearly" : "monthly";
    update.subscriptionStatus = "active";
    update.subscriptionInterval = interval;
    update.subscriptionPriceCents = interval === "yearly"
      ? YEARLY_PRICE_CENTS
      : MONTHLY_PRICE_CENTS;
    update.subscriptionStartedAt = dossier.subscriptionStartedAt || nowIso;
    update.subscriptionEndsAt = null;
    update.graceEndsAt = null;
  } else if (body.action === "mark_past_due") {
    update.subscriptionStatus = "past_due";
    update.graceEndsAt = addDays(now, GRACE_DAYS).toISOString();
  } else if (body.action === "suspend") {
    update.subscriptionStatus = "suspended";
    update.graceEndsAt = null;
  } else if (body.action === "cancel") {
    update.subscriptionStatus = "cancelled";
    update.subscriptionEndsAt = nowIso;
    update.graceEndsAt = null;
  } else {
    return Response.json({ error: "Action inconnue" }, { status: 400 });
  }

  const [updated] = await getDb().update(installationDossiers).set(update)
    .where(eq(installationDossiers.id, dossier.id)).returning();
  return Response.json({
    subscription: subscriptionSummary(updated),
  }, { headers: { "Cache-Control": "no-store" } });
}
