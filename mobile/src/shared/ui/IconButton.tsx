import { Pressable, StyleSheet } from 'react-native';

import { colors, radii, touchTarget, type ColorToken } from '@/shared/theme';

import { Icon, type IconName } from './Icon';

export interface IconButtonProps {
  icon: IconName;
  accessibilityLabel: string;
  onPress: () => void;
  variant?: 'surface' | 'accent' | 'plain';
  color?: ColorToken;
  size?: number;
  disabled?: boolean;
  testID?: string;
}

export function IconButton({
  icon,
  accessibilityLabel,
  onPress,
  variant = 'surface',
  color,
  size = 20,
  disabled = false,
  testID,
}: IconButtonProps) {
  const iconColor: ColorToken = color ?? (variant === 'accent' ? 'textOnAccent' : 'textPrimary');
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        variant === 'surface' && { backgroundColor: pressed ? colors.surface3 : colors.surface2, borderColor: colors.border },
        variant === 'accent' && { backgroundColor: pressed ? colors.accentStrongPressed : colors.accentStrong, borderColor: colors.accentStrong },
        variant === 'plain' && { backgroundColor: pressed ? colors.surface2 : colors.transparent, borderColor: colors.transparent },
        disabled && { opacity: 0.45 },
      ]}
    >
      <Icon name={icon} size={size} color={iconColor} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    width: touchTarget,
    height: touchTarget,
    borderRadius: radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
