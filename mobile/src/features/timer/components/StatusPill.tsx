import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Animated, StyleSheet, View } from 'react-native';

import { AppText } from '@/shared/ui';
import { colors, radii, spacing, type ColorToken } from '@/shared/theme';

export type TimerUiStatus = 'idle' | 'running' | 'paused';

const config = {
  idle: { label: 'timer.statusIdle', color: 'textMuted', bg: colors.surface2 },
  running: { label: 'timer.statusRunning', color: 'success', bg: colors.successSoft },
  paused: { label: 'timer.statusPaused', color: 'warning', bg: colors.warningSoft },
} as const satisfies Record<TimerUiStatus, { label: string; color: ColorToken; bg: string }>;

export function StatusPill({ status }: { status: TimerUiStatus }) {
  const { t } = useTranslation();
  const [pulse] = useState(() => new Animated.Value(1));
  const c = config[status];
  const label = t(c.label);

  useEffect(() => {
    if (status !== 'running') {
      pulse.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 0.25, duration: 800, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 800, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [status, pulse]);

  return (
    <View style={[styles.pill, { backgroundColor: c.bg }]} accessibilityLabel={t('timer.statusA11y', { status: label })}>
      <Animated.View style={[styles.dot, { backgroundColor: colors[c.color], opacity: pulse }]} />
      <AppText variant="captionMedium" color={c.color}>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs + 2,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radii.pill,
    alignSelf: 'flex-start',
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
});
