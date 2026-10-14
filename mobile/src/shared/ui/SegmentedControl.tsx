import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { colors, radii, spacing } from '@/shared/theme';

import { AppText } from './AppText';

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  count?: number;
}

export interface SegmentedControlProps<T extends string> {
  options: readonly SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  accessibilityLabel: string;
  /** Stretch segments to fill the width (default) or scroll horizontally. */
  layout?: 'fill' | 'scroll';
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  accessibilityLabel,
  layout = 'fill',
}: SegmentedControlProps<T>) {
  const items = options.map((option) => {
    const selected = option.value === value;
    return (
      <Pressable
        key={option.value}
        accessibilityRole="tab"
        accessibilityState={{ selected }}
        accessibilityLabel={option.count !== undefined ? `${option.label}, ${option.count}` : option.label}
        onPress={() => onChange(option.value)}
        style={({ pressed }) => [
          styles.segment,
          layout === 'fill' && styles.fill,
          selected && styles.selected,
          pressed && !selected && styles.pressed,
        ]}
      >
        <AppText variant="captionMedium" color={selected ? 'textPrimary' : 'textSecondary'} numberOfLines={1}>
          {option.label}
        </AppText>
        {option.count !== undefined ? (
          <View style={[styles.count, selected && styles.countSelected]}>
            <AppText variant="monoSmall" color={selected ? 'accentText' : 'textMuted'} style={styles.countText}>
              {option.count}
            </AppText>
          </View>
        ) : null}
      </Pressable>
    );
  });

  if (layout === 'scroll') {
    return (
      <ScrollView horizontal showsHorizontalScrollIndicator={false} accessibilityRole="tablist" accessibilityLabel={accessibilityLabel}>
        <View style={styles.track}>{items}</View>
      </ScrollView>
    );
  }

  return (
    <View style={styles.track} accessibilityRole="tablist" accessibilityLabel={accessibilityLabel}>
      {items}
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    flexDirection: 'row',
    padding: 3,
    gap: 3,
    borderRadius: radii.md,
    backgroundColor: colors.surface1,
    borderWidth: 1,
    borderColor: colors.border,
  },
  segment: {
    minHeight: 38,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs + 2,
    paddingHorizontal: spacing.md,
    borderRadius: radii.sm,
  },
  fill: { flex: 1 },
  selected: { backgroundColor: colors.surface3 },
  pressed: { backgroundColor: colors.surface2 },
  count: { paddingHorizontal: 6, borderRadius: radii.pill, backgroundColor: colors.surface2 },
  countSelected: { backgroundColor: colors.accentSoft },
  countText: { fontSize: 11, lineHeight: 16 },
});
