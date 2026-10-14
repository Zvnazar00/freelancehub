import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, View } from 'react-native';

import { formatDuration } from '@/shared/lib/time';
import type { Task } from '@/shared/types/domain';
import { AppText, Badge, Icon } from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

import { priorityTone } from '../labels';

export interface TaskRowProps {
  task: Task;
  onToggleDone: () => void;
}

export function TaskRow({ task, onToggleDone }: TaskRowProps) {
  const { t } = useTranslation();
  const done = task.status === 'done';
  return (
    <View style={styles.row}>
      <Pressable
        testID={`task-toggle-${task.id}`}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: done }}
        accessibilityLabel={done ? t('tasks.doneA11y', { title: task.title }) : task.title}
        onPress={onToggleDone}
        hitSlop={10}
        style={[styles.check, done && styles.checkDone]}
      >
        {done ? <Icon name="checkmark" size={14} color="textOnAccent" /> : null}
      </Pressable>
      <View style={styles.text}>
        <AppText variant="bodyMedium" color={done ? 'textMuted' : 'textPrimary'} style={done ? styles.strike : null} numberOfLines={2}>
          {task.title}
        </AppText>
        <View style={styles.meta}>
          {task.status === 'in_progress' ? <Badge label={t('tasks.inProgress')} tone="info" /> : null}
          {!done ? <Badge label={t(`tasks.priority.${task.priority}`)} tone={priorityTone[task.priority]} /> : null}
        </View>
      </View>
      <AppText variant="monoSmall" color="textMuted">
        {task.estimateMinutes ? formatDuration(task.estimateMinutes * 60) : ''}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md },
  check: {
    width: 24,
    height: 24,
    borderRadius: radii.sm - 1,
    borderWidth: 1.5,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkDone: { backgroundColor: colors.accentStrong, borderColor: colors.accentStrong },
  text: { flex: 1, gap: spacing.xs },
  meta: { flexDirection: 'row', gap: spacing.xs },
  strike: { textDecorationLine: 'line-through' },
});
