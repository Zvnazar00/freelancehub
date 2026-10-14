import Constants from 'expo-constants';
import { Platform } from 'react-native';

const API_PORT = 8000;
const API_PREFIX = '/api/v1';

/**
 * Base URL of the backend API.
 *
 * 1. `EXPO_PUBLIC_API_URL` wins (required for tunnels, staging and production builds).
 * 2. In development, the host that serves the JS bundle (Metro) is the developer's machine, so
 *    the API is assumed on the same host at port 8000 — this makes a physical phone on the same Wi-Fi work.
 * 3. Web / simulators fall back to localhost.
 */
export function resolveApiBaseUrl(
  env: string | undefined = process.env.EXPO_PUBLIC_API_URL,
  hostUri: string | undefined = Constants.expoConfig?.hostUri,
  os: string = Platform.OS,
): string {
  const explicit = env?.trim();
  if (explicit) return explicit.replace(/\/+$/, '') + (explicit.includes(API_PREFIX) ? '' : API_PREFIX);

  const host = hostUri?.split(':')[0];
  if (host && os !== 'web') return `http://${host}:${API_PORT}${API_PREFIX}`;
  if (os === 'android') return `http://10.0.2.2:${API_PORT}${API_PREFIX}`; // Android emulator → host machine
  return `http://localhost:${API_PORT}${API_PREFIX}`;
}

export const API_BASE_URL = resolveApiBaseUrl();
