import { and, eq, gt, isNull } from "drizzle-orm";
import { getDb } from "../../../../db";
import { agentBoxes, agentEnrollmentCodes } from "../../../../db/schema";
import { randomSecret, sha256 } from "../../../../lib/agent-auth";

export async function POST(request: Request) {
  try {
    const body = await request.json() as { code?: string; label?: string };
    const code = String(body.code ?? "").trim().toUpperCase();
    if (!/^[A-Z2-9]{8}$/.test(code)) {
      return Response.json({ error: "Code invalide" }, { status: 400 });
    }
    const db = getDb();
    const [enrollment] = await db.select().from(agentEnrollmentCodes).where(and(
      eq(agentEnrollmentCodes.codeHash, await sha256(code)),
      isNull(agentEnrollmentCodes.usedAt),
      gt(agentEnrollmentCodes.expiresAt, new Date().toISOString()),
    )).limit(1);
    if (!enrollment) {
      return Response.json({ error: "Code expiré ou déjà utilisé" }, { status: 401 });
    }
    const [existing] = await db.select().from(agentBoxes)
      .where(eq(agentBoxes.dossierId, enrollment.dossierId)).limit(1);
    if (existing) {
      return Response.json({ error: "Une box est déjà associée" }, { status: 409 });
    }
    const token = randomSecret();
    const [agent] = await db.insert(agentBoxes).values({
      publicId: `box_${crypto.randomUUID().replaceAll("-", "")}`,
      dossierId: enrollment.dossierId,
      label: String(body.label ?? "Box domotique").trim().slice(0, 80) || "Box domotique",
      tokenHash: await sha256(token),
    }).returning();
    await db.update(agentEnrollmentCodes).set({ usedAt: new Date().toISOString() })
      .where(eq(agentEnrollmentCodes.id, enrollment.id));
    return Response.json({ agentId: agent.publicId, token }, { status: 201, headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Enrôlement impossible" }, { status: 503 });
  }
}
