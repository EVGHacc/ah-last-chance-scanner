// Scanmomenten: elke 5 minuten van 17:30 t/m 22:30 Europe/Amsterdam (61 per dag).
const START_MIN = 17 * 60 + 30;
const END_MIN = 22 * 60 + 30;
const STEP_MIN = 5;
const EXPORT_MIN = 22 * 60 + 45; // dagelijkse export, 15 minuten na de laatste scan
const REPORT_MIN = 23 * 60 + 15; // wekelijks rapport, zondag, 30 minuten na de export

// UTC-cron voor de export: 22:45 Amsterdam is 20:45 UTC (zomertijd) of 21:45 UTC (wintertijd).
export const EXPORT_CRON = "45 20,21 * * *";

// UTC-cron voor het weekrapport: zondag 23:15 Amsterdam is 21:15 UTC (zomer) of 22:15 UTC (winter),
// beide nog op zondag in UTC; het andere UTC-uur wordt in de code weggefilterd. Cloudflare telt
// weekdagen anders dan klassieke cron (zondag is 1 of 'sun', niet 0): daarom de naam 'sun'.
export const REPORT_CRON = "15 21,22 * * sun";

const formatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Amsterdam",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Rond af naar beneden op de hele minuut (ms). */
export function floorToMinute(ms) {
  return Math.floor(ms / 60000) * 60000;
}

/** Minuten sinds middernacht in Amsterdam (DST-correct). */
export function amsterdamMinutes(ms) {
  const parts = Object.fromEntries(formatter.formatToParts(new Date(ms)).map((p) => [p.type, p.value]));
  return Number(parts.hour) * 60 + Number(parts.minute);
}

export function isScanSlot(ms) {
  const minutes = amsterdamMinutes(floorToMinute(ms));
  return minutes >= START_MIN && minutes <= END_MIN && (minutes - START_MIN) % STEP_MIN === 0;
}

/** ISO-tijdstempel (UTC) van het bedoelde scanmoment. */
export function scheduledAt(ms) {
  return new Date(floorToMinute(ms)).toISOString();
}

/** True als dit moment 22:45 Europe/Amsterdam is (de cron vuurt in beide UTC-uren). */
export function isExportMoment(ms) {
  return amsterdamMinutes(floorToMinute(ms)) === EXPORT_MIN;
}

const weekdayFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Amsterdam",
  weekday: "short",
});

/** True als dit moment zondag 23:15 Europe/Amsterdam is. */
export function isReportMoment(ms) {
  const floored = floorToMinute(ms);
  return weekdayFormatter.format(new Date(floored)) === "Sun" && amsterdamMinutes(floored) === REPORT_MIN;
}
