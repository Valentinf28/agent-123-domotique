import { resolveRingCameraForDossier } from "../../../../../../lib/agent-home";
import { portalApiAuthorized } from "../../../../../../lib/portal-api-auth";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (!await portalApiAuthorized()) {
    return new Response("Authentification requise", {
      status: 401,
      headers: { "Cache-Control": "no-store" },
    });
  }
  const relayBaseUrl = process.env.RELAY_BASE_URL?.trim().replace(/\/+$/, "");
  const relaySecret = process.env.RELAY_CAMERA_SECRET?.trim();
  if (!relayBaseUrl || !relaySecret) {
    return new Response("Flux vidéo indisponible", {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  }
  try {
    const { id } = await context.params;
    const dossierPublicId = new URL(request.url).searchParams.get("dossier");
    const camera = await resolveRingCameraForDossier(id, dossierPublicId);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25_000);
    try {
      const response = await fetch(
        `${relayBaseUrl}/v1/internal/camera/${encodeURIComponent(camera.relayHouseId)}/${encodeURIComponent(camera.entityId)}`,
        {
          headers: {
            Accept: "image/jpeg,image/*",
            "X-Relay-Authorization": relaySecret,
          },
          signal: controller.signal,
          cache: "no-store",
        },
      );
      if (!response.ok || !response.body) {
        return new Response("Caméra temporairement indisponible", {
          status: 502,
          headers: { "Cache-Control": "no-store" },
        });
      }
      const contentType = response.headers.get("Content-Type") ?? "image/jpeg";
      if (!contentType.toLowerCase().startsWith("image/")) {
        return new Response("Format caméra invalide", {
          status: 502,
          headers: { "Cache-Control": "no-store" },
        });
      }
      return new Response(response.body, {
        status: 200,
        headers: {
          "Content-Type": contentType,
          "Cache-Control": "private, no-store",
          "X-Content-Type-Options": "nosniff",
        },
      });
    } finally {
      clearTimeout(timeout);
    }
  } catch (error) {
    const code = error instanceof Error ? error.message : "CAMERA_UNAVAILABLE";
    return new Response(
      code === "CAMERA_NOT_FOUND"
        ? "Caméra introuvable"
        : "Caméra temporairement indisponible",
      {
        status: code === "CAMERA_NOT_FOUND" ? 404 : 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
