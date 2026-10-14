import { StyleSheet, View } from 'react-native';

import { projectColors, radii } from '@/shared/theme';

import { AppText } from './AppText';

export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? '?';
  const second = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : (parts[0]?.[1] ?? '');
  return (first + second).toUpperCase();
}

function colorFor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) | 0;
  return projectColors[Math.abs(hash) % projectColors.length] ?? projectColors[0];
}

export interface AvatarProps {
  name: string;
  size?: number;
}

export function Avatar({ name, size = 44 }: AvatarProps) {
  const tint = colorFor(name);
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.box, { width: size, height: size, borderColor: `${tint}55`, backgroundColor: `${tint}1F` }]}
    >
      <AppText variant="subheading" style={{ color: tint, fontSize: size * 0.36 }}>
        {initialsOf(name)}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderRadius: radii.md, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
});
