import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { api, downloadFile, fetchAllPages, queryKeys } from '@/shared/api';
import { toEntry, toInvoice, toInvoiceSummary } from '@/shared/api/mappers';
import type { WireBillableEntries, WireInvoice, WireInvoiceSummary } from '@/shared/api/wire';
import { saveAndShare } from '@/shared/lib/files';
import { uuidV4 } from '@/shared/lib/id';
import type { CurrencyCode, DecimalString, Invoice, PaymentMethod } from '@/shared/types/domain';

export type InvoiceFilter = 'all' | 'draft' | 'sent' | 'overdue' | 'paid' | 'void';

export function useInvoices(filter: InvoiceFilter, clientId?: string) {
  return useQuery({
    queryKey: queryKeys.invoices.list({ status: filter, clientId }),
    queryFn: async ({ signal }) =>
      (
        await fetchAllPages<WireInvoiceSummary>(
          '/invoices',
          { status: filter === 'all' ? undefined : filter, client_id: clientId },
          signal,
        )
      ).map(toInvoiceSummary),
  });
}

export function useInvoice(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.invoices.detail(id ?? ''),
    enabled: Boolean(id),
    queryFn: async ({ signal }) => toInvoice(await api.request<WireInvoice>(`/invoices/${id}`, { signal })),
  });
}

/** Free billable work of a client; with `draftId`, the entries already on that draft are included too. */
export function useBillableEntries(clientId: string | undefined, draftId?: string) {
  return useQuery({
    queryKey: queryKeys.invoices.billable(clientId ?? '', draftId),
    enabled: Boolean(clientId),
    queryFn: async ({ signal }) => {
      const res = await api.request<WireBillableEntries>('/invoices/billable-entries', {
        query: { client_id: clientId, invoice_id: draftId },
        signal,
      });
      return {
        entries: res.items.map(toEntry),
        totals: res.totals.map((t) => ({ ...t, currency: t.currency as CurrencyCode })),
        truncated: res.truncated,
      };
    },
  });
}

/**
 * Everything that reads money or entry locks changes when an invoice changes: lists, the dashboard, analytics,
 * client/project "unbilled" stats and the entries (their invoice link).
 */
function invalidateMoney(qc: QueryClient, invoice?: Invoice) {
  if (invoice) qc.setQueryData(queryKeys.invoices.detail(invoice.id), invoice);
  void qc.invalidateQueries({ queryKey: queryKeys.invoices.all });
  void qc.invalidateQueries({ queryKey: queryKeys.money.all });
  void qc.invalidateQueries({ queryKey: queryKeys.clients.all });
  void qc.invalidateQueries({ queryKey: queryKeys.projects.all });
  void qc.invalidateQueries({ queryKey: queryKeys.entries.all });
}

export interface NewInvoice {
  clientId: string;
  timeEntryIds: string[];
  issueDate: string;
  dueDate: string;
  taxRate: DecimalString;
  notes: string;
  /** Custom lines (quantity 1), e.g. a fixed fee or an expense. */
  items: { description: string; unitPrice: DecimalString }[];
}

export function useCreateInvoice() {
  const qc = useQueryClient();
  return useMutation({
    // One key per submit attempt: a retried request after a dropped connection cannot create a second invoice.
    mutationFn: async (input: NewInvoice & { idempotencyKey: string }) =>
      toInvoice(
        await api.request<WireInvoice>('/invoices', {
          method: 'POST',
          idempotencyKey: input.idempotencyKey,
          body: {
            client_id: input.clientId,
            time_entry_ids: input.timeEntryIds,
            issue_date: input.issueDate,
            due_date: input.dueDate,
            tax_rate: input.taxRate,
            notes: input.notes || null,
            items: input.items.map((i) => ({ description: i.description, quantity: '1', unit_price: i.unitPrice })),
          },
        }),
      ),
    onSuccess: (invoice) => invalidateMoney(qc, invoice),
  });
}

export interface DraftChanges extends Omit<NewInvoice, 'clientId'> {
  /** The version the form was loaded from: a draft changed elsewhere meanwhile gets VERSION_CONFLICT. */
  version: number;
}

/** PATCH a draft: lines are replaced as a whole, removed entries are released by the server. */
export function useUpdateInvoice(invoiceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: DraftChanges) =>
      toInvoice(
        await api.request<WireInvoice>(`/invoices/${invoiceId}`, {
          method: 'PATCH',
          body: {
            version: input.version,
            time_entry_ids: input.timeEntryIds,
            issue_date: input.issueDate,
            due_date: input.dueDate,
            tax_rate: input.taxRate,
            notes: input.notes || null,
            items: input.items.map((i) => ({ description: i.description, quantity: '1', unit_price: i.unitPrice })),
          },
        }),
      ),
    onSuccess: (invoice) => invalidateMoney(qc, invoice),
    onError: () => void qc.invalidateQueries({ queryKey: queryKeys.invoices.detail(invoiceId) }),
  });
}

type Command = { kind: 'send' | 'void'; invoice: Invoice } | { kind: 'delete'; invoice: Invoice };

export function useInvoiceCommand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (command: Command): Promise<Invoice | null> => {
      const { invoice } = command;
      if (command.kind === 'delete') {
        await api.request(`/invoices/${invoice.id}`, { method: 'DELETE' });
        return null;
      }
      return toInvoice(
        await api.request<WireInvoice>(`/invoices/${invoice.id}/${command.kind}`, {
          method: 'POST',
          body: { version: invoice.version }, // a stale screen gets VERSION_CONFLICT instead of acting blindly
        }),
      );
    },
    onSuccess: (invoice, command) => {
      if (!invoice) qc.removeQueries({ queryKey: queryKeys.invoices.detail(command.invoice.id) });
      invalidateMoney(qc, invoice ?? undefined);
    },
    onError: (_error, command) => {
      void qc.invalidateQueries({ queryKey: queryKeys.invoices.detail(command.invoice.id) });
    },
  });
}

export interface NewPayment {
  amount: DecimalString;
  paidOn: string;
  method: PaymentMethod;
  note: string;
}

export function useRecordPayment(invoiceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: NewPayment & { idempotencyKey: string }) =>
      toInvoice(
        await api.request<WireInvoice>(`/invoices/${invoiceId}/payments`, {
          method: 'POST',
          idempotencyKey: input.idempotencyKey,
          body: { amount: input.amount, paid_on: input.paidOn, method: input.method, note: input.note || null },
        }),
      ),
    onSuccess: (invoice) => invalidateMoney(qc, invoice),
  });
}

export function useDeletePayment(invoiceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (paymentId: string) =>
      toInvoice(await api.request<WireInvoice>(`/invoices/${invoiceId}/payments/${paymentId}`, { method: 'DELETE' })),
    onSuccess: (invoice) => invalidateMoney(qc, invoice),
  });
}

export async function shareInvoicePdf(invoice: Pick<Invoice, 'id' | 'number'>) {
  const file = await downloadFile(
    `/invoices/${invoice.id}/pdf`,
    {},
    `${invoice.number ?? `draft-${invoice.id.slice(0, 8)}`}.pdf`,
  );
  return saveAndShare({ ...file, mimeType: 'application/pdf', uti: 'com.adobe.pdf' });
}

export function useSharePdf() {
  return useMutation({ mutationFn: shareInvoicePdf });
}

export const newIdempotencyKey = uuidV4;
