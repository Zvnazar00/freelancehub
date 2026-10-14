import type { BadgeTone } from '@/shared/ui';
import type { InvoiceSummary } from '@/shared/types/domain';

/**
 * What the user sees. The server stores draft/sent/paid/void and derives "overdue" (user time zone) and the
 * payment status; this only picks the most important of those for one badge.
 */
export type InvoiceDisplayStatus = 'draft' | 'open' | 'partial' | 'overdue' | 'paid' | 'void';

export function displayStatus(invoice: Pick<InvoiceSummary, 'status' | 'isOverdue' | 'paymentStatus'>): InvoiceDisplayStatus {
  if (invoice.status === 'draft' || invoice.status === 'void' || invoice.status === 'paid') return invoice.status;
  if (invoice.isOverdue) return 'overdue';
  return invoice.paymentStatus === 'partial' ? 'partial' : 'open';
}

export const statusTone: Record<InvoiceDisplayStatus, BadgeTone> = {
  draft: 'neutral',
  open: 'info',
  partial: 'warning',
  overdue: 'danger',
  paid: 'success',
  void: 'neutral',
};

/** Actions offered for each stored status (the server enforces the same rules). */
export function allowedActions(invoice: Pick<InvoiceSummary, 'status' | 'amountPaid'>) {
  const hasPayments = invoice.amountPaid !== '0.00';
  return {
    send: invoice.status === 'draft',
    edit: invoice.status === 'draft',
    delete: invoice.status === 'draft',
    recordPayment: invoice.status === 'sent',
    void: invoice.status === 'sent' && !hasPayments,
    deletePayment: invoice.status === 'sent' || invoice.status === 'paid',
  };
}
