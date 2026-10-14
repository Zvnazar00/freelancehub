import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { useBreakdown, useDashboard, useTimeseries } from '@/features/analytics/api';
import { ActivityChart } from '@/features/analytics/components/ActivityChart';
import { BreakdownList } from '@/features/analytics/components/BreakdownList';
import { MoneyFlowCard } from '@/features/analytics/components/MoneyCards';
import { PeriodBar } from '@/features/analytics/components/PeriodBar';
import { chartInterval, periodContaining, type Period } from '@/features/analytics/range';
import { useCurrentUser } from '@/features/auth/store';
import { StatTile } from '@/features/dashboard/components/StatTile';
import { useExportCsv, type ExportKind } from '@/features/exports/api';
import { errorMessageKey } from '@/shared/api';
import { formatHours } from '@/shared/lib/time';
import { AppText, Button, Card, EmptyState, ErrorState, InlineError, LoadingState, Screen, SectionHeader, SegmentedControl, Skeleton } from '@/shared/ui';
import { spacing } from '@/shared/theme';

export default function AnalyticsScreen() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const today = useMemo(() => new Date(), []);
  const [period, setPeriod] = useState<Period>(() => periodContaining('month', today, user.weekStart));
  const [groupBy, setGroupBy] = useState<'project' | 'client'>('project');
  const summary = useDashboard(period);
  const series = useTimeseries(period, chartInterval(period.kind));
  const breakdown = useBreakdown(period, groupBy);
  const exporter = useExportCsv();
  const [exporting, setExporting] = useState<ExportKind | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const runExport = (kind: ExportKind) => {
    setExporting(kind);
    exporter.mutate({ kind, from: period.from, to: period.to }, { onSettled: () => setExporting(null) });
  };

  const refresh = () => {
    setRefreshing(true);
    void Promise.all([summary.refetch(), series.refetch(), breakdown.refetch()]).finally(() => setRefreshing(false));
  };

  const data = summary.data;
  return (
    <Screen edges={['bottom']} testID="analytics-screen" onRefresh={refresh} refreshing={refreshing}>
      <PeriodBar period={period} onChange={setPeriod} weekStart={user.weekStart} today={today} testID="analytics-period" />

      {summary.isError && !data ? (
        <ErrorState message={t(errorMessageKey(summary.error))} onRetry={() => void summary.refetch()} retrying={summary.isFetching} />
      ) : (
        <>
          <View style={styles.tiles}>
            <StatTile icon="time-outline" label={t('dashboard.trackedTime')} value={data ? formatHours(data.trackedSeconds) : '—'} />
            <StatTile
              icon="cash-outline"
              label={t('dashboard.billable')}
              value={data ? formatHours(data.billableSeconds) : '—'}
              hint={data ? t('dashboard.entries', { count: data.entries }) : undefined}
            />
          </View>

          <Card>
            {series.data ? (
              <ActivityChart series={series.data} kind={period.kind} today={today} testID="analytics-chart" />
            ) : series.isError ? (
              <InlineError error={series.error} />
            ) : (
              <Skeleton width="100%" height={200} />
            )}
          </Card>

          <View style={styles.section}>
            <SectionHeader title={t('dashboard.earnings')} />
            {!data ? (
              <Card>
                <Skeleton width="60%" height={28} />
              </Card>
            ) : data.flows.length === 0 ? (
              <Card>
                <EmptyState compact icon="cash-outline" title={t('dashboard.noMoney')} message={t('dashboard.noMoneyHint')} />
              </Card>
            ) : (
              data.flows.map((flow) => <MoneyFlowCard key={flow.currency} flow={flow} />)
            )}
          </View>
        </>
      )}

      <View style={styles.section}>
        <SectionHeader title={t('analytics.breakdown')} meta={breakdown.data ? formatHours(breakdown.data.totalSeconds) : undefined} />
        <SegmentedControl
          accessibilityLabel={t('analytics.groupByA11y')}
          value={groupBy}
          onChange={setGroupBy}
          options={[
            { value: 'project', label: t('analytics.byProject') },
            { value: 'client', label: t('analytics.byClient') },
          ]}
        />
        {breakdown.isPending ? (
          <Card>
            <LoadingState rows={3} />
          </Card>
        ) : breakdown.isError && !breakdown.data ? (
          <ErrorState message={t(errorMessageKey(breakdown.error))} onRetry={() => void breakdown.refetch()} retrying={breakdown.isFetching} />
        ) : (breakdown.data?.rows ?? []).length === 0 ? (
          <Card>
            <EmptyState compact icon="analytics-outline" title={t('dashboard.noTimePeriod')} message={t('dashboard.noTimePeriodHint')} />
          </Card>
        ) : (
          <BreakdownList
            rows={breakdown.data?.rows ?? []}
            onPressRow={(row) =>
              router.push(groupBy === 'project' ? { pathname: '/projects/[id]', params: { id: row.id } } : { pathname: '/clients/[id]', params: { id: row.id } })
            }
          />
        )}
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('exports.title')} />
        <Card style={styles.exportCard}>
          <AppText variant="caption" color="textSecondary">
            {t('exports.hint')}
          </AppText>
          <View style={styles.exportButtons}>
            <Button
              testID="export-entries"
              label={t('exports.timeEntries')}
              icon="download-outline"
              variant="secondary"
              loading={exporting === 'time-entries'}
              disabled={exporting !== null}
              onPress={() => runExport('time-entries')}
              style={styles.flex}
            />
            <Button
              testID="export-invoices"
              label={t('exports.invoices')}
              icon="download-outline"
              variant="secondary"
              loading={exporting === 'invoices'}
              disabled={exporting !== null}
              onPress={() => runExport('invoices')}
              style={styles.flex}
            />
          </View>
          {exporter.isSuccess && exporter.data === 'saved' ? (
            <AppText variant="caption" color="success" accessibilityLiveRegion="polite">
              {t('exports.saved')}
            </AppText>
          ) : null}
          <InlineError error={exporter.error} />
        </Card>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  tiles: { flexDirection: 'row', gap: spacing.md },
  section: { gap: spacing.md },
  exportCard: { gap: spacing.md },
  exportButtons: { flexDirection: 'row', gap: spacing.sm },
});
