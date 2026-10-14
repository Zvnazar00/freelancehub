import { z } from 'zod';

import { centsToDecimal, decimalToCents, isValidDecimal } from '@/shared/lib/money';
import { SUPPORTED_CURRENCIES } from '@/shared/types/domain';

/**
 * Mirrors backend constraints in docs/database.md §3.3. Server remains authoritative.
 * Error messages are i18n keys; the form translates them at render time.
 */
export const clientFormSchema = z.object({
  name: z.string().trim().min(1, 'clientForm.errors.nameRequired').max(120, 'clientForm.errors.nameTooLong'),
  company: z.string().trim().max(160, 'clientForm.errors.companyTooLong'),
  email: z
    .string()
    .trim()
    .max(254)
    .refine((v) => v === '' || z.email().safeParse(v).success, 'clientForm.errors.emailInvalid'),
  defaultHourlyRate: z
    .string()
    .trim()
    .refine((v) => v === '' || isValidDecimal(v), 'clientForm.errors.rateFormat')
    .refine((v) => v === '' || !isValidDecimal(v) || decimalToCents(v) <= 999_999, 'clientForm.errors.rateMax'),
  currency: z.enum(SUPPORTED_CURRENCIES),
});

export type ClientFormValues = z.infer<typeof clientFormSchema>;

export const emptyClientForm: ClientFormValues = {
  name: '',
  company: '',
  email: '',
  defaultHourlyRate: '',
  currency: 'USD',
};

export interface ClientPayload {
  name: string;
  company: string | null;
  email: string | null;
  defaultHourlyRate: string | null;
  currency: ClientFormValues['currency'];
}

/** Normalised payload: empty strings become null, rate gets 2 fraction digits. */
export function toClientPayload(values: ClientFormValues): ClientPayload {
  const rate = values.defaultHourlyRate.trim();
  return {
    name: values.name.trim(),
    company: values.company.trim() || null,
    email: values.email.trim().toLowerCase() || null,
    defaultHourlyRate: rate ? centsToDecimal(decimalToCents(rate)) : null,
    currency: values.currency,
  };
}
