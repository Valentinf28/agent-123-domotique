import { eq } from "drizzle-orm";
import { getDb } from "../db";
import { agentBoxes } from "../db/schema";

export async function sha256(value: string) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}

export function randomSecret(bytes = 32) {
  const data = crypto.getRandomValues(new Uint8Array(bytes));
  return Array.from(data, byte => byte.toString(16).padStart(2, "0")).join("");
}

export function enrollmentCode() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const data = crypto.getRandomValues(new Uint8Array(8));
  return Array.from(data, byte => alphabet[byte % alphabet.length]).join("");
}

export async function authenticatedAgent(request: Request) {
  const header = request.headers.get("X-Agent-Authorization") ??
    request.headers.get("Authorization") ?? "";
  if (!header.startsWith("Bearer ")) return null;
  const token = header.slice(7).trim();
  if (token.length < 40) return null;
  const tokenHash = await sha256(token);
  const [agent] = await getDb().select().from(agentBoxes)
    .where(eq(agentBoxes.tokenHash, tokenHash)).limit(1);
  return agent ?? null;
}
