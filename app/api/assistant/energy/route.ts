import { getChatGPTUser } from "../../../chatgpt-auth";
import { sha256 } from "../../../../lib/agent-auth";
import {
  consumeAssistantRequest,
  getEnergyCoachContext,
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

async function authorized() {
  const user = await getChatGPTUser();
  const localDevelopment =
    process.env.NODE_ENV === "development" &&
    process.env.HA_ALLOW_LOCAL_DEVELOPMENT === "true";
  return Boolean(user || localDevelopment);
}

function localReply(message: string, insights: EnergyInsight[]): CoachReply {
  const normalized = message.toLowerCase();
  const matching = insights.find((insight) => {
    if (/nuit|veille/.test(normalized)) return insight.id === "night-base";
    if (/solaire|surplus|autoconsomm/.test(normalized)) return insight.id === "solar-surplus";
    if (/chauffe|ballon|eau chaude/.test(normalized)) return insight.id === "hot-water";
    if (/voiture|tesla|recharge/.test(normalized)) return insight.id === "vehicle-charge";
    if (/batterie/.test(normalized)) return insight.id === "battery-low";
    return false;
  }) ?? insights[0];
  const asksAutomation = /automat|programme|règle|decale|décale/.test(normalized);
  return {
    answer: matching
      ? `${matching.title}. ${matching.description} ${matching.impact}. Je peux vous aider à préparer une automatisation, mais elle ne sera jamais activée sans votre confirmation.`
      : "Je n’ai pas encore assez d’historique pour répondre précisément. Le coach continue d’apprendre les habitudes de la maison.",
    automationProposal: asksAutomation && matching ? {
      name: `Optimisation · ${matching.title}`,
      trigger: "Quand les conditions énergétiques sont favorables",
      action: matching.action,
      rationale: matching.description,
    } : null,
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
): Promise<CoachReply | null> {
  const apiKey = process.env.OPENAI_API_KEY?.trim();
  if (!apiKey) return null;
  if (!await consumeAssistantRequest(context.dossier.id)) {
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
    if (!response.ok) return null;
    const payload = await response.json() as {
      output_text?: string;
      output?: Array<{ content?: Array<{ text?: string }> }>;
    };
    const text = responseText(payload);
    if (!text) return null;
    const parsed = JSON.parse(text) as CoachReply;
    return typeof parsed.answer === "string" ? parsed : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export async function GET(request: Request) {
  if (!await authorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const dossier = new URL(request.url).searchParams.get("dossier");
    const context = await getEnergyCoachContext(dossier);
    return Response.json({
      coach: {
        insights: context.insights,
        historySamples: context.historySamples,
        week: context.week,
        solarForecast: context.solarForecast,
        predictivePlan: context.predictivePlan,
        predictivePlans: context.predictivePlans,
        ready: context.historySamples >= 4,
      },
    }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Analyse temporairement indisponible" }, { status: 502 });
  }
}

export async function POST(request: Request) {
  if (!await authorized()) {
    return Response.json({ error: "Authentification requise" }, { status: 401 });
  }
  try {
    const body = await request.json() as { message?: string; dossierPublicId?: string };
    const message = String(body.message ?? "").trim().slice(0, 600);
    if (message.length < 3) {
      return Response.json({ error: "Question trop courte" }, { status: 400 });
    }
    const context = await getEnergyCoachContext(body.dossierPublicId);
    const reply = await openAiReply(message, context) ??
      localReply(message, context.insights);
    return Response.json({ reply }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Le coach ne peut pas répondre pour le moment" }, { status: 502 });
  }
}
