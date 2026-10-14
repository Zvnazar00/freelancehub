import { createApiClient } from '@/shared/api/client';
import { resolveApiBaseUrl } from '@/shared/api/config';
import { ApiError, errorMessageKey } from '@/shared/api/errors';
import { createTokenStorage } from '@/shared/api/tokens';

import { createFakeApi, NetworkDown, problem, tokenPair } from '../test-utils/fakeApi';

function setup(opts: { refreshToken?: string; accessToken?: string } = {}) {
  const fake = createFakeApi();
  const tokens = createTokenStorage(false);
  if (opts.accessToken) tokens.setAccessToken(opts.accessToken);
  if (opts.refreshToken) void tokens.saveRefreshToken(opts.refreshToken);
  const onSessionExpired = jest.fn();
  const api = createApiClient({ baseUrl: fake.baseUrl, tokens, fetchImpl: fake.fetchImpl, onSessionExpired });
  return { fake, tokens, api, onSessionExpired };
}

describe('API client', () => {
  it('sends the bearer token, JSON body, query and Idempotency-Key', async () => {
    const { fake, api } = setup({ accessToken: 'a-1' });
    fake.on('POST /things', () => [201, { ok: true }]);
    const res = await api.request<{ ok: boolean }>('/things', {
      method: 'POST',
      body: { name: 'x' },
      query: { a: 1, empty: '', skip: undefined },
      idempotencyKey: 'key-123',
    });
    expect(res).toEqual({ ok: true });
    const [call] = fake.calls;
    expect(call?.headers.Authorization).toBe('Bearer a-1');
    expect(call?.headers['Idempotency-Key']).toBe('key-123');
    expect(call?.body).toEqual({ name: 'x' });
    expect(call?.query.toString()).toBe('a=1');
  });

  it('turns problem+json into a typed ApiError with field errors and request id', async () => {
    const { fake, api } = setup({ accessToken: 'a-1' });
    fake.on('POST /clients', () => [
      422,
      problem(422, 'VALIDATION_ERROR', { errors: [{ field: 'email', message: 'bad', code: 'value_error' }] }),
    ]);
    const error = await api.request('/clients', { method: 'POST', body: {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, code: 'VALIDATION_ERROR', requestId: 'req-1' });
    expect((error as ApiError).fieldErrors).toEqual([{ field: 'email', message: 'bad', code: 'value_error' }]);
    expect(errorMessageKey(error)).toBe('errors.VALIDATION_ERROR');
  });

  it('reports unreachable servers as a transient NETWORK_ERROR', async () => {
    const { fake, api } = setup({ accessToken: 'a-1' });
    fake.on('GET /me', () => {
      throw new NetworkDown();
    });
    const error = (await api.request('/me').catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe('NETWORK_ERROR');
    expect(error.isTransient).toBe(true);
    expect(errorMessageKey(error)).toBe('errors.NETWORK_ERROR');
    expect(errorMessageKey(new Error('boom'))).toBe('errors.UNKNOWN');
  });

  it('refreshes an expired access token once for concurrent requests, then retries them', async () => {
    const { fake, api, tokens } = setup({ accessToken: 'old', refreshToken: 'refresh-token-0-xxxxxxxxxxxx' });
    fake.on('POST /auth/refresh', () => [200, tokenPair(1)]);
    fake.on('GET /me', (c) => (c.headers.Authorization === 'Bearer access-1' ? [200, { me: 1 }] : [401, problem(401, 'TOKEN_EXPIRED')]));
    fake.on('GET /clients', (c) => (c.headers.Authorization === 'Bearer access-1' ? [200, { items: [] }] : [401, problem(401, 'TOKEN_EXPIRED')]));

    const results = await Promise.all([api.request('/me'), api.request('/clients'), api.request('/me')]);
    expect(results).toEqual([{ me: 1 }, { items: [] }, { me: 1 }]);
    expect(fake.callsTo('POST /auth/refresh')).toHaveLength(1);
    expect(fake.callsTo('POST /auth/refresh')[0]?.body).toEqual({ refresh_token: 'refresh-token-0-xxxxxxxxxxxx' });
    expect(tokens.getAccessToken()).toBe('access-1');
    expect(await tokens.loadRefreshToken()).toBe('refresh-token-1-xxxxxxxxxxxx'); // rotated
  });

  it('obtains an access token first when only a refresh token is stored (cold start)', async () => {
    const { fake, api } = setup({ refreshToken: 'refresh-token-0-xxxxxxxxxxxx' });
    fake.on('POST /auth/refresh', () => [200, tokenPair(1)]);
    fake.on('GET /me', () => [200, { me: 1 }]);
    await api.request('/me');
    expect(fake.calls.map((c) => `${c.method} ${c.path}`)).toEqual(['POST /auth/refresh', 'GET /me']);
    expect(fake.calls[1]?.headers.Authorization).toBe('Bearer access-1');
  });

  it('ends the session when the refresh token is rejected', async () => {
    const { fake, api, tokens, onSessionExpired } = setup({ accessToken: 'old', refreshToken: 'refresh-token-0-xxxxxxxxxxxx' });
    fake.on('GET /me', () => [401, problem(401, 'TOKEN_EXPIRED')]);
    fake.on('POST /auth/refresh', () => [401, problem(401, 'TOKEN_INVALID')]);
    const error = (await api.request('/me').catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe('SESSION_EXPIRED');
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
    expect(tokens.getAccessToken()).toBeNull();
    expect(await tokens.loadRefreshToken()).toBeNull();
  });

  it('keeps the stored session when the refresh fails only because the network is down', async () => {
    const { fake, api, tokens, onSessionExpired } = setup({ refreshToken: 'refresh-token-0-xxxxxxxxxxxx' });
    fake.on('POST /auth/refresh', () => {
      throw new NetworkDown();
    });
    const error = (await api.request('/me').catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe('NETWORK_ERROR');
    expect(onSessionExpired).not.toHaveBeenCalled();
    expect(await tokens.loadRefreshToken()).toBe('refresh-token-0-xxxxxxxxxxxx');
  });

  it('does not try to refresh on wrong credentials', async () => {
    const { fake, api } = setup();
    fake.on('POST /auth/login', () => [401, problem(401, 'INVALID_CREDENTIALS')]);
    const error = (await api.request('/auth/login', { method: 'POST', auth: false, body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe('INVALID_CREDENTIALS');
    expect(fake.callsTo('POST /auth/refresh')).toHaveLength(0);
  });
});

describe('resolveApiBaseUrl', () => {
  it('prefers EXPO_PUBLIC_API_URL and appends the API prefix', () => {
    expect(resolveApiBaseUrl('https://api.example.com/', 'x:8081', 'ios')).toBe('https://api.example.com/api/v1');
    expect(resolveApiBaseUrl('https://api.example.com/api/v1', undefined, 'ios')).toBe('https://api.example.com/api/v1');
  });
  it('uses the Metro host for devices on the LAN, localhost on web', () => {
    expect(resolveApiBaseUrl(undefined, '192.168.1.20:8081', 'ios')).toBe('http://192.168.1.20:8000/api/v1');
    expect(resolveApiBaseUrl(undefined, 'localhost:8081', 'web')).toBe('http://localhost:8000/api/v1');
    expect(resolveApiBaseUrl(undefined, undefined, 'android')).toBe('http://10.0.2.2:8000/api/v1');
  });
});
