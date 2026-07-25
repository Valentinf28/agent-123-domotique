declare module "cloudflare:workers" {
  export const env: Record<string, unknown> & { DB?: D1Database };
}

interface Fetcher {
  fetch(request: Request): Promise<Response>;
}

type D1Database = any;

declare class WebSocketPair {
  0: WebSocket;
  1: WebSocket;
}

interface WebSocket {
  accept(): void;
}

interface Response {
  webSocket?: WebSocket;
}

interface ResponseInit {
  webSocket?: WebSocket;
}
