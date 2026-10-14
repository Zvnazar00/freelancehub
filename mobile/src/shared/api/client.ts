import { ApiError } from './errors';
import type { TokenStorage } from './tokens';
import type { WireProblem, WireTokenPair } from './wire';

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  query?: Record<string, QueryValue>;
  body?: unknown;
  /** Sent as `Idempotency-Key`; reuse the same key when retrying the same command. */
  idempotencyKey?: string;
  /** Attach the access token and refresh it when expired (default true). */
  auth?: boolean;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Return the raw bytes (PDF, CSV) instead of parsing JSON. Errors are still parsed as problem+json. */
  binary?: boolean;
}

export interface ApiResponse<T> {
  data: T;
  status: number;
  headers: Headers;
  /** Device clock (ms) when the request was sent and when the response arrived — used for clock-offset estimates. */
  sentAt: number;
  receivedAt: number;
}

export interface ApiClientOptions {
  baseUrl: string;
  tokens: TokenStorage;
  fetchImpl?: typeof fetch;
  now?: () => number;
  defaultTimeoutMs?: number;
  /** Called after every successful login/refresh (e.g. to update the cached profile). */
  onSession?: (pair: WireTokenPair) => void;
  /** Called once the refresh token is rejected: the user must sign in again. */
  onSessionExpired?: () => void;
  /** false after a request could not reach the server, true after any HTTP response. */
  onReachability?: (reachable: boolean) => void;
}

export interface ApiClient {
  readonly baseUrl: string;
  request<T>(path: string, options?: RequestOptions): Promise<T>;
  requestWithMeta<T>(path: string, options?: RequestOptions): Promise<ApiResponse<T>>;
  /** Stores a freshly issued token pair (login/register). */
  acceptSession(pair: WireTokenPair): Promise<void>;
  /** Exchanges the stored refresh token for a new pair. Concurrent callers share one request. */
  refreshSession(): Promise<WireTokenPair>;
}

const NO_RETRY_401 = new Set(['INVALID_CREDENTIALS']);

function buildUrl(baseUrl: string, path: string, query?: Record<string, QueryValue>): string {
  const url = `${baseUrl}${path}`;
  if (!query) return url;
  const params = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return params.length ? `${url}?${params.join('&')}` : url;
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ApiError({ status: response.status, code: 'BAD_RESPONSE', detail: 'The server returned invalid JSON.' });
  }
}

export function createApiClient({
  baseUrl,
  tokens,
  fetchImpl = (...args) => fetch(...args),
  now = Date.now,
  defaultTimeoutMs = 15_000,
  onSession,
  onSessionExpired,
  onReachability,
}: ApiClientOptions): ApiClient {
  let refreshing: Promise<WireTokenPair> | null = null;

  async function send<T>(path: string, options: RequestOptions, accessToken: string | null): Promise<ApiResponse<T>> {
    const headers: Record<string, string> = {
      Accept: options.binary ? '*/*' : 'application/json, application/problem+json',
    };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, options.timeoutMs ?? defaultTimeoutMs);
    const onAbort = () => controller.abort();
    options.signal?.addEventListener('abort', onAbort);

    const sentAt = now();
    let response: Response;
    try {
      response = await fetchImpl(buildUrl(baseUrl, path, options.query), {
        method: options.method ?? 'GET',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
      });
    } catch (error) {
      if (options.signal?.aborted) throw error; // caller cancelled (e.g. query unmounted) — propagate as-is
      onReachability?.(false);
      throw new ApiError({
        status: 0,
        code: timedOut ? 'TIMEOUT' : 'NETWORK_ERROR',
        detail: timedOut ? 'The server did not respond in time.' : 'Could not reach the server.',
      });
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', onAbort);
    }

    onReachability?.(true);
    if (options.binary && response.ok) {
      const bytes = await response.arrayBuffer();
      return { data: bytes as T, status: response.status, headers: response.headers, sentAt, receivedAt: now() };
    }
    const body = await readBody(response);
    const receivedAt = now();
    if (!response.ok) {
      throw ApiError.fromProblem(response.status, (body as WireProblem | undefined) ?? null, response.headers.get('x-request-id'));
    }
    return { data: body as T, status: response.status, headers: response.headers, sentAt, receivedAt };
  }

  async function acceptSession(pair: WireTokenPair): Promise<void> {
    // Persist the new refresh token before using the session: the old one is already invalid server-side.
    await tokens.saveRefreshToken(pair.refresh_token);
    tokens.setAccessToken(pair.access_token);
    onSession?.(pair);
  }

  async function doRefresh(): Promise<WireTokenPair> {
    const refreshToken = await tokens.loadRefreshToken();
    if (!refreshToken) {
      throw new ApiError({ status: 401, code: 'SESSION_EXPIRED', detail: 'No stored session.' });
    }
    try {
      const { data } = await send<WireTokenPair>('/auth/refresh', { method: 'POST', body: { refresh_token: refreshToken } }, null);
      await acceptSession(data);
      return data;
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 422)) {
        await tokens.clear();
        onSessionExpired?.();
        throw new ApiError({ status: 401, code: 'SESSION_EXPIRED', detail: error.detail, requestId: error.requestId });
      }
      throw error; // network/server trouble: keep the stored session and let the caller retry later
    }
  }

  function refreshSession(): Promise<WireTokenPair> {
    refreshing ??= doRefresh().finally(() => {
      refreshing = null;
    });
    return refreshing;
  }

  async function requestWithMeta<T>(path: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
    if (options.auth === false) return send<T>(path, options, null);

    if (refreshing) await refreshing.catch(() => undefined);
    let token = tokens.getAccessToken();
    if (!token) token = (await refreshSession()).access_token;
    try {
      return await send<T>(path, options, token);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401 || NO_RETRY_401.has(error.code)) throw error;
      // Access token expired or revoked: refresh once (shared with concurrent requests) and retry.
      // If another request already refreshed meanwhile, reuse its token instead of rotating again.
      const current = tokens.getAccessToken();
      const fresh = current && current !== token ? current : (await refreshSession()).access_token;
      return send<T>(path, options, fresh);
    }
  }

  return {
    baseUrl,
    requestWithMeta,
    request: async <T>(path: string, options?: RequestOptions) => (await requestWithMeta<T>(path, options)).data,
    acceptSession,
    refreshSession,
  };
}
