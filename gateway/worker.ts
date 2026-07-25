interface Env {
  HA_BASE_URL?: string;
  HA_ACCESS_TOKEN?: string;
  PORTAL_ORIGIN?: string;
  PORTAL_BYPASS_TOKEN?: string;
}

async function agentApi(request: Request, env: Env, pathname: string) {
  const portalOrigin = env.PORTAL_ORIGIN?.trim().replace(/\/+$/, "");
  const bypassToken = env.PORTAL_BYPASS_TOKEN?.trim();
  if (!portalOrigin || !bypassToken || request.method !== "POST") {
    return new Response("Passerelle indisponible", { status: 503 });
  }
  const length = Number(request.headers.get("Content-Length") ?? "0");
  if (length > 64_000) return new Response("Requête trop volumineuse", { status: 413 });
  const headers = new Headers({
    Authorization: `Bearer ${bypassToken}`,
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Forwarded-Proto": "https",
  });
  const agentAuthorization = request.headers.get("Authorization");
  if (agentAuthorization) headers.set("X-Agent-Authorization", agentAuthorization);
  const response = await fetch(`${portalOrigin}${pathname}`, {
    method: "POST",
    headers,
    body: request.body,
  });
  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

const encoder = new TextEncoder();
const blockedSocketTypes = [
  "backup/",
  "repairs/",
  "onboarding/",
  "system_health/",
];

function decodeBase64url(value: string) {
  const padded = value
    .replaceAll("-", "+")
    .replaceAll("_", "/")
    .padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function signingKey(secret: string) {
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );
}

async function verifyPortalSession(secret: string, token: string) {
  const [payload, signature] = token.split(".");
  if (!payload || !signature) return false;
  const valid = await crypto.subtle.verify(
    "HMAC",
    await signingKey(secret),
    decodeBase64url(signature),
    encoder.encode(payload),
  );
  if (!valid) return false;
  try {
    const data = JSON.parse(
      new TextDecoder().decode(decodeBase64url(payload)),
    ) as { exp?: number; scope?: string };
    return data.scope === "lovelace" &&
      typeof data.exp === "number" &&
      data.exp > Date.now() / 1000;
  } catch {
    return false;
  }
}

function socketTypePermitted(type: string) {
  if (type === "auth/current_user") return true;
  if (type.startsWith("auth/")) return false;
  if (type.startsWith("config/")) {
    return type.endsWith("/list") ||
      type.endsWith("/list_for_display") ||
      type.endsWith("/get");
  }
  return !blockedSocketTypes.some((prefix) => type.startsWith(prefix));
}

async function openGateway(request: Request, env: Env) {
  const baseUrl = env.HA_BASE_URL?.trim().replace(/\/+$/, "");
  const accessToken = env.HA_ACCESS_TOKEN?.trim();
  const portalOrigin = env.PORTAL_ORIGIN?.trim().replace(/\/+$/, "");
  if (!baseUrl || !accessToken || !portalOrigin) {
    return new Response("Passerelle indisponible", { status: 503 });
  }
  if (request.headers.get("Origin") !== portalOrigin) {
    return new Response("Origine refusée", { status: 403 });
  }

  const pair = new WebSocketPair();
  const client = pair[0];
  const browser = pair[1];
  browser.accept();

  const upstreamResponse = await fetch(`${baseUrl}/api/websocket`, {
    headers: { Upgrade: "websocket" },
  });
  const upstream = upstreamResponse.webSocket;
  if (!upstream) {
    browser.close(1011, "Maison inaccessible");
    return new Response("Maison inaccessible", { status: 502 });
  }

  browser.addEventListener("message", async (event) => {
    try {
      const message = JSON.parse(String(event.data)) as {
        id?: number;
        type?: string;
        access_token?: string;
      };
      if (message.type === "auth") {
        const accepted = Boolean(
          message.access_token &&
          await verifyPortalSession(accessToken, message.access_token),
        );
        if (!accepted) {
          browser.close(1008, "Session refusée");
          upstream.close(1008, "Session refusée");
          return;
        }
        upstream.send(JSON.stringify({
          type: "auth",
          access_token: accessToken,
        }));
        return;
      }
      if (message.type && !socketTypePermitted(message.type)) {
        browser.send(JSON.stringify({
          id: message.id,
          type: "result",
          success: false,
          error: {
            code: "unauthorized",
            message: "Action non autorisée",
          },
        }));
        return;
      }
      upstream.send(event.data);
    } catch {
      browser.close(1003, "Message invalide");
    }
  });

  upstream.addEventListener("message", (event) => browser.send(event.data));
  upstream.addEventListener("close", () =>
    browser.close(1000, "Maison déconnectée")
  );
  browser.addEventListener("close", () =>
    upstream.close(1000, "Client déconnecté")
  );
  upstream.accept();

  return new Response(null, { status: 101, webSocket: client });
}

const worker = {
  async fetch(request: Request, env: Env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json(
        { ready: true, service: "ma-maison-gateway" },
        {
          headers: {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
          },
        },
      );
    }
    if (
      url.pathname === "/api/websocket" &&
      request.headers.get("Upgrade")?.toLowerCase() === "websocket"
    ) {
      return openGateway(request, env);
    }
    if (url.pathname === "/agent/enroll") {
      return agentApi(request, env, "/api/agent/enroll");
    }
    if (url.pathname === "/agent/heartbeat") {
      return agentApi(request, env, "/api/agent/heartbeat");
    }
    return new Response("Not found", { status: 404 });
  },
};

export default worker;
