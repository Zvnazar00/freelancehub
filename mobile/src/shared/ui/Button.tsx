import { ActivityIndicator, Pressable, StyleSheet, View, type PressableProps, type ViewStyle } from 'react-native';

import { colors, radii, spacing, type ColorToken } from '@/shared/theme';

import { AppText } from './AppText';
import { Icon, type IconName } from './Icon';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends Omit<PressableProps, 'style' | 'children'> {
  label: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  loading?: boolean;
  fullWidth?: boolean;
  style?: ViewStyle;
}

const variantStyles: Record<ButtonVariant, { bg: string; bgPressed: string; border: string; text: ColorToken }> = {
  primary: { bg: colors.accentStrong, bgPressed: colors.accentStrongPressed, border: colors.accentStrong, text: 'textOnAccent' },
  secondary: { bg: colors.surface2, bgPressed: colors.surface3, border: colors.border, text: 'textPrimary' },
  ghost: { bg: colors.transparent, bgPressed: colors.surface2, border: colors.transparent, text: 'accentText' },
  danger: { bg: colors.dangerSoft, bgPressed: 'rgba(255, 107, 107, 0.22)', border: 'rgba(255, 107, 107, 0.35)', text: 'danger' },
};

const sizeStyles: Record<ButtonSize, { height: number; paddingX: number; icon: number }> = {
  sm: { height: 36, paddingX: spacing.md, icon: 16 },
  md: { height: 46, paddingX: spacing.lg, icon: 18 },
  lg: { height: 56, paddingX: spacing.xl, icon: 20 },
};

export function Button({
  label,
  variant = 'primary',
  size = 'md',
  icon,
  loading = false,
  disabled,
  fullWidth = false,
  style,
  accessibilityLabel,
  ...rest
}: ButtonProps) {
  const v = variantStyles[variant];
  const s = sizeStyles[size];
  const isDisabled = disabled === true || loading;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: isDisabled, busy: loading }}
      disabled={isDisabled}
      hitSlop={size === 'sm' ? 4 : 0}
      style={({ pressed }) => [
        styles.base,
        {
          minHeight: s.height,
          paddingHorizontal: s.paddingX,
          backgroundColor: pressed ? v.bgPressed : v.bg,
          borderColor: v.border,
          opacity: isDisabled ? 0.45 : 1,
          alignSelf: fullWidth ? 'stretch' : 'auto',
          transform: [{ scale: pressed ? 0.985 : 1 }],
        },
        style,
      ]}
      {...rest}
    >
      {loading ? (
        <ActivityIndicator size="small" color={colors[v.text]} />
      ) : (
        <View style={styles.content}>
          {icon ? <Icon name={icon} size={s.icon} color={v.text} /> : null}
          <AppText variant={size === 'sm' ? 'captionMedium' : 'subheading'} color={v.text} numberOfLines={1}>
            {label}
          </AppText>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
});
