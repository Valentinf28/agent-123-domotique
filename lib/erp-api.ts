import type { ErpDossierDetail, ErpDossierSummary } from "./erp-house-import";

function configuration() {
  const baseUrl = (process.env.ERP_API_URL || "https://gestion.123panneaux-solaires.fr/api").replace(/\/$/, "");
  const secret = process.env.ERP_PORTAL_TOKEN || "";
  if (!secret) throw new Error("ERP_NOT_CONFIGURED");
  return { baseUrl, secret };
}

async function erpFetch<T>(path: string): Promise<T> {
  const { baseUrl, secret } = configuration();
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { Accept: "application/json", "X-Portal-Secret": secret },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(response.status === 404 ? "ERP_DOSSIER_NOT_FOUND" : "ERP_UNAVAILABLE");
  }
  return response.json() as Promise<T>;
}

export async function searchErpDossiers(query: string) {
  const payload = await erpFetch<{ dossiers: ErpDossierSummary[] }>(
    `/integrations/domotique/dossiers?q=${encodeURIComponent(query)}&limit=25`,
  );
  return payload.dossiers;
}

export function getErpDossier(id: number) {
  return erpFetch<ErpDossierDetail>(`/integrations/domotique/dossiers/${id}`);
}
