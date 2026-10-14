/** Duration & date helpers. All durations are integer seconds. Output follows the active UI language. */
import { activeLanguage, localeTagFor, type AppLanguage } from '@/shared/i18n/locale';

const pad2 = (n: number) => String(n).padStart(2, '0');

/** 3725 → "01:02:05" (hours grow beyond 99 if needed). Language-neutral. */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  return `${pad2(hours)}:${pad2(minutes)}:${pad2(seconds)}`;
}

const durationUnits: Record<AppLanguage, { h: string; m: string; space: string }> = {
  en: { h: 'h', m: 'm', space: '' },
  uk: { h: 'год', m: 'хв', space: ' ' },
  ru: { h: 'ч', m: 'мин', space: ' ' },
};

/** en: 5400 → "1h 30m", 45 → "<1m"; uk: "1 год 30 хв"; ru: "1 ч 30 мин". */
export function formatDuration(totalSeconds: number, language: AppLanguage = activeLanguage()): string {
  const u = durationUnits[language];
  const s = Math.max(0, Math.floor(totalSeconds));
  if (s > 0 && s < 60) return `<1${u.space}${u.m}`;
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const h = `${hours}${u.space}${u.h}`;
  const m = `${minutes}${u.space}${u.m}`;
  if (hours === 0) return m;
  if (minutes === 0) return h;
  return `${h} ${m}`;
}

const numberCache = new Map<string, Intl.NumberFormat>();

function decimalFormatter(language: AppLanguage, digits: number): Intl.NumberFormat {
  const key = `${language}:${digits}`;
  let f = numberCache.get(key);
  if (!f) {
    f = new Intl.NumberFormat(localeTagFor(language), { minimumFractionDigits: digits, maximumFractionDigits: digits });
    numberCache.set(key, f);
  }
  return f;
}

/** 5400 → "1.5" (en) / "1,5" (uk, ru). Display only. */
export function formatHoursDecimal(totalSeconds: number, digits = 1, language: AppLanguage = activeLanguage()): string {
  return decimalFormatter(language, digits).format(Math.max(0, totalSeconds) / 3600);
}

/** 50760 → "14.1h" (en) / "14,1 год" (uk) / "14,1 ч" (ru). */
export function formatHours(totalSeconds: number, digits = 1, language: AppLanguage = activeLanguage()): string {
  const u = durationUnits[language];
  return `${formatHoursDecimal(totalSeconds, digits, language)}${u.space}${u.h}`;
}

/** "120" hours → "120h" / "120 год" / "120 ч". */
export function formatWholeHours(hours: number, language: AppLanguage = activeLanguage()): string {
  const u = durationUnits[language];
  return `${hours}${u.space}${u.h}`;
}

export function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addDays(date: Date, days: number): Date {
  return new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate() + days,
    date.getHours(),
    date.getMinutes(),
    date.getSeconds(),
    date.getMilliseconds(),
  );
}

/**
 * Local start of the week containing `date`.
 * weekStart: 1 = Monday, 7 = Sunday (matches users.week_start in docs/database.md).
 */
export function startOfWeek(date: Date, weekStart: 1 | 7): Date {
  const day = startOfLocalDay(date);
  const jsDay = day.getDay(); // 0 = Sunday … 6 = Saturday
  const startJsDay = weekStart === 7 ? 0 : 1;
  const diff = (jsDay - startJsDay + 7) % 7;
  return addDays(day, -diff);
}

export function isSameLocalDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** Local calendar key, e.g. "2026-10-11". */
export function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

type DateStyle = 'time' | 'shortDay' | 'weekdayLong' | 'dayMonth' | 'weekdayNarrow' | 'weekdayShort' | 'date';

const dateOptions: Record<DateStyle, Intl.DateTimeFormatOptions> = {
  time: { hour: '2-digit', minute: '2-digit', hour12: false },
  shortDay: { weekday: 'short', month: 'short', day: 'numeric' },
  weekdayLong: { weekday: 'long' },
  dayMonth: { day: 'numeric', month: 'long' },
  weekdayNarrow: { weekday: 'narrow' },
  weekdayShort: { weekday: 'short' },
  date: { day: 'numeric', month: 'short', year: 'numeric' },
};

const dateCache = new Map<string, Intl.DateTimeFormat>();

function dateFormatter(style: DateStyle, language: AppLanguage): Intl.DateTimeFormat {
  const key = `${language}:${style}`;
  let f = dateCache.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat(localeTagFor(language), dateOptions[style]);
    dateCache.set(key, f);
  }
  return f;
}

export const formatTimeOfDay = (date: Date, language: AppLanguage = activeLanguage()) => dateFormatter('time', language).format(date);
export const formatShortDay = (date: Date, language: AppLanguage = activeLanguage()) => dateFormatter('shortDay', language).format(date);
/**
 * "Wednesday, October 14" / "середа, 14 жовтня". Composed from two parts because some ICU builds
 * inflect the weekday in a combined pattern (uk: "середу"), which reads wrong as a heading.
 */
export const formatLongDay = (date: Date, language: AppLanguage = activeLanguage()) =>
  `${dateFormatter('weekdayLong', language).format(date)}, ${dateFormatter('dayMonth', language).format(date)}`;
export const formatWeekdayInitial = (date: Date, language: AppLanguage = activeLanguage()) =>
  dateFormatter('weekdayNarrow', language).format(date);
export const formatWeekdayShort = (date: Date, language: AppLanguage = activeLanguage()) =>
  dateFormatter('weekdayShort', language).format(date);

/** "2026-12-15" (calendar date, no timezone shift) → "Dec 15, 2026" / "15 груд. 2026 р.". */
export function formatCalendarDate(isoDate: string, language: AppLanguage = activeLanguage()): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  if (!y || !m || !d) return isoDate;
  return dateFormatter('date', language).format(new Date(y, m - 1, d));
}

/** "Today", "Yesterday" (labels supplied by the caller, already translated) or a short date. */
export function formatRelativeDay(date: Date, now: Date, labels: { today: string; yesterday: string }): string {
  if (isSameLocalDay(date, now)) return labels.today;
  if (isSameLocalDay(date, addDays(now, -1))) return labels.yesterday;
  return formatShortDay(date);
}

export type GreetingKey = 'night' | 'morning' | 'afternoon' | 'evening';

export function greetingFor(date: Date): GreetingKey {
  const h = date.getHours();
  if (h < 5) return 'night';
  if (h < 12) return 'morning';
  if (h < 18) return 'afternoon';
  return 'evening';
}
