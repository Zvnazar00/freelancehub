import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { formatMoney } from '@/shared/lib/money';
import { formatHours, formatHoursDecimal, formatWholeHours } from '@/shared/lib/time';
import type { MoneyAmount, Project } from '@/shared/types/domain';
import { AppText, Badge, Card, ProgressBar } from '@/shared/ui';
import { colors, spacing } from '@/shared/theme';

import { billingLabel, projectStatusTone } from '../labels';

export interface ProjectCardProps {
  project: Project;
  clientName: string;
  trackedSeconds: number;
  /** Per-currency totals; usually one entry in the project's currency. */
  unbilled: MoneyAmount[];
  isTracking?: boolean;
  onPress: () => void;
}

export function ProjectCard({ project, clientName, trackedSeconds, unbilled, isTracking = false, onPress }: ProjectCardProps) {
  const { t } = useTranslation();
  const statusLabel = t(`projects.status.${project.status}`);
  const budgetSeconds = project.budgetHours ? Number(project.budgetHours) * 3600 : null;
  const usage = budgetSeconds ? trackedSeconds / budgetSeconds : null;

  return (
    <Card onPress={onPress} accessibilityLabel={`${project.name}, ${clientName}, ${statusLabel}`} accessibilityHint={t('projects.openDetailsHint')}>
      <View style={styles.top}>
        <View style={[styles.swatch, { backgroundColor: project.color }]} />
        <View style={styles.title}>
          <AppText variant="subheading" numberOfLines={1}>
            {project.name}
          </AppText>
          <AppText variant="caption" color="textMuted" numberOfLines={1}>
            {clientName}
          </AppText>
        </View>
        {isTracking ? <Badge label={t('projects.tracking')} tone="accent" dot /> : <Badge label={statusLabel} tone={projectStatusTone[project.status]} />}
      </View>

      <View style={styles.stats}>
        <View style={styles.stat}>
          <AppText variant="caption" color="textMuted">
            {t('projects.tracked')}
          </AppText>
          <AppText variant="mono" numberOfLines={1}>
            {formatHours(trackedSeconds)}
          </AppText>
        </View>
        <View style={styles.stat}>
          <AppText variant="caption" color="textMuted">
            {t('projects.unbilled')}
          </AppText>
          <AppText variant="mono" numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.8}>
            {formatAmounts(unbilled)}
          </AppText>
        </View>
        <View style={[styles.stat, styles.statRight]}>
          <AppText variant="caption" color="textMuted">
            {t('projects.billing')}
          </AppText>
          <AppText variant="captionMedium" color="textSecondary" numberOfLines={2} align="right">
            {billingLabel(project, t)}
          </AppText>
        </View>
      </View>

      {usage !== null && project.budgetHours ? (
        <View style={styles.budget}>
          <ProgressBar
            value={usage}
            color={usage > 0.85 ? colors.warning : project.color}
            accessibilityLabel={t('projects.budgetUsedA11y', { percent: Math.round(usage * 100) })}
          />
          <AppText variant="monoSmall" color="textMuted">
            {t('projects.budgetLine', { used: formatHoursDecimal(trackedSeconds), total: formatWholeHours(Number(project.budgetHours)) })}
          </AppText>
        </View>
      ) : null}
    </Card>
  );
}

/** "€1,200.00 · $300.00", or an em dash when there is nothing. */
export function formatAmounts(amounts: readonly MoneyAmount[], options?: Parameters<typeof formatMoney>[2]): string {
  return amounts.length ? amounts.map((a) => formatMoney(a.amount, a.currency, options)).join(' · ') : '—';
}

const styles = StyleSheet.create({
  top: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  swatch: { width: 10, height: 36, borderRadius: 5 },
  title: { flex: 1 },
  stats: { flexDirection: 'row', marginTop: spacing.lg, gap: spacing.md },
  stat: { flex: 1, gap: 2, minWidth: 0 },
  statRight: { alignItems: 'flex-end' },
  budget: { marginTop: spacing.md, gap: spacing.xs + 2 },
});
