import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

import { createTokenStorage } from '@/shared/api/tokens';

const keystore = (jest.requireMock('expo-secure-store') as { __store: Map<string, string> }).__store;

describe('token storage', () => {
  beforeEach(async () => {
    keystore.clear();
    await AsyncStorage.clear();
    jest.clearAllMocks();
  });

  it('persists only the refresh token, and only in the secure keystore (native)', async () => {
    const tokens = createTokenStorage(true);
    tokens.setAccessToken('access-secret');
    await tokens.saveRefreshToken('refresh-secret');

    expect([...keystore.values()]).toEqual(['refresh-secret']);
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('freelancehub.refreshToken', 'refresh-secret', {
      keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
    });
    // Nothing secret ever reaches unencrypted storage.
    const plain = await AsyncStorage.multiGet(await AsyncStorage.getAllKeys());
    expect(JSON.stringify(plain)).not.toMatch(/secret/);

    // A new process (app restart) reads the refresh token back; the access token is gone.
    const restarted = createTokenStorage(true);
    expect(restarted.getAccessToken()).toBeNull();
    expect(await restarted.loadRefreshToken()).toBe('refresh-secret');
  });

  it('clear() wipes memory and keystore', async () => {
    const tokens = createTokenStorage(true);
    tokens.setAccessToken('a');
    await tokens.saveRefreshToken('r');
    await tokens.clear();
    expect(tokens.getAccessToken()).toBeNull();
    expect(keystore.size).toBe(0);
    expect(await createTokenStorage(true).loadRefreshToken()).toBeNull();
  });

  it('keeps tokens in memory only on web (no encrypted storage there)', async () => {
    const tokens = createTokenStorage(false);
    await tokens.saveRefreshToken('r');
    expect(await tokens.loadRefreshToken()).toBe('r');
    expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
    expect(await AsyncStorage.getAllKeys()).toEqual([]);
  });

  it('treats an unreadable keystore as signed out', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(new Error('keystore corrupted'));
    expect(await createTokenStorage(true).loadRefreshToken()).toBeNull();
  });
});
