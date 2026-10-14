import { z } from 'zod';

import { decimalToCents, isValidDecimal } from '@/shared/lib/money';
import { addDays, localDateKey } from '@/shared/lib/time';
import { PAYMENT_METHODS, type PaymentMethod } from '@/shared/types/domain';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function isIsoDate(value: string): boolean {
  if (!ISO_DATE.test(value)) return false;
  const [y = 0, m = 0, d = 0] = value.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d;
}

/** Mirrors the server rules (docs/api.md §4.10); the server stays authoritative. Messages are i18n keys. */
export function paymentFormSchema(amountDueCents: number, today: Date) {
  const todayKey = localDateKey(today);
  return z.object({
    amount: z
      .string()
      .trim()
      .refine(isValidDecimal, 'paymentForm.errors.amountFormat')
      .refine((v) => !isValidDecimal(v) || decimalToCents(v) > 0, 'paymentForm.errors.amountPositive')
      .refine((v) => !isValidDecimal(v) || decimalToCents(v) <= amountDueCents, 'paymentForm.errors.amountTooHigh'),
    paidOn: z
      .string()
      .trim()
      .refine(isIsoDate, 'paymentForm.errors.dateFormat')
      .refine((v) => !isIsoDate(v) || v <= todayKey, 'paymentForm.errors.dateFuture'),
    method: z.enum(PAYMENT_METHODS as [PaymentMethod, ...PaymentMethod[]]),
    note: z.string().trim().max(500, 'paymentForm.errors.noteTooLong'),
  });
}

export type PaymentFormValues = z.infer<ReturnType<typeof paymentFormSchema>>;

export const DUE_PRESETS = [7, 14, 30] as const;

export const invoiceFormSchema = z.object({
  issueDate: z.string().trim().refine(isIsoDate, 'invoiceForm.errors.dateFormat'),
  dueDays: z.number().int().min(0).max(365),
  taxRate: z
    .string()
    .trim()
    .refine((v) => v === '' || isValidDecimal(v), 'invoiceForm.errors.taxFormat')
    .refine((v) => v === '' || !isValidDecimal(v) || decimalToCents(v) <= 10_000, 'invoiceForm.errors.taxMax'),
  notes: z.string().trim().max(2000, 'invoiceForm.errors.notesTooLong'),
});

export type InvoiceFormValues = z.infer<typeof invoiceFormSchema>;

export function dueDateFor(issueDate: string, dueDays: number): string {
  const [y = 1970, m = 1, d = 1] = issueDate.split('-').map(Number);
  return localDateKey(addDays(new Date(y, m - 1, d), dueDays));
}

/** "7.5" → "7.50", "" → "0.00": the API expects a decimal string with 2 fraction digits at most. */
export function normalizeTaxRate(value: string): string {
  const v = value.trim();
  if (!v) return '0.00';
  const cents = decimalToCents(v);
  return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`;
}

/** Whole days between two ISO dates (due − issue). Calendar arithmetic in UTC, so DST never shifts it. */
export function daysBetween(from: string, to: string): number {
  const utc = (iso: string) => {
    const [y = 1970, m = 1, d = 1] = iso.split('-').map(Number);
    return Date.UTC(y, m - 1, d);
  };
  return Math.round((utc(to) - utc(from)) / 86_400_000);
}

/** Due-date presets, plus the draft's own term when it is not one of them (e.g. 21 days set through the API). */
export function duePresetsWith(days: number): number[] {
  const all = new Set<number>([...DUE_PRESETS, days]);
  return [...all].sort((a, b) => a - b);
}

/** "7.50" → "7.5", "0.00" → "" — how a stored tax rate is shown back in the input. */
export function taxRateInput(stored: string): string {
  if (!isValidDecimal(stored) || decimalToCents(stored) === 0) return '';
  return stored.includes('.') ? stored.replace(/\.?0+$/, '') : stored;
}
