/** 4-pt spacing scale. Use these tokens for padding, margin and gap. */
export const spacing = {
  none: 0,
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  huge: 48,
} as const;

export const radii = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 22,
  pill: 999,
} as const;

/** Minimum touch target (iOS HIG 44pt, Material 48dp — we use 44 with hitSlop where smaller). */
export const touchTarget = 44;

export const layout = {
  screenPadding: spacing.lg,
  maxContentWidth: 640,
} as const;

export type SpacingToken = keyof typeof spacing;
