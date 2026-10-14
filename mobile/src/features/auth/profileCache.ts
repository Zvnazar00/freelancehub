import AsyncStorage from '@react-native-async-storage/async-storage';

import type { UserProfile } from '@/shared/types/domain';

/**
 * Last known profile, so a signed-in user can open the app offline. Contains no secrets
 * (name, e-mail, preferences); tokens live only in SecureStore/memory (see shared/api/tokens.ts).
 */
const KEY = 'freelancehub.profile.v1';

export async function loadCachedProfile(): Promise<UserProfile | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<UserProfile>;
    return typeof value.id === 'string' && typeof value.email === 'string' ? (value as UserProfile) : null;
  } catch {
    return null;
  }
}

export async function saveCachedProfile(user: UserProfile): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(user));
  } catch {
    // Cache only.
  }
}

export async function clearCachedProfile(): Promise<void> {
  try {
    await AsyncStorage.removeItem(KEY);
  } catch {
    // Cache only.
  }
}
