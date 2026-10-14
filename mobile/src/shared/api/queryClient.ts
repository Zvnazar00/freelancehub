import { focusManager, QueryClient } from '@tanstack/react-query';
import { AppState, Platform, type AppStateStatus } from 'react-native';

import { isApiError } from './errors';

/** Only failures that may succeed on a second attempt are retried; 4xx answers are final. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false;
  return !isApiError(error) || error.isTransient || error.status >= 500;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 10 * 60_000,
        retry: shouldRetry,
        refetchOnWindowFocus: true,
      },
      mutations: { retry: false },
    },
  });
}

export const queryClient = createQueryClient();

/**
 * React Native has no window focus: map app foreground/background to TanStack's focus manager so
 * stale queries (above all the active timer) refetch when the user returns to the app.
 */
export function bindFocusToAppState(): () => void {
  if (Platform.OS === 'web') return () => undefined; // the browser's visibilitychange handler is used on web
  focusManager.setEventListener((setFocused) => {
    const sub = AppState.addEventListener('change', (status: AppStateStatus) => setFocused(status === 'active'));
    return () => sub.remove();
  });
  return () => focusManager.setEventListener(() => () => undefined);
}

/** Query-key factories: one place defines what each cache entry means, so invalidation stays precise. */
export const queryKeys = {
  me: ['me'] as const,
  timer: ['timer', 'current'] as const,
  clients: {
    all: ['clients'] as const,
    list: () => ['clients', 'list'] as const,
    detail: (id: string) => ['clients', 'detail', id] as const,
  },
  projects: {
    all: ['projects'] as const,
    list: (filter: { clientId?: string } = {}) => ['projects', 'list', filter] as const,
    detail: (id: string) => ['projects', 'detail', id] as const,
  },
  tasks: {
    all: ['tasks'] as const,
    byProject: (projectId: string) => ['tasks', 'project', projectId] as const,
  },
  entries: {
    all: ['entries'] as const,
    range: (params: Record<string, string | number | boolean | undefined>) => ['entries', 'range', params] as const,
    summary: (params: Record<string, string | number | boolean | undefined>) => ['entries', 'summary', params] as const,
  },
  /** Everything derived from money: dashboard, analytics, project summaries. Invalidated by any money change. */
  money: {
    all: ['money'] as const,
    dashboard: (range: { from: string; to: string }) => ['money', 'dashboard', range] as const,
    timeseries: (params: { from: string; to: string; interval?: string }) => ['money', 'timeseries', params] as const,
    breakdown: (params: { from: string; to: string; groupBy: string }) => ['money', 'breakdown', params] as const,
    projectSummary: (id: string) => ['money', 'project', id] as const,
  },
  invoices: {
    all: ['invoices'] as const,
    list: (filter: { status?: string; clientId?: string } = {}) => ['invoices', 'list', filter] as const,
    detail: (id: string) => ['invoices', 'detail', id] as const,
    billable: (clientId: string, draftId?: string) => ['invoices', 'billable', clientId, draftId ?? null] as const,
  },
};
