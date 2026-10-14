import { StyleSheet, View } from 'react-native';

import { colors, radii } from '@/shared/theme';

export interface ProgressBarProps {
  /** 0..1 (values > 1 render full in danger tone — over budget). */
  value: number;
  color?: string;
  height?: number;
  accessibilityLabel?: string;
}

export function ProgressBar({ value, color = colors.accent, height = 6, accessibilityLabel }: ProgressBarProps) {
  const safe = Number.isFinite(value) ? Math.max(0, value) : 0;
  const over = safe > 1;
  const pct = Math.min(1, safe) * 100;
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel={accessibilityLabel}
      accessibilityValue={{ min: 0, max: 100, now: Math.round(safe * 100) }}
      style={[styles.track, { height, borderRadius: height / 2 }]}
    >
      <View style={[styles.fill, { width: `${pct}%`, backgroundColor: over ? colors.danger : color, borderRadius: height / 2 }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  track: { width: '100%', backgroundColor: colors.surface3, overflow: 'hidden', borderRadius: radii.pill },
  fill: { height: '100%' },
});
