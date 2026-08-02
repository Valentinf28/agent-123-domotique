const pad2 = (value) => String(value).padStart(2, '0');

export function energyDateKey(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

export function energyDayBounds(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const end = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1);
  return { start, end };
}

export function addEnergyDays(value, amount) {
  const date = value instanceof Date ? value : new Date(value);
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + amount);
}

export function isEnergyToday(value, now = new Date()) {
  return energyDateKey(value) === energyDateKey(now);
}

export function formatEnergyDay(value, options = {}) {
  const date = value instanceof Date ? value : new Date(value);
  if (options.relative !== false && isEnergyToday(date)) return "Aujourd’hui";
  return new Intl.DateTimeFormat('fr-FR', {
    weekday: options.weekday === false ? undefined : 'short',
    day: 'numeric',
    month: 'long',
    year: options.year === false ? undefined : 'numeric',
  }).format(date);
}

export function calendarMonthDays(value) {
  const date = value instanceof Date ? value : new Date(value);
  const first = new Date(date.getFullYear(), date.getMonth(), 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  const gridStart = addEnergyDays(first, -mondayOffset);
  return Array.from({ length: 42 }, (_, index) => addEnergyDays(gridStart, index));
}
