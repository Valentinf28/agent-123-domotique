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
import { asksForBatteryEndurance, asksForCoachActionPlan, asksForFiltrationBatteryProtection, asksForHouseStatus, coachQuestionIntent, needsDeterministicFinancialAnswer } from "../../../../lib/coach-question-intent";
import { batterySavingsGuidance, filtrationBatteryProtectionGuidance, financialCoachGuidance, solarAutoconsumptionGuidance, solarCoachGuidance, unavailableEquipmentGuidance, vehicleChargingGuidance } from "../../../../lib/coach-local-advice";
import { coachConversationContinuation } from "../../../../lib/coach-conversation";

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
    .replace(/green box/gi, "box 1.2.3. Home")
    .replace(/home assistant/gi, "box 1.2.3. Home");
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
  let automationProposal: AutomationProposal | null = null;
  if (asksForHouseStatus(message)) {
    const filtration = Math.max(0, context.current.filtrationWatts);
    const hotWater = Math.max(0, context.current.hotWaterWatts);
    const detailed = filtration + hotWater;
    const remainder = Math.max(0, context.current.homeWatts - detailed);
    const breakdown = [
      filtration > 0 ? `filtration piscine : ${watts(filtration)}` : null,
      hotWater > 0 ? `chauffe-eau : ${watts(hotWater)}` : null,
      remainder > 0 ? `autres usages non détaillés : ${watts(remainder)}` : null,
    ].filter(Boolean).join(", ");
    if (/équipements?.{0,20}pilotables?/.test(normalized)) {
      const loads = context.predictivePlans.filter((plan) => plan.loadId !== "configuration" && plan.loadCategory !== "other");
      answer = loads.length
        ? `Les usages énergétiques explicitement configurés pour le pilotage sont : ${loads.map((plan) => plan.loadLabel).join(", ")}. Le Coach ne présente pas comme pilotable un appareil simplement détecté ou mesuré.`
        : "Aucun usage énergétique pilotable n’est encore explicitement configuré pour cette maison.";
    } else if (/sait réellement|données.{0,15}manquent/.test(normalized)) {
      answer = `Le Coach connaît la consommation totale, le solaire, les achats et injections réseau, la batterie de ${context.dossier.batteryCapacityWh / 1000} kWh avec sa réserve à ${context.dossier.batteryReservePercent} %, le contrat électrique, ${context.historySamples} relevés et les équipements mesurés ou configurés. Il ne devine pas le détail des ${watts(remainder)} encore regroupés : des pinces ou associations supplémentaires permettraient de les identifier.`;
    } else if (/anomalie|normale/.test(normalized)) {
      const night = context.insights.find((insight) => insight.id === "night-base");
      answer = `La maison consomme actuellement ${watts(context.current.homeWatts)} au total (${breakdown}). Un instant seul ne permet pas de déclarer une anomalie. ${night ? `${night.description} C’est le premier écart récurrent à examiner.` : "Aucun écart récurrent certain n’est identifié avec l’historique disponible."}`;
    } else if (/premier changement/.test(normalized)) {
      const first = context.insights[0];
      answer = first ? `Premier changement recommandé : ${first.title.toLowerCase()}. ${first.description} ${first.action}.` : "Le Coach doit encore collecter davantage de mesures avant de recommander un changement durable.";
    } else {
      answer = `La maison consomme actuellement ${watts(context.current.homeWatts)} au total : ${breakdown}. Le solaire produit ${watts(context.current.solarWatts)} et la batterie ${context.current.batteryWatts > 0 ? "fournit" : context.current.batteryWatts < 0 ? "absorbe" : "n’échange pas"} ${watts(Math.abs(context.current.batteryWatts))}, avec ${context.current.batteryPercent} % de charge.`;
    }
  } else if (asksForBatteryEndurance(message)) {
    const outlook = context.batteryOutlook;
    if (!outlook.available) {
      answer = "Je connais le niveau actuel de la batterie, mais sa capacité utile n’est pas renseignée pour cette maison. Je ne peux donc pas calculer honnêtement si elle tiendra jusqu’au retour du solaire.";
    } else {
      const capacityKwh = context.dossier.batteryCapacityWh / 1000;
      const usableKwh = outlook.usableWh / 1000;
      const expectedKwh = outlook.expectedWh / 1000;
      const marginKwh = Math.abs(outlook.marginWh) / 1000;
      const solarTime = outlook.nextSolarAt
        ? new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" }).format(new Date(outlook.nextSolarAt))
        : `dans environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(outlook.horizonHours)} h`;
      const basis = outlook.confidence === "measured"
        ? `le profil mesuré sur ${outlook.observedNights} nuits`
        : "la consommation actuellement disponible, faute d’un historique nocturne assez complet";
      const averageNightWatts = outlook.horizonHours > 0 ? outlook.expectedWh / outlook.horizonHours : 0;
      const autonomyHours = averageNightWatts > 0 ? outlook.usableWh / averageNightWatts : 0;
      if (/combien.{0,20}énergie|énergie.{0,20}avant|avant.{0,20}réserve/.test(normalized)) {
        answer = `Avec une batterie de ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(capacityKwh)} kWh, ${context.current.batteryPercent} % de charge et une réserve à ${context.dossier.batteryReservePercent} %, il reste environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(usableKwh)} kWh utilisables avant la réserve.`;
      } else if (/combien.{0,20}heures|heures?.{0,20}autonomie/.test(normalized)) {
        answer = `Selon ${basis}, l’autonomie au rythme nocturne habituel est d’environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(autonomyHours)} h avant la réserve de ${context.dossier.batteryReservePercent} %. Il faut environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(expectedKwh)} kWh jusqu’au retour du solaire, pour ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(usableKwh)} kWh disponibles.`;
      } else answer = outlook.holdsUntilSolar
        ? `Oui, selon ${basis}. La batterie configurée fait ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(capacityKwh)} kWh : à ${context.current.batteryPercent} % avec une réserve à ${context.dossier.batteryReservePercent} %, environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(usableKwh)} kWh restent utilisables. Le besoin estimé jusqu’au retour du solaire vers ${solarTime} est de ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(expectedKwh)} kWh, soit une marge d’environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(marginKwh)} kWh. Les ${watts(context.current.batteryWatts)} actuels ne sont pas prolongés artificiellement sur toute la nuit.`
        : `Non, pas avec la marge configurée si ${basis} se répète. Sur ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(capacityKwh)} kWh, environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(usableKwh)} kWh sont utilisables avant la réserve de ${context.dossier.batteryReservePercent} %, contre ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(expectedKwh)} kWh estimés jusqu’au solaire vers ${solarTime}. Il manquerait environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(marginKwh)} kWh.`;
    }
  } else if (asksForCoachActionPlan(message)) {
    if (context.actionPlan.status === "ready") {
      const actions = context.actionPlan.actions
        .map((action) => `${action.priority}. ${action.title} — ${action.impact}`)
        .join(" ; ");
      answer = `Après ${context.actionPlan.learningDays} jours de mesures, voici les trois priorités : ${actions}. Ouvrez une action pour obtenir le conseil détaillé ou préparer une automatisation applicable.`;
    } else {
      answer = `Le plan personnalisé est encore en préparation : ${context.actionPlan.daysRemaining} jour${context.actionPlan.daysRemaining > 1 ? "s" : ""} d’analyse reste${context.actionPlan.daysRemaining > 1 ? "nt" : ""}. Le Coach continue néanmoins de donner des conseils avec les mesures déjà disponibles.`;
    }
  } else if (intent === "hot-water") {
    const unavailable = unavailableEquipmentGuidance("hot-water", context.equipmentCapabilities);
    if (unavailable) {
      answer = unavailable;
    } else if (context.current.hotWaterWatts > 100) {
      answer = `Le chauffe-eau fonctionne actuellement à ${watts(context.current.hotWaterWatts)}. Avant de le déplacer, le Coach doit vérifier que le cycle quotidien reste suffisant et que le solaire couvre sa puissance.`;
    } else {
      answer = context.solarForecast.available
        ? "Le chauffe-eau est disponible et ne consomme pas actuellement. Le Coach peut rechercher un créneau solaire prudent, mais une règle ne sera préparée qu’après vérification du cycle nécessaire."
        : "Le chauffe-eau est disponible et ne consomme pas actuellement. Sans prévision solaire exploitable, le Coach ne propose pas d’heure future et conserve la programmation existante.";
    }
  } else if (intent === "vehicle") {
    const unavailable = unavailableEquipmentGuidance("vehicle", context.equipmentCapabilities);
    if (unavailable) {
      answer = unavailable;
    } else {
      const exportWatts = Math.max(0, -context.current.gridWatts);
      if (/(?:combien|quelle quantité|quelle quantite).{0,35}(?:kwh|énergie|energie).{0,35}(?:voiture|véhicule|vehicule|recharge)|(?:kwh|énergie|energie).{0,35}(?:envoyés?|consommés?|reçus?).{0,35}(?:voiture|véhicule|vehicule).{0,20}aujourd/.test(normalized)) {
        answer = context.vehicleEnergyToday.available
          ? `Aujourd’hui, environ ${kilowattHours(context.vehicleEnergyToday.energyWh)} ont été envoyés à la voiture d’après ${context.vehicleEnergyToday.sampleCount} relevés de la borne. Le calcul couvre ${context.vehicleEnergyToday.coveredMinutes} minutes réellement mesurées et n’extrapole pas les périodes sans données.`
          : "Je n’ai pas assez de relevés de la borne aujourd’hui pour calculer honnêtement l’énergie envoyée à la voiture. Je peux seulement indiquer sa puissance actuelle.";
      } else if (/charge-t-elle|charge t elle|actuellement/.test(normalized)) {
        answer = context.current.vehicleWatts > 100
          ? `Oui, une recharge à domicile est mesurée à ${watts(context.current.vehicleWatts)}.`
          : "Non, aucune recharge du véhicule n’est mesurée à la maison actuellement.";
      } else if (/intensité|intensite|ampères?|amperes?|rapide/.test(normalized)) {
        answer = "L’intensité sûre ne peut pas être déduite des mesures énergétiques seules. Utilisez la limite configurée par l’installateur pour la borne et l’installation ; le mode Surplus peut ensuite réduire automatiquement l’intensité pour éviter l’achat réseau et préserver la batterie.";
      } else if (/uniquement.{0,20}surplus|surplus.{0,20}uniquement|crée.{0,20}règle|cree.{0,20}regle/.test(normalized)) {
        answer = "Pour une recharge uniquement au surplus, utilisez le mode Surplus de la borne : il ajuste la puissance sur l’injection réellement mesurée. Une heure fixe ne reproduirait pas ce comportement et risquerait de tirer sur le réseau ou la batterie ; je ne prépare donc pas de fausse règle horaire.";
      } else answer = vehicleChargingGuidance({
        now: new Date(),
        vehicleWatts: context.current.vehicleWatts,
        currentExportWatts: exportWatts,
        forecastSlots: context.solarForecast.slots,
        forecastConfidence: context.solarForecast.confidence,
        reservePercent: context.dossier.batteryReservePercent,
        offPeakPeriods: context.tariff.plan === "hp_hc" ? context.tariff.offPeakPeriods : [],
      });
    }
  } else if (/quoi|appareil|équipement|equipement|consomm/.test(normalized) && topConsumers.length) {
    const list = topConsumers
      .map((item) => `${item.name} : ${watts(item.watts)} (${item.sharePercent} %)`)
      .join(", ");
    answer = `En ce moment, les principaux appareils mesurés sont ${list}. Le reste de la maison est regroupé séparément pour éviter tout double comptage.`;
  } else if (/équipements?.{0,20}pilotables?|pilotables?.{0,20}maison/.test(normalized)) {
    const loads = context.predictivePlans.filter((plan) => plan.loadId !== "configuration" && plan.loadCategory !== "other");
    answer = loads.length
      ? `Les usages énergétiques configurés pour le pilotage sont : ${loads.map((plan) => plan.loadLabel).join(", ")}. Le Coach ne présente pas comme pilotable un appareil simplement détecté ou mesuré.`
      : "Aucun usage énergétique pilotable n’est encore configuré pour cette maison.";
  } else if (intent === "battery" && /\bréserve\b|\breserve\b/.test(normalized)) {
    answer = /augmenter|monter|changer/.test(normalized)
      ? `La réserve est à ${context.dossier.batteryReservePercent} %. Il n’est pas nécessaire de l’augmenter sur un seul instant ; faites-le seulement si l’historique montre qu’elle est atteinte trop tôt plusieurs nuits, ou si vous souhaitez conserver davantage d’énergie de secours.`
      : `La réserve de ${context.dossier.batteryReservePercent} % protège la batterie contre une décharge trop profonde et conserve une marge pour les usages essentiels. L’objectif est de reporter les usages flexibles avant d’atteindre ce seuil.`;
  } else if (intent === "battery" && /charge.{0,45}réseau|réseau.{0,45}charge/.test(normalized)) {
    answer = context.batteryOutlook.holdsUntilSolar
      ? `La batterie devrait tenir jusqu’au retour du solaire selon le profil nocturne ; la charger sur le réseau n’est donc pas recommandée cette nuit. Les heures creuses restent un repli, mais leur intérêt doit dépasser les pertes de charge et la valeur du solaire attendu.`
      : "Une charge réseau en heures creuses peut servir de secours si l’autonomie prévue est insuffisante, mais le Coach doit intégrer les pertes de charge et le solaire attendu avant de la recommander.";
  } else if (intent === "battery" && /pourquoi|décharge|decharge/.test(normalized)) {
    answer = `Le solaire est actuellement à ${watts(context.current.solarWatts)} et la maison consomme ${watts(context.current.homeWatts)} au total. La batterie fournit donc ${watts(Math.max(0, context.current.batteryWatts))} pour couvrir la maison ; la filtration, lorsqu’elle fonctionne, est incluse dans ce total et n’est pas ajoutée une seconde fois.`;
  } else if (intent === "battery" && /reporter|décaler|decaler|usages?/.test(normalized)) {
    const loads = context.predictivePlans.filter((plan) => plan.loadId !== "configuration" && plan.loadCategory !== "other");
    answer = loads.length
      ? `Pour préserver la batterie, reportez d’abord les usages suivants : ${loads.map((plan) => plan.loadLabel).join(", ")}. Attendez que leur puissance soit couverte par le solaire. Les autres appareils ne sont pas proposés sans configuration explicite.`
      : "Aucun usage flexible n’est suffisamment configuré pour proposer une coupure automatique. Le Coach ne doit pas deviner quels appareils sont reportables.";
  } else if (intent === "money" && /batterie/.test(normalized)) {
    answer = batterySavingsGuidance(context.tariff.pricesConfigured);
  } else if (intent === "money" && context.historySamples >= 4) {
    const tariffText = tariffGuidance(context.tariff.plan, context.tariff.offPeakPeriods, context.tariff.prices);
    if (/contrat.{0,70}adapt|adapté.{0,70}contrat/.test(normalized)) {
      const imports = Math.max(1, context.gridCost.importedWh);
      const offPeakShare = Math.round(context.gridCost.offPeakImportedWh / imports * 100);
      answer = context.tariff.plan === "hp_hc"
        ? `Sur les ${context.week.observedDays} jours observés, ${offPeakShare} % des achats réseau ont eu lieu en heures creuses et ${100 - offPeakShare} % en heures pleines. Ce recul est encore court pour recommander un changement de contrat, mais il permet déjà de suivre si l’écart de prix compense l’option HP/HC. ${tariffText}`
        : tariffText;
    } else if (/vendre.{0,30}surplus|consommer.{0,30}surplus/.test(normalized)) {
      const purchasePrice = context.tariff.plan === "hp_hc" ? context.tariff.prices.peakMilliEurosPerKwh : context.tariff.prices.baseMilliEurosPerKwh;
      const exportPrice = context.tariff.prices.exportMilliEurosPerKwh;
      answer = purchasePrice != null && exportPrice != null
        ? purchasePrice > exportPrice
          ? `Consommer un kWh solaire utile évite jusqu’à ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(purchasePrice / 1000)} € d’achat, contre ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(exportPrice / 1000)} € reçu s’il est vendu. Il vaut donc mieux autoconsommer les usages réellement nécessaires, sans créer une consommation inutile.`
          : "Le tarif de rachat est au moins égal au prix d’achat évité ; vendre peut donc être aussi intéressant que déplacer un usage. Vérifiez toutefois les taxes et conditions contractuelles."
        : "Le prix d’achat ou le tarif de rachat manque : le Coach ne peut pas comparer honnêtement vente et autoconsommation.";
    } else if (/heures?\s+creuses?.{0,30}(?:déplacer|deplacer)|déplacer.{0,30}heures?\s+creuses?/.test(normalized)) {
      answer = `Priorisez d’abord le surplus solaire réellement mesuré. Utilisez ensuite les heures creuses ${context.tariff.offPeakPeriods.map((period) => `${period.start}–${period.end}`).join(", ")} comme solution de repli si l’appareil doit fonctionner avant le prochain solaire. Un déplacement du solaire vers la nuit réduirait l’autoconsommation.`;
    } else answer = financialCoachGuidance({
        observedDays: context.week.observedDays,
        ...context.gridCost,
        plan: context.tariff.plan,
        tariffGuidance: tariffText,
      });
  } else if (/heures?\s+creuses?|tarif|facture|prix/.test(normalized)) {
    answer = tariffGuidance(context.tariff.plan, context.tariff.offPeakPeriods, context.tariff.prices);
  } else if (/solaire|surplus|autoconsomm/.test(normalized)) {
    const exportWatts = Math.max(0, -context.current.gridWatts);
    const historical = context.insights.find((insight) => insight.id === "historical-solar-export");
    if (historical) {
      const exportedWh = context.gridCost.exportedWh;
      const peakMatch = historical.description.match(/vers\s+(\d{1,2})\s*h/i);
      const loads = context.predictivePlans
        .filter((plan) => plan.loadCategory !== "other" && plan.loadId !== "configuration")
        .map((plan) => ({ label: plan.loadLabel, category: plan.loadCategory }));
      if (/combien|injecté|injecte/.test(normalized) && !/économ|gagner/.test(normalized)) {
        answer = `Sur les ${context.week.observedDays} derniers jours disponibles, ${kilowattHours(exportedWh)} ont été injectés, soit environ ${kilowattHours(exportedWh / Math.max(1, context.week.observedDays))} par jour.`;
      } else if (/quelle heure|à quelle heure|généralement|generalement/.test(normalized)) {
        answer = peakMatch
          ? `Le surplus a été observé le plus souvent autour de ${peakMatch[1]} h sur les ${context.week.observedDays} derniers jours. C’est un constat historique, pas une garantie pour aujourd’hui.`
          : "L’historique disponible ne permet pas encore d’identifier une heure de surplus récurrente.";
      } else if (/meilleur créneau|meilleur creneau/.test(normalized)) {
        const now = new Date();
        const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
        const slots = context.solarForecast.slots.filter((slot) => new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(slot.startsAt)) === today && Date.parse(slot.startsAt) > now.getTime());
        const best = [...slots].sort((left, right) => right.estimatedWh - left.estimatedWh)[0];
        answer = best
          ? `Le meilleur point de la prévision restante aujourd’hui est vers ${new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" }).format(new Date(best.startsAt))}. La confiance est ${context.solarForecast.confidence === "low" ? "faible : attendez le surplus réellement mesuré avant de démarrer un appareil" : "suffisante pour préparer le créneau, avec contrôle du surplus réel"}.`
          : "Aucun créneau solaire futur n’est encore exploitable aujourd’hui.";
      } else {
        answer = solarAutoconsumptionGuidance({
          observedDays: context.week.observedDays,
          exportedWh,
          peakHour: peakMatch ? Number(peakMatch[1]) : null,
          flexibleLoads: loads,
          currentExportWatts: exportWatts,
        });
        const pool = loads.find((load) => /pool|pac|piscine/i.test(`${load.category} ${load.label}`));
        if (pool && /augmenter|éviter|eviter|prioriser|absorber|perdre/.test(normalized)) automationProposal = {
          name: `Arrêt nocturne de ${pool.label}`,
          trigger: "Au coucher du soleil",
          action: `Éteindre ${pool.label}`,
          rationale: "Éviter que cet usage flexible sollicite la batterie après la production solaire.",
        };
      }
    } else {
      const remaining = context.solarForecast.prudentRemainingWh;
      answer = solarCoachGuidance({
        forecastAvailable: context.solarForecast.available,
        exportWatts,
        prudentRemainingKwh: kilowattHours(remaining),
      });
    }
  } else {
    answer = matching
      ? `${matching.title}. ${matching.description} ${matching.impact}. Je peux vous aider à préparer une automatisation, mais elle ne sera jamais activée sans votre confirmation.`
      : "Je n’ai pas encore assez d’historique pour répondre précisément. Le coach continue d’apprendre les habitudes de la maison.";
  }
  return {
    answer,
    // The local fallback gives advice only. It must not manufacture an
    // executable energy trigger that the automation engine cannot parse.
    automationProposal,
    suggestedQuestions: intent === "solar" ? [
      "Quel appareil prioriser sur le surplus ?",
      "Préparer l’arrêt de la PAC piscine au coucher du soleil",
      "Comment préserver la batterie après le solaire ?",
    ] : [
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
        model: process.env.OPENAI_MODEL?.trim() || "gpt-5.6-sol",
        store: false,
        safety_identifier: safetyIdentifier,
        reasoning: { effort: "medium" },
        max_output_tokens: 700,
        instructions: [
          "Tu es le Coach énergie de 1.2.3. Home. Réponds en français, simplement et sans jargon.",
          "Réponds en 90 mots maximum. Commence par le constat utile, puis donne une proposition concrète. Évite les paragraphes répétitifs.",
          "Lis les échanges récents avant de répondre. Une réponse courte comme oui, non, d’accord, fais-le, explique ou pourquoi se rapporte toujours au dernier message du Coach ; ne repars jamais sur un autre sujet.",
          "Si le client répond oui à une proposition d’automatisation déjà affichée, rappelle qu’elle est prête et demande-lui d’utiliser le bouton Préparer cette proposition. Ne prétends jamais l’avoir activée.",
          "Si oui ou non ne permet pas de choisir entre plusieurs options proposées dans la question précédente, demande uniquement laquelle il choisit au lieu de produire un nouveau conseil.",
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
          "N’emploie jamais les expressions Green Box ou Home Assistant. Dis uniquement box 1.2.3. Home si la box doit être nommée.",
          "Si une intervention électrique ou une modification matérielle est nécessaire, recommande un professionnel.",
        ].join("\n"),
        input: [{
          role: "user",
          content: [{
            type: "input_text",
            text: JSON.stringify({
              question: message,
              echangesRecents: conversation,
              maison: {
                nom: context.dossier.name,
                capaciteBatterieKwh: context.dossier.batteryCapacityWh / 1000,
                reserveBatteriePourcent: context.dossier.batteryReservePercent,
              },
              mesuresActuelles: context.current,
              autonomieBatterieCalculee: context.batteryOutlook,
              bilanSeptJours: context.week,
              bilanFinancierMesure: context.gridCost,
              nombreDeReleves: context.historySamples,
              planActionsCoach: context.actionPlan,
              previsionSolaire: context.solarForecast,
              contratTarifaire: context.tariff,
              equipementsDisponibles: context.equipmentCapabilities,
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
    const intent = coachQuestionIntent(message);
    const equipmentMissing = (intent === "vehicle" && !context.equipmentCapabilities.vehicle) ||
      (intent === "hot-water" && !context.equipmentCapabilities.hotWater);
    const filtrationBatteryScenario = asksForFiltrationBatteryProtection(message);
    const filtrationPlan = context.predictivePlans.find((plan) => /filtration/i.test(plan.loadLabel));
    const filtrationReply: CoachReply | null = filtrationBatteryScenario ? {
      answer: filtrationBatteryProtectionGuidance({
        reservePercent: context.dossier.batteryReservePercent,
        filtrationWatts: context.current.filtrationWatts,
        configuredForEnergyControl: Boolean(filtrationPlan),
      }),
      automationProposal: null,
      suggestedQuestions: filtrationPlan
        ? ["Quel surplus faut-il pour relancer la filtration ?", "Comment garantir la durée quotidienne de filtration ?"]
        : ["Comment déclarer la filtration comme usage flexible ?", "Quel surplus faut-il pour relancer la filtration ?"],
    } : null;
    const reply = coachConversationContinuation(message, conversation) ??
      poolHeatPumpCoachReply(message) ??
      filtrationReply ??
      (asksForHouseStatus(message) ? localReply(message, context) : null) ??
      (asksForBatteryEndurance(message) ? localReply(message, context) : null) ??
      (asksForCoachActionPlan(message) ? localReply(message, context) : null) ??
      (equipmentMissing ? localReply(message, context) : null) ??
      (intent === "vehicle" ? localReply(message, context) : null) ??
      (intent === "battery" ? localReply(message, context) : null) ??
      (needsDeterministicFinancialAnswer(message) ? localReply(message, context) : null) ??
      (intent === "solar" ? localReply(message, context) : null) ??
      await openAiReply(message, context, conversation) ??
      localReply(message, context);
    return Response.json({ reply: safeReply(reply) }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Le coach ne peut pas répondre pour le moment" }, { status: 502 });
  }
}
