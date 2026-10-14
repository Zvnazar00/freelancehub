import { StyleSheet, View } from 'react-native';

import { colors, radii, spacing, type ColorToken } from '@/shared/theme';

import { AppText } from './AppText';
import { Icon, type IconName } from './Icon';

export type BadgeTone = 'neutral' | 'accent' | 'info' | 'success' | 'warning' | 'danger';

const tones: Record<BadgeTone, { bg: string; fg: ColorToken }> = {
  neutral: { bg: colors.surface3, fg: 'textSecondary' },
  accent: { bg: colors.accentSoft, fg: 'accentText' },
  info: { bg: colors.infoSoft, fg: 'info' },
  success: { bg: colors.successSoft, fg: 'success' },
  warning: { bg: colors.warningSoft, fg: 'warning' },
  danger: { bg: colors.dangerSoft, fg: 'danger' },
};

export interface BadgeProps {
  label: string;
  tone?: BadgeTone;
  icon?: IconName;
  dot?: boolean;
}

export function Badge({ label, tone = 'neutral', icon, dot = false }: BadgeProps) {
  const t = tones[tone];
  return (
    <View style={[styles.badge, { backgroundColor: t.bg }]}>
      {dot ? <View style={[styles.dot, { backgroundColor: colors[t.fg] }]} /> : null}
      {icon ? <Icon name={icon} size={12} color={t.fg} /> : null}
      <AppText variant="captionMedium" color={t.fg} style={styles.label}>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radii.pill,
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  label: { fontSize: 12, lineHeight: 16 },
});
