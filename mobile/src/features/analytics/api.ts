import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api, queryKeys } from '@/shared/api';
import { toBreakdown, toDashboard, toProjectSummary, toTimeseries } from '@/shared/api/mappers';
import type { WireBreakdown, WireDashboard, WireProjectSummary, WireTimeseries } from '@/shared/api/wire';

import type { Period } from './range';

/** Period navigation keeps the previous numbers on screen while the next period loads (no flashing skeletons). */
const smooth = { placeholderData: keepPreviousData } as const;

export function useDashboard(period: Pick<Period, 'from' | 'to'>) {
  const range = { from: period.from, to: period.to };
  return useQuery({
    queryKey: queryKeys.money.dashboard(range),
    queryFn: async ({ signal }) => toDashboard(await api.request<WireDashboard>('/dashboard/summary', { query: range, signal })),
    ...smooth,
  });
}

export function useTimeseries(period: Pick<Period, 'from' | 'to'>, interval: 'day' | 'week' | 'month') {
  const params = { from: period.from, to: period.to, interval };
  return useQuery({
    queryKey: queryKeys.money.timeseries(params),
    queryFn: async ({ signal }) =>
      toTimeseries(await api.request<WireTimeseries>('/analytics/timeseries', { query: params, signal })),
    ...smooth,
  });
}

export function useBreakdown(period: Pick<Period, 'from' | 'to'>, groupBy: 'project' | 'client') {
  const params = { from: period.from, to: period.to, groupBy };
  return useQuery({
    queryKey: queryKeys.money.breakdown(params),
    queryFn: async ({ signal }) =>
      toBreakdown(
        await api.request<WireBreakdown>('/analytics/breakdown', {
          query: { from: period.from, to: period.to, group_by: groupBy },
          signal,
        }),
      ),
    ...smooth,
  });
}

export function useProjectSummary(projectId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.money.projectSummary(projectId ?? ''),
    enabled: Boolean(projectId),
    queryFn: async ({ signal }) =>
      toProjectSummary(await api.request<WireProjectSummary>(`/projects/${projectId}/summary`, { signal })),
  });
}
