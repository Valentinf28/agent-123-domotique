const defaultTimeZone = 'Europe/Paris';

function dateKey(value, timeZone = defaultTimeZone) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

function sampleTimestamp(sample) {
  return sample?.capturedAt
    || sample?.last_updated
    || sample?.last_changed
    || sample?.timestamp
    || null;
}

function sampleWatts(sample) {
  if (Number.isFinite(Number(sample?.solarWatts))) {
    return Math.max(0, Number(sample.solarWatts));
  }
  const numeric = Number(sample?.state);
  if (!Number.isFinite(numeric)) return null;
  const unit = String(sample?.attributes?.unit_of_measurement || 'W').trim().toLowerCase();
  if (unit === 'kw') return Math.max(0, numeric * 1000);
  if (unit === 'mw') return Math.max(0, numeric * 1000000);
  return Math.max(0, numeric);
}

export function dailySolarPeakWatts({
  samples = [],
  currentWatts = 0,
  reportedPeakWatts = 0,
  reportedPeakDate = null,
  now = new Date(),
  timeZone = defaultTimeZone,
} = {}) {
  const today = dateKey(now, timeZone);
  const flattened = Array.isArray(samples) ? samples.flat(1) : [];
  const values = flattened.flatMap((sample) => {
    if (dateKey(sampleTimestamp(sample), timeZone) !== today) return [];
    const watts = sampleWatts(sample);
    return watts === null ? [] : [watts];
  });
  values.push(Math.max(0, Number(currentWatts) || 0));
  if (dateKey(reportedPeakDate, timeZone) === today) {
    values.push(Math.max(0, Number(reportedPeakWatts) || 0));
  }
  return Math.round(Math.max(0, ...values));
}
