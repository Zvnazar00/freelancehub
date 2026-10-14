import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { useClient } from '@/features/clients/api';
import { useInvoices } from '@/features/invoices/api';
import { InvoiceRow } from '@/features/invoices/components/InvoiceRow';
import { StatTile } from '@/features/dashboard/components/StatTile';
import { useProjects } from '@/features/projects/api';
import { formatAmounts, ProjectCard } from '@/features/projects/components/ProjectCard';
import { errorMessageKey, isApiError } from '@/shared/api';
import { formatMoney } from '@/shared/lib/money';
import { formatHours } from '@/shared/lib/time';
import { AppText, Avatar, Badge, Button, Card, EmptyState, ErrorState, Icon, LoadingState, Screen, SectionHeader } from '@/shared/ui';
import { spacing } from '@/shared/theme';

export default function ClientDetailScreen() {
  const { t } = useTranslation();
  const { id } = useLocalSearchParams<{ id: string }>();
  const clientQuery = useClient(id);
  const projects = useProjects({ clientId: id });
  const invoices = useInvoices('all', id);
  const [refreshing, setRefreshing] = useState(false);
  const client = clientQuery.data;

  if (!client) {
    const notFound = isApiError(clientQuery.error) && clientQuery.error.status === 404;
    return (
      <Screen edges={['bottom']}>
        <Stack.Screen options={{ title: t('screens.client') }} />
        {clientQuery.isPending ? (
          <LoadingState rows={4} />
        ) : notFound ? (
          <EmptyState
            icon="person-remove-outline"
            title={t('client.notFound')}
            message={t('client.notFoundHint')}
            actionLabel={t('client.back')}
            onAction={() => router.navigate('/clients')}
          />
        ) : (
          <ErrorState message={t(errorMessageKey(clientQuery.error))} onRetry={() => void clientQuery.refetch()} retrying={clientQuery.isFetching} />
        )}
      </Screen>
    );
  }

  const clientProjects = projects.data ?? [];
  const refresh = () => {
    setRefreshing(true);
    void Promise.all([clientQuery.refetch(), projects.refetch(), invoices.refetch()]).finally(() => setRefreshing(false));
  };

  return (
    <Screen edges={['bottom']} testID="client-detail-screen" onRefresh={refresh} refreshing={refreshing}>
      <Stack.Screen options={{ title: client.name }} />

      <Card>
        <View style={styles.head}>
          <Avatar name={client.name} size={56} />
          <View style={styles.flex}>
            <AppText variant="heading">{client.name}</AppText>
            {client.company ? (
              <AppText variant="caption" color="textSecondary">
                {client.company}
              </AppText>
            ) : null}
          </View>
          <Badge label={client.currency} tone="accent" />
        </View>
        <View style={styles.contacts}>
          <View style={styles.contact}>
            <Icon name="mail-outline" size={16} color="textMuted" />
            <AppText variant="caption" color={client.email ? 'textSecondary' : 'textMuted'}>
              {client.email ?? t('client.noEmail')}
            </AppText>
          </View>
          <View style={styles.contact}>
            <Icon name="pricetag-outline" size={16} color="textMuted" />
            <AppText variant="monoSmall" color="textSecondary">
              {client.defaultHourlyRate
                ? t('client.defaultRate', { rate: formatMoney(client.defaultHourlyRate, client.currency) })
                : t('client.noDefaultRate')}
            </AppText>
          </View>
        </View>
        {client.notes ? (
          <AppText variant="caption" color="textMuted" style={styles.notes}>
            {client.notes}
          </AppText>
        ) : null}
      </Card>

      <View style={styles.tiles}>
        <StatTile icon="time-outline" label={t('client.tracked')} value={formatHours(client.stats.trackedSeconds)} />
        <StatTile
          icon="cash-outline"
          label={t('client.unbilled')}
          value={formatAmounts(client.stats.unbilled, { compact: true })}
          hint={t('client.notInvoiced')}
        />
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('client.projects')} meta={String(clientProjects.length)} />
        {projects.isPending ? (
          <Card>
            <LoadingState rows={2} />
          </Card>
        ) : clientProjects.length === 0 ? (
          <Card>
            <EmptyState compact icon="folder-open-outline" title={t('client.noProjects')} message={t('client.noProjectsHint')} />
          </Card>
        ) : (
          clientProjects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              clientName={client.name}
              trackedSeconds={project.stats.trackedSeconds}
              unbilled={project.stats.unbilled}
              onPress={() => router.push({ pathname: '/projects/[id]', params: { id: project.id } })}
            />
          ))
        )}
        {client.archivedAt === null ? (
          <Button
            testID="client-add-project"
            label={t('projects.add')}
            icon="add"
            variant="secondary"
            fullWidth
            onPress={() => router.push({ pathname: '/projects/new', params: { clientId: client.id } })}
          />
        ) : null}
      </View>

      <View style={styles.section}>
        <SectionHeader
          title={t('client.invoices')}
          meta={invoices.data ? String(invoices.data.length) : undefined}
          actionLabel={(invoices.data?.length ?? 0) > 3 ? t('client.allInvoices') : undefined}
          onAction={() => router.push('/invoices')}
        />
        {invoices.isPending ? (
          <Card>
            <LoadingState rows={1} />
          </Card>
        ) : (invoices.data ?? []).length === 0 ? (
          <Card>
            <EmptyState compact icon="document-text-outline" title={t('client.noInvoices')} message={t('client.noInvoicesHint')} />
          </Card>
        ) : (
          (invoices.data ?? []).slice(0, 3).map((invoice) => (
            <InvoiceRow key={invoice.id} invoice={invoice} onPress={() => router.push({ pathname: '/invoices/[id]', params: { id: invoice.id } })} />
          ))
        )}
        <Button
          testID="client-new-invoice"
          label={t('client.newInvoice')}
          icon="document-text-outline"
          variant="secondary"
          fullWidth
          onPress={() => router.push({ pathname: '/invoices/new', params: { clientId: client.id } })}
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  head: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  contacts: { marginTop: spacing.lg, gap: spacing.sm },
  contact: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  notes: { marginTop: spacing.md },
  tiles: { flexDirection: 'row', gap: spacing.md },
  section: { gap: spacing.md },
});
