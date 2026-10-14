import {
  elapsedSeconds,
  pauseTimer,
  pausedAtMs,
  resumeTimer,
  startTimer,
  stopTimer,
  TimerError,
  type ResolvedRate,
} from '@/features/timer/model';
import type { Project } from '@/shared/types/domain';

const project: Project = {
  id: 'p1',
  clientId: 'c1',
  clientName: 'Acme',
  name: 'App',
  description: null,
  status: 'active',
  billingType: 'hourly',
  hourlyRate: '85.00',
  fixedFee: null,
  currency: 'USD',
  budgetHours: null,
  deadline: null,
  color: '#8B7CFF',
  archivedAt: null,
  stats: { tasksTotal: 0, tasksDone: 0, trackedSeconds: 0, unbilled: [] },
};
const rate: ResolvedRate = { rate: '85.00', currency: 'USD', source: 'project' };
const t = (hhmmss: string) => `2026-10-12T${hhmmss}.000Z`;
const ms = (hhmmss: string) => new Date(t(hhmmss)).getTime();

const start = (at = t('09:00:00')) =>
  startTimer(undefined, { id: 'e1', project, taskId: null, description: '  Login form  ', rate, at });

describe('startTimer', () => {
  it('creates a running entry with a rate snapshot and trimmed description', () => {
    const e = start();
    expect(e).toMatchObject({ status: 'running', hourlyRate: '85.00', currency: 'USD', rateSource: 'project', billable: true, description: 'Login form', version: 1 });
  });

  it('refuses to start while another entry is active (invariant: one active entry)', () => {
    const active = start();
    expect(() => startTimer(active, { id: 'e2', project, taskId: null, description: '', rate, at: t('10:00:00') })).toThrow(
      expect.objectContaining({ code: 'ACTIVE_TIMER_EXISTS' }),
    );
  });

  it('marks non-hourly projects as non-billable', () => {
    const e = startTimer(undefined, { id: 'e3', project: { ...project, billingType: 'fixed' }, taskId: null, description: '', rate: { rate: null, currency: 'USD', source: 'none' }, at: t('09:00:00') });
    expect(e.billable).toBe(false);
  });
});

describe('elapsedSeconds', () => {
  it('derives elapsed time from timestamps, excluding pauses', () => {
    let e = start();
    e = pauseTimer(e, t('09:30:00'));
    e = resumeTimer(e, t('09:45:00'));
    expect(elapsedSeconds(e, ms('10:00:00'))).toBe(45 * 60);
  });

  it('freezes while paused', () => {
    const e = pauseTimer(start(), t('09:10:00'));
    expect(elapsedSeconds(e, ms('09:20:00'))).toBe(600);
    expect(elapsedSeconds(e, ms('12:00:00'))).toBe(600);
    expect(pausedAtMs(e)).toBe(ms('09:10:00'));
  });

  it('never returns negative values (clock behind start)', () => {
    expect(elapsedSeconds(start(), ms('08:59:00'))).toBe(0);
  });

  it('floors sub-second remainders', () => {
    expect(elapsedSeconds(start(), ms('09:00:01') + 999)).toBe(1);
  });
});

describe('transitions', () => {
  it('rejects invalid transitions', () => {
    const running = start();
    expect(() => resumeTimer(running, t('09:05:00'))).toThrow(TimerError);
    const paused = pauseTimer(running, t('09:05:00'));
    expect(() => pauseTimer(paused, t('09:06:00'))).toThrow(expect.objectContaining({ code: 'INVALID_TRANSITION' }));
    const stopped = stopTimer(paused, t('09:10:00'));
    expect(() => stopTimer(stopped, t('09:11:00'))).toThrow(expect.objectContaining({ code: 'INVALID_TRANSITION' }));
  });

  it('rejects commands timestamped before the last transition', () => {
    const paused = pauseTimer(start(), t('09:30:00'));
    expect(() => resumeTimer(paused, t('09:29:59'))).toThrow(expect.objectContaining({ code: 'TIMESTAMP_OUT_OF_ORDER' }));
  });

  it('increments version on every transition', () => {
    let e = start();
    e = pauseTimer(e, t('09:01:00'));
    e = resumeTimer(e, t('09:02:00'));
    expect(e.version).toBe(3);
  });
});

describe('stopTimer', () => {
  it('computes net duration and amount from the rate snapshot', () => {
    let e = start();
    e = pauseTimer(e, t('10:00:00'));
    e = resumeTimer(e, t('10:30:00'));
    const stopped = stopTimer(e, t('11:00:00'));
    expect(stopped.durationSeconds).toBe(5400);
    expect(stopped.billableAmount).toBe('127.50');
    expect(stopped.endedAt).toBe(t('11:00:00'));
  });

  it('closes an open pause when stopping a paused entry', () => {
    const paused = pauseTimer(start(), t('09:20:00'));
    const stopped = stopTimer(paused, t('09:50:00'));
    expect(stopped.pauses[0]?.resumedAt).toBe(t('09:50:00'));
    expect(stopped.durationSeconds).toBe(1200);
  });

  it('leaves amount null for non-billable or rate-less entries', () => {
    const e = { ...start(), billable: false };
    expect(stopTimer(e, t('10:00:00')).billableAmount).toBeNull();
    const noRate = { ...start(), hourlyRate: null };
    expect(stopTimer(noRate, t('10:00:00')).billableAmount).toBeNull();
  });
});

