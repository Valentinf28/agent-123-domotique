import { eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes } from "../../../../db/schema";
import { authenticatedAgent } from "../../../../lib/agent-auth";

export async function POST(request: Request) {
  const agent = await authenticatedAgent(request);
  if (!agent) return Response.json({ error: "Agent non autorisé" }, { status: 401 });
  try {
    const body = await request.json() as { haVersion?: string; inventoryCount?: number };
    const now = new Date().toISOString();
    await getDb().update(agentBoxes).set({
      status: "online",
      haVersion: String(body.haVersion ?? "").slice(0, 40) || null,
      inventoryCount: Math.min(10000, Math.max(0, Math.round(Number(body.inventoryCount) || 0))),
      lastSeenAt: now,
      updatedAt: now,
    }).where(eq(agentBoxes.id, agent.id));
    return Response.json({ accepted: true, nextHeartbeatSeconds: 30 });
  } catch {
    return Response.json({ error: "État invalide" }, { status: 400 });
  }
}
