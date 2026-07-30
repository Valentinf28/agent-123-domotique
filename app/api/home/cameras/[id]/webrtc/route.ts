import { resolveRingCameraForDossier } from "../../../../../../lib/agent-home";
import { portalApiAuthorized } from "../../../../../../lib/portal-api-auth";

type WebRTCScope = {
  cameraId: string;
  dossier: string;
  expiresAt: number;
  relaySessionId: string;
};

function encodeBase64Url(value: string | ArrayBuffer) {
  const bytes = typeof value === "string"
    ? new TextEncoder().encode(value)
    : new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function decodeBase64Url(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const binary = atob(padded);
  return new TextDecoder().decode(
    Uint8Array.from(binary, (character) => character.charCodeAt(0)),
  );
}

async function signingKey(secret: string) {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

async function createScope(value: WebRTCScope, secret: string) {
  const payload = encodeBase64Url(JSON.stringify(value));
  const signature = await crypto.subtle.sign(
    "HMAC",
    await signingKey(secret),
    new TextEncoder().encode(payload),
  );
  return `${payload}.${encodeBase64Url(signature)}`;
}

async function readScope(value: string, secret: string): Promise<WebRTCScope> {
  const [payload, signature] = value.split(".");
  if (!payload || !signature) throw new Error("WEBRTC_SCOPE_INVALID");
  const normalized = signature.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const binary = atob(padded);
  const valid = await crypto.subtle.verify(
    "HMAC",
    await signingKey(secret),
    Uint8Array.from(binary, (character) => character.charCodeAt(0)),
    new TextEncoder().encode(payload),
  );
  if (!valid) throw new Error("WEBRTC_SCOPE_INVALID");
  const parsed = JSON.parse(decodeBase64Url(payload)) as WebRTCScope;
  if (
    !parsed ||
    typeof parsed.cameraId !== "string" ||
    typeof parsed.dossier !== "string" ||
    typeof parsed.relaySessionId !== "string" ||
    typeof parsed.expiresAt !== "number" ||
    parsed.expiresAt < Date.now()
  ) {
    throw new Error("WEBRTC_SCOPE_INVALID");
  }
  return parsed;
}

function json(value: unknown, status = 200) {
  return Response.json(value, {
    status,
    headers: {
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (!await portalApiAuthorized()) {
    return json({ error: "Authentification requise" }, 401);
  }
  const relayBaseUrl = process.env.RELAY_BASE_URL?.trim().replace(/\/+$/, "");
  const relaySecret = process.env.RELAY_CAMERA_SECRET?.trim();
  if (!relayBaseUrl || !relaySecret) {
    return json({ error: "Direct vidéo indisponible" }, 503);
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 70_000);
  try {
    const { id } = await context.params;
    const body = await request.json() as {
      action?: unknown;
      candidate?: unknown;
      dossier?: unknown;
      offer?: unknown;
      scope?: unknown;
    };
    const action = String(body.action ?? "");
    const dossier = typeof body.dossier === "string" ? body.dossier : "";
    const camera = await resolveRingCameraForDossier(id, dossier || null);
    const headers = {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Relay-Authorization": relaySecret,
    };
    if (action === "config") {
      const response = await fetch(
        `${relayBaseUrl}/v1/internal/camera/${encodeURIComponent(camera.relayHouseId)}/${encodeURIComponent(camera.entityId)}/webrtc/config`,
        { headers, signal: controller.signal, cache: "no-store" },
      );
      if (!response.ok) throw new Error("WEBRTC_CONFIG_FAILED");
      return json(await response.json());
    }
    if (action === "offer") {
      const offer = typeof body.offer === "string" ? body.offer : "";
      if (!offer || offer.length > 200_000) {
        return json({ error: "Offre vidéo invalide" }, 400);
      }
      const response = await fetch(
        `${relayBaseUrl}/v1/internal/camera/${encodeURIComponent(camera.relayHouseId)}/${encodeURIComponent(camera.entityId)}/webrtc/offer`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({ offer }),
          signal: controller.signal,
          cache: "no-store",
        },
      );
      if (!response.ok) throw new Error("WEBRTC_OFFER_FAILED");
      const result = await response.json() as {
        answer?: unknown;
        candidates?: unknown;
        relaySessionId?: unknown;
      };
      if (
        typeof result.answer !== "string" ||
        typeof result.relaySessionId !== "string"
      ) {
        throw new Error("WEBRTC_OFFER_FAILED");
      }
      const scope = await createScope({
        cameraId: id,
        dossier,
        expiresAt: Date.now() + 9 * 60_000,
        relaySessionId: result.relaySessionId,
      }, relaySecret);
      return json({
        answer: result.answer,
        candidates: Array.isArray(result.candidates) ? result.candidates : [],
        scope,
      });
    }
    const scopeValue = typeof body.scope === "string" ? body.scope : "";
    const scope = await readScope(scopeValue, relaySecret);
    if (scope.cameraId !== id || scope.dossier !== dossier) {
      throw new Error("WEBRTC_SCOPE_INVALID");
    }
    const sessionUrl =
      `${relayBaseUrl}/v1/internal/camera/webrtc/${encodeURIComponent(scope.relaySessionId)}`;
    if (action === "poll") {
      const response = await fetch(`${sessionUrl}/events`, {
        headers,
        signal: controller.signal,
        cache: "no-store",
      });
      if (!response.ok) throw new Error("WEBRTC_POLL_FAILED");
      return json(await response.json());
    }
    if (action === "candidate") {
      if (!body.candidate || typeof body.candidate !== "object") {
        return json({ error: "Candidat vidéo invalide" }, 400);
      }
      const response = await fetch(`${sessionUrl}/candidate`, {
        method: "POST",
        headers,
        body: JSON.stringify({ candidate: body.candidate }),
        signal: controller.signal,
        cache: "no-store",
      });
      if (!response.ok) throw new Error("WEBRTC_CANDIDATE_FAILED");
      return json({ accepted: true });
    }
    if (action === "close") {
      await fetch(sessionUrl, {
        method: "DELETE",
        headers,
        signal: controller.signal,
        cache: "no-store",
      });
      return json({ closed: true });
    }
    return json({ error: "Action vidéo inconnue" }, 400);
  } catch {
    return json({ error: "Direct vidéo temporairement indisponible" }, 502);
  } finally {
    clearTimeout(timeout);
  }
}
