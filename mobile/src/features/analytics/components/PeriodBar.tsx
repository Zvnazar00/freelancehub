import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { AppText, IconButton, SegmentedControl } from '@/shared/ui';
import { spacing } from '@/shared/theme';

import { canGoForward, containsDay, PERIOD_KINDS, periodContaining, periodLabel, shiftPeriod, type Period, type PeriodKind } from '../range';

export interface PeriodBarProps {
  period: Period;
  onChange: (period: Period) => void;
  weekStart: 1 | 7;
  today: Date;
  /** Period kinds offered (the dashboard hides "year"). */
  kinds?: readonly PeriodKind[];
  testID?: string;
}

/** Date-range filter: period kind + previous/next navigation. "Back to now" appears once you leave the current period. */
export function PeriodBar({ period, onChange, weekStart, today, kinds = PERIOD_KINDS, testID }: PeriodBarProps) {
  const { t } = useTranslation();
  const label = periodLabel(period, (quarter, year) => t('period.quarterLabel', { quarter, year }));
  const isCurrent = containsDay(period, today);
  const forward = canGoForward(period, today);

  return (
    <View style={styles.wrap} testID={testID}>
      <SegmentedControl
        accessibilityLabel={t('period.kindA11y')}
        options={kinds.map((k) => ({ value: k, label: t(`period.${k}`) }))}
        value={period.kind}
        onChange={(kind) => onChange(periodContaining(kind, today, weekStart))}
      />
      <View style={styles.nav}>
        <IconButton
          icon="chevron-back"
          variant="plain"
          accessibilityLabel={t('period.previous')}
          onPress={() => onChange(shiftPeriod(period, -1, weekStart))}
          testID={testID ? `${testID}-prev` : undefined}
        />
        <View style={styles.center}>
          <AppText variant="subheading" accessibilityLiveRegion="polite" testID={testID ? `${testID}-label` : undefined}>
            {label}
          </AppText>
          {!isCurrent ? (
            <AppText
              variant="captionMedium"
              color="accentText"
              accessibilityRole="button"
              onPress={() => onChange(periodContaining(period.kind, today, weekStart))}
            >
              {t('period.backToNow')}
            </AppText>
          ) : null}
        </View>
        <IconButton
          icon="chevron-forward"
          variant="plain"
          accessibilityLabel={t('period.next')}
          disabled={!forward}
          onPress={() => onChange(shiftPeriod(period, 1, weekStart))}
          testID={testID ? `${testID}-next` : undefined}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  nav: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  center: { flex: 1, alignItems: 'center', gap: 2 },
});
