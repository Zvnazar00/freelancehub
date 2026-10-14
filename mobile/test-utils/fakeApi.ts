import type { WireTimeEntry } from '@/shared/api/wire';

/**
 * A tiny fetch double for tests: routes "METHOD /path" to handlers and records every call.
 * Handlers return [status, body] (body is JSON-encoded) or throw to simulate a network failure.
 */
export interface RecordedCall {
  method: string;
  path: string;
  query: URLSearchParams;
  headers: Record<string, string>;
  body: unknown;
}

export type Handler = (call: RecordedCall) => [number, unknown] | Promise<[number, unknown]>;

export class NetworkDown extends Error {
  constructor() {
    super('Network request failed');
    this.name = 'TypeError';
  }
}

export function createFakeApi(baseUrl = 'http://api.test/api/v1') {
  const routes = new Map<string, Handler>();
  const calls: RecordedCall[] = [];

  const fetchImpl = jest.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input));
    const path = url.pathname.replace(new URL(baseUrl).pathname, '');
    const headers = Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>));
    const call: RecordedCall = {
      method: init?.method ?? 'GET',
      path,
      query: url.searchParams,
      headers,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    const handler = routes.get(`${call.method} ${path}`) ?? [...routes.entries()].find(([k]) => matches(k, call))?.[1];
    if (!handler) return json(404, { code: 'NOT_FOUND', status: 404, title: 'Not found' });
    const [status, body] = await handler(call);
    return json(status, body);
  });

  function matches(pattern: string, call: RecordedCall) {
    const [method, path] = pattern.split(' ');
    if (method !== call.method || !path) return false;
    const re = new RegExp(`^${path.replace(/:[a-z]+/gi, '[^/]+')}$`);
    return re.test(call.path);
  }

  return {
    baseUrl,
    calls,
    fetchImpl: fetchImpl as unknown as typeof fetch,
    on(route: string, handler: Handler) {
      routes.set(route, handler);
      return this;
    },
    callsTo(route: string) {
      const [method, path] = route.split(' ');
      return calls.filter((c) => c.method === method && (c.path === path || matches(route, c)));
    },
  };
}

function json(status: number, body: unknown): Response {
  const text = body === undefined ? '' : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': status >= 400 ? 'application/problem+json' : 'application/json' }),
    text: async () => text,
  } as unknown as Response;
}

export const problem = (status: number, code: string, extra: Record<string, unknown> = {}) => ({
  type: 'about:blank',
  title: code,
  status,
  code,
  detail: code,
  request_id: 'req-1',
  ...extra,
});

export function wireUser(overrides: Record<string, unknown> = {}) {
  return {
    id: 'u-1',
    email: 'alex@example.com',
    full_name: 'Alex Morgan',
    timezone: 'UTC',
    default_currency: 'USD',
    default_hourly_rate: null,
    week_start: 1,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    ...overrides,
  };
}

export function tokenPair(n = 1, user = wireUser()) {
  return { access_token: `access-${n}`, token_type: 'bearer', expires_in: 900, refresh_token: `refresh-token-${n}-xxxxxxxxxxxx`, user };
}

export function wireEntry(overrides: Partial<WireTimeEntry> = {}): WireTimeEntry {
  return {
    id: 'e-1',
    project: { id: 'p-1', name: 'Mobile app', color: '#8B7CFF' },
    task: null,
    description: '',
    source: 'timer',
    status: 'running',
    started_at: '2026-10-12T09:00:00Z',
    ended_at: null,
    pauses: [],
    duration_seconds: null,
    elapsed_seconds: 0,
    billable: true,
    hourly_rate: '100.00',
    currency: 'USD',
    rate_source: 'project',
    rate_corrected_at: null,
    billable_amount: null,
    version: 1,
    created_at: '2026-10-12T09:00:00Z',
    updated_at: '2026-10-12T09:00:00Z',
    ...overrides,
  };
}
