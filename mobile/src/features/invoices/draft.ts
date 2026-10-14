import { centsToDecimal, decimalToCents, isValidDecimal, taxCents } from '@/shared/lib/money';
import type { CurrencyCode, DecimalString, InvoiceItem, TimeEntry } from '@/shared/types/domain';

export interface ExtraLine {
  key: string;
  description: string;
  /** Unit price as typed; quantity is 1. */
  amount: string;
}

export interface DraftPreview {
  count: number;
  seconds: number;
  subtotal: DecimalString;
  tax: DecimalString;
  total: DecimalString;
}

/**
 * Preview of the invoice the server will create, with the same rules (sum of per-entry rounded amounts,
 * tax half-up once on the subtotal). Integer cents only. The server's numbers are what gets stored.
 */
export function draftPreview(entries: readonly TimeEntry[], selected: ReadonlySet<string>, extras: readonly ExtraLine[], taxRate: string): DraftPreview {
  let cents = 0;
  let seconds = 0;
  let count = 0;
  for (const e of entries) {
    if (!selected.has(e.id) || !e.billableAmount) continue;
    cents += decimalToCents(e.billableAmount);
    seconds += e.durationSeconds ?? 0;
    count += 1;
  }
  for (const line of extras) {
    if (isValidDecimal(line.amount)) cents += decimalToCents(line.amount);
  }
  const rate = taxRate.trim() && isValidDecimal(taxRate) && decimalToCents(taxRate) <= 10_000 ? taxRate : '0';
  const tax = taxCents(cents, rate);
  return { count, seconds, subtotal: centsToDecimal(cents), tax: centsToDecimal(tax), total: centsToDecimal(cents + tax) };
}

/** Currencies present among the entries, the client's own currency first. */
export function entryCurrencies(entries: readonly TimeEntry[], preferred: CurrencyCode | undefined): CurrencyCode[] {
  const set = [...new Set(entries.map((e) => e.currency))].sort();
  return preferred && set.includes(preferred) ? [preferred, ...set.filter((c) => c !== preferred)] : set;
}

export function isExtraLineValid(line: ExtraLine): boolean {
  return line.description.trim().length > 0 && isValidDecimal(line.amount) && decimalToCents(line.amount) > 0;
}

/**
 * A draft's custom lines as editor lines. The editor bills custom lines as quantity 1, so a line created through
 * the API with another quantity becomes one line of the same amount: the invoice total does not change.
 */
export function extraLinesFrom(items: readonly InvoiceItem[], makeKey: () => string): ExtraLine[] {
  return items.filter((i) => i.kind === 'custom').map((i) => ({ key: makeKey(), description: i.description, amount: i.amount }));
}

/** Time entries currently on the draft. */
export function draftEntryIds(items: readonly InvoiceItem[]): Set<string> {
  return new Set(items.flatMap((i) => (i.kind === 'time' && i.timeEntryId ? [i.timeEntryId] : [])));
}
