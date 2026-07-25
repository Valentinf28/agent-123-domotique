/** Cloudflare Worker entry point for the vinext-starter template. */
import { handleImageOptimization, DEFAULT_DEVICE_SIZES, DEFAULT_IMAGE_SIZES } from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";
import { verifyLovelaceSession } from "../lib/lovelace-session";

interface Env {
  ASSETS: Fetcher;
  DB: D1Database;
  HA_BASE_URL?: string;
  HA_ACCESS_TOKEN?: string;
  IMAGES: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

const LOVELACE_PREFIX = "/ma-maison/ha";
const blockedPaths = [
  "/config", "/developer-tools", "/profile", "/auth", "/api/config",
  "/api/error", "/api/repairs", "/api/onboarding",
];
const allowedPrefixes = [
  "/lovelace/0", "/frontend_latest/", "/static/", "/local/", "/hacsfiles/",
  "/api/websocket", "/api/states", "/api/services/", "/api/history/",
  "/api/lovelace/", "/api/camera_proxy/", "/api/media_proxy/",
];
const blockedSocketTypes = [
  "backup/", "repairs/", "onboarding/", "system_health/",
];

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

function upstreamConfig(env: Env) {
  const baseUrl = env.HA_BASE_URL?.trim().replace(/\/+$/, "");
  const token = env.HA_ACCESS_TOKEN?.trim();
  if (!baseUrl || !token) return null;
  return { baseUrl, token };
}

function upstreamHeaders(request: Request, token: string) {
  const headers = new Headers({
    Accept: request.headers.get("Accept") ?? "*/*",
    Authorization: `Bearer ${token}`,
  });
  const forwardedHeaders = [
    "Accept-Language",
    "Content-Type",
    "If-Modified-Since",
    "If-None-Match",
    "Range",
    "User-Agent",
  ];
  for (const name of forwardedHeaders) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

function permittedPath(pathname: string) {
  if (blockedPaths.some((path) => pathname === path || pathname.startsWith(`${path}/`))) return false;
  return allowedPrefixes.some((path) => pathname === path || pathname.startsWith(path));
}

function bridgeScript() {
  return `(() => {
    const prefix = ${JSON.stringify(LOVELACE_PREFIX)};
    const originalFetch = window.fetch.bind(window);
    const proxiedPaths = ["/api/", "/static/", "/local/", "/hacsfiles/", "/frontend_latest/"];
    window.fetch = (input, init) => {
      if (typeof input === "string" && proxiedPaths.some((path) => input.startsWith(path))) input = prefix + input;
      else if (input instanceof Request && new URL(input.url).origin === location.origin) {
        const url = new URL(input.url);
        if (proxiedPaths.some((path) => url.pathname.startsWith(path))) {
          url.pathname = prefix + url.pathname;
          input = new Request(url, input);
        }
      }
      return originalFetch(input, init);
    };
    const requestToken = async (payload) => {
      console.info("[MaMaison] auth-request");
      document.documentElement.dataset.maMaisonStage = "auth-request";
      const message = typeof payload === "string" ? JSON.parse(payload) : payload;
      const response = await originalFetch("/api/lovelace/browser-token", { credentials: "same-origin", cache: "no-store" });
      const callback = window[message.callback];
      if (typeof callback !== "function") return;
      if (!response.ok) return callback(false);
      console.info("[MaMaison] auth-ready");
      document.documentElement.dataset.maMaisonStage = "auth-ready";
      callback(true, await response.json());
    };
    window.externalApp = {
      getExternalAuth: requestToken,
      revokeExternalAuth: (payload) => {
        const message = typeof payload === "string" ? JSON.parse(payload) : payload;
        window[message.callback](true);
      }
    };
    window.externalAppV2 = {
      postMessage: (payload) => {
        const message = typeof payload === "string" ? JSON.parse(payload) : payload;
        if (message.type === "getExternalAuth") return requestToken(message.payload);
        if (message.type === "revokeExternalAuth") {
          const callback = window[message.payload?.callback];
          if (typeof callback === "function") callback(true);
        }
      }
    };
    const NativeWebSocket = window.WebSocket;
    if (typeof NativeWebSocket === "function") {
      window.WebSocket = class extends NativeWebSocket {
        constructor(url, protocols) {
          const next = new URL(url, location.href);
          if (next.pathname === "/api/websocket") {
            next.protocol = location.protocol === "https:" ? "wss:" : "ws:";
            next.host = location.host;
            next.pathname = prefix + next.pathname;
          }
          console.info("[MaMaison] websocket", next.pathname);
          document.documentElement.dataset.maMaisonStage = "websocket";
          super(next.toString(), protocols);
        }
      };
    }
    const kioskCss = [
      "app-header,ha-sidebar,ha-menu-button,#drawer,.menu,.header{display:none!important}",
      "app-drawer-layout{--app-drawer-width:0px!important}",
      ".sidebar-shell{display:none!important}.app-content{margin-left:0!important;width:100%!important}",
      "ha-panel-lovelace{padding-top:0!important}",
      "hui-root{--header-height:0px!important}",
      "ha-init-page img{display:none!important}",
      "body{padding-top:72px!important;box-sizing:border-box!important}",
      "#ma-maison-web-header{position:fixed;inset:0 0 auto 0;height:72px;z-index:2147483647;display:flex;align-items:center;justify-content:space-between;padding:0 22px;background:#11120f;border-bottom:1px solid #2a2b25;color:#fff;font-family:Arial,sans-serif;box-sizing:border-box}",
      "#ma-maison-web-header a,#ma-maison-web-header button{width:42px;height:42px;border:1px solid #34352e;border-radius:14px;background:#20211c;color:#f7c948;display:grid;place-items:center;text-decoration:none;font-size:26px;cursor:pointer}",
      "#ma-maison-web-header div{text-align:center;line-height:1.1}#ma-maison-web-header span{display:block;color:#f7c948;font-size:11px;font-weight:800;letter-spacing:.18em;margin-bottom:5px}#ma-maison-web-header strong{font-size:17px}",
      "@media(max-width:640px){body{padding-top:64px!important}#ma-maison-web-header{height:64px;padding:0 12px}#ma-maison-web-header a,#ma-maison-web-header button{width:38px;height:38px;border-radius:12px}}"
    ].join("");
    const lockRoot = (root) => {
      if (!root || root.querySelector("style[data-ma-maison]")) return;
      const style = document.createElement("style");
      style.dataset.maMaison = "true";
      style.textContent = kioskCss;
      (root.nodeType === 9 ? root.documentElement : root).appendChild(style);
      root.addEventListener("click", (event) => {
        const path = event.composedPath();
        const link = path.find((node) => node && node.tagName === "A");
        if (!link) return;
        const target = new URL(link.href, location.href);
        if (!target.pathname.startsWith("/lovelace/0")) {
          event.preventDefault();
          event.stopImmediatePropagation();
        }
      }, true);
    };
    const scan = (root) => {
      lockRoot(root);
      root.querySelectorAll("*").forEach((element) => {
        if (["HA-SIDEBAR", "HA-MENU-BUTTON", "APP-HEADER"].includes(element.tagName)) {
          element.style.setProperty("display", "none", "important");
          element.setAttribute("aria-hidden", "true");
        }
        if (element.shadowRoot) scan(element.shadowRoot);
      });
    };
    const installShell = () => {
      if (!document.body || document.getElementById("ma-maison-web-header")) return;
      const header = document.createElement("header");
      header.id = "ma-maison-web-header";
      const back = document.createElement("a");
      back.href = "/";
      back.setAttribute("aria-label", "Retour au portail");
      back.textContent = "‹";
      const title = document.createElement("div");
      const brand = document.createElement("span");
      brand.textContent = "MA MAISON";
      const label = document.createElement("strong");
      label.textContent = "Tableau de bord";
      title.append(brand, label);
      const refresh = document.createElement("button");
      refresh.type = "button";
      refresh.setAttribute("aria-label", "Actualiser le tableau de bord");
      refresh.textContent = "↻";
      refresh.addEventListener("click", () => location.reload());
      header.append(back, title, refresh);
      document.body.prepend(header);
    };
    console.info("[MaMaison] bridge-ready");
    document.documentElement.dataset.maMaisonStage = "bridge-ready";
    scan(document);
    installShell();
    setInterval(() => {
      scan(document);
      installShell();
    }, 400);
  })();`;
}

async function proxyHttp(request: Request, env: Env, upstreamPath: string) {
  const config = upstreamConfig(env);
  if (!config || !permittedPath(upstreamPath)) return new Response("Not found", { status: 404 });
  const incoming = new URL(request.url);
  const target = new URL(`${upstreamPath}${incoming.search}`, config.baseUrl);
  if (target.pathname === "/lovelace/0") target.searchParams.set("external_auth", "1");

  // Only forward headers Home Assistant needs. Sites adds dispatcher and
  // Cloudflare headers that are invalid or unsafe on a subrequest.
  const headers = upstreamHeaders(request, config.token);
  const response = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    redirect: "manual",
  });
  const outgoing = new Headers(response.headers);
  outgoing.set("Cache-Control", target.pathname === "/lovelace/0" ? "no-store" : outgoing.get("Cache-Control") ?? "private");
  outgoing.set("Content-Security-Policy", "frame-ancestors 'self'; object-src 'none'; base-uri 'self'");
  outgoing.delete("Set-Cookie");

  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.includes("text/html")) {
    let html = await response.text();
    html = html
      .replace(/(<head[^>]*>)/i, `$1<script src="/ma-maison/bridge.js"></script><base href="${LOVELACE_PREFIX}/">`)
      .replaceAll('"/frontend_latest/', `"${LOVELACE_PREFIX}/frontend_latest/`)
      .replaceAll('"/static/', `"${LOVELACE_PREFIX}/static/`)
      .replaceAll('"/local/', `"${LOVELACE_PREFIX}/local/`)
      .replaceAll('"/hacsfiles/', `"${LOVELACE_PREFIX}/hacsfiles/`);
    outgoing.delete("Content-Length");
    return new Response(html, { status: response.status, headers: outgoing });
  }
  return new Response(response.body, { status: response.status, headers: outgoing });
}

async function proxyWebSocket(request: Request, env: Env) {
  const config = upstreamConfig(env);
  if (!config) return new Response("Not found", { status: 404 });
  console.log("[MaMaison] ws-proxy-open");
  const pair = new WebSocketPair();
  const client = pair[0];
  const browser = pair[1];

  const upstreamResponse = await fetch(`${config.baseUrl}/api/websocket`, {
    headers: { Upgrade: "websocket" },
  });
  const upstream = upstreamResponse.webSocket;
  if (!upstream) return new Response("Maison inaccessible", { status: 502 });

  browser.addEventListener("message", async (event) => {
    try {
      const message = JSON.parse(String(event.data)) as { type?: string; access_token?: string };
      console.log("[MaMaison] ws-browser-message", message.type ?? "unknown");
      if (message.type === "auth") {
        if (!message.access_token || !await verifyLovelaceSession(config.token, message.access_token)) {
          browser.close(1008, "Session refusée");
          upstream.close(1008, "Session refusée");
          return;
        }
        upstream.send(JSON.stringify({ type: "auth", access_token: config.token }));
        return;
      }
      if (message.type && !socketTypePermitted(message.type)) {
        browser.send(JSON.stringify({ id: (message as { id?: number }).id, type: "result", success: false, error: { code: "unauthorized", message: "Action non autorisée" } }));
        return;
      }
      upstream.send(event.data);
    } catch {
      browser.close(1003, "Message invalide");
    }
  });
  upstream.addEventListener("message", (event) => {
    try {
      const message = JSON.parse(String(event.data)) as { type?: string };
      console.log("[MaMaison] ws-upstream-message", message.type ?? "unknown");
    } catch {
      console.log("[MaMaison] ws-upstream-message", "binary");
    }
    browser.send(event.data);
  });
  upstream.addEventListener("close", () => browser.close(1000, "Maison déconnectée"));
  browser.addEventListener("close", () => upstream.close(1000, "Client déconnecté"));
  upstream.accept();
  browser.accept();
  return new Response(null, { status: 101, webSocket: client });
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

// Image security config. SVG sources with .svg extension auto-skip the
// optimization endpoint on the client side (served directly, no proxy).
// To route SVGs through the optimizer (with security headers), set
// dangerouslyAllowSVG: true in next.config.js and uncomment below:
// const imageConfig: ImageConfig = { dangerouslyAllowSVG: true };

const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/ma-maison/bridge.js") {
      return new Response(bridgeScript(), {
        headers: {
          "Content-Type": "application/javascript; charset=utf-8",
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }

    if (url.pathname === "/api/websocket" && request.headers.get("Upgrade")?.toLowerCase() === "websocket") {
      return proxyWebSocket(request, env);
    }

    if (["/static/", "/local/", "/hacsfiles/", "/frontend_latest/"].some((path) => url.pathname.startsWith(path))) {
      return proxyHttp(request, env, url.pathname);
    }

    if (url.pathname.startsWith(`${LOVELACE_PREFIX}/`)) {
      const upstreamPath = url.pathname.slice(LOVELACE_PREFIX.length);
      if (upstreamPath === "/api/websocket" && request.headers.get("Upgrade")?.toLowerCase() === "websocket") {
        return proxyWebSocket(request, env);
      }
      return proxyHttp(request, env, upstreamPath);
    }

    if (url.pathname === "/_vinext/image") {
      const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
      return handleImageOptimization(request, {
        fetchAsset: (path) => env.ASSETS.fetch(new Request(new URL(path, request.url))),
        transformImage: async (body, { width, format, quality }) => {
          const result = await env.IMAGES.input(body).transform(width > 0 ? { width } : {}).output({ format, quality });
          return result.response();
        },
      }, allowedWidths);
    }

    return handler.fetch(request, env, ctx);
  },
};

export default worker;
