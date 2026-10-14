import AsyncStorage from '@react-native-async-storage/async-storage';

import { restoreSession, signIn, signOut } from '@/features/auth/session';
import { useAuth } from '@/features/auth/store';
import type { TimerData } from '@/features/timer/api';
import { saveTimerSnapshot } from '@/features/timer/persistence';
import { queryClient, queryKeys, tokenStorage, useReachability } from '@/shared/api';
import { toEntry } from '@/shared/api/mappers';

import { createFakeApi, NetworkDown, problem, tokenPair, wireEntry } from '../test-utils/fakeApi';

const keystore = (jest.requireMock('expo-secure-store') as { __store: Map<string, string> }).__store;
const API = 'http://localhost:8000/api/v1';

describe('session lifecycle', () => {
  let fake: ReturnType<typeof createFakeApi>;

  beforeEach(async () => {
    await tokenStorage.clear();
    keystore.clear();
    await AsyncStorage.clear();
    queryClient.clear();
    useAuth.setState({ status: 'restoring', user: null, offline: false });
    useReachability.setState({ reachable: true });
    fake = createFakeApi(API);
    globalThis.fetch = fake.fetchImpl;
  });

  it('starts signed out without a stored refresh token (no network call)', async () => {
    await restoreSession();
    expect(useAuth.getState().status).toBe('signedOut');
    expect(fake.calls).toHaveLength(0);
  });

  it('signs in, stores the refresh token in the keystore only, and restores it after a restart', async () => {
    fake.on('POST /auth/login', () => [200, tokenPair(1)]);
    await signIn({ email: 'alex@example.com', password: 'correct horse battery' });
    expect(useAuth.getState()).toMatchObject({ status: 'signedIn', user: { email: 'alex@example.com', fullName: 'Alex Morgan' } });
    expect([...keystore.values()]).toEqual(['refresh-token-1-xxxxxxxxxxxx']);
    const plain = JSON.stringify(await AsyncStorage.multiGet(await AsyncStorage.getAllKeys()));
    expect(plain).not.toContain('refresh-token');
    expect(plain).not.toContain('access-1');

    // Simulated cold start: memory is gone, keystore remains.
    tokenStorage.setAccessToken(null);
    useAuth.setState({ status: 'restoring', user: null });
    fake.on('POST /auth/refresh', () => [200, tokenPair(2)]);
    await restoreSession();
    expect(useAuth.getState().status).toBe('signedIn');
    expect(fake.callsTo('POST /auth/refresh')[0]?.body).toEqual({ refresh_token: 'refresh-token-1-xxxxxxxxxxxx' });
    expect(tokenStorage.getAccessToken()).toBe('access-2');
  });

  it('hydrates the persisted timer before the network answers', async () => {
    await tokenStorage.saveRefreshToken('refresh-token-1-xxxxxxxxxxxx');
    await saveTimerSnapshot('u-1', toEntry(wireEntry()), 2000);
    fake.on('POST /auth/refresh', () => [200, tokenPair(2)]);
    await restoreSession();
    expect(queryClient.getQueryData<TimerData>(queryKeys.timer)?.entry?.id).toBe('e-1');
  });

  it('opens offline from the cached profile when the server is unreachable', async () => {
    fake.on('POST /auth/login', () => [200, tokenPair(1)]);
    await signIn({ email: 'alex@example.com', password: 'correct horse battery' });
    tokenStorage.setAccessToken(null);
    fake.on('POST /auth/refresh', () => {
      throw new NetworkDown();
    });
    await restoreSession();
    expect(useAuth.getState()).toMatchObject({ status: 'signedIn', offline: true, user: { id: 'u-1' } });
    expect(useReachability.getState().reachable).toBe(false);
    expect(await tokenStorage.loadRefreshToken()).toBe('refresh-token-1-xxxxxxxxxxxx'); // kept for later
  });

  it('shows the unreachable state when offline and nothing is cached', async () => {
    await tokenStorage.saveRefreshToken('refresh-token-1-xxxxxxxxxxxx');
    fake.on('POST /auth/refresh', () => {
      throw new NetworkDown();
    });
    await restoreSession();
    expect(useAuth.getState().status).toBe('unreachable');
  });

  it('signs out when the stored session was revoked, wiping local data', async () => {
    await tokenStorage.saveRefreshToken('refresh-token-1-xxxxxxxxxxxx');
    await saveTimerSnapshot('u-1', toEntry(wireEntry()), 0);
    fake.on('POST /auth/refresh', () => [401, problem(401, 'TOKEN_INVALID')]);
    await restoreSession();
    expect(useAuth.getState().status).toBe('signedOut');
    expect(keystore.size).toBe(0);
    expect(await AsyncStorage.getItem('freelancehub.timer.v1')).toBeNull();
  });

  it('sign-out revokes the server session and clears every local trace', async () => {
    fake.on('POST /auth/login', () => [200, tokenPair(1)]);
    fake.on('POST /auth/logout', () => [204, undefined]);
    await signIn({ email: 'alex@example.com', password: 'correct horse battery' });
    queryClient.setQueryData(queryKeys.clients.list(), [{ id: 'c' }]);
    await signOut();
    expect(fake.callsTo('POST /auth/logout')[0]?.body).toEqual({ refresh_token: 'refresh-token-1-xxxxxxxxxxxx' });
    expect(useAuth.getState()).toMatchObject({ status: 'signedOut', user: null });
    expect(queryClient.getQueryData(queryKeys.clients.list())).toBeUndefined();
    expect(keystore.size).toBe(0);
    expect(await AsyncStorage.getAllKeys()).toEqual([]);
  });
});
