import { router, Stack } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { useInvoices, type InvoiceFilter } from '@/features/invoices/api';
import { InvoiceRow } from '@/features/invoices/components/InvoiceRow';
import { errorMessageKey } from '@/shared/api';
import { Button, Card, EmptyState, ErrorState, LoadingState, Screen, SegmentedControl } from '@/shared/ui';
import { spacing } from '@/shared/theme';

const FILTERS: readonly InvoiceFilter[] = ['all', 'draft', 'sent', 'overdue', 'paid', 'void'];

export default function InvoicesScreen() {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<InvoiceFilter>('all');
  const invoices = useInvoices(filter);
  const [refreshing, setRefreshing] = useState(false);
  const items = invoices.data ?? [];

  const refresh = () => {
    setRefreshing(true);
    void invoices.refetch().finally(() => setRefreshing(false));
  };

  return (
    <Screen edges={['bottom']} testID="invoices-screen" onRefresh={refresh} refreshing={refreshing}>
      <Stack.Screen options={{ title: t('screens.invoices') }} />
      <Button testID="invoice-new" label={t('invoices.new')} icon="add" fullWidth onPress={() => router.push('/invoices/new')} />
      <SegmentedControl
        layout="scroll"
        accessibilityLabel={t('invoices.filterA11y')}
        value={filter}
        onChange={setFilter}
        options={FILTERS.map((f) => ({ value: f, label: t(`invoices.filters.${f}`) }))}
      />
      {invoices.isPending ? (
        <Card>
          <LoadingState rows={4} />
        </Card>
      ) : invoices.isError && !invoices.data ? (
        <ErrorState message={t(errorMessageKey(invoices.error))} onRetry={() => void invoices.refetch()} retrying={invoices.isFetching} />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon="document-text-outline"
            title={t(filter === 'all' ? 'invoices.emptyTitle' : 'invoices.emptyFilteredTitle')}
            message={t(filter === 'all' ? 'invoices.emptyHint' : 'invoices.emptyFilteredHint')}
            actionLabel={filter === 'all' ? t('invoices.new') : t('common.clearFilters')}
            onAction={() => (filter === 'all' ? router.push('/invoices/new') : setFilter('all'))}
          />
        </Card>
      ) : (
        <View style={styles.list}>
          {items.map((invoice) => (
            <InvoiceRow key={invoice.id} invoice={invoice} onPress={() => router.push({ pathname: '/invoices/[id]', params: { id: invoice.id } })} />
          ))}
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm },
});
