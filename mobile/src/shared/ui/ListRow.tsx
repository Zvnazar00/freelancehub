import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { colors, spacing } from '@/shared/theme';

import { AppText } from './AppText';
import { Icon, type IconName } from './Icon';

export interface ListRowProps {
  label: string;
  description?: string;
  icon?: IconName;
  value?: string;
  right?: ReactNode;
  onPress?: () => void;
  accessibilityHint?: string;
  showDivider?: boolean;
}

/** Settings-style row. With `onPress` it is a button with a chevron. */
export function ListRow({ label, description, icon, value, right, onPress, accessibilityHint, showDivider = true }: ListRowProps) {
  const content = (
    <>
      {icon ? (
        <View style={styles.iconBox}>
          <Icon name={icon} size={18} color="textSecondary" />
        </View>
      ) : null}
      <View style={styles.text}>
        <AppText variant="bodyMedium">{label}</AppText>
        {description ? (
          <AppText variant="caption" color="textMuted">
            {description}
          </AppText>
        ) : null}
      </View>
      {value ? (
        <AppText variant="caption" color="textSecondary" numberOfLines={1} style={styles.value}>
          {value}
        </AppText>
      ) : null}
      {right}
      {onPress ? <Icon name="chevron-forward" size={18} color="textMuted" /> : null}
    </>
  );

  const rowStyle = [styles.row, showDivider && styles.divider];
  if (onPress) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={value ? `${label}, ${value}` : label}
        accessibilityHint={accessibilityHint}
        onPress={onPress}
        style={({ pressed }) => [...rowStyle, pressed && styles.pressed]}
      >
        {content}
      </Pressable>
    );
  }
  return <View style={rowStyle}>{content}</View>;
}

const styles = StyleSheet.create({
  row: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  divider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  pressed: { backgroundColor: colors.surface2 },
  iconBox: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  text: { flex: 1, gap: 2 },
  value: { maxWidth: 160 },
});
