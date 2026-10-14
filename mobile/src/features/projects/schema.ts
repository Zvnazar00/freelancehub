import { z } from 'zod';

import { centsToDecimal, decimalToCents, isValidDecimal } from '@/shared/lib/money';
import type { BillingType } from '@/shared/types/domain';

/** Mirrors app/schemas/projects.py and the billing rules of docs/database.md §3.4. Messages are i18n keys. */
const optionalDecimal = (max: number, formatKey: string, maxKey: string) =>
  z
    .string()
    .trim()
    .refine((v) => v === '' || isValidDecimal(v), formatKey)
    .refine((v) => v === '' || !isValidDecimal(v) || decimalToCents(v) <= max * 100, maxKey);

export const PROJECT_COLORS = ['#8B7CFF', '#4C9EFF', '#2BD4A4', '#F5B14C', '#FF6B8B', '#C77DFF'] as const;

export const projectFormSchema = z
  .object({
    clientId: z.string().min(1, 'projectForm.errors.clientRequired'),
    name: z.string().trim().min(1, 'projectForm.errors.nameRequired').max(120, 'projectForm.errors.nameTooLong'),
    billingType: z.enum(['hourly', 'fixed', 'non_billable']),
    hourlyRate: optionalDecimal(99_999_999, 'projectForm.errors.amountFormat', 'projectForm.errors.amountMax'),
    fixedFee: optionalDecimal(999_999_999, 'projectForm.errors.amountFormat', 'projectForm.errors.amountMax'),
    budgetHours: optionalDecimal(999_999, 'projectForm.errors.amountFormat', 'projectForm.errors.amountMax'),
    color: z.string().regex(/^#[0-9A-Fa-f]{6}$/),
  })
  .refine((v) => v.billingType !== 'fixed' || v.fixedFee.trim() !== '', {
    path: ['fixedFee'],
    message: 'projectForm.errors.feeRequired',
  });

export type ProjectFormValues = z.infer<typeof projectFormSchema>;

export const emptyProjectForm = (clientId = ''): ProjectFormValues => ({
  clientId,
  name: '',
  billingType: 'hourly',
  hourlyRate: '',
  fixedFee: '',
  budgetHours: '',
  color: PROJECT_COLORS[0],
});

export interface ProjectPayload {
  clientId: string;
  name: string;
  billingType: BillingType;
  hourlyRate: string | null;
  fixedFee: string | null;
  budgetHours: string | null;
  color: string;
}

const money = (v: string) => (v.trim() ? centsToDecimal(decimalToCents(v.trim())) : null);

/** Drops values that do not apply to the chosen billing type (the server would reject them). */
export function toProjectPayload(v: ProjectFormValues): ProjectPayload {
  return {
    clientId: v.clientId,
    name: v.name.trim(),
    billingType: v.billingType,
    hourlyRate: v.billingType === 'hourly' ? money(v.hourlyRate) : null,
    fixedFee: v.billingType === 'fixed' ? money(v.fixedFee) : null,
    budgetHours: money(v.budgetHours),
    color: v.color.toUpperCase(),
  };
}
