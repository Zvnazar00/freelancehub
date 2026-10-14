import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { useProjectSummary } from '@/features/analytics/api';
import { useCurrentUser } from '@/features/auth/store';
import { StatTile } from '@/features/dashboard/components/StatTile';
import { weekRange } from '@/features/dashboard/summary';
import { useCreateTask, useProject, useSetTaskStatus, useTasks } from '@/features/projects/api';
import { formatAmounts } from '@/features/projects/components/ProjectCard';
import { ProjectMoneyCard } from '@/features/projects/components/ProjectMoneyCard';
import { TaskRow } from '@/features/projects/components/TaskRow';
import { billingLabel, projectStatusTone } from '@/features/projects/labels';
import { useEntrySummary, useRecentEntries } from '@/features/time-entries/api';
import { EntryRow } from '@/features/time-entries/components/EntryRow';
import { useTimerCommands, useTimerQuery } from '@/features/timer/api';
import { errorMessageKey, isApiError } from '@/shared/api';
import { formatCalendarDate, formatDuration, formatHoursDecimal, formatWholeHours, startOfWeek } from '@/shared/lib/time';
import {
  AppText,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  IconButton,
  InlineError,
  Input,
  LoadingState,
  ProgressBar,
  Screen,
  SectionHeader,
} from '@/shared/ui';
import { colors, spacing } from '@/shared/theme';

export default function ProjectDetailScreen() {
  const { t } = useTranslation();
  const { id } = useLocalSearchParams<{ id: string }>();
  const user = useCurrentUser();
  const projectQuery = useProject(id);
  const summary = useProjectSummary(id);
  const tasksQuery = useTasks(id);
  const recent = useRecentEntries({ projectId: id }, 6);
  const week = useEntrySummary({ projectId: id, ...weekRange(startOfWeek(new Date(), user.weekStart)) }, Boolean(id));
  const timer = useTimerQuery();
  const commands = useTimerCommands();
  const createTask = useCreateTask(id ?? '');
  const setTaskStatus = useSetTaskStatus(id ?? '');
  const [newTask, setNewTask] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const project = projectQuery.data;

  if (!project) {
    const notFound = isApiError(projectQuery.error) && projectQuery.error.status === 404;
    return (
      <Screen edges={['bottom']}>
        <Stack.Screen options={{ title: t('screens.project') }} />
        {projectQuery.isPending ? (
          <LoadingState rows={4} />
        ) : notFound ? (
          <EmptyState
            icon="folder-open-outline"
            title={t('project.notFound')}
            message={t('project.notFoundHint')}
            actionLabel={t('project.back')}
            onAction={() => router.navigate('/projects')}
          />
        ) : (
          <ErrorState message={t(errorMessageKey(projectQuery.error))} onRetry={() => void projectQuery.refetch()} retrying={projectQuery.isFetching} />
        )}
      </Screen>
    );
  }

  const tasks = tasksQuery.data ?? [];
  const tracked = project.stats.trackedSeconds;
  const weekSeconds = (week.data ?? []).reduce((a, s) => a + s.seconds, 0);
  const budgetSeconds = project.budgetHours ? Number(project.budgetHours) * 3600 : null;
  const activeEntry = timer.data?.entry ?? null;
  const trackingThis = activeEntry?.projectId === project.id;
  const otherTimerRunning = activeEntry !== null && !trackingThis;
  const canTrack = project.status === 'active' && project.archivedAt === null;

  const addTask = () => {
    const title = newTask.trim();
    if (!title) return;
    createTask.mutate(title, { onSuccess: () => setNewTask('') });
  };

  const refresh = () => {
    setRefreshing(true);
    void Promise.all([projectQuery.refetch(), tasksQuery.refetch(), recent.refetch(), week.refetch(), summary.refetch()]).finally(() =>
      setRefreshing(false),
    );
  };

  return (
    <Screen edges={['bottom']} testID="project-detail-screen" onRefresh={refresh} refreshing={refreshing}>
      <Stack.Screen options={{ title: project.name }} />

      <Card>
        <View style={styles.head}>
          <View style={[styles.swatch, { backgroundColor: project.color }]} />
          <View style={styles.flex}>
            <AppText variant="heading">{project.name}</AppText>
            <AppText
              variant="captionMedium"
              color="accentText"
              accessibilityRole="link"
              onPress={() => router.push({ pathname: '/clients/[id]', params: { id: project.clientId } })}
            >
              {project.clientName}
            </AppText>
          </View>
        </View>
        <View style={styles.badges}>
          <Badge label={t(`projects.status.${project.status}`)} tone={projectStatusTone[project.status]} />
          <Badge label={billingLabel(project, t)} tone="neutral" icon="pricetag-outline" />
          {project.deadline ? (
            <Badge label={t('project.due', { date: formatCalendarDate(project.deadline) })} tone="info" icon="flag-outline" />
          ) : null}
        </View>
        {project.description ? (
          <AppText variant="caption" color="textSecondary" style={styles.desc}>
            {project.description}
          </AppText>
        ) : null}
      </Card>

      <View style={styles.tiles}>
        <StatTile
          icon="time-outline"
          label={t('projects.tracked')}
          value={formatDuration(tracked)}
          hint={t('project.weekDuration', { duration: formatDuration(weekSeconds) })}
        />
        <StatTile
          icon="cash-outline"
          label={t('projects.unbilled')}
          value={formatAmounts(project.stats.unbilled, { compact: true })}
          hint={project.billingType === 'hourly' ? t('project.notInvoiced') : billingLabel(project, t)}
        />
      </View>

      {budgetSeconds ? (
        <Card padding="md" style={styles.budget}>
          <View style={styles.budgetRow}>
            <AppText variant="captionMedium" color="textSecondary">
              {t('project.budget')}
            </AppText>
            <AppText variant="monoSmall" color="textMuted">
              {formatHoursDecimal(tracked)} / {formatWholeHours(Number(project.budgetHours))}
            </AppText>
          </View>
          <ProgressBar
            value={tracked / budgetSeconds}
            color={tracked / budgetSeconds > 0.85 ? colors.warning : project.color}
            height={8}
            accessibilityLabel={t('projects.budgetUsedA11y', { percent: Math.round((tracked / budgetSeconds) * 100) })}
          />
        </Card>
      ) : null}

      <View style={styles.actions}>
        {trackingThis ? (
          <Button label={t('project.openTimer')} icon="timer-outline" variant="secondary" fullWidth onPress={() => router.navigate('/time')} />
        ) : (
          <Button
            testID="project-start-timer"
            label={t('project.startTimer')}
            icon="play"
            fullWidth
            loading={commands.pending}
            disabled={otherTimerRunning || !canTrack}
            onPress={() => {
              void commands.run({ kind: 'start', project, taskId: null, description: '' }).then((ok) => ok && router.navigate('/time'));
            }}
          />
        )}
        {otherTimerRunning ? (
          <AppText variant="caption" color="textMuted" align="center">
            {t('project.otherRunning')}
          </AppText>
        ) : !canTrack ? (
          <AppText variant="caption" color="textMuted" align="center">
            {t('project.completedNoTrack')}
          </AppText>
        ) : null}
        {commands.error ? <InlineError error={commands.error} /> : null}
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('projectMoney.title')} />
        {summary.data ? (
          <ProjectMoneyCard summary={summary.data} color={project.color} />
        ) : summary.isError ? (
          <InlineError error={summary.error} />
        ) : (
          <Card>
            <LoadingState rows={2} />
          </Card>
        )}
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('project.tasks')} meta={t('project.tasksDone', { done: tasks.filter((x) => x.status === 'done').length, total: tasks.length })} />
        <Card padding="md" style={styles.listCard}>
          {tasksQuery.isPending ? (
            <LoadingState rows={2} />
          ) : tasks.length === 0 ? (
            <EmptyState compact icon="checkbox-outline" title={t('project.noTasks')} message={t('project.noTasksHint')} />
          ) : (
            tasks.map((task, i) => (
              <View key={task.id} style={i > 0 ? styles.divider : null}>
                <TaskRow
                  task={task}
                  onToggleDone={() => setTaskStatus.mutate({ id: task.id, status: task.status === 'done' ? 'todo' : 'done' })}
                />
              </View>
            ))
          )}
          <View style={[styles.addRow, tasks.length > 0 && styles.divider]}>
            <View style={styles.flex}>
              <Input
                testID="new-task-title"
                placeholder={t('project.addTaskPlaceholder')}
                accessibilityLabel={t('project.addTaskA11y')}
                value={newTask}
                onChangeText={setNewTask}
                onSubmitEditing={addTask}
                returnKeyType="done"
                maxLength={200}
              />
            </View>
            <IconButton testID="add-task" icon="add" variant="accent" accessibilityLabel={t('project.addTask')} onPress={addTask} disabled={!newTask.trim() || createTask.isPending} />
          </View>
          {createTask.error || setTaskStatus.error ? <InlineError error={createTask.error ?? setTaskStatus.error} /> : null}
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('project.recentEntries')} />
        <Card padding="md" style={styles.listCard}>
          {recent.isPending ? (
            <LoadingState rows={2} />
          ) : (recent.data ?? []).length === 0 ? (
            <EmptyState compact icon="time-outline" title={t('project.noEntries')} message={t('project.noEntriesHint')} />
          ) : (
            (recent.data ?? []).map((e, i) => (
              <View key={e.id} style={i > 0 ? styles.divider : null}>
                <EntryRow entry={e} />
              </View>
            ))
          )}
        </Card>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  head: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  swatch: { width: 12, height: 44, borderRadius: 6 },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.lg },
  desc: { marginTop: spacing.md },
  tiles: { flexDirection: 'row', gap: spacing.md },
  budget: { gap: spacing.sm },
  budgetRow: { flexDirection: 'row', justifyContent: 'space-between' },
  actions: { gap: spacing.sm },
  section: { gap: spacing.md },
  listCard: { paddingVertical: spacing.xs },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  addRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.md },
});
