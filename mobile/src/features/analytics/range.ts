import { activeLanguage, localeTagFor, type AppLanguage } from '@/shared/i18n/locale';
import { addDays, localDateKey, startOfWeek } from '@/shared/lib/time';
import type { IsoDate } from '@/shared/types/domain';

/**
 * Calendar periods for the dashboard and analytics. Dates are local calendar dates; the server interprets
 * them in the user's profile time zone (inclusive on both ends), so no instant arithmetic happens here.
 */
export type PeriodKind = 'week' | 'month' | 'quarter' | 'year';
export const PERIOD_KINDS: readonly PeriodKind[] = ['week', 'month', 'quarter', 'year'];

export interface Period {
  kind: PeriodKind;
  from: IsoDate;
  to: IsoDate;
}

export function parseIsoDate(value: IsoDate): Date {
  const [y = 1970, m = 1, d = 1] = value.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function monthStart(date: Date, offsetMonths = 0): Date {
  return new Date(date.getFullYear(), date.getMonth() + offsetMonths, 1);
}

function monthEnd(date: Date, offsetMonths = 0): Date {
  return new Date(date.getFullYear(), date.getMonth() + offsetMonths + 1, 0);
}

export function periodContaining(kind: PeriodKind, date: Date, weekStart: 1 | 7): Period {
  switch (kind) {
    case 'week': {
      const start = startOfWeek(date, weekStart);
      return { kind, from: localDateKey(start), to: localDateKey(addDays(start, 6)) };
    }
    case 'month':
      return { kind, from: localDateKey(monthStart(date)), to: localDateKey(monthEnd(date)) };
    case 'quarter': {
      const first = new Date(date.getFullYear(), Math.floor(date.getMonth() / 3) * 3, 1);
      return { kind, from: localDateKey(first), to: localDateKey(monthEnd(first, 2)) };
    }
    case 'year':
      return { kind, from: `${date.getFullYear()}-01-01`, to: `${date.getFullYear()}-12-31` };
  }
}

/** The period `delta` steps before (negative) or after (positive) `period`. */
export function shiftPeriod(period: Period, delta: number, weekStart: 1 | 7): Period {
  const from = parseIsoDate(period.from);
  switch (period.kind) {
    case 'week':
      return periodContaining('week', addDays(from, delta * 7), weekStart);
    case 'month':
      return periodContaining('month', monthStart(from, delta), weekStart);
    case 'quarter':
      return periodContaining('quarter', monthStart(from, delta * 3), weekStart);
    case 'year':
      return periodContaining('year', new Date(from.getFullYear() + delta, 0, 1), weekStart);
  }
}

export function containsDay(period: Period, day: Date): boolean {
  const key = localDateKey(day);
  return period.from <= key && key <= period.to;
}

/** Periods that start after today have no data yet, so navigation stops at the current one. */
export function canGoForward(period: Period, today: Date): boolean {
  return period.to < localDateKey(today);
}

/** Bar granularity that keeps a chart readable on a phone. */
export function chartInterval(kind: PeriodKind): 'day' | 'week' | 'month' {
  return kind === 'year' ? 'month' : kind === 'quarter' ? 'week' : 'day';
}

const formatters = new Map<string, Intl.DateTimeFormat>();
function fmt(language: AppLanguage, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${language}:${JSON.stringify(options)}`;
  let f = formatters.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat(localeTagFor(language), options);
    formatters.set(key, f);
  }
  return f;
}

/** "12 – 18 Oct 2026", "October 2026", "Q4 2026", "2026". `quarterLabel` comes from i18n (e.g. "Q{{n}} {{year}}"). */
export function periodLabel(
  period: Period,
  quarterLabel: (quarter: number, year: number) => string,
  language: AppLanguage = activeLanguage(),
): string {
  const from = parseIsoDate(period.from);
  const to = parseIsoDate(period.to);
  switch (period.kind) {
    case 'week': {
      const day = fmt(language, { day: 'numeric', month: 'short' });
      return `${day.format(from)} – ${day.format(to)} ${to.getFullYear()}`;
    }
    case 'month':
      return fmt(language, { month: 'long', year: 'numeric' }).format(from);
    case 'quarter':
      return quarterLabel(Math.floor(from.getMonth() / 3) + 1, from.getFullYear());
    case 'year':
      return String(from.getFullYear());
  }
}

/** Short label for a chart bar: weekday initial for week views, day number for months, month for years. */
export function bucketLabel(start: IsoDate, interval: 'day' | 'week' | 'month', kind: PeriodKind, language: AppLanguage = activeLanguage()): string {
  const date = parseIsoDate(start);
  if (interval === 'month') return fmt(language, { month: 'narrow' }).format(date);
  if (interval === 'week') return fmt(language, { day: 'numeric', month: 'numeric' }).format(date);
  return kind === 'week' ? fmt(language, { weekday: 'narrow' }).format(date) : String(date.getDate());
}
