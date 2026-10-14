import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/shared/ui';
import { spacing } from '@/shared/theme';

import type { TimerUiStatus } from './StatusPill';

export interface TimerControlsProps {
  status: TimerUiStatus;
  startDisabled?: boolean;
  /** Disables every control while a command is in flight (prevents double submits). */
  busy?: boolean;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onDiscard: () => void;
}

export function TimerControls({ status, startDisabled = false, busy = false, onStart, onPause, onResume, onStop, onDiscard }: TimerControlsProps) {
  const { t } = useTranslation();
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  useEffect(() => {
    if (!confirmDiscard) return;
    const id = setTimeout(() => setConfirmDiscard(false), 4000);
    return () => clearTimeout(id);
  }, [confirmDiscard]);

  if (status === 'idle') {
    return (
      <Button
        testID="timer-start"
        label={t('timer.start')}
        icon="play"
        size="lg"
        fullWidth
        disabled={startDisabled || busy}
        onPress={onStart}
      />
    );
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        {status === 'running' ? (
          <Button testID="timer-pause" disabled={busy} label={t('timer.pause')} icon="pause" size="lg" variant="secondary" style={styles.flex} onPress={onPause} />
        ) : (
          <Button testID="timer-resume" disabled={busy} label={t('timer.resume')} icon="play" size="lg" variant="secondary" style={styles.flex} onPress={onResume} />
        )}
        <Button testID="timer-stop" disabled={busy} label={t('timer.stop')} icon="stop" size="lg" style={styles.flex} onPress={onStop} />
      </View>
      <Button
        testID="timer-discard"
        disabled={busy}
        label={confirmDiscard ? t('timer.discardConfirm') : t('timer.discard')}
        icon="trash-outline"
        size="sm"
        variant={confirmDiscard ? 'danger' : 'ghost'}
        onPress={() => {
          if (confirmDiscard) {
            setConfirmDiscard(false);
            onDiscard();
          } else {
            setConfirmDiscard(true);
          }
        }}
        style={styles.discard}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  row: { flexDirection: 'row', gap: spacing.md },
  flex: { flex: 1 },
  discard: { alignSelf: 'center' },
});
