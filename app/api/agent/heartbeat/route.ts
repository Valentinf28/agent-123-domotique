import { eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes } from "../../../../db/schema";
import { authenticatedAgent } from "../../../../lib/agent-auth";

export async function POST(request: Request) {
  const agent = await authenticatedAgent(request);
  if (!agent) return Response.json({ error: "Agent non autorisé" }, { status: 401 });
  try {
    const body = await request.json() as {
      haVersion?: string;
      inventoryCount?: number;
      inventory?: Array<{
        entityId?: string; name?: string; domain?: string;
        state?: string; deviceClass?: string | null;
      }>;
    };
    const inventory = Array.isArray(body.inventory) ? body.inventory.slice(0, 1000).map((item) => ({
      entityId: String(item.entityId ?? "").slice(0, 180),
      name: String(item.name ?? "").slice(0, 180),
      domain: String(item.domain ?? "").slice(0, 40),
      state: String(item.state ?? "").slice(0, 80),
      deviceClass: String(item.deviceClass ?? "").slice(0, 80) || null,
    })).filter((item) => item.entityId.includes(".")) : [];
    const now = new Date().toISOString();
    await getDb().update(agentBoxes).set({
      status: "online",
      haVersion: String(body.haVersion ?? "").slice(0, 40) || null,
      inventoryCount: Math.min(10000, Math.max(0, Math.round(Number(body.inventoryCount) || 0))),
      inventoryJson: JSON.stringify(inventory),
      lastSeenAt: now,
      updatedAt: now,
    }).where(eq(agentBoxes.id, agent.id));
    return Response.json({ accepted: true, nextHeartbeatSeconds: 30 });
  } catch {
    return Response.json({ error: "État invalide" }, { status: 400 });
  }
}
