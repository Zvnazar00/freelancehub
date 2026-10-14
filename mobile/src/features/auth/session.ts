import { getCalendars, getLocales } from 'expo-localization';

import { clearTimerSnapshot, loadTimerSnapshot } from '@/features/timer/persistence';
import { useServerClock } from '@/features/timer/clock';
import type { TimerData } from '@/features/timer/api';
import { api, isApiError, queryClient, queryKeys, setSessionListeners, tokenStorage, useReachability } from '@/shared/api';
import { toUser } from '@/shared/api/mappers';
import { normalizeTimeZone } from '@/shared/lib/timezone';
import type { WireTokenPair, WireUser } from '@/shared/api/wire';
import { SUPPORTED_CURRENCIES, type CurrencyCode, type UserProfile } from '@/shared/types/domain';

import { clearCachedProfile, loadCachedProfile, saveCachedProfile } from './profileCache';
import type { SignInValues, SignUpValues } from './schema';
import { useAuth } from './store';

function setUser(user: UserProfile) {
  useAuth.setState({ user });
  queryClient.setQueryData(queryKeys.me, user);
  void saveCachedProfile(user);
}

/** Wipes everything that belongs to the signed-in user from this device. */
async function clearLocalSession() {
  await tokenStorage.clear();
  await queryClient.cancelQueries();
  queryClient.clear();
  useServerClock.getState().setOffset(0);
  await Promise.all([clearTimerSnapshot(), clearCachedProfile()]);
  useAuth.setState({ status: 'signedOut', user: null, offline: false });
}

let listenersBound = false;
function bindListeners() {
  if (listenersBound) return;
  listenersBound = true;
  setSessionListeners({
    onSession: (pair: WireTokenPair) => {
      if (useAuth.getState().status === 'signedIn') setUser(toUser(pair.user));
    },
    // The refresh token was rejected (expired, revoked by "sign out everywhere", or reused).
    onExpired: () => void clearLocalSession(),
  });
}

/** Seeds the timer cache from the persisted snapshot so the timer renders before the network answers. */
async function hydrateTimer(userId: string) {
  const snapshot = await loadTimerSnapshot(userId);
  if (!snapshot) return;
  useServerClock.getState().setOffset(snapshot.offsetMs);
  queryClient.setQueryData<TimerData>(queryKeys.timer, { entry: snapshot.entry }, { updatedAt: snapshot.savedAt });
}

async function enterSession(user: UserProfile, offline: boolean) {
  await hydrateTimer(user.id);
  setUser(user);
  useAuth.setState({ status: 'signedIn', offline });
}

/**
 * Runs once during the splash screen. Exchanges the keystore refresh token for a fresh session.
 * Offline with a stored session → signed in from cache (requests refresh lazily once online).
 */
export async function restoreSession(): Promise<void> {
  bindListeners();
  useAuth.setState({ status: 'restoring' });
  const refreshToken = await tokenStorage.loadRefreshToken();
  if (!refreshToken) {
    // No session: make sure nothing from a previous user lingers (e.g. app reinstalled → keystore wiped).
    await Promise.all([clearTimerSnapshot(), clearCachedProfile()]);
    useAuth.setState({ status: 'signedOut', user: null });
    return;
  }
  try {
    const pair = await api.refreshSession();
    await enterSession(toUser(pair.user), false);
  } catch (error) {
    if (isApiError(error) && error.code === 'SESSION_EXPIRED') {
      await clearLocalSession();
      return;
    }
    const cached = await loadCachedProfile();
    if (cached) {
      useReachability.setState({ reachable: false });
      await enterSession(cached, true);
    }
    else useAuth.setState({ status: 'unreachable' });
  }
}

function deviceTimeZone(): string {
  return normalizeTimeZone(getCalendars()[0]?.timeZone);
}

function deviceCurrency(): CurrencyCode {
  const code = getLocales()[0]?.currencyCode;
  return code && (SUPPORTED_CURRENCIES as readonly string[]).includes(code) ? (code as CurrencyCode) : 'USD';
}

export async function signIn(values: SignInValues): Promise<void> {
  bindListeners();
  const pair = await api.request<WireTokenPair>('/auth/login', {
    method: 'POST',
    auth: false,
    body: { email: values.email.trim(), password: values.password },
  });
  await api.acceptSession(pair);
  await enterSession(toUser(pair.user), false);
}

export async function signUp(values: SignUpValues): Promise<void> {
  bindListeners();
  const pair = await api.request<WireTokenPair>('/auth/register', {
    method: 'POST',
    auth: false,
    body: {
      full_name: values.fullName.trim(),
      email: values.email.trim(),
      password: values.password,
      timezone: deviceTimeZone(),
      default_currency: deviceCurrency(),
    },
  });
  await api.acceptSession(pair);
  await enterSession(toUser(pair.user), false);
}

/** Revokes this device's session on the server (best effort) and clears local state. */
export async function signOut(): Promise<void> {
  const refreshToken = await tokenStorage.loadRefreshToken();
  if (refreshToken) {
    try {
      await api.request('/auth/logout', { method: 'POST', auth: false, body: { refresh_token: refreshToken }, timeoutMs: 5000 });
    } catch {
      // Offline: the local session is still removed; the server token expires on its own.
    }
  }
  await clearLocalSession();
}

/** Revokes every session of the user (all devices). Requires the server — errors are surfaced. */
export async function signOutEverywhere(): Promise<void> {
  await api.request('/auth/logout-all', { method: 'POST' });
  await clearLocalSession();
}

export async function updateProfile(patch: Partial<{ week_start: 1 | 7; timezone: string; default_currency: CurrencyCode }>) {
  const user = toUser(await api.request<WireUser>('/me', { method: 'PATCH', body: patch }));
  setUser(user);
  // Week boundaries and local-day grouping depend on the profile.
  void queryClient.invalidateQueries({ queryKey: queryKeys.entries.all });
  void queryClient.invalidateQueries({ queryKey: queryKeys.money.all });
  void queryClient.invalidateQueries({ queryKey: queryKeys.invoices.all }); // "overdue" uses the profile time zone
  return user;
}

export async function refreshProfile(): Promise<UserProfile> {
  const user = toUser(await api.request<WireUser>('/me'));
  setUser(user);
  return user;
}

export { deviceTimeZone };
