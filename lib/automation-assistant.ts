export type AssistantDevice = {
  publicId: string;
  name: string;
  room: string;
  category: string;
  available: boolean;
  controllable: boolean;
};

export type SafeAutomationRule = {
  version: 1;
  name: string;
  time: string;
  publicDeviceId: string;
  deviceName: string;
  desiredActive: boolean;
  triggerLabel: string;
  actionLabel: string;
};

export type AutomationAssistantResult =
  | { status: "ready"; proposal: SafeAutomationRule; summary: string }
  | { status: "needs_clarification" | "unsupported" | "refused"; message: string };

type SignedPayload = {
  dossierPublicId: string;
  expiresAt: number;
  nonce: string;
  rule: SafeAutomationRule;
};

const forbiddenRequest = /(?:déverrouill|ouvrir|ouvre|désactiv|couper|supprim|effac|contourn|bypass|forcer).{0,35}(?:porte|portail|garage|serrure|alarme|sécurit|caméra|détecteur|protection|disjoncteur|relais)|(?:code|mot de passe).{0,25}(?:alarme|serrure)|désactiver.{0,25}(?:sécurité|protection)/i;
const stopWords = new Set(["la", "le", "les", "de", "du", "des", "d", "un", "une", "a", "à", "au", "aux", "dans", "tous", "tout", "chaque", "jour", "jours", "ma", "mon"]);

function normalize(value: string) {
  return value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, " ").trim();
}
function words(value: string) {
  return normalize(value).split(/\s+/).filter((word) => word && !stopWords.has(word));
}

function requestedTime(message: string) {
  const normalized = normalize(message);
  if (/\bmidi\b/.test(normalized)) return "12:00";
  if (/\bminuit\b/.test(normalized)) return "00:00";
  const match = normalized.match(/(?:^|\s)([01]?\d|2[0-3])\s*(?:h|:)\s*([0-5]\d)?(?:\s|$)/);
  if (!match) return null;
  return `${match[1].padStart(2, "0")}:${(match[2] ?? "00").padStart(2, "0")}`;
}

function desiredActive(message: string) {
  return !/(?:etein|étein|arrete|arrête|stoppe|coupe|desactive|désactive)/i.test(message);
}

function intendedDevice(message: string, devices: AssistantDevice[]) {
  const normalized = normalize(message);
  const aliasPatterns: Array<[RegExp, RegExp]> = [
    [/ballon|chauffe eau|eau chaude/, /ballon|chauffe eau/],
    [/filtration/, /filtration/],
    [/pac piscine|pompe a chaleur piscine/, /pac piscine|pompe a chaleur/],
    [/lumiere piscine|eclairage piscine/, /eclairage piscine|lumiere piscine/],
    [/terrasse/, /terrasse/],
    [/chauffage/, /chauffage/],
  ];
  const requestedPattern = aliasPatterns.find(([request]) => request.test(normalized))?.[1];
  if (!requestedPattern && /\bpiscine\b/.test(normalized)) return { ambiguousPool: true, device: null };
  const safeDevices = devices.filter((device) =>
    device.available && device.controllable &&
    !["securite", "acces", "vehicule"].includes(normalize(device.category))
  );
  if (requestedPattern) {
    return {
      ambiguousPool: false,
      device: safeDevices.find((device) => requestedPattern.test(normalize(device.name))) ?? null,
    };
  }
  const requestWords = new Set(words(message));
  const ranked = safeDevices.map((device) => ({
    device,
    score: words(`${device.name} ${device.room}`).filter((word) => requestWords.has(word)).length,
  })).filter((candidate) => candidate.score > 0).sort((left, right) => right.score - left.score);
  return { ambiguousPool: false, device: ranked[0]?.device ?? null };
}

export function proposeSafeAutomation(
  message: string,
  devices: AssistantDevice[],
): AutomationAssistantResult {
  const request = message.trim().slice(0, 600);
  if (request.length < 3) {
    return { status: "needs_clarification", message: "Décrivez l’appareil, l’action et l’heure souhaitée." };
  }
  if (forbiddenRequest.test(request)) {
    return {
      status: "refused",
      message: "Cette demande touche à la sécurité ou à un accès sensible. Elle ne peut pas être automatisée par l’assistant.",
    };
  }
  if (/\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|semaine|week end|weekend)\b/i.test(normalize(request))) {
    return {
      status: "unsupported",
      message: "Les calendriers hebdomadaires complexes ne sont pas encore créés automatiquement. Le support peut vous aider à les préparer.",
    };
  }
  const time = requestedTime(request);
  if (!time) {
    return {
      status: "needs_clarification",
      message: "À quelle heure cette action doit-elle avoir lieu chaque jour ?",
    };
  }
  const target = intendedDevice(request, devices);
  if (target.ambiguousPool) {
    return {
      status: "needs_clarification",
      message: "Dans la piscine, souhaitez-vous piloter la filtration, la PAC ou l’éclairage ?",
    };
  }
  if (!target.device) {
    return {
      status: "needs_clarification",
      message: "Je ne trouve pas d’appareil pilotable correspondant dans cette maison. Vérifiez son association ou demandez l’aide du support.",
    };
  }
  const active = desiredActive(request);
  const verb = active ? "Allumer" : "Éteindre";
  const rule: SafeAutomationRule = {
    version: 1,
    name: `${verb} ${target.device.name} à ${time}`,
    time,
    publicDeviceId: target.device.publicId,
    deviceName: target.device.name,
    desiredActive: active,
    triggerLabel: `Tous les jours à ${time}`,
    actionLabel: `${verb} « ${target.device.name} »`,
  };
  return {
    status: "ready",
    proposal: rule,
    summary: `${rule.triggerLabel}, la Green Box va ${rule.actionLabel.toLowerCase()}.`,
  };
}

function encodeBase64Url(bytes: Uint8Array) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeBase64Url(value: string) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function signature(content: string, secret: string) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(content)));
}

function sameBytes(left: Uint8Array, right: Uint8Array) {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) difference |= left[index] ^ right[index];
  return difference === 0;
}

export async function signAutomationProposal(
  rule: SafeAutomationRule,
  dossierPublicId: string,
  secret: string,
  now = Date.now(),
) {
  const payload: SignedPayload = {
    dossierPublicId,
    expiresAt: now + 10 * 60 * 1000,
    nonce: crypto.randomUUID(),
    rule,
  };
  const encoded = encodeBase64Url(new TextEncoder().encode(JSON.stringify(payload)));
  const signed = encodeBase64Url(await signature(encoded, secret));
  return `${encoded}.${signed}`;
}

export async function verifyAutomationProposal(
  token: string,
  secret: string,
  now = Date.now(),
) {
  const [encoded, signed, extra] = token.split(".");
  if (!encoded || !signed || extra) return null;
  try {
    const expected = await signature(encoded, secret);
    if (!sameBytes(expected, decodeBase64Url(signed))) return null;
    const payload = JSON.parse(new TextDecoder().decode(decodeBase64Url(encoded))) as SignedPayload;
    if (payload.expiresAt < now || payload.rule?.version !== 1 || !payload.dossierPublicId) return null;
    return payload;
  } catch {
    return null;
  }
}
