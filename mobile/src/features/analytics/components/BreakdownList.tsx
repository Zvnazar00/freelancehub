import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { formatAmounts } from '@/features/projects/components/ProjectCard';
import { formatMoney } from '@/shared/lib/money';
import { formatDuration } from '@/shared/lib/time';
import type { BreakdownRow } from '@/shared/types/domain';
import { AppText, Card, ProgressBar } from '@/shared/ui';
import { colors, spacing } from '@/shared/theme';

export interface BreakdownListProps {
  rows: BreakdownRow[];
  onPressRow?: (row: BreakdownRow) => void;
}

export function BreakdownList({ rows, onPressRow }: BreakdownListProps) {
  const { t } = useTranslation();
  return (
    <View style={styles.list}>
      {rows.map((row) => {
        const rate = row.effectiveHourlyRate
          .map((r) => t('money.perHour', { rate: formatMoney(r.rate, r.currency) }))
          .join(' · ');
        const percent = Math.round(row.share * 100);
        return (
          <Card
            key={row.id}
            padding="md"
            style={styles.row}
            onPress={onPressRow ? () => onPressRow(row) : undefined}
            accessibilityLabel={`${row.name}, ${formatDuration(row.seconds)}, ${percent}%`}
            testID={`breakdown-${row.id}`}
          >
            <View style={styles.head}>
              <View style={[styles.dot, { backgroundColor: row.color ?? colors.accent }]} />
              <View style={styles.flex}>
                <AppText variant="bodyMedium" numberOfLines={1}>
                  {row.name}
                </AppText>
                {row.clientName ? (
                  <AppText variant="caption" color="textMuted" numberOfLines={1}>
                    {row.clientName}
                  </AppText>
                ) : null}
              </View>
              <View style={styles.right}>
                <AppText variant="mono">{formatDuration(row.seconds)}</AppText>
                <AppText variant="monoSmall" color="textMuted">
                  {row.billingType === 'fixed' ? t('analytics.fixedFee') : formatAmounts(row.amounts)}
                </AppText>
              </View>
            </View>
            <ProgressBar value={row.share} color={row.color ?? colors.accent} height={4} />
            <View style={styles.meta}>
              <AppText variant="caption" color="textMuted">
                {t('analytics.share', { percent })}
              </AppText>
              {rate ? (
                <AppText variant="monoSmall" color="textSecondary">
                  {t('analytics.effective', { rate })}
                </AppText>
              ) : null}
            </View>
          </Card>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm },
  row: { gap: spacing.sm },
  head: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  flex: { flex: 1 },
  right: { alignItems: 'flex-end' },
  dot: { width: 10, height: 10, borderRadius: 5 },
  meta: { flexDirection: 'row', justifyContent: 'space-between' },
});
