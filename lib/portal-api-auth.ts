import { getChatGPTUser } from "../app/chatgpt-auth";

function normalizedEmail(value: string) {
  return value.trim().toLowerCase();
}

function configuredEmails(name: string) {
  return new Set(
    (process.env[name] ?? "")
      .split(",")
      .map(normalizedEmail)
      .filter(Boolean),
  );
}

export function configuredHouseAccess(raw = process.env.PORTAL_HOUSE_ACCESS_JSON ?? "") {
  const access = new Map<string, Set<string>>();
  if (!raw.trim()) return access;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    for (const [publicId, emails] of Object.entries(parsed)) {
      if (!Array.isArray(emails)) continue;
      const allowed = new Set(
        emails
          .filter((email): email is string => typeof email === "string")
          .map(normalizedEmail)
          .filter(Boolean),
      );
      if (publicId.trim() && allowed.size > 0) access.set(publicId.trim(), allowed);
    }
  } catch {
    // Une configuration invalide refuse l'accès au lieu d'ouvrir toutes les maisons.
  }
  return access;
}

export function houseAccessAllows(
  raw: string,
  email: string,
  publicId: string,
  adminEmails = "",
) {
  const normalized = normalizedEmail(email);
  if (new Set(adminEmails.split(",").map(normalizedEmail).filter(Boolean)).has(normalized)) {
    return true;
  }
  return configuredHouseAccess(raw).get(publicId)?.has(normalized) ?? false;
}

function localDevelopmentAllowed() {
  return process.env.NODE_ENV === "development" &&
    process.env.HA_ALLOW_LOCAL_DEVELOPMENT === "true";
}

export async function portalApiAuthorized() {
  const user = await getChatGPTUser();
  return Boolean(user || localDevelopmentAllowed());
}

export async function portalApiAdminAuthorized() {
  if (localDevelopmentAllowed()) return true;
  const user = await getChatGPTUser();
  if (!user) return false;
  return configuredEmails("PORTAL_ADMIN_EMAILS").has(normalizedEmail(user.email));
}

export async function portalAuthorizedHouseIds() {
  if (localDevelopmentAllowed()) return null;
  const user = await getChatGPTUser();
  if (!user) return new Set<string>();
  const email = normalizedEmail(user.email);
  if (configuredEmails("PORTAL_ADMIN_EMAILS").has(email)) return null;
  return new Set(
    [...configuredHouseAccess().entries()]
      .filter(([, emails]) => emails.has(email))
      .map(([publicId]) => publicId),
  );
}

export async function portalHouseAuthorized(publicId: string) {
  const houseIds = await portalAuthorizedHouseIds();
  return houseIds === null || houseIds.has(publicId);
}

export function portalApiError(error: unknown) {
  const code = error instanceof Error ? error.message : "CONNECTOR_ERROR";
  const notFound = code.endsWith("_NOT_FOUND");
  const invalid = code.startsWith("INVALID_");
  return Response.json(
    {
      error: notFound
        ? "Élément introuvable"
        : invalid
        ? "Informations invalides"
        : "La modification n’a pas pu être appliquée",
    },
    {
      status: notFound ? 404 : invalid ? 400 : 502,
      headers: { "Cache-Control": "no-store" },
    },
  );
}
