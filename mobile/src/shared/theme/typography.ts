import type { TextStyle } from 'react-native';

/** Font family names registered in the root layout via expo-font. */
export const fontFamilies = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
  mono: 'JetBrainsMono_500Medium',
  monoBold: 'JetBrainsMono_700Bold',
} as const;

const tabular: TextStyle['fontVariant'] = ['tabular-nums'];

export const typography = {
  display: { fontFamily: fontFamilies.bold, fontSize: 32, lineHeight: 38, letterSpacing: -0.6 },
  title: { fontFamily: fontFamilies.bold, fontSize: 24, lineHeight: 30, letterSpacing: -0.4 },
  heading: { fontFamily: fontFamilies.semibold, fontSize: 18, lineHeight: 24, letterSpacing: -0.2 },
  subheading: { fontFamily: fontFamilies.semibold, fontSize: 15, lineHeight: 20 },
  body: { fontFamily: fontFamilies.regular, fontSize: 15, lineHeight: 22 },
  bodyMedium: { fontFamily: fontFamilies.medium, fontSize: 15, lineHeight: 22 },
  caption: { fontFamily: fontFamilies.regular, fontSize: 13, lineHeight: 18 },
  captionMedium: { fontFamily: fontFamilies.medium, fontSize: 13, lineHeight: 18 },
  overline: {
    fontFamily: fontFamilies.semibold,
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  timer: { fontFamily: fontFamilies.monoBold, fontSize: 52, lineHeight: 60, letterSpacing: -1, fontVariant: tabular },
  monoLarge: { fontFamily: fontFamilies.monoBold, fontSize: 26, lineHeight: 32, fontVariant: tabular },
  mono: { fontFamily: fontFamilies.mono, fontSize: 15, lineHeight: 20, fontVariant: tabular },
  monoSmall: { fontFamily: fontFamilies.mono, fontSize: 13, lineHeight: 18, fontVariant: tabular },
} as const satisfies Record<string, TextStyle>;

export type TypographyVariant = keyof typeof typography;
