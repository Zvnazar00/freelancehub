import { QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import TimeScreen from '@/app/(tabs)/time';
import { useAuth } from '@/features/auth/store';
import { queryClient, tokenStorage } from '@/shared/api';
import { toUser } from '@/shared/api/mappers';
import type { WireTimeEntry } from '@/shared/api/wire';

import { createFakeApi, wireEntry, wireUser } from '../test-utils/fakeApi';

/** Minimal stateful timer backend: enough to exercise the real request/response flow. */
function timerBackend(fake: ReturnType<typeof createFakeApi>) {
  let entry: WireTimeEntry | null = null;
  const now = () => new Date().toISOString();
  const state = () => [200, { entry, server_time: now() }] as [number, unknown];
  const project = {
    id: 'p-1', client: { id: 'c-1', name: 'Acme' }, name: 'Mobile app', description: null, status: 'active',
    billing_type: 'hourly', hourly_rate: '100.00', fixed_fee: null, currency: 'USD', budget_hours: null, deadline: null,
    color: '#8B7CFF', archived_at: null, created_at: now(), updated_at: now(),
    stats: { tasks_total: 0, tasks_done: 0, tracked_seconds: 0, unbilled: [] },
  };
  fake
    .on('GET /projects', () => [200, { items: [project], next_cursor: null }])
    .on('GET /tasks', () => [200, { items: [], next_cursor: null }])
    .on('GET /time-entries', () => [200, { items: [], next_cursor: null, summary: [], days: [], server_time: now() }])
    .on('GET /timer/current', state)
    .on('POST /timer/start', (c) => {
      const body = c.body as { id: string };
      entry = wireEntry({ id: body.id, started_at: now() });
      return [201, { entry, server_time: now() }];
    })
    .on('POST /timer/:id/pause', () => {
      entry = { ...entry!, status: 'paused', pauses: [{ paused_at: now(), resumed_at: null }] };
      return state();
    })
    .on('POST /timer/:id/resume', () => {
      entry = { ...entry!, status: 'running', pauses: entry!.pauses.map((p) => ({ ...p, resumed_at: now() })) };
      return state();
    })
    .on('POST /timer/:id/stop', () => {
      entry = null;
      return state();
    });
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TimeScreen />
    </QueryClientProvider>
  );
}

describe('Time screen against the API', () => {
  let fake: ReturnType<typeof createFakeApi>;

  beforeEach(() => {
    queryClient.clear();
    fake = createFakeApi('http://localhost:8000/api/v1');
    globalThis.fetch = fake.fetchImpl;
    timerBackend(fake);
    tokenStorage.setAccessToken('access-1');
    useAuth.setState({ status: 'signedIn', user: toUser(wireUser()), offline: false });
  });

  it('drives start → pause → resume → stop through idempotent server commands', async () => {
    await renderRouter({ index: App }, { initialUrl: '/' });

    const start = await screen.findByTestId('timer-start');
    await waitFor(() => expect(screen.getByText('Mobile app')).toBeOnTheScreen());
    await act(async () => fireEvent.press(start));
    expect(await screen.findByTestId('timer-pause')).toBeOnTheScreen();

    await act(async () => fireEvent.press(screen.getByTestId('timer-pause')));
    expect(await screen.findByTestId('timer-resume')).toBeOnTheScreen();

    await act(async () => fireEvent.press(screen.getByTestId('timer-resume')));
    expect(await screen.findByTestId('timer-pause')).toBeOnTheScreen();

    await act(async () => fireEvent.press(screen.getByTestId('timer-stop')));
    expect(await screen.findByTestId('timer-start')).toBeOnTheScreen();

    const commands = fake.calls.filter((c) => c.method === 'POST');
    expect(commands.map((c) => c.path.replace(/\/timer\/[^/]+\//, '/timer/:id/'))).toEqual([
      '/timer/start',
      '/timer/:id/pause',
      '/timer/:id/resume',
      '/timer/:id/stop',
    ]);
    // Every command carries its own Idempotency-Key and a client-side timestamp.
    const keys = commands.map((c) => c.headers['Idempotency-Key']);
    expect(new Set(keys).size).toBe(4);
    expect(commands.every((c) => typeof (c.body as { at?: string } | undefined)?.at === 'string')).toBe(true);
  });
});
