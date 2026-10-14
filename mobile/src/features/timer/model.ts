import { amountForDuration } from '@/shared/lib/money';
import type { ActiveTimeEntry, CurrencyCode, DecimalString, IsoDateTime, Project, RateSource, TimeEntry, TimeEntryPause } from '@/shared/types/domain';

/** Rate snapshot of a new entry (resolved by the server; the client only uses it for optimistic UI). */
export interface ResolvedRate {
  rate: DecimalString | null;
  currency: CurrencyCode;
  source: RateSource;
}

/**
 * Time-tracking state machine (docs/architecture.md §7).
 * Pure functions: no I/O, no Date.now() — callers pass timestamps. The backend enforces the same rules
 * authoritatively; on the client they drive optimistic updates and live elapsed-time rendering.
 *
 *   [none] --start--> running --pause--> paused --resume--> running
 *   running|paused --stop--> stopped        running|paused --discard--> [deleted]
 */

export type TimerErrorCode = 'ACTIVE_TIMER_EXISTS' | 'INVALID_TRANSITION' | 'TIMESTAMP_OUT_OF_ORDER';

export class TimerError extends Error {
  constructor(
    public readonly code: TimerErrorCode,
    message: string,
  ) {
    super(message);
    this.name = 'TimerError';
  }
}

const ms = (iso: IsoDateTime) => new Date(iso).getTime();

/** Net elapsed seconds (floor), excluding paused intervals. `nowMs` is used while the entry is active. */
export function elapsedSeconds(entry: Pick<TimeEntry, 'startedAt' | 'endedAt' | 'pauses'>, nowMs: number): number {
  const start = ms(entry.startedAt);
  const end = entry.endedAt ? ms(entry.endedAt) : nowMs;
  if (end <= start) return 0;
  const pausedMs = entry.pauses.reduce((acc, p) => {
    const pStart = Math.max(ms(p.pausedAt), start);
    const pEnd = Math.min(p.resumedAt ? ms(p.resumedAt) : end, end);
    return acc + Math.max(0, pEnd - pStart);
  }, 0);
  return Math.max(0, Math.floor((end - start - pausedMs) / 1000));
}

/**
 * The instant at which a paused entry's elapsed time is frozen (start of the open pause),
 * or null when the entry is not paused. Lets the UI show exact paused time without a clock.
 */
export function pausedAtMs(entry: Pick<TimeEntry, 'status' | 'pauses'>): number | null {
  if (entry.status !== 'paused') return null;
  const open = entry.pauses.find((p) => p.resumedAt === null);
  return open ? ms(open.pausedAt) : null;
}

/** Timestamp of the last state change — new commands must not be earlier than this. */
export function lastTransitionMs(entry: TimeEntry): number {
  let last = ms(entry.startedAt);
  for (const p of entry.pauses) {
    last = Math.max(last, ms(p.pausedAt), p.resumedAt ? ms(p.resumedAt) : 0);
  }
  return last;
}

function assertNotBefore(entry: TimeEntry, at: IsoDateTime) {
  if (ms(at) < lastTransitionMs(entry)) {
    throw new TimerError('TIMESTAMP_OUT_OF_ORDER', 'Command timestamp is earlier than the last timer change.');
  }
}

export interface StartInput {
  id: string;
  project: Pick<Project, 'id' | 'name' | 'color' | 'billingType'>;
  taskId: string | null;
  taskTitle?: string;
  description: string;
  rate: ResolvedRate;
  at: IsoDateTime;
}

export function startTimer(active: TimeEntry | undefined, input: StartInput): ActiveTimeEntry {
  if (active) throw new TimerError('ACTIVE_TIMER_EXISTS', 'Another timer is already active.');
  return {
    id: input.id,
    projectId: input.project.id,
    taskId: input.taskId,
    project: { id: input.project.id, name: input.project.name, color: input.project.color },
    task: input.taskId ? { id: input.taskId, title: input.taskTitle ?? '' } : null,
    description: input.description.trim(),
    source: 'timer',
    status: 'running',
    startedAt: input.at,
    endedAt: null,
    pauses: [],
    durationSeconds: null,
    billable: input.project.billingType === 'hourly',
    hourlyRate: input.rate.rate,
    currency: input.rate.currency,
    rateSource: input.rate.source,
    billableAmount: null,
    version: 1,
  };
}

export function pauseTimer(entry: TimeEntry, at: IsoDateTime): ActiveTimeEntry {
  if (entry.status !== 'running') throw new TimerError('INVALID_TRANSITION', `Cannot pause a ${entry.status} entry.`);
  assertNotBefore(entry, at);
  return { ...entry, status: 'paused', pauses: [...entry.pauses, { pausedAt: at, resumedAt: null }], version: entry.version + 1 };
}

export function resumeTimer(entry: TimeEntry, at: IsoDateTime): ActiveTimeEntry {
  if (entry.status !== 'paused') throw new TimerError('INVALID_TRANSITION', `Cannot resume a ${entry.status} entry.`);
  assertNotBefore(entry, at);
  const pauses: TimeEntryPause[] = entry.pauses.map((p) => (p.resumedAt === null ? { ...p, resumedAt: at } : p));
  return { ...entry, status: 'running', pauses, version: entry.version + 1 };
}

/** Stops a running or paused entry; closes an open pause at `at`, computes duration and amount. */
export function stopTimer(entry: TimeEntry, at: IsoDateTime): TimeEntry {
  if (entry.status === 'stopped') throw new TimerError('INVALID_TRANSITION', 'Entry is already stopped.');
  assertNotBefore(entry, at);
  const pauses = entry.pauses.map((p) => (p.resumedAt === null ? { ...p, resumedAt: at } : p));
  const closed = { ...entry, pauses, endedAt: at };
  const durationSeconds = elapsedSeconds(closed, ms(at));
  return {
    ...closed,
    status: 'stopped',
    durationSeconds,
    billableAmount: entry.billable && entry.hourlyRate !== null ? amountForDuration(durationSeconds, entry.hourlyRate) : null,
    version: entry.version + 1,
  };
}

/** Guard used before discarding — only active entries can be discarded. */
export function assertDiscardable(entry: TimeEntry): void {
  if (entry.status === 'stopped') throw new TimerError('INVALID_TRANSITION', 'Stopped entries are deleted, not discarded.');
}

/** Running longer than this shows the "Still working?" banner (architecture §7.5). */
export const LONG_RUNNING_SECONDS = 10 * 60 * 60;
