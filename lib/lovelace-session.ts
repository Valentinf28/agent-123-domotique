const encoder = new TextEncoder();

function base64url(bytes: Uint8Array) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function decodeBase64url(value: string) {
  const padded = value.replaceAll("-", "+").replaceAll("_", "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function signingKey(secret: string) {
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

export async function createLovelaceSession(secret: string, subject: string) {
  const payload = base64url(encoder.encode(JSON.stringify({
    sub: subject,
    exp: Math.floor(Date.now() / 1000) + 300,
    scope: "lovelace",
  })));
  const signature = await crypto.subtle.sign("HMAC", await signingKey(secret), encoder.encode(payload));
  return `${payload}.${base64url(new Uint8Array(signature))}`;
}

export async function verifyLovelaceSession(secret: string, token: string) {
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
    const data = JSON.parse(new TextDecoder().decode(decodeBase64url(payload))) as {
      exp?: number; scope?: string;
    };
    return data.scope === "lovelace" && typeof data.exp === "number" && data.exp > Date.now() / 1000;
  } catch {
    return false;
  }
}
