export type MoonPhase =
  | "new_moon"
  | "waxing_crescent"
  | "first_quarter"
  | "waxing_gibbous"
  | "full_moon"
  | "waning_gibbous"
  | "last_quarter"
  | "waning_crescent";

const PHASES: MoonPhase[] = [
  "new_moon",
  "waxing_crescent",
  "first_quarter",
  "waxing_gibbous",
  "full_moon",
  "waning_gibbous",
  "last_quarter",
  "waning_crescent",
];

const PHASE_ALIASES: Record<string, MoonPhase> = {
  new: "new_moon",
  new_moon: "new_moon",
  nouvelle_lune: "new_moon",
  waxing_crescent: "waxing_crescent",
  premier_croissant: "waxing_crescent",
  first_quarter: "first_quarter",
  premier_quartier: "first_quarter",
  waxing_gibbous: "waxing_gibbous",
  gibbeuse_croissante: "waxing_gibbous",
  full: "full_moon",
  full_moon: "full_moon",
  pleine_lune: "full_moon",
  waning_gibbous: "waning_gibbous",
  gibbeuse_decroissante: "waning_gibbous",
  last_quarter: "last_quarter",
  dernier_quartier: "last_quarter",
  waning_crescent: "waning_crescent",
  dernier_croissant: "waning_crescent",
};

const normalize = (value = "") => String(value)
  .trim()
  .toLowerCase()
  .normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "")
  .replace(/[\s-]+/g, "_");

export function normalizeMoonPhase(value?: string | null): MoonPhase | null {
  return PHASE_ALIASES[normalize(value ?? "")] ?? null;
}

const moonCycleFraction = (date = new Date()) => {
  const referenceNewMoon = Date.UTC(2000, 0, 6, 18, 14);
  const synodicMonthMs = 29.53058867 * 24 * 60 * 60 * 1000;
  const elapsed = date.getTime() - referenceNewMoon;
  const age = ((elapsed % synodicMonthMs) + synodicMonthMs) % synodicMonthMs;
  return age / synodicMonthMs;
};

export function moonIlluminationForDate(date = new Date()) {
  return (1 - Math.cos(2 * Math.PI * moonCycleFraction(date))) / 2;
}

export function moonPhaseForDate(date = new Date()): MoonPhase {
  const index = Math.round(moonCycleFraction(date) * PHASES.length) % PHASES.length;
  return PHASES[index];
}

export function moonDisplayPhase(sensorValue?: string | null, date = new Date()): MoonPhase {
  if (moonIlluminationForDate(date) >= 0.9) return "full_moon";
  return normalizeMoonPhase(sensorValue) ?? moonPhaseForDate(date);
}

export const MOON_PHASE_GLYPHS: Record<MoonPhase, string> = {
  new_moon: "🌑",
  waxing_crescent: "🌒",
  first_quarter: "🌓",
  waxing_gibbous: "🌔",
  full_moon: "🌕",
  waning_gibbous: "🌖",
  last_quarter: "🌗",
  waning_crescent: "🌘",
};

export const MOON_PHASE_LABELS: Record<MoonPhase, string> = {
  new_moon: "Nouvelle lune",
  waxing_crescent: "Premier croissant",
  first_quarter: "Premier quartier",
  waxing_gibbous: "Lune gibbeuse croissante",
  full_moon: "Pleine lune",
  waning_gibbous: "Lune gibbeuse décroissante",
  last_quarter: "Dernier quartier",
  waning_crescent: "Dernier croissant",
};
