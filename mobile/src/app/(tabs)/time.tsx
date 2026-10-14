import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, View } from 'react-native';

import { useCurrentUser } from '@/features/auth/store';
import { weekRange } from '@/features/dashboard/summary';
import { useProjects, useTasks } from '@/features/projects/api';
import { useAppPreferences } from '@/features/settings/preferences';
import { useEntryRange } from '@/features/time-entries/api';
import { EntryRow } from '@/features/time-entries/components/EntryRow';
import { groupStoppedByDay } from '@/features/time-entries/grouping';
import { useTimerCommands, useUpdateActiveDescription } from '@/features/timer/api';
import { ProjectPickerSheet, type PickerProject } from '@/features/timer/components/ProjectPickerSheet';
import { StatusPill } from '@/features/timer/components/StatusPill';
import { TimerControls } from '@/features/timer/components/TimerControls';
import { TimerDisplay } from '@/features/timer/components/TimerDisplay';
import { useActiveTimer } from '@/features/timer/hooks';
import { LONG_RUNNING_SECONDS } from '@/features/timer/model';
import { amountForDuration, formatMoney } from '@/shared/lib/money';
import { formatDuration, formatLongDay, formatRelativeDay, formatTimeOfDay, startOfWeek } from '@/shared/lib/time';
import {
  AppText,
  Card,
  EmptyState,
  ErrorState,
  Icon,
  InlineError,
  Input,
  LoadingState,
  OfflineBanner,
  Screen,
  ScreenHeader,
  SectionHeader,
} from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

/** Description edits of a running entry are saved after a short pause in typing. */
const DESCRIPTION_SAVE_DELAY_MS = 800;

export default function TimeScreen() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const active = useActiveTimer();
  const commands = useTimerCommands();
  const updateDescription = useUpdateActiveDescription();
  const longRunningWarning = useAppPreferences((s) => s.longRunningWarning);
  const projects = useProjects();
  const [refreshing, setRefreshing] = useState(false);

  const today = new Date();
  const weekStartDate = startOfWeek(today, user.weekStart);
  const week = useEntryRange(weekRange(weekStartDate));

  const trackable = useMemo(() => (projects.data ?? []).filter((p) => p.status === 'active' && p.archivedAt === null), [projects.data]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [chosenProjectId, setChosenProjectId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [description, setDescription] = useState('');
  const [draft, setDraft] = useState<{ entryId: string; text: string } | null>(null);

  // Default to the most recently tracked project that can still be tracked.
  const defaultProjectId = useMemo(() => {
    const recent = week.data?.entries.find((e) => trackable.some((p) => p.id === e.projectId));
    return recent?.projectId ?? trackable[0]?.id ?? null;
  }, [week.data, trackable]);
  const projectId = chosenProjectId ?? defaultProjectId;
  const tasks = useTasks(projectId ?? undefined);

  // Debounced save of the running entry's description.
  useEffect(() => {
    if (!draft || !active || draft.entryId !== active.entry.id || draft.text === active.entry.description) return;
    const id = setTimeout(() => updateDescription.mutate({ entryId: draft.entryId, description: draft.text }), DESCRIPTION_SAVE_DELAY_MS);
    return () => clearTimeout(id);
  }, [draft, active, updateDescription]);

  const pickerItems: PickerProject[] = useMemo(
    () => trackable.map((project) => ({ project, clientName: project.clientName, tasks: project.id === projectId ? (tasks.data ?? []) : [] })),
    [trackable, projectId, tasks.data],
  );

  const status = active ? active.entry.status : 'idle';
  const shownProject = active ? active.entry.project : trackable.find((p) => p.id === projectId);
  const shownTaskTitle = active ? active.entry.task?.title : tasks.data?.find((x) => x.id === taskId)?.title;
  const activeDescription = active ? (draft?.entryId === active.entry.id ? draft.text : active.entry.description) : description;

  const groups = useMemo(() => groupStoppedByDay(week.data?.entries ?? []), [week.data]);

  const estimate =
    active && active.entry.billable && active.entry.hourlyRate
      ? { amount: amountForDuration(active.seconds, active.entry.hourlyRate), rate: active.entry.hourlyRate, currency: active.entry.currency }
      : null;

  const refresh = () => {
    setRefreshing(true);
    void Promise.all([week.refetch(), projects.refetch()]).finally(() => setRefreshing(false));
  };

  const start = () => {
    const project = trackable.find((p) => p.id === projectId);
    if (!project) return;
    const taskTitle = tasks.data?.find((x) => x.id === taskId)?.title;
    void commands.run({ kind: 'start', project, taskId, taskTitle, description });
    setDescription('');
  };

  return (
    <Screen testID="time-screen" onRefresh={refresh} refreshing={refreshing}>
      <ScreenHeader subtitle={formatLongDay(today)} title={t('timer.title')} />
      <OfflineBanner />

      <Card variant="raised" padding="xl" style={styles.timerCard}>
        <View style={styles.cardTop}>
          <StatusPill status={status} />
          {active ? (
            <AppText variant="monoSmall" color="textMuted">
              {t('timer.since', { time: formatTimeOfDay(new Date(active.entry.startedAt)) })}
            </AppText>
          ) : null}
        </View>

        <TimerDisplay seconds={active?.seconds ?? 0} status={status} />

        {estimate ? (
          <AppText variant="monoSmall" color="textSecondary" align="center" testID="timer-estimate">
            {t('timer.estimate', {
              amount: formatMoney(estimate.amount, estimate.currency),
              rate: formatMoney(estimate.rate, estimate.currency),
            })}
          </AppText>
        ) : active ? (
          <AppText variant="caption" color="textMuted" align="center">
            {t(active.entry.billable ? 'timer.noRate' : 'timer.nonBillable')}
          </AppText>
        ) : null}

        <Pressable
          testID="project-selector"
          accessibilityRole="button"
          accessibilityLabel={shownProject ? t('timer.projectA11y', { name: shownProject.name }) : t('timer.chooseProject')}
          accessibilityHint={t(active ? 'timer.projectLockedHint' : 'timer.openPickerHint')}
          disabled={active !== null}
          onPress={() => setPickerOpen(true)}
          style={({ pressed }) => [styles.selector, pressed && styles.selectorPressed]}
        >
          <View style={[styles.dot, { backgroundColor: shownProject?.color ?? colors.borderStrong }]} />
          <View style={styles.flex}>
            <AppText variant="bodyMedium" color={shownProject ? 'textPrimary' : 'textMuted'} numberOfLines={1}>
              {shownProject?.name ?? t('timer.chooseProject')}
            </AppText>
            <AppText variant="caption" color="textMuted" numberOfLines={1}>
              {shownTaskTitle ?? t('common.noTask')}
            </AppText>
          </View>
          {active ? <Icon name="lock-closed-outline" size={16} color="textMuted" /> : <Icon name="chevron-down" size={18} color="textMuted" />}
        </Pressable>

        {!active && projects.isSuccess && trackable.length === 0 ? (
          <AppText variant="caption" color="textMuted" align="center">
            {t('projects.needClient')}
          </AppText>
        ) : null}

        <Input
          testID="timer-description"
          placeholder={t('timer.descriptionPlaceholder')}
          value={activeDescription}
          onChangeText={(text) => (active ? setDraft({ entryId: active.entry.id, text }) : setDescription(text))}
          maxLength={500}
          returnKeyType="done"
          accessibilityLabel={t('timer.descriptionA11y')}
        />

        {commands.error ? <InlineError error={commands.error} testID="timer-error" /> : null}

        {active && longRunningWarning && active.seconds >= LONG_RUNNING_SECONDS ? (
          <View style={styles.warning} accessibilityRole="alert">
            <Icon name="hourglass-outline" size={16} color="warning" />
            <AppText variant="caption" color="warning" style={styles.flex}>
              {t('timer.longRunning')}
            </AppText>
          </View>
        ) : null}

        <TimerControls
          status={status}
          busy={commands.pending}
          startDisabled={!projectId || !shownProject}
          onStart={start}
          onPause={() => active && void commands.run({ kind: 'pause', entryId: active.entry.id })}
          onResume={() => active && void commands.run({ kind: 'resume', entryId: active.entry.id })}
          onStop={() => {
            if (!active) return;
            const pending = draft?.entryId === active.entry.id && draft.text !== active.entry.description ? draft.text : undefined;
            void commands.run({ kind: 'stop', entryId: active.entry.id, description: pending });
            setDraft(null);
          }}
          onDiscard={() => {
            if (!active) return;
            void commands.run({ kind: 'discard', entryId: active.entry.id });
            setDraft(null);
          }}
        />
      </Card>

      <View style={styles.section}>
        <SectionHeader title={t('timer.thisWeek')} meta={formatDuration(groups.reduce((a, g) => a + g.totalSeconds, 0))} />
        {week.isPending ? (
          <Card>
            <LoadingState rows={2} />
          </Card>
        ) : week.isError && !week.data ? (
          <ErrorState message={t('errors.NETWORK_ERROR')} onRetry={() => void week.refetch()} retrying={week.isFetching} />
        ) : groups.length === 0 ? (
          <Card>
            <EmptyState compact icon="time-outline" title={t('timer.emptyWeek')} message={t('timer.emptyWeekHint')} />
          </Card>
        ) : (
          groups.map((group) => (
            <View key={group.key} style={styles.group}>
              <View style={styles.groupHeader}>
                <AppText variant="captionMedium" color="textSecondary">
                  {formatRelativeDay(group.date, today, { today: t('common.today'), yesterday: t('common.yesterday') })}
                </AppText>
                <AppText variant="monoSmall" color="textMuted">
                  {formatDuration(group.totalSeconds)}
                </AppText>
              </View>
              <Card padding="md" style={styles.groupCard}>
                {group.entries.map((e, i) => (
                  <View key={e.id} style={i > 0 ? styles.rowDivider : null}>
                    <EntryRow entry={e} />
                  </View>
                ))}
              </Card>
            </View>
          ))
        )}
      </View>

      <ProjectPickerSheet
        visible={pickerOpen}
        items={pickerItems}
        selectedProjectId={projectId}
        selectedTaskId={taskId}
        onSelectProject={(id) => {
          setChosenProjectId(id);
          setTaskId(null);
        }}
        onSelectTask={setTaskId}
        onClose={() => setPickerOpen(false)}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  timerCard: { gap: spacing.lg },
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  selector: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface1,
  },
  selectorPressed: { backgroundColor: colors.surface3 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  warning: { flexDirection: 'row', gap: spacing.sm, padding: spacing.md, borderRadius: radii.md, backgroundColor: colors.warningSoft },
  section: { gap: spacing.md },
  group: { gap: spacing.sm },
  groupHeader: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: spacing.xs },
  groupCard: { paddingVertical: spacing.xs },
  rowDivider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
});
