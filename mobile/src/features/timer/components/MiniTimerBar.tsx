import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, View } from 'react-native';

import { formatClock } from '@/shared/lib/time';
import { AppText, IconButton } from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

export interface MiniTimerBarProps {
  projectName: string;
  projectColor: string;
  description: string;
  seconds: number;
  status: 'running' | 'paused';
  onOpen: () => void;
  onToggle: () => void;
}

/** Compact active-timer bar shown above the tab bar on every tab except Time. */
export function MiniTimerBar({ projectName, projectColor, description, seconds, status, onOpen, onToggle }: MiniTimerBarProps) {
  const { t } = useTranslation();
  const statusLabel = t(status === 'running' ? 'timer.statusRunning' : 'timer.statusPaused');
  return (
    <View style={styles.outer}>
      <Pressable
        testID="mini-timer-bar"
        accessibilityRole="button"
        accessibilityLabel={t('timer.miniA11y', { project: projectName, status: statusLabel })}
        onPress={onOpen}
        style={({ pressed }) => [styles.bar, pressed && styles.pressed]}
      >
        <View style={[styles.stripe, { backgroundColor: projectColor }]} />
        <View style={styles.text}>
          <AppText variant="captionMedium" numberOfLines={1}>
            {projectName}
          </AppText>
          <AppText variant="caption" color="textMuted" numberOfLines={1}>
            {description || t('common.noDescription')}
          </AppText>
        </View>
        <AppText variant="mono" color={status === 'paused' ? 'warning' : 'textPrimary'}>
          {formatClock(seconds)}
        </AppText>
        <IconButton
          icon={status === 'running' ? 'pause' : 'play'}
          accessibilityLabel={t(status === 'running' ? 'timer.miniPause' : 'timer.miniResume')}
          variant="accent"
          size={18}
          onPress={onToggle}
        />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: { paddingHorizontal: spacing.md, paddingBottom: spacing.sm, backgroundColor: colors.bg },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingLeft: spacing.md,
    paddingRight: spacing.xs,
    paddingVertical: spacing.xs,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.accentBorder,
    backgroundColor: colors.surface2,
    overflow: 'hidden',
  },
  pressed: { backgroundColor: colors.surface3 },
  stripe: { width: 4, alignSelf: 'stretch', borderRadius: 2 },
  text: { flex: 1 },
});
