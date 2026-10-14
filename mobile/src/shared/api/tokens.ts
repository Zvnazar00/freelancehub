import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

/**
 * Token storage (docs/architecture.md, ADR-05).
 *
 * - The access token (15 min) lives only in memory and is never persisted.
 * - The refresh token is persisted only in the OS keystore (iOS Keychain / Android Keystore via
 *   expo-secure-store), readable after first unlock and never migrated to another device.
 * - On web there is no encrypted storage, so the refresh token stays in memory as well:
 *   a web session ends on reload. Tokens are never written to AsyncStorage or localStorage.
 */
const REFRESH_KEY = 'freelancehub.refreshToken';
const secureOptions: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
};

export interface TokenStorage {
  getAccessToken(): string | null;
  setAccessToken(token: string | null): void;
  loadRefreshToken(): Promise<string | null>;
  saveRefreshToken(token: string): Promise<void>;
  clear(): Promise<void>;
}

export function createTokenStorage(persistent: boolean = Platform.OS !== 'web'): TokenStorage {
  let accessToken: string | null = null;
  let refreshToken: string | null = null;

  return {
    getAccessToken: () => accessToken,
    setAccessToken: (token) => {
      accessToken = token;
    },
    async loadRefreshToken() {
      if (refreshToken !== null || !persistent) return refreshToken;
      try {
        refreshToken = await SecureStore.getItemAsync(REFRESH_KEY, secureOptions);
      } catch {
        // Keystore unavailable or corrupted (e.g. restored backup): treat as signed out.
        refreshToken = null;
      }
      return refreshToken;
    },
    async saveRefreshToken(token) {
      refreshToken = token;
      if (persistent) await SecureStore.setItemAsync(REFRESH_KEY, token, secureOptions);
    },
    async clear() {
      accessToken = null;
      refreshToken = null;
      if (persistent) {
        try {
          await SecureStore.deleteItemAsync(REFRESH_KEY, secureOptions);
        } catch {
          // Nothing more we can do; the server-side session is revoked separately.
        }
      }
    },
  };
}
