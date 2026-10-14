import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useInvoice } from '@/features/invoices/api';
import { InvoiceEditor } from '@/features/invoices/components/InvoiceEditor';
import { errorMessageKey, isApiError } from '@/shared/api';
import { EmptyState, ErrorState, LoadingState, Screen } from '@/shared/ui';

/** Edit a draft invoice: lines, dates, tax and notes. Issued invoices are documents and cannot be edited. */
export default function EditInvoiceScreen() {
  const { t } = useTranslation();
  const { id } = useLocalSearchParams<{ id: string }>();
  const query = useInvoice(id);
  // Bumped after a version conflict: the form remounts from the freshly loaded draft.
  const [generation, setGeneration] = useState(0);
  const invoice = query.data;

  if (!invoice) {
    const notFound = isApiError(query.error) && query.error.status === 404;
    return (
      <Screen edges={['bottom']}>
        {query.isPending ? (
          <LoadingState rows={5} />
        ) : notFound ? (
          <EmptyState icon="document-outline" title={t('invoices.notFound')} message={t('invoices.notFoundHint')} actionLabel={t('invoices.back')} onAction={() => router.replace('/invoices')} />
        ) : (
          <ErrorState message={t(errorMessageKey(query.error))} onRetry={() => void query.refetch()} retrying={query.isFetching} />
        )}
      </Screen>
    );
  }

  if (invoice.status !== 'draft') {
    return (
      <Screen edges={['bottom']} testID="invoice-edit-locked">
        <EmptyState icon="lock-closed-outline" title={t('invoiceForm.notEditable')} message={t('invoiceForm.notEditableHint')} actionLabel={t('invoices.back')} onAction={() => router.back()} />
      </Screen>
    );
  }

  return (
    <InvoiceEditor
      key={`${invoice.id}:${generation}`}
      client={{ id: invoice.client.id, name: invoice.client.name, currency: invoice.currency }}
      mode={{
        kind: 'edit',
        invoice,
        onReload: () => void query.refetch().then(() => setGeneration((g) => g + 1)),
      }}
    />
  );
}
