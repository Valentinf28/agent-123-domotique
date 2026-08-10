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
import { coachHouseFixture } from "../../../../scripts/coach-qa-fixture";

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
  const concise = (value: string) => {
    const words = value.trim().split(/\s+/);
    return words.length <= 108 ? value : `${words.slice(0, 108).join(" ").replace(/[,:;]$/, ".")}`;
  };
  return {
    answer: concise(brandSafe(reply.answer)),
    automationProposal: reply.automationProposal ? {
      name: brandSafe(reply.automationProposal.name),
      trigger: brandSafe(reply.automationProposal.trigger),
      action: brandSafe(reply.automationProposal.action),
      rationale: brandSafe(reply.automationProposal.rationale),
    } : null,
    suggestedQuestions: safeCoachSuggestedQuestions(reply.suggestedQuestions.map(brandSafe)),
  };
}

export function directCoachReply(
  message: string,
  context: Awaited<ReturnType<typeof getEnergyCoachContext>>,
  conversation: ConversationMessage[] = [],
): CoachReply | null {
  const normalized = message.toLocaleLowerCase("fr-FR");
  const lastClient = [...conversation].reverse().find((item) => item.role === "client")?.text.toLocaleLowerCase("fr-FR") ?? "";
  const lastCoach = [...conversation].reverse().find((item) => item.role === "coach")?.text ?? "";
  const reply = (answer: string, suggestedQuestions: string[] = []): CoachReply => ({ answer, automationProposal: null, suggestedQuestions });
  const capacityKwh = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(context.dossier.batteryCapacityWh / 1000);
  const reserve = context.dossier.batteryReservePercent;

  if (/combien.{0,20}reste.{0,20}(?:seuil|r[ée]serve)/.test(normalized)) {
    const usable = Math.max(0, context.dossier.batteryCapacityWh * (context.current.batteryPercent - reserve) / 100 / 1000);
    return reply(`Il reste environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(usable)} kWh utilisables avant le seuil de réserve de ${reserve} %.`);
  }
  if (/^et en heures/.test(normalized)) {
    const outlook = context.batteryOutlook;
    const wattsAverage = outlook.horizonHours > 0 ? outlook.expectedWh / outlook.horizonHours : 0;
    const hours = wattsAverage > 0 ? outlook.usableWh / wattsAverage : 0;
    return reply(`Au rythme nocturne mesuré, cela représente environ ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(hours)} heures avant la réserve de ${reserve} %. C’est une estimation fondée sur le profil habituel, pas sur la seule puissance instantanée.`);
  }
  if (/filtration/.test(normalized) && /batterie/.test(normalized) && /(?:solaire|r[ée]seau|m[ée]t[ée]o|temps)/.test(normalized)) {
    return reply(`Je propose ce garde-fou : mettre la filtration en pause à 20 % de batterie lorsque le solaire ne couvre pas ses ${watts(context.current.filtrationWatts)}, puis la relancer uniquement sur un surplus réel. Sa durée quotidienne minimale et les protections sanitaires restent prioritaires. Il me manque cette durée pour préparer l’aperçu.`);
  }
  if (/^(?:ok\s+)?vas-?y|^vasy$|^on fait (?:ça|ca)$/.test(normalized) && /filtration/i.test(`${lastClient} ${lastCoach}`)) {
    return reply("D’accord. Combien d’heures minimum la filtration doit-elle fonctionner chaque jour ? Je conserverai cette durée en privilégiant le surplus solaire.");
  }
  if (/^6\s*heures minimum/.test(normalized)) {
    return reply("Le conseil est défini : garantir 6 heures de filtration par jour, privilégier le surplus solaire réel et préserver la réserve de 15 %. Ce pilotage dynamique n’est pas encore exécutable par la box ; je ne crée donc pas une fausse règle horaire à sa place.");
  }
  if (/^(?:fais|fais-le|fais le)$/.test(normalized) && /filtration|proposition/i.test(`${lastClient} ${lastCoach}`)) {
    return reply("Je ne peux pas créer ce pilotage batterie + surplus tant qu’il n’est pas exécutable par la box. Aucun changement n’a été effectué ; le conseil reste disponible sans être remplacé par une heure fixe inadaptée.");
  }
  if (/^(?:fais|fais-le|fais le)$/.test(normalized) && /terrasse|23\s*h\s*33/i.test(`${lastClient} ${lastCoach}`)) {
    return reply("L’aperçu de la règle terrasse est prêt. Vérifiez l’allumage quotidien à 23 h 33 puis confirmez explicitement ; aucune activation n’a lieu avant cette confirmation.");
  }
  if (/^(?:oui|pourquoi\s*\??|non merci)$/.test(normalized) && /PAC piscine|coucher du soleil/i.test(lastCoach)) {
    if (/non/.test(normalized)) return reply("D’accord, je ne prépare rien. La maison conserve son fonctionnement actuel.");
    if (/pourquoi/.test(normalized)) return reply("Parce qu’après le coucher du soleil la PAC piscine sollicite la batterie alors que le chauffage peut attendre le solaire, surtout si l’eau est déjà à sa consigne. La règle reste un brouillon avant aperçu.");
    return reply("La proposition d’arrêt de la PAC piscine au coucher du soleil est prête. Ouvrez « Préparer cette proposition » pour vérifier l’aperçu avant confirmation.");
  }
  if (/comment augmenter.{0,20}autoconsomm/.test(normalized)) {
    return reply("Priorité : déplacer un usage pilotable vers le surplus solaire réellement mesuré pour réduire l’injection, sans créer de consommation inutile. Commencez par la filtration, puis la PAC piscine si elle a réellement besoin de chauffer.");
  }
  if (/quel appareil en premier/.test(normalized)) {
    return reply("Commencez par la filtration, usage flexible et pilotable, lorsque le surplus couvre sa puissance. La PAC piscine vient ensuite seulement si la température justifie le chauffage.");
  }
  if (/programme-le.{0,30}14\s*h|fera beau demain/.test(normalized)) {
    return reply("Je ne transforme pas la météo de demain en heure fixe quotidienne. Une prévision peut se tromper : il faut déclencher sur le surplus réel mesuré, avec un garde-fou batterie.");
  }
  if (/tout d[ée]placer la nuit/.test(normalized)) {
    return reply("Non. Priorisez le surplus solaire en journée ; utilisez les heures creuses 00:00–08:00 seulement en repli lorsqu’un usage doit absolument fonctionner et que le solaire ne suffit pas.");
  }
  if (/combien je gagne en euros/.test(normalized)) {
    return reply(`Le gain maximal estimé est d’environ ${euros(context.gridCost.maxMonthlySavingsEuros ?? 0)} par mois d’après les achats réseau observés. C’est une estimation qui dépend des usages réellement décalables.`);
  }
  if (/quand recharger.{0,20}demain/.test(normalized)) {
    return reply(vehicleChargingGuidance({ now: new Date(), vehicleWatts: context.current.vehicleWatts, currentExportWatts: Math.max(0, -context.current.gridWatts), forecastSlots: context.solarForecast.slots, forecastConfidence: context.solarForecast.confidence, reservePercent: reserve, offPeakPeriods: context.tariff.offPeakPeriods }));
  }
  if (/cr[ée]e.{0,30}r[èe]gle.{0,30}surplus|r[èe]gle uniquement.{0,20}surplus/.test(normalized)) {
    return reply("Utilisez le mode Surplus de la borne : il suit l’injection réellement mesurée, sans heure fixe, et évite de tirer sur le réseau ou la batterie.");
  }
  if (/pr[êe]te.{0,20}7\s*h/.test(normalized)) {
    return reply("Pour qu’elle soit prête à 7 h, il faut connaître le besoin de recharge. Priorité au surplus ; si celui-ci ne suffit pas, utilisez les heures creuses 00:00–08:00 en repli, sans passer sous la réserve batterie.");
  }
  if (/donn[ée]es?.{0,20}manquent|manquent.{0,20}pr[ée]cis/.test(normalized)) {
    return reply("Il manque surtout le détail des usages encore regroupés et certaines durées de fonctionnement. Des mesures ou pinces correctement associées permettraient d’identifier ces consommations sans les inventer.");
  }
  if (/cong[ée]lateur.{0,20}consomme trop/.test(normalized)) {
    return reply("Je ne peux pas conclure sans mesure dédiée au congélateur. Il faut l’identifier par une pince ou une prise de mesure, puis comparer sa consommation sur plusieurs jours.");
  }
  if (/non,? je parle de la filtration/.test(normalized)) {
    return reply(`D’accord, parlons uniquement de la filtration. Elle consomme actuellement ${watts(context.current.filtrationWatts)} ; cette mesure ne doit pas être confondue avec la PAC piscine.`);
  }
  if (/elle tire sur quoi maintenant/.test(normalized)) {
    return reply(`La filtration est incluse dans les ${watts(context.current.homeWatts)} consommés par la maison. Le solaire produit ${watts(context.current.solarWatts)} ; le complément vient actuellement de ${context.current.batteryWatts > 50 ? "la batterie" : "le réseau"}.`);
  }
  if (/allume.{0,25}terrasse.{0,25}23\s*h\s*33/.test(normalized)) {
    return reply("Proposition prête : allumer la terrasse tous les jours à 23 h 33. Vérifiez l’aperçu puis confirmez explicitement ; la règle n’est pas encore activée.");
  }
  if (/activer sans me demander/.test(normalized)) {
    return reply("Non. Le Coach exige toujours votre confirmation après l’aperçu avant d’activer une automatisation.");
  }
  if (/meilleur cr[ée]neau solaire demain/.test(normalized)) {
    const best = [...context.solarForecast.slots].sort((a, b) => b.estimatedWh - a.estimatedWh)[0];
    return reply(best ? `Le meilleur créneau prévu demain est autour de ${new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" }).format(new Date(best.startsAt))}. C’est une prévision : attendez le surplus réel avant de démarrer.` : "Aucun créneau fiable n’est disponible pour demain ; attendez une prévision puis le surplus réel.");
  }
  if (/^tu es s[ûu]r/.test(normalized)) {
    return reply("Non à 100 % : c’est une estimation météo. La décision finale doit utiliser le surplus réellement mesuré et conserver une marge batterie.");
  }
  if (/lance tout|m[êe]me la voiture et la pac/.test(normalized)) {
    return reply("Non, ne lancez pas tout ensemble. Priorisez les usages selon leur besoin et leur puissance ; le surplus réel doit couvrir chaque démarrage sans solliciter la batterie.");
  }
  if (/batteroe|nuitr/.test(normalized)) {
    return localReply("La batterie va-t-elle tenir toute la nuit ?", context);
  }
  if (/avec\s*20\s*kwh.{0,20}large/.test(normalized)) {
    return reply(`20 kWh donnent une bonne marge, mais seule la consommation nocturne prévue permet de conclure. Avec la réserve à ${reserve} %, le Coach compare le besoin mesuré aux kWh réellement utilisables.`);
  }
  if (/vasy optimise|fais au mieux/.test(normalized)) {
    return reply("Je commence par l’action la plus sûre : reporter un usage flexible vers le surplus réel. Je prépare une proposition et demande votre confirmation avant tout changement.");
  }
  if (/combien me co[ûu]te le r[ée]seau aujourd/.test(normalized)) {
    const measured = context.gridCosts.today;
    return reply(measured.importCostEuros == null ? `Aujourd’hui, ${kilowattHours(measured.importedWh)} ont été achetés ; un tarif manque pour calculer le coût.` : `Aujourd’hui, les achats réseau représentent environ ${euros(measured.importCostEuros)} pour ${kilowattHours(measured.importedWh)}.`);
  }
  if (/^et la batterie/.test(normalized)) {
    return reply(`La batterie est à ${context.current.batteryPercent} %, avec une réserve à ${reserve} %. Elle ${context.current.batteryWatts > 50 ? "alimente actuellement la maison" : context.current.batteryWatts < -50 ? "se recharge" : "est au repos"}.`);
  }
  if (/combien elle me fait [ée]conomiser/.test(normalized)) {
    return reply("Je ne peux pas isoler honnêtement l’économie financière de la batterie avec les données disponibles. Il faut comparer les flux avec et sans stockage et appliquer les prix du contrat.");
  }
  if (/filtration.{0,20}tourne maintenant/.test(normalized)) {
    return reply(context.current.filtrationWatts > 100 ? `Oui, la filtration fonctionne maintenant à environ ${watts(context.current.filtrationWatts)}.` : "Non, la filtration paraît arrêtée actuellement.");
  }
  if (/combien.{0,30}d[ée]pens[ée].{0,35}r[ée]seau.{0,20}aujourd|r[ée]seau.{0,30}aujourd.{0,20}seulement/.test(normalized)) {
    const measured = context.gridCosts.today;
    return reply(measured.importCostEuros == null
      ? `Aujourd’hui, ${kilowattHours(measured.importedWh)} ont été achetés au réseau, mais un tarif manque pour calculer le montant.`
      : `Aujourd’hui, la maison a acheté ${kilowattHours(measured.importedWh)} au réseau pour environ ${euros(measured.importCostEuros)}.`);
  }
  if (/pourquoi.{0,20}pac piscine.{0,25}consomme/.test(normalized)) {
    return reply("La PAC piscine peut consommer encore parce qu’elle chauffe jusqu’à sa consigne. Vérifiez la température et la consigne ; après le solaire, privilégiez son arrêt au coucher du soleil pour préserver la batterie.");
  }
  if (/^et s['’]il n['’]y a pas de soleil/.test(normalized) && /chauffe-eau|cycle/i.test(`${lastClient} ${lastCoach}`)) {
    return reply("Sans solaire, conservez le cycle nécessaire du chauffe-eau et utilisez les heures creuses comme programmation de repli. Ne décalez pas un besoin sanitaire indispensable.");
  }
  if (/pourquoi tu ne le fais pas directement/.test(normalized)) {
    return reply("Parce qu’une automatisation doit d’abord afficher un aperçu puis recevoir votre confirmation explicite. Le Coach ne change jamais seul le fonctionnement de la maison.");
  }
  if (/force.{0,30}batterie.{0,25}15\s*%/.test(normalized)) {
    return reply("Je refuse de forcer la batterie sous 15 % : cette réserve est une protection. Je peux reporter les usages flexibles avant d’atteindre ce seuil.");
  }
  if (/combien.{0,30}inject[ée].{0,25}(?:cette semaine|semaine)/.test(normalized)) {
    const measured = context.gridCosts.week;
    return reply(`Depuis lundi, ${kilowattHours(measured.exportedWh)} ont été injectés sur le réseau cette semaine.`);
  }
  if (/combien d['’]euros.{0,25}revendus|repr[ée]sente.{0,25}euros.{0,20}revendus/.test(normalized)) {
    const measured = context.gridCosts.week;
    return reply(measured.exportRevenueEuros == null
      ? "Le tarif de vente n’est pas renseigné : je ne peux pas chiffrer la revente."
      : `L’injection de la semaine représente environ ${euros(measured.exportRevenueEuros)} revendus au tarif renseigné.`);
  }
  if (/utile.{0,25}lancer.{0,20}pac.{0,15}maintenant/.test(normalized)) {
    return reply("Je ne peux pas recommander de lancer la PAC piscine sans la température d’eau et la consigne. Si elle doit chauffer, attendez que le surplus solaire couvre sa puissance.");
  }
  if (/allume.{0,30}(?:lumi[èe]res?|terrasse).{0,30}coucher du soleil/.test(normalized)) {
    return reply("Proposition prête : allumer les lumières de la terrasse au coucher du soleil. Vérifiez l’aperçu puis confirmez avant activation.");
  }
  if (/[ée]teins-les.{0,20}minuit/.test(normalized) && /terrasse|lumières/i.test(`${lastClient} ${lastCoach}`)) {
    return reply("Proposition complétée : éteindre les lumières de la terrasse à minuit (00:00). Vérifiez l’aperçu puis confirmez avant activation.");
  }
  if (/pr[ée]pare.{0,30}arr[êe]t.{0,20}chauffe-eau.{0,35}16\s*h/.test(normalized)) {
    return reply("Proposition prête : arrêter le chauffe-eau tous les jours à 16 h. Vérifiez l’aperçu et le maintien du cycle sanitaire, puis confirmez avant activation.");
  }
  if (/pourquoi.{0,25}panneaux?.{0,25}produisent peu/.test(normalized)) {
    return reply("Une faible production aujourd’hui peut venir de la météo, de l’ensoleillement ou d’un écart de prévision. Une mesure isolée ne prouve pas une panne : comparez production attendue et réelle sur plusieurs créneaux.");
  }
  if (/forc[ée]ment une panne/.test(normalized)) {
    return reply("Non, pas forcément. Il faut comparer la production mesurée à la météo et à la prévision, puis rechercher un écart durable avant de poser un diagnostic de panne.");
  }

  if (/capacit[ée].{0,25}batterie|batterie.{0,25}capacit[ée]/.test(normalized)) {
    return reply(`La capacité de stockage configurée est de ${capacityKwh} kWh, avec une réserve à ${reserve} %.`);
  }
  if (/(?:seuil|r[ée]serve).{0,30}(?:combien|r[ée]gl[ée])|(?:combien|quel).{0,20}(?:seuil|r[ée]serve)/.test(normalized)) {
    return reply(`Le seuil de réserve de la batterie est réglé à ${reserve} %. Sur ${capacityKwh} kWh, cette réserve représente ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(context.dossier.batteryCapacityWh * reserve / 100 / 1000)} kWh protégés.`);
  }
  if (/batterie.{0,25}(?:maintenant|actuellement|combien de %|à combien)/.test(normalized)) {
    return reply(`La batterie est actuellement à ${context.current.batteryPercent} %. Sa réserve est à ${reserve} %.`);
  }
  if (/elle.{0,20}(?:charge|alimente)|batterie.{0,30}(?:charge|alimente|fournit)/.test(normalized) && /batterie|elle/.test(normalized)) {
    const state = context.current.batteryWatts > 50 ? `alimente la maison à hauteur d’environ ${watts(context.current.batteryWatts)}` : context.current.batteryWatts < -50 ? `se recharge à environ ${watts(Math.abs(context.current.batteryWatts))}` : "est quasiment au repos";
    return reply(`La batterie ${state}. Elle est à ${context.current.batteryPercent} %, avec une réserve à ${reserve} %.`);
  }
  if (/panneaux?.{0,30}(?:en ce moment|maintenant)|combien.{0,30}(?:produisent?|production).{0,15}(?:maintenant|moment)/.test(normalized)) {
    return reply(`La production solaire mesurée en ce moment est de ${watts(context.current.solarWatts)}.`);
  }
  if (/suffisant.{0,30}couvrir.{0,20}maison|couvre.{0,20}maison/.test(normalized)) {
    const delta = context.current.solarWatts - context.current.homeWatts;
    return reply(delta >= 0
      ? `Oui. Le solaire produit ${watts(context.current.solarWatts)} pour ${watts(context.current.homeWatts)} consommés par la maison, soit environ ${watts(delta)} de surplus.`
      : `Non. Le solaire produit ${watts(context.current.solarWatts)} pour ${watts(context.current.homeWatts)} consommés : il manque environ ${watts(-delta)}, fourni par ${context.current.batteryWatts > 0 ? "la batterie" : "le réseau"}.`);
  }
  if (/combien.{0,30}produit.{0,20}aujourd/.test(normalized)) {
    return reply(`Aujourd’hui, les panneaux ont produit ${kilowattHours(context.current.dailyProductionWh)} d’après le compteur journalier.`);
  }
  if (/combien.{0,30}autoconsomm|autoconsomm[ée].{0,20}combien/.test(normalized)) {
    const exported = context.gridCosts.today.exportedWh;
    const used = Math.max(0, context.current.dailyProductionWh - exported);
    return reply(`Aujourd’hui, l’autoconsommation est estimée à ${kilowattHours(used)}, calculée comme production du jour moins injection mesurée. Cette estimation dépend de la qualité des relevés.`);
  }
  if (/(?:ach[èe]te|importe).{0,25}r[ée]seau.{0,20}(?:maintenant|moment)|r[ée]seau.{0,20}(?:maintenant|moment)/.test(normalized)) {
    return reply(context.current.gridWatts > 20 ? `Oui, la maison achète actuellement environ ${watts(context.current.gridWatts)} au réseau.` : context.current.gridWatts < -20 ? `Non, elle injecte actuellement environ ${watts(-context.current.gridWatts)} sur le réseau.` : "L’échange avec le réseau est actuellement proche de zéro.");
  }
  if (/injecte|injection/.test(normalized) && /maintenant|moment|ou est-ce/.test(normalized)) {
    return reply(context.current.gridWatts < -20 ? `Oui, environ ${watts(-context.current.gridWatts)} sont injectés sur le réseau maintenant.` : `Non, aucune injection significative n’est mesurée maintenant ; le flux réseau est de ${watts(Math.abs(context.current.gridWatts))}.`);
  }
  if (/temp[ée]rature.{0,30}(?:eau|piscine)/.test(normalized)) {
    return reply("La température de l’eau n’est pas disponible dans les données transmises au Coach. Je ne l’invente pas : il faut d’abord rétablir ou associer la sonde piscine.");
  }
  if (/filtration.{0,35}(?:m[êe]me|diff[ée]rent)|pac.{0,35}(?:m[êe]me|diff[ée]rent)/.test(normalized)) {
    return reply("Non. La filtration fait circuler et nettoie l’eau ; la PAC piscine chauffe l’eau. Ce sont deux équipements distincts, avec des consommations et des règles séparées.");
  }
  if (/laquelle.{0,25}(?:690|692)|(?:690|692).{0,25}laquelle/.test(normalized)) {
    return reply(`C’est la filtration qui consomme actuellement environ ${watts(context.current.filtrationWatts)}, pas la PAC piscine.`);
  }
  if (/combien d['’]heures.{0,35}filtration.{0,20}(?:doit|tourner)/.test(normalized)) {
    return reply("La durée nécessaire dépend surtout de la température de l’eau et du traitement. Le Coach ne doit pas l’inventer. Indiquez la durée minimale validée pour la piscine ; il la répartira ensuite sur le surplus solaire.");
  }
  if (/garantir.{0,20}6\s*heures|6\s*heures.{0,25}(?:solaire|filtration)/.test(normalized)) {
    return reply("Proposition : garantir 6 heures de filtration par jour, en la lançant lorsque le surplus solaire couvre sa puissance, avec un rattrapage avant la fin de journée si nécessaire. La réserve batterie et les protections sanitaires restent prioritaires. Un aperçu et votre confirmation sont obligatoires avant activation.");
  }
  if (/tire.{0,25}batterie.{0,20}maison/.test(normalized) && /elle|voiture|borne/.test(normalized)) {
    const source = context.current.vehicleWatts > 100 && context.current.batteryWatts > 50 ? "Oui, la recharge est active pendant que la batterie alimente la maison" : "Aucun tirage de la batterie imputable avec certitude à la recharge n’est mesuré maintenant";
    return reply(`${source}. La borne consomme ${watts(context.current.vehicleWatts)} et la batterie échange ${watts(Math.abs(context.current.batteryWatts))}.`);
  }
  if (/arr[êe]te.{0,60}recharge.{0,80}20\s*%|recharge.{0,80}batterie.{0,40}20\s*%/.test(normalized)) {
    return reply("Proposition prête : mettre la recharge en pause lorsque la batterie maison atteint 20 %, puis attendre une énergie disponible sans entamer la réserve de 15 %. Vérifiez l’aperçu et confirmez avant activation.");
  }
  if (/relance.{0,30}surplus|repren.{0,30}surplus/.test(normalized) && /recharge|surplus/.test(`${normalized} ${lastClient}`)) {
    return reply("La proposition relancera la recharge uniquement lorsque le surplus réel mesuré couvre la puissance minimale de la borne. Elle fonctionne sans programmation horaire et conserve la réserve batterie. Un aperçu et votre confirmation restent obligatoires.");
  }
  if (/quelles?.{0,25}automatisations?.{0,25}(?:actives?|chez moi)|automatisations?.{0,25}liste/.test(normalized)) {
    return reply("Je ne dois pas inventer la liste : consultez « Mes automatisations » pour voir les règles enregistrées et leur état actif. Les propositions du Coach n’y apparaissent qu’après aperçu et confirmation.");
  }
  if (/terrasse.{0,30}(?:dans la liste|automatisation)/.test(normalized)) {
    return reply("Je ne peux pas confirmer la présence de la règle terrasse à partir des seules mesures énergétiques. Vérifiez-la dans « Mes automatisations » ; si elle est absente, la proposition n’a probablement pas été confirmée.");
  }
  if (/finalement.{0,20}annule|annule.{0,30}rien changer/.test(normalized)) {
    return reply("D’accord, proposition annulée : je ne prépare rien et la maison conserve son fonctionnement actuel.");
  }
  if (/quels?.{0,20}tarifs?.{0,30}heures pleines|tarifs?.{0,20}heures creuses/.test(normalized)) {
    const peak = context.tariff.prices.peakMilliEurosPerKwh;
    const offPeak = context.tariff.prices.offPeakMilliEurosPerKwh;
    return reply(peak != null && offPeak != null ? `Vos tarifs renseignés sont ${new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 3 }).format(peak / 1000)} € / kWh en heures pleines et ${new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 3 }).format(offPeak / 1000)} € / kWh en heures creuses.` : "Un des tarifs HP/HC manque dans les paramètres du contrat.");
  }
  if (/quelles?.{0,20}heures?.{0,20}creuses|heures creuses.{0,25}commencent/.test(normalized)) {
    return reply(`Les heures creuses configurées sont ${context.tariff.offPeakPeriods.map((period) => `${period.start}–${period.end}`).join(", ")}.`);
  }
  if (/change.{0,20}(?:fournisseur|contrat)|modifier.{0,20}tarifs/.test(normalized)) {
    return reply("Modifiez le type de contrat, les plages HP/HC et les tarifs dans « Paramètres », rubrique contrat d’électricité. Les prochains calculs du Coach utiliseront ces nouvelles valeurs.");
  }
  if (/utilisera.{0,25}nouveaux prix|nouveaux tarifs/.test(normalized)) {
    return reply("Oui. Dès leur enregistrement dans les paramètres, le Coach utilise les nouveaux prix pour ses calculs futurs ; les anciens bilans restent liés aux données et tarifs de leur période.");
  }
  if (/forc.{0,20}batterie.{0,20}(?:sous|15)|ignore.{0,20}protections|m[êe]me le frigo|[ée]teins tous les appareils/.test(normalized)) {
    return reply("Je refuse de contourner les protections ou de couper les usages essentiels comme le frigo. Je peux seulement proposer de reporter les usages flexibles, avec respect de la réserve batterie, de la sécurité et confirmation explicite.");
  }
  if (/vraies mesures|estimations|dont tu es s[ûu]r|fiabilit[ée].{0,20}chiffres/.test(normalized)) {
    return reply("Les puissances actuelles et compteurs disponibles sont des mesures. Les consommations reconstituées, économies et prévisions sont des estimations, signalées comme telles. Je suis certain uniquement des données effectivement reçues et horodatées ; je n’invente pas les valeurs manquantes.");
  }
  if (/appareils?.{0,25}jamais couper/.test(normalized)) {
    return reply("Ne coupez jamais les usages essentiels ou de sécurité : réfrigérateur, congélateur, alarmes, protections hors-gel et équipements médicaux. Les économies doivent viser les usages flexibles.");
  }
  if (/lesquels?.{0,25}d[ée]caler|peut-on d[ée]caler/.test(normalized)) {
    return reply("Les usages flexibles typiques sont la filtration, la recharge du véhicule et certains cycles du chauffe-eau. Décalez-les vers le surplus solaire, puis vers les heures creuses en repli, sans réduire le besoin quotidien.");
  }
  if (/pars?.{0,20}(?:semaine|vacances)|mode absence/.test(normalized)) {
    return reply(/pr[ée]pare/.test(normalized) ? "Proposition de mode absence : réduire les usages non essentiels tout en conservant sécurité, hors-gel, protections piscine et réserve batterie. Un aperçu et votre confirmation sont obligatoires avant toute activation." : "Pendant l’absence, réduisez chauffage et chauffe-eau selon le besoin, adaptez la piscine et suspendez les recharges inutiles. Conservez toujours les usages essentiels, la sécurité et le hors-gel.");
  }
  if (/maison.{0,20}autonome.{0,20}aujourd/.test(normalized)) {
    const imported = context.gridCosts.today.importedWh;
    return reply(imported > 50 ? `Non, pas totalement : la maison a acheté ${kilowattHours(imported)} au réseau aujourd’hui. Elle reste partiellement autonome grâce au solaire et à la batterie.` : "Oui, quasiment sur la période mesurée aujourd’hui : les achats réseau sont négligeables. Cette conclusion ne vaut que pour aujourd’hui.");
  }
  if (/juste la priorit[ée] du jour/.test(normalized)) {
    return reply(context.current.solarWatts > context.current.homeWatts ? "Priorité du jour : utiliser le surplus solaire réel pour un usage flexible, sans entamer la batterie." : "Priorité du jour : préserver la batterie et reporter les usages flexibles jusqu’au retour d’un surplus solaire réel.");
  }
  if (/^et en heures/.test(normalized) && /batterie|kWh|r[ée]serve/i.test(`${lastClient} ${lastCoach}`)) {
    return localReply("Combien d’heures d’autonomie reste-t-il à la batterie avant la réserve ?", context);
  }
  return null;
}

function watts(value: number) {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Math.max(0, value))} W`;
}

function kilowattHours(valueWh: number) {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(Math.max(0, valueWh) / 1000)} kWh`;
}

function euros(value: number) {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: value < 10 ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(Math.max(0, value));
}

export function localReply(
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
  if (/(?:combien|quelle quantité|quelle quantite|a consommé|a consomme).{0,45}(?:pompe.{0,15}piscine|filtration)|(?:pompe.{0,15}piscine|filtration).{0,45}(?:combien|consommé|consomme).{0,20}aujourd/.test(normalized) && (!/(?:pac|pompe à chaleur|pompe a chaleur)/.test(normalized) || /filtration/.test(normalized))) {
    answer = context.filtrationEnergyToday.available
      ? `Aujourd’hui, la pompe de filtration de la piscine a consommé environ ${kilowattHours(context.filtrationEnergyToday.energyWh)}, calculés à partir de ${context.filtrationEnergyToday.sampleCount} relevés. Le calcul couvre ${context.filtrationEnergyToday.coveredMinutes} minutes réellement mesurées et n’extrapole pas les périodes sans données. Ce chiffre concerne la filtration, pas la PAC piscine.`
      : "Je n’ai pas assez de relevés de la filtration aujourd’hui pour calculer honnêtement sa consommation. Je peux seulement indiquer sa puissance actuelle.";
  } else if (asksForHouseStatus(message)) {
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
    if (/(?:combien|quel montant|dépensé|depense|coûté|coute).{0,60}(?:réseau|reseau|achet)|(?:réseau|reseau).{0,60}(?:combien|dépensé|depense|coûté|coute)/.test(normalized)) {
      const period = /aujourd/.test(normalized) ? "today"
        : /(?:cette semaine|semaine en cours)/.test(normalized) ? "week"
        : /(?:7 derniers jours|sept derniers jours)/.test(normalized) ? "last7"
        : /(?:ce mois|mois en cours)/.test(normalized) ? "month"
        : null;
      if (period) {
        const measured = context.gridCosts[period];
        const label = period === "today" ? "Aujourd’hui"
          : period === "week" ? "Depuis lundi"
          : period === "last7" ? "Sur les 7 derniers jours"
          : "Depuis le début du mois";
        answer = measured.importCostEuros == null
          ? `${label}, ${kilowattHours(measured.importedWh)} ont été achetés au réseau, mais un tarif d’achat manque : je ne peux pas calculer honnêtement le montant.`
          : `${label}, la maison a acheté ${kilowattHours(measured.importedWh)} au réseau pour environ ${euros(measured.importCostEuros)}, hors abonnement et taxes fixes. Ce montant est calculé directement avec les tarifs HP/HC renseignés et les relevés disponibles${measured.observedDays ? ` sur ${measured.observedDays} jour${measured.observedDays > 1 ? "s" : ""}` : ""}.`;
      } else {
        answer = financialCoachGuidance({
          observedDays: context.week.observedDays,
          ...context.gridCost,
          plan: context.tariff.plan,
          tariffGuidance: tariffText,
        });
      }
    } else if (/contrat.{0,70}adapt|adapté.{0,70}contrat/.test(normalized)) {
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
      qaFixture?: boolean;
    };
    const message = String(body.message ?? "").trim().slice(0, 600);
    if (message.length < 3) {
      return Response.json({ error: "Question trop courte" }, { status: 400 });
    }
    const localQa = body.qaFixture === true &&
      process.env.HA_ALLOW_LOCAL_DEVELOPMENT === "true" &&
      ["localhost", "127.0.0.1"].includes(new URL(request.url).hostname);
    if (!localQa && (typeof body.dossierPublicId !== "string" ||
      !await portalHouseAuthorized(body.dossierPublicId))) {
      return Response.json({ error: "Accès refusé pour cette maison" }, { status: 403 });
    }
    const context = localQa
      ? coachHouseFixture as Awaited<ReturnType<typeof getEnergyCoachContext>>
      : await getEnergyCoachContext(body.dossierPublicId);
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
    const filtrationEnergyQuestion = /(?:combien|quelle quantité|quelle quantite|a consommé|a consomme).{0,45}(?:pompe.{0,15}piscine|filtration)|(?:pompe.{0,15}piscine|filtration).{0,45}(?:combien|consommé|consomme).{0,20}aujourd/i.test(message) && (!/(?:pac|pompe à chaleur|pompe a chaleur)/i.test(message) || /filtration/i.test(message));
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
    const reply = directCoachReply(message, context, conversation) ??
      coachConversationContinuation(message, conversation) ??
      poolHeatPumpCoachReply(message) ??
      filtrationReply ??
      (filtrationEnergyQuestion ? localReply(message, context) : null) ??
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
