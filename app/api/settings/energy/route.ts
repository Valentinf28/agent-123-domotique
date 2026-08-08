import { eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { installationDossiers } from "../../../../db/schema";
import { portalHouseAuthorized } from "../../../../lib/portal-api-auth";

type OffPeakPeriod = { id: string; label: string; start: string; end: string };

function periodsFrom(value: string): OffPeakPeriod[] {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function sanitizePeriods(value: unknown): OffPeakPeriod[] {
  if (!Array.isArray(value)) return [];
  const time = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
  return value.slice(0, 4).map((raw, index) => {
    const item = raw && typeof raw === "object" ? raw as Partial<OffPeakPeriod> : {};
    const start = String(item.start ?? "").trim();
    const end = String(item.end ?? "").trim();
    if (!time.test(start) || !time.test(end) || start === end) throw new Error("INVALID_PERIOD");
    return {
      id: String(item.id ?? `hc-${index + 1}`).replace(/[^a-z0-9_-]/gi, "-").slice(0, 40),
      label: String(item.label ?? `Plage ${index + 1}`).trim().slice(0, 40),
      start,
      end,
    };
  });
}

function price(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0 || numeric > 2_000) throw new Error("INVALID_PRICE");
  return Math.round(numeric);
}

async function authorizedDossier(publicId: string) {
  if (!publicId || !await portalHouseAuthorized(publicId)) return null;
  const [dossier] = await getDb().select().from(installationDossiers)
    .where(eq(installationDossiers.publicId, publicId)).limit(1);
  return dossier ?? null;
}

function response(dossier: typeof installationDossiers.$inferSelect) {
  return {
    tariffPlan: dossier.tariffPlan === "hp_hc" ? "hp_hc" : "base",
    basePriceMilliEurosPerKwh: dossier.basePriceMilliEurosPerKwh,
    peakPriceMilliEurosPerKwh: dossier.peakPriceMilliEurosPerKwh,
    offPeakPriceMilliEurosPerKwh: dossier.offPeakPriceMilliEurosPerKwh,
    exportPriceMilliEurosPerKwh: dossier.exportPriceMilliEurosPerKwh,
    offPeakPeriods: periodsFrom(dossier.offPeakPeriodsJson),
  };
}

export async function GET(request: Request) {
  const dossier = await authorizedDossier(new URL(request.url).searchParams.get("dossier") ?? "");
  if (!dossier) return Response.json({ error: "Accès refusé" }, { status: 403 });
  return Response.json({ energyContract: response(dossier) }, { headers: { "Cache-Control": "no-store" } });
}

export async function PUT(request: Request) {
  try {
    const body = await request.json() as Record<string, unknown>;
    const publicId = String(body.dossierPublicId ?? "");
    const dossier = await authorizedDossier(publicId);
    if (!dossier) return Response.json({ error: "Accès refusé" }, { status: 403 });
    const tariffPlan = body.tariffPlan === "hp_hc" ? "hp_hc" : "base";
    const offPeakPeriods = tariffPlan === "hp_hc" ? sanitizePeriods(body.offPeakPeriods) : [];
    if (tariffPlan === "hp_hc" && offPeakPeriods.length === 0) {
      return Response.json({ error: "Ajoutez au moins une plage d’heures creuses" }, { status: 400 });
    }
    const values = {
      tariffPlan,
      basePriceMilliEurosPerKwh: price(body.basePriceMilliEurosPerKwh),
      peakPriceMilliEurosPerKwh: price(body.peakPriceMilliEurosPerKwh),
      offPeakPriceMilliEurosPerKwh: price(body.offPeakPriceMilliEurosPerKwh),
      exportPriceMilliEurosPerKwh: price(body.exportPriceMilliEurosPerKwh),
      offPeakPeriodsJson: JSON.stringify(offPeakPeriods),
      updatedAt: new Date().toISOString(),
    };
    await getDb().update(installationDossiers).set(values)
      .where(eq(installationDossiers.id, dossier.id));
    return Response.json({ saved: true, energyContract: { ...values, offPeakPeriods } });
  } catch (error) {
    const message = error instanceof Error && error.message === "INVALID_PERIOD"
      ? "Une plage d’heures creuses est invalide"
      : "Un prix du contrat est invalide";
    return Response.json({ error: message }, { status: 400 });
  }
}
