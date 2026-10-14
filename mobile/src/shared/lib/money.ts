import { localeTagFor, activeLanguage, type AppLanguage } from '@/shared/i18n/locale';
import type { CurrencyCode, DecimalString } from '@/shared/types/domain';

/**
 * Client-side money helpers.
 *
 * Authoritative amounts come from the server (Decimal / NUMERIC). On the client we only:
 *  - parse decimal strings into integer cents without floating-point math,
 *  - show *estimates* for a running timer (labelled "est."),
 *  - format values for display.
 * Rounding rule (same as backend): amount = round_half_up(seconds × rate / 3600, 2 dp).
 */

const DECIMAL_RE = /^(\d{1,12})(?:\.(\d{1,2}))?$/;

export class MoneyParseError extends Error {
  constructor(value: string) {
    super(`Invalid decimal money value: "${value}"`);
    this.name = 'MoneyParseError';
  }
}

/** "85.5" → 8550. Throws for negative, non-numeric or >2 fraction digits. */
export function decimalToCents(value: DecimalString): number {
  const match = DECIMAL_RE.exec(value.trim());
  if (!match) throw new MoneyParseError(value);
  const whole = Number(match[1]);
  const fraction = (match[2] ?? '').padEnd(2, '0');
  return whole * 100 + Number(fraction);
}

/** 8550 → "85.50" */
export function centsToDecimal(cents: number): DecimalString {
  if (!Number.isSafeInteger(cents) || cents < 0) {
    throw new RangeError(`Cents must be a non-negative safe integer, got ${cents}`);
  }
  const whole = Math.floor(cents / 100);
  const fraction = String(cents % 100).padStart(2, '0');
  return `${whole}.${fraction}`;
}

export function isValidDecimal(value: string): boolean {
  return DECIMAL_RE.test(value.trim());
}

/**
 * Amount in cents for `seconds` of work at `rateCents` per hour, rounded half-up.
 * Pure integer arithmetic: floor((2·s·r + 3600) / 7200) == round_half_up(s·r / 3600).
 */
export function amountCentsForDuration(seconds: number, rateCents: number): number {
  if (!Number.isInteger(seconds) || seconds < 0) throw new RangeError('seconds must be a non-negative integer');
  if (!Number.isInteger(rateCents) || rateCents < 0) throw new RangeError('rateCents must be a non-negative integer');
  const numerator = 2 * seconds * rateCents + 3600;
  if (!Number.isSafeInteger(numerator)) throw new RangeError('Amount exceeds safe integer range');
  return Math.floor(numerator / 7200);
}

export function amountForDuration(seconds: number, rate: DecimalString): DecimalString {
  return centsToDecimal(amountCentsForDuration(seconds, decimalToCents(rate)));
}

/** Sum of decimal strings (already rounded per entry), returned as a decimal string. */
export function sumDecimals(values: readonly DecimalString[]): DecimalString {
  return centsToDecimal(values.reduce((acc, v) => acc + decimalToCents(v), 0));
}

const formatterCache = new Map<string, Intl.NumberFormat>();

/** Their narrow symbol is a bare "$", which would be indistinguishable from USD. */
const AMBIGUOUS_NARROW_SYMBOL = new Set<CurrencyCode>(['CAD', 'AUD']);

function getFormatter(currency: CurrencyCode, compact: boolean, language: AppLanguage): Intl.NumberFormat {
  const key = `${language}:${currency}:${compact ? 'c' : 'f'}`;
  let formatter = formatterCache.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat(localeTagFor(language), {
      style: 'currency',
      currency,
      currencyDisplay: AMBIGUOUS_NARROW_SYMBOL.has(currency) ? 'symbol' : 'narrowSymbol',
      minimumFractionDigits: compact ? 0 : 2,
      maximumFractionDigits: compact ? 0 : 2,
    });
    formatterCache.set(key, formatter);
  }
  return formatter;
}

/**
 * Display formatting only. Converting cents → number is safe here because the value is already
 * rounded to 2 dp and is never used for further arithmetic.
 */
export function formatMoney(
  value: DecimalString,
  currency: CurrencyCode,
  options: { compact?: boolean; language?: AppLanguage } = {},
): string {
  const cents = decimalToCents(value);
  const compact = options.compact === true && cents >= 100_000;
  const language = options.language ?? activeLanguage();
  return getFormatter(currency, compact, language).format(compact ? Math.round(cents / 100) : cents / 100);
}

/**
 * Tax preview in cents: round_half_up(subtotal × rate% / 100), the same rule the server applies once on the
 * invoice subtotal. `rate` is a percentage with up to 2 dp ("7.5" → 750 hundredths of a percent).
 * Integer-only: floor((2·s·r + 10000) / 20000) == round_half_up(s·r / 10000).
 */
export function taxCents(subtotalCents: number, rate: DecimalString): number {
  if (!Number.isSafeInteger(subtotalCents) || subtotalCents < 0) throw new RangeError('subtotal must be non-negative cents');
  const hundredths = decimalToCents(rate);
  if (hundredths > 10_000) throw new RangeError('tax rate must be at most 100%');
  const numerator = 2 * subtotalCents * hundredths + 10_000;
  if (!Number.isSafeInteger(numerator)) throw new RangeError('Amount exceeds safe integer range');
  return Math.floor(numerator / 20_000);
}

/** Signed difference in cents between two decimal strings (display-only comparisons such as "vs last period"). */
export function diffCents(current: DecimalString, previous: DecimalString): number {
  return decimalToCents(current) - decimalToCents(previous);
}
