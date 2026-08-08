import { sha256 } from "../../../../lib/agent-auth";
import {
  portalApiAuthorized,
  portalAuthorizedHouseIds,
  portalHouseAuthorized,
} from "../../../../lib/portal-api-auth";
import {
  consumeAssistantRequest,
  getEnergyCoachContext,
  refundAssistantRequest,
  type EnergyInsight,
} from "../../../../lib/energy-coach";

type AutomationProposal = {
  name: string;
  trigger: string;
  action: string;
  rationale: string;
};

type CoachReply = {
  answer: string;
  automationProposal: AutomationProposal | null;
  suggestedQuestions: string[];
};

function watts(value: number) {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Math.max(0, value))} W`;
}

function kilowattHours(valueWh: number) {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(Math.max(0, valueWh) / 1000)} kWh`;
}

function localReply(
  message: string,
  context: Awaited<ReturnType<typeof getEnergyCoachContext>>,
): CoachReply {
  const normalized = message.toLowerCase();
  const matching = context.insights.find((insight) => {
    if (/nuit|veille/.test(normalized)) return insight.id === "night-base";
    if (/solaire|surplus|autoconsomm/.test(normalized)) return insight.id === "solar-surplus";
    if (/chauffe|ballon|eau chaude/.test(normalized)) return insight.id === "hot-water";
    if (/voiture|tesla|recharge/.test(normalized)) return insight.id === "vehicle-charge";
    if (/batterie/.test(normalized)) return insight.id === "battery-low";
    return false;
  }) ?? context.insights[0];
  const topConsumers = context.consumptionBreakdown
    .filter((item) => item.id !== "other-home" && item.watts > 0)
    .slice(0, 3);
  let answer: string;
  if (/quoi|appareil|équipement|equipement|consomm/.test(normalized) && topConsumers.length) {
    const list = topConsumers
      .map((item) => `${item.name} : ${watts(item.watts)} (${item.sharePercent} %)`)
      .join(", ");
    answer = `En ce moment, les principaux appareils mesurés sont ${list}. Le reste de la maison est regroupé séparément pour éviter tout double comptage.`;
  } else if (/mois|économ|econom|bilan/.test(normalized) && context.historySamples >= 4) {
    const observedDays = Math.max(1, context.week.observedDays);
    const projectedConsumption = context.week.consumptionWh * 30 / observedDays;
    const period = observedDays >= 7
      ? "Sur les sept derniers jours disponibles"
      : `Sur les ${observedDays} jours disponibles`;
    answer = `${period}, la maison a consommé ${kilowattHours(context.week.consumptionWh)} et produit ${kilowattHours(context.week.productionWh)}. À rythme identique, la consommation mensuelle serait d’environ ${kilowattHours(projectedConsumption)}. C’est une projection, pas une facture.`;
  } else if (/solaire|surplus|autoconsomm/.test(normalized)) {
    const exportWatts = Math.max(0, -context.current.gridWatts);
    const remaining = context.solarForecast.prudentRemainingWh;
    answer = exportWatts > 100
      ? `La maison exporte actuellement environ ${watts(exportWatts)}. La prévision prudente estime encore ${kilowattHours(remaining)} à produire aujourd’hui ; un appareil flexible peut être déplacé sur ce créneau si ses garde-fous le permettent.`
      : `Il n’y a pas de surplus significatif mesuré maintenant. La prévision prudente estime encore ${kilowattHours(remaining)} à produire aujourd’hui ; mieux vaut conserver les garde-fous batterie avant de déplacer un appareil.`;
  } else if (/voiture|tesla|recharge/.test(normalized)) {
    const exportWatts = Math.max(0, -context.current.gridWatts);
    answer = context.current.vehicleWatts > 100
      ? `La voiture charge actuellement à ${watts(context.current.vehicleWatts)}. Le coach recommande de laisser la borne piloter l’intensité et de conserver la réserve batterie configurée.`
      : exportWatts > 100
        ? `La voiture ne charge pas actuellement et environ ${watts(exportWatts)} sont exportés. Vérifiez qu’elle est branchée et disponible ; la borne pourra ensuite ajuster la charge au surplus.`
        : "La voiture ne charge pas actuellement et aucun surplus significatif n’est mesuré. Le démarrage doit attendre un créneau plus favorable ou un mode de charge choisi par le client.";
  } else {
    answer = matching
      ? `${matching.title}. ${matching.description} ${matching.impact}. Je peux vous aider à préparer une automatisation, mais elle ne sera jamais activée sans votre confirmation.`
      : "Je n’ai pas encore assez d’historique pour répondre précisément. Le coach continue d’apprendre les habitudes de la maison.";
  }
  return {
    answer,
    // The local fallback gives advice only. It must not manufacture an
    // executable energy trigger that the automation engine cannot parse.
    automationProposal: null,
    suggestedQuestions: [
      "Que puis-je économiser ce mois-ci ?",
      "Quand recharger la voiture ?",
      "Comment augmenter mon autoconsommation ?",
    ],
  };
}

function executableProposal(proposal: AutomationProposal | null) {
  if (!proposal) return null;
  const trigger = proposal.trigger.trim();
  const action = proposal.action.trim();
  const hasSupportedTrigger = /\b(?:[01]?\d|2[0-3])\s*(?:h|:)\s*[0-5]\d\b/i.test(trigger) ||
    /\b(?:lever|coucher)\s+(?:du\s+)?soleil\b/i.test(trigger);
  const hasConcreteAction = /\b(?:allum|étein|etein|active|désactive|desactive|ouvre|ferme|démarre|demarre|arrête|arrete|coupe)\w*\b/i.test(action);
  return hasSupportedTrigger && hasConcreteAction ? proposal : null;
}

function responseText(payload: {
  output_text?: string;
  output?: Array<{ content?: Array<{ text?: string }> }>;
}) {
  if (payload.output_text) return payload.output_text;
  return payload.output?.flatMap((item) => item.content ?? [])
    .map((item) => item.text)
    .find((text): text is string => Boolean(text));
}

async function openAiReply(
  message: string,
  context: Awaited<ReturnType<typeof getEnergyCoachContext>>,
): Promise<CoachReply | null> {
  const apiKey = process.env.OPENAI_API_KEY?.trim();
  if (!apiKey) return null;
  if (!await consumeAssistantRequest(context.dossier.id, "energy")) {
    return {
      answer: "Le coach a atteint sa limite de protection pour ce mois. Les recommandations automatiques restent disponibles et le service reprendra au prochain cycle.",
      automationProposal: null,
      suggestedQuestions: [],
    };
  }
  const safetyIdentifier = await sha256(`energy-coach:${context.dossier.publicId}`);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 18_000);
  try {
    const response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL?.trim() || "gpt-5.6-luna",
        store: false,
        safety_identifier: safetyIdentifier,
        reasoning: { effort: "low" },
        max_output_tokens: 700,
        instructions: [
          "Tu es le Coach énergie de 1.2.3 Home. Réponds en français, simplement et sans jargon.",
          "Utilise exclusivement les mesures et analyses fournies. Ne fabrique jamais une économie, un tarif, une présence ou une mesure manquante.",
          "Présente les économies comme des estimations lorsqu’elles le sont.",
          "Tu peux proposer une automatisation, mais tu ne peux jamais dire qu’elle est créée, activée ou appliquée.",
          "Ne fournis une automatisation que si le déclencheur contient une heure précise ou le lever/coucher du soleil, et si l’action nomme clairement l’équipement et l’ordre à exécuter.",
          "Pour une optimisation dépendant du surplus, de la batterie, de la météo ou d’une prévision, donne uniquement un conseil et laisse automationProposal à null.",
          "Toute automatisation reste un brouillon jusqu’à confirmation explicite du client dans l’interface.",
          "Ne révèle aucun identifiant technique ni donnée interne.",
          "Si une intervention électrique ou une modification matérielle est nécessaire, recommande un professionnel.",
        ].join("\n"),
        input: [{
          role: "user",
          content: [{
            type: "input_text",
            text: JSON.stringify({
              question: message,
              maison: context.dossier.name,
              mesuresActuelles: context.current,
              bilanSeptJours: context.week,
              nombreDeReleves: context.historySamples,
              previsionSolaire: context.solarForecast,
              contratTarifaire: context.tariff,
              plansPredictifs: context.predictivePlans,
              appareilsQuiConsomment: context.consumptionBreakdown,
              recommandationsCalculees: context.insights,
            }),
          }],
        }],
        text: {
          format: {
            type: "json_schema",
            name: "energy_coach_reply",
            strict: true,
            schema: {
              type: "object",
              additionalProperties: false,
              properties: {
                answer: { type: "string" },
                automationProposal: {
                  anyOf: [
                    {
                      type: "object",
                      additionalProperties: false,
                      properties: {
                        name: { type: "string" },
                        trigger: { type: "string" },
                        action: { type: "string" },
                        rationale: { type: "string" },
                      },
                      required: ["name", "trigger", "action", "rationale"],
                    },
                    { type: "null" },
                  ],
                },
                suggestedQuestions: {
                  type: "array",
                  items: { type: "string" },
                  maxItems: 3,
                },
              },
              required: ["answer", "automationProposal", "suggestedQuestions"],
            },
          },
        },
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      await refundAssistantRequest(context.dossier.id, "energy");
      return null;
    }
    const payload = await response.json() as {
      output_text?: string;
      output?: Array<{ content?: Array<{ text?: string }> }>;
    };
    const text = responseText(payload);
    if (!text) {
      await refundAssistantRequest(context.dossier.id, "energy");
      return null;
    }
    const parsed = JSON.parse(text) as CoachReply;
    if (typeof parsed.answer !== "string") {
      await refundAssistantRequest(context.dossier.id, "energy");
      return null;
    }
    return {
      ...parsed,
      automationProposal: executableProposal(parsed.automationProposal),
    };
  } catch {
    await refundAssistantRequest(context.dossier.id, "energy").catch(() => undefined);
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export async function GET(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const requested = new URL(request.url).searchParams.get("dossier");
    const allowed = await portalAuthorizedHouseIds();
    const dossier = requested || (allowed?.size === 1 ? [...allowed][0] : null);
    if (allowed && (!dossier || !allowed.has(dossier))) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const context = await getEnergyCoachContext(dossier);
    return Response.json({
      coach: {
        insights: context.insights,
        historySamples: context.historySamples,
        week: context.week,
        solarForecast: context.solarForecast,
        predictivePlan: context.predictivePlan,
        predictivePlans: context.predictivePlans,
        consumptionBreakdown: context.consumptionBreakdown,
        ready: context.historySamples >= 4,
      },
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Analyse temporairement indisponible" }, { status: 502 });
  }
}

export async function POST(request: Request) {
  if (!await portalApiAuthorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const body = await request.json() as { message?: string; dossierPublicId?: string };
    const message = String(body.message ?? "").trim().slice(0, 600);
    if (message.length < 3) {
      return Response.json({ error: "Question trop courte" }, { status: 400 });
    }
    if (typeof body.dossierPublicId !== "string" ||
      !await portalHouseAuthorized(body.dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const context = await getEnergyCoachContext(body.dossierPublicId);
    const reply = await openAiReply(message, context) ??
      localReply(message, context);
    return Response.json({ reply }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Le coach ne peut pas répondre pour le moment" }, { status: 502 });
  }
}
