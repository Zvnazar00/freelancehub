import Ionicons from '@expo/vector-icons/Ionicons';
import type { ComponentProps } from 'react';
import type { ColorValue } from 'react-native';

import { colors, type ColorToken } from '@/shared/theme';

export type IconName = ComponentProps<typeof Ionicons>['name'];

export interface IconProps {
  name: IconName;
  size?: number;
  color?: ColorToken;
  /** Raw color override (e.g. project color). Prefer `color` tokens. */
  rawColor?: ColorValue;
}

export function Icon({ name, size = 20, color = 'textSecondary', rawColor }: IconProps) {
  return <Ionicons name={name} size={size} color={rawColor ?? colors[color]} accessibilityElementsHidden importantForAccessibility="no" />;
}
