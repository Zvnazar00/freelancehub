import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { useClients } from '@/features/clients/api';
import { InvoiceEditor } from '@/features/invoices/components/InvoiceEditor';
import { formatAmounts } from '@/features/projects/components/ProjectCard';
import { errorMessageKey } from '@/shared/api';
import type { Client } from '@/shared/types/domain';
import { AppText, Avatar, Card, EmptyState, ErrorState, LoadingState, Screen, SectionHeader } from '@/shared/ui';
import { spacing } from '@/shared/theme';

export default function NewInvoiceScreen() {
  const params = useLocalSearchParams<{ clientId?: string }>();
  const clients = useClients();
  const [clientId, setClientId] = useState<string | undefined>(params.clientId);
  const client = (clients.data ?? []).find((c) => c.id === clientId);

  if (!clientId || (!client && !clients.isPending)) {
    return <ClientStep clients={clients.data} loading={clients.isPending} error={clients.error} retry={() => void clients.refetch()} onPick={setClientId} />;
  }
  if (!client) {
    return (
      <Screen edges={['bottom']}>
        <LoadingState rows={4} />
      </Screen>
    );
  }
  return <InvoiceEditor key={client.id} client={client} mode={{ kind: 'create', onChangeClient: () => setClientId(undefined) }} />;
}

function ClientStep({
  clients,
  loading,
  error,
  retry,
  onPick,
}: {
  clients: Client[] | undefined;
  loading: boolean;
  error: unknown;
  retry: () => void;
  onPick: (id: string) => void;
}) {
  const { t } = useTranslation();
  const list = (clients ?? []).slice().sort((a, b) => Number(b.stats.unbilled.length > 0) - Number(a.stats.unbilled.length > 0));
  return (
    <Screen edges={['bottom']} testID="invoice-client-step">
      <SectionHeader title={t('invoiceForm.chooseClient')} />
      {loading ? (
        <Card>
          <LoadingState rows={3} />
        </Card>
      ) : error && !clients ? (
        <ErrorState message={t(errorMessageKey(error))} onRetry={retry} />
      ) : list.length === 0 ? (
        <Card>
          <EmptyState icon="people-outline" title={t('invoiceForm.noClients')} message={t('invoiceForm.noClientsHint')} actionLabel={t('clients.add')} onAction={() => router.replace('/clients/new')} />
        </Card>
      ) : (
        list.map((c) => (
          <Card key={c.id} padding="md" onPress={() => onPick(c.id)} accessibilityLabel={c.name} testID={`invoice-client-${c.id}`}>
            <View style={styles.clientRow}>
              <Avatar name={c.name} size={40} />
              <View style={styles.flex}>
                <AppText variant="bodyMedium" numberOfLines={1}>
                  {c.name}
                </AppText>
                <AppText variant="caption" color="textMuted">
                  {c.stats.unbilled.length > 0 ? t('invoiceForm.unbilledAmount', { amount: formatAmounts(c.stats.unbilled) }) : t('invoiceForm.nothingUnbilled')}
                </AppText>
              </View>
            </View>
          </Card>
        ))
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  clientRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
});
