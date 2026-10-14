import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { useDashboard, useTimeseries } from '@/features/analytics/api';
import { ActivityChart } from '@/features/analytics/components/ActivityChart';
import { BalanceCard, MoneyFlowCard } from '@/features/analytics/components/MoneyCards';
import { PeriodBar } from '@/features/analytics/components/PeriodBar';
import { chartInterval, containsDay, periodContaining, type Period } from '@/features/analytics/range';
import { useCurrentUser } from '@/features/auth/store';
import { StatTile } from '@/features/dashboard/components/StatTile';
import { formatAmounts } from '@/features/projects/components/ProjectCard';
import { useTimerCommands } from '@/features/timer/api';
import { StatusPill } from '@/features/timer/components/StatusPill';
import { TimerDisplay } from '@/features/timer/components/TimerDisplay';
import { useActiveTimer } from '@/features/timer/hooks';
import { errorMessageKey } from '@/shared/api';
import { useNow } from '@/shared/hooks/useNow';
import { formatDuration, formatHours, formatLongDay, greetingFor } from '@/shared/lib/time';
import {
  AppText,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Icon,
  InlineError,
  ListRow,
  OfflineBanner,
  ProgressBar,
  Screen,
  ScreenHeader,
  SectionHeader,
  Skeleton,
} from '@/shared/ui';
import { spacing } from '@/shared/theme';

const DASHBOARD_KINDS = ['week', 'month', 'quarter'] as const;

export default function DashboardScreen() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const active = useActiveTimer();
  const commands = useTimerCommands();
  const nowMs = useNow(true, active?.entry.status === 'running' ? 1000 : 30_000);
  const now = useMemo(() => new Date(nowMs), [nowMs]);
  const [period, setPeriod] = useState<Period>(() => periodContaining('month', new Date(), user.weekStart));

  const summary = useDashboard(period);
  const series = useTimeseries(period, chartInterval(period.kind));
  const [refreshing, setRefreshing] = useState(false);
  const data = summary.data;
  const firstName = user.fullName.split(' ')[0] ?? user.fullName;

  // The running timer is not in the server totals yet (they cover stopped entries); show it live on top.
  const liveSeconds = active && containsDay(period, new Date(active.entry.startedAt)) ? active.seconds : 0;
  const tracked = (data?.trackedSeconds ?? 0) + liveSeconds;
  const billableShare = data && data.trackedSeconds > 0 ? Math.round((data.billableSeconds / data.trackedSeconds) * 100) : 0;
  const deltaSeconds = data ? data.trackedSeconds - data.previousTrackedSeconds : 0;

  const refresh = () => {
    setRefreshing(true);
    void Promise.all([summary.refetch(), series.refetch()]).finally(() => setRefreshing(false));
  };

  return (
    <Screen testID="dashboard-screen" onRefresh={refresh} refreshing={refreshing}>
      <ScreenHeader
        subtitle={formatLongDay(now)}
        title={t('greeting.format', { greeting: t(`greeting.${greetingFor(now)}`), name: firstName })}
      />
      <OfflineBanner />

      {active ? (
        <Card variant="accent" onPress={() => router.navigate('/time')} accessibilityLabel={t('dashboard.openActiveTimer')}>
          <View style={styles.timerTop}>
            <StatusPill status={active.entry.status} />
            <AppText variant="caption" color="textSecondary" numberOfLines={1} style={styles.flex} align="right">
              {active.entry.project.name}
              {active.entry.task ? ` · ${active.entry.task.title}` : ''}
            </AppText>
          </View>
          <View style={styles.timerBody}>
            <TimerDisplay seconds={active.seconds} status={active.entry.status} size="medium" />
            <Button
              label={t(active.entry.status === 'running' ? 'timer.pause' : 'timer.resume')}
              icon={active.entry.status === 'running' ? 'pause' : 'play'}
              variant="secondary"
              size="sm"
              disabled={commands.pending}
              onPress={() =>
                void commands.run({ kind: active.entry.status === 'running' ? 'pause' : 'resume', entryId: active.entry.id })
              }
            />
          </View>
          {commands.error ? <InlineError error={commands.error} /> : null}
        </Card>
      ) : (
        <Card variant="outline">
          <View style={styles.idleRow}>
            <Icon name="timer-outline" size={22} color="textMuted" />
            <View style={styles.flex}>
              <AppText variant="bodyMedium">{t('dashboard.noTimer')}</AppText>
              <AppText variant="caption" color="textMuted">
                {t('dashboard.noTimerHint')}
              </AppText>
            </View>
            <Button label={t('dashboard.start')} icon="play" size="sm" onPress={() => router.navigate('/time')} />
          </View>
        </Card>
      )}

      <PeriodBar period={period} onChange={setPeriod} weekStart={user.weekStart} today={now} kinds={DASHBOARD_KINDS} testID="dashboard-period" />

      {summary.isError && !data ? (
        <ErrorState message={t(errorMessageKey(summary.error))} onRetry={() => void summary.refetch()} retrying={summary.isFetching} />
      ) : (
        <>
          <View style={styles.tiles}>
            <StatTile
              icon="time-outline"
              label={t('dashboard.trackedTime')}
              value={data ? formatHours(tracked) : '—'}
              hint={
                data
                  ? deltaSeconds === 0
                    ? t('dashboard.sameAsBefore')
                    : t(deltaSeconds > 0 ? 'dashboard.moreThanBefore' : 'dashboard.lessThanBefore', {
                        duration: formatDuration(Math.abs(deltaSeconds)),
                      })
                  : undefined
              }
            />
            <StatTile
              icon="pie-chart-outline"
              label={t('dashboard.billable')}
              value={data ? `${billableShare}%` : '—'}
              hint={data ? t('dashboard.entries', { count: data.entries }) : undefined}
            />
          </View>

          <View style={styles.section}>
            <SectionHeader title={t('dashboard.earnings')} actionLabel={t('dashboard.analytics')} onAction={() => router.push('/analytics')} />
            {!data ? (
              <Card>
                <Skeleton width="45%" height={14} />
                <Skeleton width="70%" height={30} style={styles.skeletonGap} />
              </Card>
            ) : data.flows.length === 0 ? (
              <Card>
                <EmptyState compact icon="cash-outline" title={t('dashboard.noMoney')} message={t('dashboard.noMoneyHint')} />
              </Card>
            ) : (
              data.flows.map((flow) => <MoneyFlowCard key={flow.currency} flow={flow} />)
            )}
            <AppText variant="caption" color="textMuted">
              {t('money.trackedNote')}
            </AppText>
          </View>

          <View style={styles.section}>
            <SectionHeader title={t('money.balancesNow')} actionLabel={t('dashboard.invoices')} onAction={() => router.push('/invoices')} />
            {data && data.balances.length > 0
              ? data.balances.map((b) => <BalanceCard key={b.currency} balance={b} onPressOutstanding={() => router.push('/invoices')} />)
              : null}
            {data && data.balances.length === 0 ? (
              <Card>
                <EmptyState compact icon="checkmark-done-outline" title={t('dashboard.allSettled')} message={t('dashboard.allSettledHint')} />
              </Card>
            ) : null}
            {data && (data.invoices.draft > 0 || data.invoices.open > 0) ? (
              <Card padding="none">
                <ListRow
                  icon="document-text-outline"
                  label={t('dashboard.invoiceCounts', { open: data.invoices.open, draft: data.invoices.draft })}
                  description={data.invoices.overdue > 0 ? t('dashboard.overdueCount', { count: data.invoices.overdue }) : undefined}
                  onPress={() => router.push('/invoices')}
                  showDivider={false}
                />
              </Card>
            ) : null}
          </View>

          <View style={styles.section}>
            <SectionHeader title={t('dashboard.activity')} />
            <Card>
              {series.data ? (
                <ActivityChart series={series.data} kind={period.kind} today={now} testID="dashboard-chart" />
              ) : series.isError ? (
                <InlineError error={series.error} />
              ) : (
                <Skeleton width="100%" height={170} />
              )}
            </Card>
          </View>

          <View style={styles.section}>
            <SectionHeader title={t('dashboard.topProjects')} actionLabel={t('dashboard.allProjects')} onAction={() => router.navigate('/projects')} />
            <Card padding="sm">
              {!data ? (
                <Skeleton width="100%" height={60} />
              ) : data.topProjects.length === 0 ? (
                <EmptyState compact icon="folder-open-outline" title={t('dashboard.noTimePeriod')} message={t('dashboard.noTimePeriodHint')} />
              ) : (
                data.topProjects.map((project) => (
                  <Card
                    key={project.id}
                    variant="surface"
                    padding="md"
                    style={styles.topRow}
                    onPress={() => router.push({ pathname: '/projects/[id]', params: { id: project.id } })}
                    accessibilityLabel={`${project.name}, ${formatDuration(project.seconds)}`}
                  >
                    <View style={styles.topHead}>
                      <View style={[styles.dot, { backgroundColor: project.color }]} />
                      <View style={styles.flex}>
                        <AppText variant="bodyMedium" numberOfLines={1}>
                          {project.name}
                        </AppText>
                        <AppText variant="caption" color="textMuted" numberOfLines={1}>
                          {project.clientName}
                        </AppText>
                      </View>
                      <View style={styles.topRight}>
                        <AppText variant="mono">{formatDuration(project.seconds)}</AppText>
                        {project.amounts.length > 0 ? (
                          <AppText variant="monoSmall" color="textMuted">
                            {formatAmounts(project.amounts)}
                          </AppText>
                        ) : null}
                      </View>
                    </View>
                    <ProgressBar value={data.trackedSeconds > 0 ? project.seconds / data.trackedSeconds : 0} color={project.color} height={4} />
                  </Card>
                ))
              )}
            </Card>
          </View>
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  timerTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  timerBody: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: spacing.md },
  idleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  tiles: { flexDirection: 'row', gap: spacing.md },
  section: { gap: spacing.md },
  skeletonGap: { marginTop: spacing.sm },
  topRow: { borderWidth: 0, gap: spacing.sm, borderRadius: 12 },
  topHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  topRight: { alignItems: 'flex-end' },
  dot: { width: 10, height: 10, borderRadius: 5 },
});
