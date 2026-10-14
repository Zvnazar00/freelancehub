import { estimateOffset, useServerClock } from '@/features/timer/clock';
import { elapsedSeconds, pausedAtMs } from '@/features/timer/model';
import { loadTimerSnapshot, saveTimerSnapshot } from '@/features/timer/persistence';
import { optimisticTimer, prepareCommand, sendTimerCommand } from '@/features/timer/api';
import { tokenStorage } from '@/shared/api';
import { toEntry } from '@/shared/api/mappers';
import type { ActiveTimeEntry } from '@/shared/types/domain';

import { createFakeApi, NetworkDown, problem, wireEntry } from '../test-utils/fakeApi';

const API = 'http://localhost:8000/api/v1';
const iso = (hhmmss: string) => `2026-10-12T${hhmmss}.000Z`;
const ms = (hhmmss: string) => Date.parse(iso(hhmmss));

const running = toEntry(wireEntry({ started_at: iso('09:00:00') })) as ActiveTimeEntry;
const paused = toEntry(
  wireEntry({ status: 'paused', started_at: iso('09:00:00'), pauses: [{ paused_at: iso('09:30:00'), resumed_at: null }] }),
) as ActiveTimeEntry;

describe('elapsed time survives backgrounding and restarts', () => {
  it('is derived from persisted timestamps, not from a counter', async () => {
    await saveTimerSnapshot('u-1', running, 1500, ms('09:10:00'));

    // "App killed" at 09:10; reopened at 10:00 device time, server clock 1.5 s ahead.
    const restored = await loadTimerSnapshot('u-1');
    expect(restored?.entry?.id).toBe('e-1');
    expect(restored?.offsetMs).toBe(1500);
    const nowServer = ms('10:00:00') + restored!.offsetMs;
    expect(elapsedSeconds(restored!.entry!, nowServer)).toBe(3601);
  });

  it('freezes a paused timer at the start of the open pause, whatever the clock says', async () => {
    await saveTimerSnapshot('u-1', paused, 0);
    const restored = (await loadTimerSnapshot('u-1'))!.entry!;
    expect(elapsedSeconds(restored, pausedAtMs(restored)!)).toBe(1800);
  });

  it('never restores another user’s timer, and stores nothing for a stopped one', async () => {
    await saveTimerSnapshot('u-1', running, 0);
    expect(await loadTimerSnapshot('u-2')).toBeNull();
    await saveTimerSnapshot('u-1', { ...running, status: 'stopped' }, 0);
    expect((await loadTimerSnapshot('u-1'))?.entry).toBeNull();
  });

  it('estimates the server-clock offset from the request midpoint', () => {
    expect(estimateOffset(iso('10:00:05'), ms('10:00:00'), ms('10:00:02'))).toBe(4000);
    expect(estimateOffset('garbage', 0, 0)).toBe(0);
  });
});

describe('timer commands', () => {
  let fake: ReturnType<typeof createFakeApi>;
  beforeEach(() => {
    fake = createFakeApi(API);
    globalThis.fetch = fake.fetchImpl;
    useServerClock.setState({ offsetMs: 0 });
    tokenStorage.setAccessToken('access-1'); // authenticated client
  });

  it('never stamps a command before the last known transition (clock jitter)', () => {
    const cmd = prepareCommand({ kind: 'pause', entryId: 'e-1' }, paused, ms('09:29:59'));
    expect(cmd.at).toBe(new Date(ms('09:30:00') + 1).toISOString());
    expect(cmd.key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('retries transient failures with the same Idempotency-Key and body', async () => {
    let n = 0;
    fake.on('POST /timer/:id/pause', () => {
      n += 1;
      if (n === 1) throw new NetworkDown();
      if (n === 2) return [503, problem(503, 'HTTP_ERROR')];
      return [200, { entry: wireEntry({ status: 'paused', pauses: [{ paused_at: iso('09:30:00'), resumed_at: null }] }), server_time: iso('09:30:01') }];
    });
    const cmd = prepareCommand({ kind: 'pause', entryId: 'e-1' }, running, ms('09:30:00'));
    const result = await sendTimerCommand(cmd);

    expect(result.entry?.status).toBe('paused');
    const calls = fake.callsTo('POST /timer/:id/pause');
    expect(calls).toHaveLength(3);
    expect(new Set(calls.map((c) => c.headers['Idempotency-Key']))).toEqual(new Set([cmd.key]));
    expect(new Set(calls.map((c) => JSON.stringify(c.body)))).toEqual(new Set([JSON.stringify({ at: cmd.at })]));
  });

  it('does not retry definitive answers', async () => {
    fake.on('POST /timer/:id/resume', () => [409, problem(409, 'INVALID_TRANSITION')]);
    const cmd = prepareCommand({ kind: 'resume', entryId: 'e-1' }, paused, ms('09:40:00'));
    await expect(sendTimerCommand(cmd)).rejects.toMatchObject({ code: 'INVALID_TRANSITION' });
    expect(fake.callsTo('POST /timer/:id/resume')).toHaveLength(1);
  });

  it('lets the server stamp the time when our clock estimate is rejected', async () => {
    fake.on('POST /timer/:id/stop', (c) =>
      c.body && typeof c.body === 'object' && 'at' in c.body
        ? [422, problem(422, 'TIMESTAMP_OUT_OF_ORDER')]
        : [200, { entry: null, server_time: iso('10:00:00') }],
    );
    const cmd = prepareCommand({ kind: 'stop', entryId: 'e-1' }, running, ms('10:00:00'));
    const result = await sendTimerCommand(cmd);
    expect(result.entry).toBeNull();
    const [first, second] = fake.callsTo('POST /timer/:id/stop');
    expect(second?.body).toEqual({});
    expect(second?.headers['Idempotency-Key']).not.toBe(first?.headers['Idempotency-Key']);
  });

  it('sends the client-generated entry id on start so retries cannot create duplicates', async () => {
    fake.on('POST /timer/start', (c) => [201, { entry: wireEntry({ id: (c.body as { id: string }).id }), server_time: iso('09:00:00') }]);
    const cmd = prepareCommand(
      { kind: 'start', project: { id: 'p-1', name: 'Mobile app', color: '#8B7CFF', billingType: 'hourly', hourlyRate: '100.00', currency: 'USD' }, taskId: null, description: ' Login ' },
      null,
      ms('09:00:00'),
    );
    const result = await sendTimerCommand(cmd);
    expect(cmd.kind === 'start' && result.entry?.id).toBe(cmd.kind === 'start' ? cmd.entryId : '');
    expect(fake.calls[0]?.body).toMatchObject({ project_id: 'p-1', description: 'Login', task_id: null, at: cmd.at });
  });

  it('computes optimistic states with the same state machine', () => {
    const pause = prepareCommand({ kind: 'pause', entryId: 'e-1' }, running, ms('09:30:00'));
    expect(optimisticTimer(running, pause)?.entry?.status).toBe('paused');
    // Invalid transition → no optimistic change (the server answer decides).
    expect(optimisticTimer(paused, pause)).toBeNull();
    const stop = prepareCommand({ kind: 'stop', entryId: 'e-1' }, paused, ms('10:00:00'));
    expect(optimisticTimer(paused, stop)).toEqual({ entry: null });
  });
});
