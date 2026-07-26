import { eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes, installationDossiers, plannedDevices } from "../../../../db/schema";
import { authenticatedAgent, sha256 } from "../../../../lib/agent-auth";
import { buildDashboardConfig } from "../../../../lib/dashboard-config";

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
    const db = getDb();
    const [dossier] = await db.select().from(installationDossiers)
      .where(eq(installationDossiers.id, agent.dossierId)).limit(1);
    const associations = await db.select().from(plannedDevices)
      .where(eq(plannedDevices.dossierId, agent.dossierId));
    let enabledModules: string[] = ["home"];
    try { enabledModules = JSON.parse(dossier?.enabledModules ?? '["home"]'); } catch {}
    const configuredDevices = associations
      .filter((item) => Boolean(item.matchedEntityId))
      .map((item) => ({
        category: item.category,
        entityId: item.matchedEntityId as string,
        name: item.matchedEntityName || `${item.brand} ${item.model}`,
        room: item.room,
      }));
    if (!configuredDevices.length) {
      return Response.json({ accepted: true, nextHeartbeatSeconds: 30 });
    }
    const dashboardConfig = buildDashboardConfig(enabledModules, configuredDevices);
    const dashboardRevision = await sha256(JSON.stringify(dashboardConfig));
    return Response.json({
      accepted: true,
      nextHeartbeatSeconds: 30,
      dashboard: { revision: dashboardRevision, config: dashboardConfig },
    });
  } catch {
    return Response.json({ error: "État invalide" }, { status: 400 });
  }
}
