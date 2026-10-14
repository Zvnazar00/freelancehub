import { StyleSheet, View } from 'react-native';

import { AppText } from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

export interface ChartBar {
  key: string;
  label: string;
  /** Display-only magnitude (seconds or cents). */
  value: number;
  highlight?: boolean;
  future?: boolean;
}

export interface BarChartProps {
  bars: ChartBar[];
  formatValue: (value: number) => string;
  /** Spoken summary of the whole chart (screen readers get one label, not 31 bars). */
  accessibilityLabel: string;
  height?: number;
  testID?: string;
}

/**
 * Dependency-free bar chart built from Views: renders identically in Expo Go, dev builds and web.
 * Values above bars only when there is room; labels thin out automatically for long ranges.
 */
export function BarChart({ bars, formatValue, accessibilityLabel, height = 140, testID }: BarChartProps) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  const showValues = bars.length <= 8;
  const labelEvery = bars.length <= 12 ? 1 : Math.ceil(bars.length / 8);
  const gap = bars.length > 20 ? 2 : bars.length > 10 ? 4 : spacing.sm;
  const plot = height - (showValues ? 18 : 0);

  return (
    <View accessible accessibilityRole="image" accessibilityLabel={accessibilityLabel} testID={testID}>
      <View style={styles.scale}>
        <AppText variant="monoSmall" color="textMuted" style={styles.scaleText}>
          {formatValue(max)}
        </AppText>
      </View>
      <View style={[styles.plot, { height, gap }]}>
        <View style={[styles.gridLine, { bottom: plot }]} />
        <View style={[styles.gridLine, { bottom: plot / 2 }]} />
        {bars.map((bar) => (
          <View key={bar.key} style={styles.col}>
            {showValues && bar.value > 0 ? (
              <AppText variant="monoSmall" color={bar.highlight ? 'accentText' : 'textMuted'} style={styles.value} numberOfLines={1}>
                {formatValue(bar.value)}
              </AppText>
            ) : null}
            <View
              style={[
                styles.bar,
                {
                  height: Math.max(bar.value > 0 ? 4 : 2, (bar.value / max) * plot),
                  backgroundColor: bar.future ? colors.surface2 : bar.highlight ? colors.accent : colors.surface3,
                  borderColor: bar.highlight ? colors.accentBorder : colors.transparent,
                },
              ]}
            />
          </View>
        ))}
      </View>
      <View style={[styles.labels, { gap }]}>
        {bars.map((bar, i) => (
          // The label may be wider than its (thin) column: it is centred on the bar and allowed to overflow,
          // so "13" never shrinks to "1." on a 31-day chart (no numberOfLines: on web it caps the width at the column's).
          // Only every n-th label is drawn.
          <View key={bar.key} style={styles.labelCol}>
            {i % labelEvery === 0 ? (
              <AppText variant="captionMedium" color={bar.highlight ? 'accentText' : 'textMuted'} style={styles.label}>
                {bar.label}
              </AppText>
            ) : null}
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  scale: { alignItems: 'flex-end', marginBottom: spacing.xs },
  scaleText: { fontSize: 10, lineHeight: 12 },
  plot: { flexDirection: 'row', alignItems: 'flex-end' },
  gridLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  col: { flex: 1, alignItems: 'center', justifyContent: 'flex-end', gap: 4 },
  value: { fontSize: 10, lineHeight: 12 },
  bar: { width: '100%', maxWidth: 28, borderRadius: radii.sm, borderWidth: 1 },
  labels: { flexDirection: 'row', marginTop: spacing.sm },
  labelCol: { flex: 1, alignItems: 'center', overflow: 'visible' },
  label: { width: 44, textAlign: 'center', fontSize: 11 },
});
