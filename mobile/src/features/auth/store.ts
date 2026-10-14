import { create } from 'zustand';

import type { UserProfile } from '@/shared/types/domain';

/**
 * restoring   — splash screen; reading the keystore and refreshing the session.
 * signedOut   — no valid session: only the (auth) routes are reachable.
 * signedIn    — protected routes are reachable; `user` is set.
 * unreachable — a stored session exists but the server could not be reached and nothing is cached yet.
 */
export type AuthStatus = 'restoring' | 'signedOut' | 'signedIn' | 'unreachable';

interface AuthState {
  status: AuthStatus;
  user: UserProfile | null;
  /** True when the session was restored from cache without reaching the server. */
  offline: boolean;
}

export const useAuth = create<AuthState>()(() => ({ status: 'restoring', user: null, offline: false }));

/** The signed-in user. Only call from protected screens. */
export function useCurrentUser(): UserProfile {
  const user = useAuth((s) => s.user);
  if (!user) throw new Error('useCurrentUser() called outside a signed-in route');
  return user;
}
