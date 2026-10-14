import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { useAuth } from '@/features/auth/store';
import { api, isApiError, queryKeys } from '@/shared/api';
import type { ApiResponse } from '@/shared/api/client';
import { toEntry } from '@/shared/api/mappers';
import type { WireTimerState } from '@/shared/api/wire';
import { uuidV4 } from '@/shared/lib/id';
import { isActiveEntry, type ActiveTimeEntry, type Project } from '@/shared/types/domain';

import { estimateOffset, serverNow, useServerClock } from './clock';
import { lastTransitionMs, pauseTimer, resumeTimer, startTimer, stopTimer, TimerError } from './model';
import { saveTimerSnapshot } from './persistence';

/** Cache shape of the active-timer query. */
export interface TimerData {
  entry: ActiveTimeEntry | null;
}

/** Stores a server-confirmed state: updates the clock offset and the persisted snapshot. */
function acceptTimerState(res: ApiResponse<WireTimerState>): TimerData {
  const offset = estimateOffset(res.data.server_time, res.sentAt, res.receivedAt);
  useServerClock.getState().setOffset(offset);
  const mapped = res.data.entry ? toEntry(res.data.entry) : null;
  const entry = mapped && isActiveEntry(mapped) ? mapped : null;
  const userId = useAuth.getState().user?.id;
  if (userId) void saveTimerSnapshot(userId, entry, offset);
  return { entry };
}

export async function fetchTimer(signal?: AbortSignal): Promise<TimerData> {
  return acceptTimerState(await api.requestWithMeta<WireTimerState>('/timer/current', { signal }));
}

/** The active timer, if any. Refetched on focus/foreground and every minute (other devices may change it). */
export function useTimerQuery() {
  return useQuery({
    queryKey: queryKeys.timer,
    queryFn: ({ signal }) => fetchTimer(signal),
    staleTime: 10_000,
    refetchInterval: 60_000,
  });
}

// ---------- commands ----------

type CommandKind = 'start' | 'pause' | 'resume' | 'stop' | 'discard';

interface CommandBase {
  kind: CommandKind;
  /** One Idempotency-Key per user action; automatic retries reuse it, so a command applies at most once. */
  key: string;
  /** Moment of the tap on the server clock. Retries send the same value, so delays never add time. */
  at: string;
}

export type TimerCommand =
  | (CommandBase & {
      kind: 'start';
      entryId: string;
      project: Pick<Project, 'id' | 'name' | 'color' | 'billingType' | 'hourlyRate' | 'currency'>;
      taskId: string | null;
      taskTitle?: string;
      description: string;
    })
  | (CommandBase & { kind: 'pause' | 'resume' | 'discard'; entryId: string })
  | (CommandBase & { kind: 'stop'; entryId: string; description?: string });

type CommandInput =
  | Omit<Extract<TimerCommand, { kind: 'start' }>, 'key' | 'at' | 'entryId'>
  | Omit<Extract<TimerCommand, { kind: 'pause' | 'resume' | 'discard' }>, 'key' | 'at'>
  | Omit<Extract<TimerCommand, { kind: 'stop' }>, 'key' | 'at'>;

/**
 * Freezes a user action into a command: idempotency key, client-generated entry ID (start) and the
 * timestamp of the tap. `at` is never earlier than the last known transition, so small clock-offset
 * jitter cannot produce TIMESTAMP_OUT_OF_ORDER.
 */
export function prepareCommand(input: CommandInput, current: ActiveTimeEntry | null, nowMs: number = serverNow()): TimerCommand {
  const floor = current ? lastTransitionMs(current) + 1 : 0;
  const at = new Date(Math.max(nowMs, floor)).toISOString();
  const key = uuidV4();
  if (input.kind === 'start') return { ...input, key, at, entryId: uuidV4() };
  return { ...input, key, at } as TimerCommand;
}

function commandRequest(cmd: TimerCommand, withAt: boolean) {
  const at = withAt ? { at: cmd.at } : {};
  switch (cmd.kind) {
    case 'start':
      return {
        path: '/timer/start',
        body: { id: cmd.entryId, project_id: cmd.project.id, task_id: cmd.taskId, description: cmd.description.trim(), ...at },
      };
    case 'stop':
      return {
        path: `/timer/${cmd.entryId}/stop`,
        body: { ...(cmd.description !== undefined ? { description: cmd.description.trim() } : {}), ...at },
      };
    case 'discard':
      return { path: `/timer/${cmd.entryId}/discard`, body: undefined };
    default:
      return { path: `/timer/${cmd.entryId}/${cmd.kind}`, body: at };
  }
}

const CLOCK_CODES = new Set(['TIMESTAMP_OUT_OF_ORDER', 'TIMESTAMP_IN_FUTURE', 'TIMESTAMP_TOO_OLD', 'TIME_OVERLAP']);

/** Sends a command; transient failures are retried with the same key and body (safe replays). */
export async function sendTimerCommand(cmd: TimerCommand, attempts = 3): Promise<TimerData> {
  const send = async (key: string, withAt: boolean) => {
    const { path, body } = commandRequest(cmd, withAt);
    return acceptTimerState(
      await api.requestWithMeta<WireTimerState>(path, { method: 'POST', body, idempotencyKey: key }),
    );
  };

  for (let attempt = 1; ; attempt++) {
    try {
      return await send(cmd.key, true);
    } catch (error) {
      if (isApiError(error) && CLOCK_CODES.has(error.code)) {
        // Our estimate of the server clock disagreed with the server (e.g. another device acted):
        // let the server stamp the command itself. New key, because the body changes.
        return send(`${cmd.key}-srv`, false);
      }
      const transient = isApiError(error) && error.isTransient;
      if (!transient || attempt >= attempts) throw error;
      await new Promise((r) => setTimeout(r, 400 * 2 ** (attempt - 1)));
    }
  }
}

/** Optimistic next state, computed with the same pure state machine the server enforces. */
export function optimisticTimer(current: ActiveTimeEntry | null, cmd: TimerCommand): TimerData | null {
  try {
    switch (cmd.kind) {
      case 'start':
        return {
          entry: startTimer(current ?? undefined, {
            id: cmd.entryId,
            project: cmd.project,
            taskId: cmd.taskId,
            taskTitle: cmd.taskTitle,
            description: cmd.description,
            rate: {
              rate: cmd.project.billingType === 'hourly' ? cmd.project.hourlyRate : null,
              currency: cmd.project.currency,
              source: cmd.project.hourlyRate ? 'project' : 'none',
            },
            at: cmd.at,
          }),
        };
      case 'pause':
        return current ? { entry: pauseTimer(current, cmd.at) } : null;
      case 'resume':
        return current ? { entry: resumeTimer(current, cmd.at) } : null;
      case 'stop':
        if (current) stopTimer(current, cmd.at); // validates the transition
        return { entry: null };
      case 'discard':
        return { entry: null };
    }
  } catch (error) {
    if (error instanceof TimerError) return null;
    throw error;
  }
}

function invalidateAfterHistoryChange(qc: QueryClient) {
  void qc.invalidateQueries({ queryKey: queryKeys.entries.all });
  void qc.invalidateQueries({ queryKey: queryKeys.projects.all });
  void qc.invalidateQueries({ queryKey: queryKeys.clients.all });
  void qc.invalidateQueries({ queryKey: queryKeys.money.all }); // dashboard, analytics, project summaries
  void qc.invalidateQueries({ queryKey: queryKeys.invoices.all }); // billable entries for new invoices
}

/**
 * Timer commands with optimistic UI. On failure the previous state is restored and the server
 * state is refetched (the server is the source of truth for conflicts such as another device
 * having stopped the timer).
 */
export function useTimerCommands() {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationKey: ['timer', 'command'],
    mutationFn: (cmd: TimerCommand) => sendTimerCommand(cmd),
    onMutate: async (cmd) => {
      await qc.cancelQueries({ queryKey: queryKeys.timer });
      const previous = qc.getQueryData<TimerData>(queryKeys.timer);
      const next = optimisticTimer(previous?.entry ?? null, cmd);
      if (next) qc.setQueryData<TimerData>(queryKeys.timer, next);
      return { previous };
    },
    onError: (_error, _cmd, context) => {
      if (context?.previous) qc.setQueryData(queryKeys.timer, context.previous);
      void qc.invalidateQueries({ queryKey: queryKeys.timer });
    },
    onSuccess: (data, cmd) => {
      qc.setQueryData<TimerData>(queryKeys.timer, data);
      if (cmd.kind === 'stop' || cmd.kind === 'discard' || cmd.kind === 'start') invalidateAfterHistoryChange(qc);
    },
  });

  const current = () => qc.getQueryData<TimerData>(queryKeys.timer)?.entry ?? null;
  const run = (input: CommandInput) => mutation.mutateAsync(prepareCommand(input, current()));

  return {
    pending: mutation.isPending,
    error: mutation.error,
    reset: mutation.reset,
    /** Resolves to true when the server confirmed the command. Failures are surfaced through `error`. */
    run: (input: CommandInput): Promise<boolean> =>
      run(input).then(
        () => true,
        () => false,
      ),
  };
}

/** Updates the description of the running entry (debounced by the caller). */
export function useUpdateActiveDescription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ entryId, description }: { entryId: string; description: string }) =>
      acceptTimerState(
        await api.requestWithMeta<WireTimerState>(`/timer/${entryId}`, { method: 'PATCH', body: { description: description.trim() } }),
      ),
    onSuccess: (data) => qc.setQueryData(queryKeys.timer, data),
  });
}
