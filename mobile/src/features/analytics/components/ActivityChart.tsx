import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { centsToDecimal, decimalToCents, formatMoney } from '@/shared/lib/money';
import { formatCalendarDate, formatDuration, formatHoursDecimal, localDateKey } from '@/shared/lib/time';
import type { CurrencyCode, Timeseries } from '@/shared/types/domain';
import { AppText, SegmentedControl } from '@/shared/ui';
import { spacing } from '@/shared/theme';

import { bucketLabel, type PeriodKind } from '../range';
import { BarChart, type ChartBar } from './BarChart';

type Metric = 'hours' | 'tracked' | 'received';

export interface ActivityChartProps {
  series: Timeseries;
  kind: PeriodKind;
  today: Date;
  testID?: string;
}

/** Hours, tracked value or payments over the period. Money is charted one currency at a time (never summed). */
export function ActivityChart({ series, kind, today, testID }: ActivityChartProps) {
  const { t } = useTranslation();
  const [metric, setMetric] = useState<Metric>('hours');
  const currencies = useMemo(() => {
    const set = new Set<CurrencyCode>();
    for (const p of series.points) for (const a of [...p.tracked, ...p.received]) set.add(a.currency);
    return [...set].sort();
  }, [series]);
  const [pickedCurrency, setCurrency] = useState<CurrencyCode | null>(null);
  const currency = pickedCurrency && currencies.includes(pickedCurrency) ? pickedCurrency : (currencies[0] ?? null);

  const todayKey = localDateKey(today);
  const bars: ChartBar[] = series.points.map((p) => {
    let value = p.seconds;
    if (metric !== 'hours') {
      const list = metric === 'tracked' ? p.tracked : p.received;
      const amount = list.find((a) => a.currency === currency)?.amount ?? '0.00';
      value = decimalToCents(amount);
    }
    return {
      key: p.start,
      label: bucketLabel(p.start, series.interval, kind),
      value,
      highlight: p.start <= todayKey && todayKey <= p.end,
      future: p.start > todayKey,
    };
  });

  const format = (v: number) =>
    metric === 'hours' ? formatHoursDecimal(v) : currency ? formatMoney(centsToDecimal(Math.round(v)), currency, { compact: true }) : '';
  const summary = series.points
    .map((p, i) => ({ p, value: bars[i]?.value ?? 0 }))
    .filter((x) => x.value > 0)
    .map(({ p, value }) => `${formatCalendarDate(p.start)} ${metric === 'hours' ? formatDuration(p.seconds) : format(value)}`)
    .join(', ');

  return (
    <View style={styles.wrap} testID={testID}>
      <SegmentedControl
        accessibilityLabel={t('analytics.metricA11y')}
        value={metric}
        onChange={setMetric}
        options={[
          { value: 'hours', label: t('analytics.metricHours') },
          { value: 'tracked', label: t('analytics.metricTracked') },
          { value: 'received', label: t('analytics.metricReceived') },
        ]}
      />
      {metric !== 'hours' && currencies.length > 1 && currency ? (
        <SegmentedControl
          accessibilityLabel={t('analytics.currencyA11y')}
          layout="scroll"
          value={currency}
          onChange={setCurrency}
          options={currencies.map((c) => ({ value: c, label: c }))}
        />
      ) : null}
      {metric !== 'hours' && !currency ? (
        <AppText variant="caption" color="textMuted" align="center" style={styles.empty}>
          {t('analytics.noMoneyInPeriod')}
        </AppText>
      ) : (
        <BarChart
          bars={bars}
          formatValue={format}
          accessibilityLabel={t('analytics.chartA11y', { summary: summary || t('analytics.chartEmpty') })}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.md },
  empty: { paddingVertical: spacing.xxl },
});
