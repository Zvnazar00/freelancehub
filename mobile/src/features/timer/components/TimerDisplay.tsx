import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { formatClock, formatDuration } from '@/shared/lib/time';
import { AppText } from '@/shared/ui';

import type { TimerUiStatus } from './StatusPill';

export interface TimerDisplayProps {
  seconds: number;
  status: TimerUiStatus;
  size?: 'large' | 'medium';
}

export function TimerDisplay({ seconds, status, size = 'large' }: TimerDisplayProps) {
  const { t } = useTranslation();
  return (
    <View
      accessible
      accessibilityRole="timer"
      accessibilityLabel={t('timer.elapsedA11y', { duration: formatDuration(seconds) }) + (status === 'paused' ? t('timer.pausedSuffix') : '')}
      style={styles.wrap}
    >
      <AppText
        testID="timer-display"
        variant={size === 'large' ? 'timer' : 'monoLarge'}
        color={status === 'idle' ? 'textMuted' : status === 'paused' ? 'textSecondary' : 'textPrimary'}
        maxFontSizeMultiplier={1.2}
        adjustsFontSizeToFit
        numberOfLines={1}
      >
        {formatClock(seconds)}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center' },
});
