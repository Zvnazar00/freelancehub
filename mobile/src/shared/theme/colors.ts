/**
 * Dark Developer palette. All UI colors must come from here — never hardcode hex values in components.
 * Contrast (WCAG AA): every text token ≥ 4.5:1 on bg and all surfaces; white on accentStrong 4.86:1.
 * `accent` is for highlights (bars, icons, borders); filled buttons use `accentStrong`.
 */
export const palette = {
  charcoal950: '#0B0C10',
  charcoal900: '#0E0F13',
  charcoal850: '#15171D',
  charcoal800: '#1C1F27',
  charcoal750: '#252935',
  charcoal700: '#2E3340',
  charcoal600: '#3A4050',
  gray300: '#ECEEF3',
  gray400: '#A3A9B8',
  gray500: '#8C93A4',
  violet400: '#A498FF',
  violet500: '#8B7CFF',
  violet600: '#6C5CE7',
  violet700: '#5B4BD6',
  blue400: '#4CC2FF',
  green400: '#3DD68C',
  amber400: '#F5B44A',
  red400: '#FF6B6B',
  white: '#FFFFFF',
} as const;

export const colors = {
  bg: palette.charcoal900,
  bgDeep: palette.charcoal950,
  surface1: palette.charcoal850,
  surface2: palette.charcoal800,
  surface3: palette.charcoal750,
  border: palette.charcoal700,
  borderStrong: palette.charcoal600,

  textPrimary: palette.gray300,
  textSecondary: palette.gray400,
  textMuted: palette.gray500,
  textOnAccent: palette.white,

  accent: palette.violet500,
  /** Filled controls with white text (4.86:1 contrast). */
  accentStrong: palette.violet600,
  accentStrongPressed: palette.violet700,
  accentSoft: 'rgba(139, 124, 255, 0.14)',
  accentBorder: 'rgba(139, 124, 255, 0.45)',
  accentText: palette.violet400,

  info: palette.blue400,
  infoSoft: 'rgba(76, 194, 255, 0.12)',
  success: palette.green400,
  successSoft: 'rgba(61, 214, 140, 0.12)',
  warning: palette.amber400,
  warningSoft: 'rgba(245, 180, 74, 0.12)',
  danger: palette.red400,
  dangerSoft: 'rgba(255, 107, 107, 0.12)',

  overlay: 'rgba(5, 6, 9, 0.72)',
  transparent: 'transparent',
} as const;

/** Project colors offered in pickers and used by demo data. */
export const projectColors = [
  '#8B7CFF',
  '#4CC2FF',
  '#3DD68C',
  '#F5B44A',
  '#FF7EB6',
  '#5EEAD4',
  '#FF8A65',
] as const;

export type ColorToken = keyof typeof colors;
