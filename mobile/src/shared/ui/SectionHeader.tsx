import { Pressable, StyleSheet, View } from 'react-native';

import { spacing } from '@/shared/theme';

import { AppText } from './AppText';

export interface SectionHeaderProps {
  title: string;
  meta?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function SectionHeader({ title, meta, actionLabel, onAction }: SectionHeaderProps) {
  return (
    <View style={styles.row}>
      <AppText variant="overline" color="textSecondary" accessibilityRole="header">
        {title}
      </AppText>
      <View style={styles.right}>
        {meta ? (
          <AppText variant="monoSmall" color="textMuted">
            {meta}
          </AppText>
        ) : null}
        {actionLabel && onAction ? (
          <Pressable accessibilityRole="button" onPress={onAction} hitSlop={12}>
            <AppText variant="captionMedium" color="accentText">
              {actionLabel}
            </AppText>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 24 },
  right: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
});
