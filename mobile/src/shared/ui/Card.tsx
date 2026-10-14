import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { colors, radii, spacing, type SpacingToken } from '@/shared/theme';

export type CardVariant = 'surface' | 'raised' | 'outline' | 'accent';

export interface CardProps {
  children: ReactNode;
  variant?: CardVariant;
  padding?: SpacingToken;
  onPress?: () => void;
  accessibilityLabel?: string;
  accessibilityHint?: string;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

const variants: Record<CardVariant, ViewStyle> = {
  surface: { backgroundColor: colors.surface1, borderColor: colors.border },
  raised: { backgroundColor: colors.surface2, borderColor: colors.borderStrong },
  outline: { backgroundColor: colors.transparent, borderColor: colors.border, borderStyle: 'dashed' },
  accent: { backgroundColor: colors.accentSoft, borderColor: colors.accentBorder },
};

export function Card({
  children,
  variant = 'surface',
  padding = 'lg',
  onPress,
  accessibilityLabel,
  accessibilityHint,
  style,
  testID,
}: CardProps) {
  const base = [styles.card, variants[variant], { padding: spacing[padding] }];

  if (onPress) {
    return (
      <Pressable
        testID={testID}
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
        accessibilityHint={accessibilityHint}
        style={({ pressed }) => [...base, pressed && styles.pressed, style]}
      >
        {children}
      </Pressable>
    );
  }

  return (
    <View testID={testID} style={[...base, style]}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.lg,
    borderWidth: 1,
  },
  pressed: {
    backgroundColor: colors.surface2,
    transform: [{ scale: 0.99 }],
  },
});
