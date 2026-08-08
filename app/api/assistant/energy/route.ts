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
} from "../../../../lib/energy-coach";
import { tariffGuidance } from "../../../../lib/energy-insights";
import { executableCoachProposal, safeCoachSuggestedQuestions } from "../../../../lib/coach-guardrails";
import { poolHeatPumpCoachReply } from "../../../../lib/pool-heat-pump-coach";
import { coachQuestionIntent, needsDeterministicFinancialAnswer } from "../../../../lib/coach-question-intent";
import { batterySavingsGuidance, observedPeriodLabel, solarCoachGuidance } from "../../../../lib/coach-local-advice";

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

type ConversationMessage = { role: "client" | "coach"; text: string };

function brandSafe(value: string) {
  return value
    .replace(/green box/gi, "box 1.2.3 Home")
    .replace(/home assistant/gi, "box 1.2.3 Home");
}

function safeReply(reply: CoachReply): CoachReply {
  return {
    answer: brandSafe(reply.answer),
    automationProposal: reply.automationProposal ? {
      name: brandSafe(reply.automationProposal.name),
      trigger: brandSafe(reply.automationProposal.trigger),
      action: brandSafe(reply.automationProposal.action),
      rationale: brandSafe(reply.automationProposal.rationale),
    } : null,
    suggestedQuestions: safeCoachSuggestedQuestions(reply.suggestedQuestions.map(brandSafe)),
  };
}

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
  const intent = coachQuestionIntent(message);
  const matching = context.insights.find((insight) => {
    if (/nuit|veille/.test(normalized)) return insight.id === "night-base";
    if (/solaire|surplus|autoconsomm/.test(normalized)) return insight.id === "solar-surplus";
    if (/chauffe|ballon|eau chaude/.test(normalized)) return insight.id === "hot-water";
    if (/voiture|tesla|recharge/.test(normalized)) return insight.id === "vehicle-charge";
    if (/batterie/.test(normalized)) return insight.goal === "battery";
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
  } else if (intent === "money" && /batterie/.test(normalized)) {
    answer = batterySavingsGuidance(context.tariff.pricesConfigured);
  } else if (intent === "money" && context.historySamples >= 4) {
    const observedDays = Math.max(1, context.week.observedDays);
    const projectedConsumption = context.week.consumptionWh * 30 / observedDays;
    const period = observedPeriodLabel(observedDays);
    answer = `${period}, la maison a consommé ${kilowattHours(context.week.consumptionWh)} et produit ${kilowattHours(context.week.productionWh)}. À rythme identique, la consommation mensuelle serait d’environ ${kilowattHours(projectedConsumption)}. C’est une projection, pas une facture. ${tariffGuidance(context.tariff.plan, context.tariff.offPeakPeriods)}`;
  } else if (/heures?\s+creuses?|tarif|facture|prix/.test(normalized)) {
    answer = tariffGuidance(context.tariff.plan, context.tariff.offPeakPeriods);
  } else if (/solaire|surplus|autoconsomm/.test(normalized)) {
    const exportWatts = Math.max(0, -context.current.gridWatts);
    const remaining = context.solarForecast.prudentRemainingWh;
    answer = solarCoachGuidance({
      forecastAvailable: context.solarForecast.available,
      exportWatts,
      prudentRemainingKwh: kilowattHours(remaining),
    });
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
  conversation: ConversationMessage[] = [],
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
          "Réponds en 90 mots maximum. Commence par le constat utile, puis donne une proposition concrète. Évite les paragraphes répétitifs.",
          "Utilise exclusivement les mesures et analyses fournies. Ne fabrique jamais une économie, un tarif, une présence ou une mesure manquante.",
          "Les mesuresActuelles décrivent uniquement l’instant présent. Ne les utilise jamais pour chiffrer ou expliquer un événement passé raconté par le client.",
          "Distingue toujours la filtration de la PAC piscine : ce sont deux équipements différents et leurs puissances ne sont pas interchangeables.",
          "Quand le client décrit lui-même un fait passé, présente-le comme son constat, pas comme une mesure vérifiée par le système.",
          "Si la piscine était déjà à sa consigne et que la PAC a continué après le solaire, recommande une coupure au coucher du soleil et propose cette règle si le client demande une solution.",
          "Présente les économies comme des estimations lorsqu’elles le sont.",
          "Tu peux proposer une automatisation, mais tu ne peux jamais dire qu’elle est créée, activée ou appliquée.",
          "Ne fournis une automatisation que si le déclencheur contient une heure précise ou le lever/coucher du soleil, et si l’action nomme clairement l’équipement et l’ordre à exécuter.",
          "Pour une optimisation dépendant du surplus, de la batterie, de la météo ou d’une prévision, donne uniquement un conseil et laisse automationProposal à null.",
          "Toute automatisation reste un brouillon jusqu’à confirmation explicite du client dans l’interface.",
          "Ne révèle aucun identifiant technique ni donnée interne.",
          "N’emploie jamais les expressions Green Box ou Home Assistant. Dis uniquement box 1.2.3 Home si la box doit être nommée.",
          "Si une intervention électrique ou une modification matérielle est nécessaire, recommande un professionnel.",
        ].join("\n"),
        input: [{
          role: "user",
          content: [{
            type: "input_text",
            text: JSON.stringify({
              question: message,
              echangesRecents: conversation,
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
    return safeReply({
      ...parsed,
      automationProposal: executableCoachProposal(parsed.automationProposal),
    });
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
        actionPlan: context.actionPlan,
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
    const body = await request.json() as {
      message?: string;
      dossierPublicId?: string;
      conversation?: ConversationMessage[];
    };
    const message = String(body.message ?? "").trim().slice(0, 600);
    if (message.length < 3) {
      return Response.json({ error: "Question trop courte" }, { status: 400 });
    }
    if (typeof body.dossierPublicId !== "string" ||
      !await portalHouseAuthorized(body.dossierPublicId)) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const context = await getEnergyCoachContext(body.dossierPublicId);
    const conversation = Array.isArray(body.conversation)
      ? body.conversation.slice(-6).flatMap((item) =>
        item && ["client", "coach"].includes(item.role) && typeof item.text === "string"
          ? [{ role: item.role, text: item.text.trim().slice(0, 600) }]
          : []
      ) as ConversationMessage[]
      : [];
    const reply = poolHeatPumpCoachReply(message) ??
      (needsDeterministicFinancialAnswer(message) ? localReply(message, context) : null) ??
      await openAiReply(message, context, conversation) ??
      localReply(message, context);
    return Response.json({ reply: safeReply(reply) }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Le coach ne peut pas répondre pour le moment" }, { status: 502 });
  }
}
