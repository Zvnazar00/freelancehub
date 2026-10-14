import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { formatMoney } from '@/shared/lib/money';
import { formatDuration } from '@/shared/lib/time';
import type { ProjectSummary } from '@/shared/types/domain';
import { AppText, Card, ProgressBar } from '@/shared/ui';
import { colors, spacing } from '@/shared/theme';

import { formatAmounts } from './ProjectCard';

function Line({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <View style={styles.line} accessible accessibilityLabel={`${label}: ${value}`}>
      <View style={styles.flex}>
        <AppText variant="caption" color="textSecondary">
          {label}
        </AppText>
        {hint ? (
          <AppText variant="caption" color="textMuted">
            {hint}
          </AppText>
        ) : null}
      </View>
      <AppText variant="mono">{value}</AppText>
    </View>
  );
}

/** Server-computed project economics: rates, tracked vs unbilled vs invoiced value, and time per task. */
export function ProjectMoneyCard({ summary, color }: { summary: ProjectSummary; color: string }) {
  const { t } = useTranslation();
  const rate = summary.currentRate;
  const effective = summary.effectiveHourlyRate.map((r) => t('money.perHour', { rate: formatMoney(r.rate, r.currency) })).join(' · ');
  const topTasks = summary.byTask.slice(0, 5);

  return (
    <Card style={styles.card} testID="project-money">
      <Line
        label={t('projectMoney.currentRate')}
        value={rate.rate ? t('money.perHour', { rate: formatMoney(rate.rate, rate.currency) }) : '—'}
        hint={t(`projectMoney.rateSource.${rate.source}`)}
      />
      {effective ? (
        <Line
          label={t('projectMoney.effectiveRate')}
          value={effective}
          hint={summary.billingType === 'fixed' ? t('projectMoney.effectiveFixedHint') : t('projectMoney.effectiveHint')}
        />
      ) : null}
      {summary.money.map((m) => (
        <View key={m.currency} style={styles.money}>
          <Line label={t('projectMoney.tracked', { currency: m.currency })} value={formatMoney(m.tracked, m.currency)} />
          <Line label={t('money.unbilled')} value={formatMoney(m.unbilled, m.currency)} />
          <Line label={t('money.invoiced')} value={formatMoney(m.invoiced, m.currency)} />
        </View>
      ))}
      <Line label={t('projectMoney.last30')} value={formatDuration(summary.last30DaysSeconds)} />
      {topTasks.length > 0 ? (
        <View style={styles.tasks}>
          <AppText variant="overline" color="textMuted">
            {t('projectMoney.byTask')}
          </AppText>
          {topTasks.map((task) => (
            <View key={task.taskId ?? 'none'} style={styles.task}>
              <View style={styles.taskHead}>
                <AppText variant="caption" numberOfLines={1} style={styles.flex} color={task.title ? 'textPrimary' : 'textMuted'}>
                  {task.title ?? t('common.noTask')}
                </AppText>
                <AppText variant="monoSmall" color="textSecondary">
                  {formatDuration(task.seconds)}
                  {task.amounts.length ? ` · ${formatAmounts(task.amounts)}` : ''}
                </AppText>
              </View>
              <ProgressBar value={summary.trackedSeconds > 0 ? task.seconds / summary.trackedSeconds : 0} color={color} height={3} />
            </View>
          ))}
        </View>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.sm },
  flex: { flex: 1 },
  line: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, minHeight: 32 },
  money: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: spacing.sm, gap: spacing.xs },
  tasks: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: spacing.md, gap: spacing.sm },
  task: { gap: 4 },
  taskHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
});
