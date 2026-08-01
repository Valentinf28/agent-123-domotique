import { and, eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes, agentCommands, energySnapshots, installationDossiers, plannedDevices } from "../../../../db/schema";
import { authenticatedAgent, sha256 } from "../../../../lib/agent-auth";
import { buildDashboardConfig } from "../../../../lib/dashboard-config";
import { energySnapshotFromInventory, fifteenMinuteBucket } from "../../../../lib/energy-coach";

export async function POST(request: Request) {
  const agent = await authenticatedAgent(request);
  if (!agent) return Response.json({ error: "Agent non autorisé" }, { status: 401 });
  try {
    const body = await request.json() as {
      haVersion?: string;
      inventoryCount?: number;
      inventoryMode?: "full" | "delta";
      inventory?: Array<{
        entityId?: string; name?: string; domain?: string;
        state?: string; deviceClass?: string | null;
        attributes?: Record<string, unknown>;
      }>;
      commandResults?: Array<{
        id?: string;
        ok?: boolean;
        error?: string;
      }>;
    };
    const incomingInventory = Array.isArray(body.inventory) ? body.inventory.slice(0, 1000).map((item) => ({
      entityId: String(item.entityId ?? "").slice(0, 180),
      name: String(item.name ?? "").slice(0, 180),
      domain: String(item.domain ?? "").slice(0, 40),
      state: String(item.state ?? "").slice(0, 80),
      deviceClass: String(item.deviceClass ?? "").slice(0, 80) || null,
      attributes: item.attributes && typeof item.attributes === "object"
        ? Object.fromEntries(Object.entries(item.attributes).slice(0, 24))
        : undefined,
    })).filter((item) => item.entityId.includes(".")) : [];
    let inventory = incomingInventory;
    if (body.inventoryMode === "delta") {
      try {
        const previous = JSON.parse(agent.inventoryJson) as typeof incomingInventory;
        const merged = new Map(
          (Array.isArray(previous) ? previous : [])
            .filter((item) => item && typeof item.entityId === "string")
            .map((item) => [item.entityId, item]),
        );
        for (const item of incomingInventory) merged.set(item.entityId, item);
        inventory = Array.from(merged.values()).slice(0, 1000);
      } catch {
        inventory = incomingInventory;
      }
    }
    const nowDate = new Date();
    const now = nowDate.toISOString();
    const energySampleDue = !agent.lastEnergySampleAt ||
      nowDate.getTime() - Date.parse(agent.lastEnergySampleAt) >= 15 * 60 * 1000;
    await getDb().update(agentBoxes).set({
      status: "online",
      haVersion: String(body.haVersion ?? "").slice(0, 40) || null,
      inventoryCount: Math.min(10000, Math.max(0, Math.round(Number(body.inventoryCount) || 0))),
      inventoryJson: JSON.stringify(inventory),
      lastSeenAt: now,
      ...(energySampleDue ? { lastEnergySampleAt: now } : {}),
      updatedAt: now,
    }).where(eq(agentBoxes.id, agent.id));
    const db = getDb();
    if (energySampleDue) {
      const snapshot = energySnapshotFromInventory(inventory);
      await db.insert(energySnapshots).values({
        dossierId: agent.dossierId,
        bucket: fifteenMinuteBucket(nowDate),
        capturedAt: now,
        ...snapshot,
      }).onConflictDoNothing();
    }
    const commandResults = Array.isArray(body.commandResults)
      ? body.commandResults.slice(0, 50)
      : [];
    for (const result of commandResults) {
      const commandId = String(result.id ?? "").slice(0, 80);
      if (!commandId) continue;
      await db.update(agentCommands).set({
        status: result.ok ? "completed" : "failed",
        error: result.ok ? null : String(result.error ?? "Commande refusée").slice(0, 240),
        completedAt: now,
      }).where(and(
        eq(agentCommands.publicId, commandId),
        eq(agentCommands.dossierId, agent.dossierId),
      ));
    }
    const queuedCommands = await db.select().from(agentCommands)
      .where(and(
        eq(agentCommands.dossierId, agent.dossierId),
        eq(agentCommands.status, "queued"),
      )).limit(20);
    if (queuedCommands.length) {
      for (const command of queuedCommands) {
        await db.update(agentCommands).set({
          status: "delivered",
          deliveredAt: now,
        }).where(eq(agentCommands.id, command.id));
      }
    }
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
    const response: Record<string, unknown> = {
      accepted: true,
      nextHeartbeatSeconds: 5,
      commands: queuedCommands.map((command) => ({
        id: command.publicId,
        action: command.action,
        payload: (() => {
          try { return JSON.parse(command.payloadJson) as unknown; } catch { return {}; }
        })(),
      })),
    };
    if (configuredDevices.length) {
      const dashboardConfig = buildDashboardConfig(enabledModules, configuredDevices);
      const dashboardRevision = await sha256(JSON.stringify(dashboardConfig));
      response.dashboard = { revision: dashboardRevision, config: dashboardConfig };
    }
    return Response.json(response);
  } catch {
    return Response.json({ error: "État invalide" }, { status: 400 });
  }
}
