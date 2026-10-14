/* eslint-disable @typescript-eslint/no-require-imports */
import i18n from '@/shared/i18n';

// babel-jest hoists jest.mock above imports, so the mock is active before any module loads.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

// Tests assert English copy unless they switch language explicitly.
void i18n.changeLanguage('en');

// In-memory keystore: tests can assert what was (and was not) written to secure storage.
jest.mock('expo-secure-store', () => {
  const store = new Map<string, string>();
  return {
    __store: store,
    AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY: 0,
    getItemAsync: jest.fn(async (key: string) => store.get(key) ?? null),
    setItemAsync: jest.fn(async (key: string, value: string) => {
      store.set(key, value);
    }),
    deleteItemAsync: jest.fn(async (key: string) => {
      store.delete(key);
    }),
  };
});

// expo-crypto is a native module (auto-mocked by jest-expo); back it with Node's CSPRNG.
jest.mock('expo-crypto', () => ({
  randomUUID: () => require('node:crypto').randomUUID(),
}));
