import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, fetchAllPages, queryKeys } from '@/shared/api';
import { toClient } from '@/shared/api/mappers';
import type { WireClient } from '@/shared/api/wire';
import type { Client } from '@/shared/types/domain';

import type { ClientPayload } from './schema';

export function useClients() {
  return useQuery({
    queryKey: queryKeys.clients.list(),
    queryFn: async ({ signal }) => (await fetchAllPages<WireClient>('/clients', {}, signal)).map(toClient),
  });
}

export function useClient(id: string | undefined) {
  const qc = useQueryClient();
  return useQuery<Client, Error, Client, ReturnType<typeof queryKeys.clients.detail>>({
    queryKey: queryKeys.clients.detail(id ?? ''),
    enabled: Boolean(id),
    queryFn: async ({ signal }) => toClient(await api.request<WireClient>(`/clients/${id}`, { signal })),
    // Show the list's copy instantly while the detail loads.
    placeholderData: () => qc.getQueryData<Client[]>(queryKeys.clients.list())?.find((c) => c.id === id),
  });
}

export function useCreateClient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ClientPayload) =>
      toClient(
        await api.request<WireClient>('/clients', {
          method: 'POST',
          body: {
            name: payload.name,
            company: payload.company,
            email: payload.email,
            default_hourly_rate: payload.defaultHourlyRate,
            currency: payload.currency,
          },
        }),
      ),
    onSuccess: (client) => {
      qc.setQueryData(queryKeys.clients.detail(client.id), client);
      void qc.invalidateQueries({ queryKey: queryKeys.clients.list() });
    },
  });
}
